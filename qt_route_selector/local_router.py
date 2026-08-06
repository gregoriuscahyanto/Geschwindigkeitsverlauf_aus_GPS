from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SPEED_KMH = {
    "motorway": 120.0,
    "motorway_link": 70.0,
    "trunk": 100.0,
    "trunk_link": 70.0,
    "primary": 70.0,
    "primary_link": 60.0,
    "secondary": 60.0,
    "secondary_link": 50.0,
    "tertiary": 50.0,
    "tertiary_link": 40.0,
    "unclassified": 50.0,
    "residential": 30.0,
    "living_street": 10.0,
    "service": 20.0,
}


class RoutingError(RuntimeError):
    """Raised when a local route cannot be calculated."""


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _parse_maxspeed(value: Any, highway: str) -> float:
    text = _text(value).lower().replace(" ", "")
    if text:
        first = text.split(";")[0]
        try:
            if first.endswith("mph"):
                return max(5.0, float(first[:-3]) * 1.609344)
            for suffix in ("km/h", "kmh", "kph"):
                if first.endswith(suffix):
                    return max(5.0, float(first[: -len(suffix)]))
            return max(5.0, float(first))
        except ValueError:
            pass
    return DEFAULT_SPEED_KMH.get(highway, 30.0)


def _is_blocked(record: dict[str, Any]) -> bool:
    values = (
        record.get("motor_vehicle"),
        record.get("vehicle"),
        record.get("access"),
    )
    blocked = {"no", "private"}
    allowed = {"yes", "permissive", "destination", "customers", "delivery"}

    for value in values:
        text = _text(value).lower()
        if text in allowed:
            return False
        if text in blocked:
            return True
    return False


def _oneway_mode(record: dict[str, Any]) -> str:
    value = _text(record.get("oneway")).lower()
    junction = _text(record.get("junction")).lower()

    if value in {"-1", "reverse"}:
        return "reverse"
    if value in {"yes", "true", "1"} or junction == "roundabout":
        return "forward"
    return "both"


def _iter_lines(geometry: Any) -> Iterable[Any]:
    if geometry is None:
        return
    geometry_type = getattr(geometry, "geom_type", "")
    if geometry_type == "LineString":
        yield geometry
    elif geometry_type == "MultiLineString":
        yield from geometry.geoms


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return 6_371_008.8 * 2.0 * math.atan2(
        math.sqrt(value), math.sqrt(max(0.0, 1.0 - value))
    )


def _node_key(lon: float, lat: float) -> tuple[float, float]:
    # Identical OSM nodes normally have identical coordinates. Rounding also
    # joins tiny floating-point differences introduced by file conversion.
    return round(float(lon), 7), round(float(lat), 7)


def _record_value(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in record:
            value = record[name]
            if _text(value):
                return value
    return None


def _add_edge(graph: Any, source: Any, target: Any, attributes: dict[str, Any]) -> None:
    existing = graph.get_edge_data(source, target)
    if existing is None or attributes["travel_time_s"] < existing["travel_time_s"]:
        graph.add_edge(source, target, **attributes)


def _load_roads(path: Path, bbox: tuple[float, float, float, float]) -> Any:
    import pyogrio

    try:
        roads = pyogrio.read_dataframe(path, bbox=bbox, use_arrow=True, force_2d=True)
    except (TypeError, ValueError):
        roads = pyogrio.read_dataframe(path, bbox=bbox, force_2d=True)
    except Exception as exc:
        raise RoutingError(f"Straßendaten konnten nicht gelesen werden: {exc}") from exc

    if roads is None or roads.empty:
        raise RoutingError("Im gewählten Kartenausschnitt wurden keine Straßen gefunden.")
    if "geometry" not in roads.columns:
        raise RoutingError("Die Straßendatei besitzt keine Geometriespalte.")
    return roads


def _build_graph(roads: Any) -> tuple[Any, dict[tuple[float, float], tuple[float, float]]]:
    import networkx as nx

    graph = nx.DiGraph()
    node_positions: dict[tuple[float, float], tuple[float, float]] = {}

    for record in roads.to_dict("records"):
        if _is_blocked(record):
            continue

        highway = _text(record.get("highway")).lower() or "unclassified"
        maxspeed = _parse_maxspeed(
            _record_value(
                record,
                "maxspeed_kmh",
                "maxspeed",
                "maxspeed:forward",
                "maxspeed_forward",
            ),
            highway,
        )
        speed_mps = maxspeed / 3.6
        direction = _oneway_mode(record)
        common = {
            "highway": highway,
            "maxspeed_kmh": maxspeed,
            "surface": _text(record.get("surface")),
            "name": _text(record.get("name")),
            "ref": _text(record.get("ref")),
            "oneway": direction != "both",
        }

        for line in _iter_lines(record.get("geometry")):
            coordinates = list(line.coords)
            for first, second in zip(coordinates[:-1], coordinates[1:]):
                lon1, lat1 = float(first[0]), float(first[1])
                lon2, lat2 = float(second[0]), float(second[1])
                source = _node_key(lon1, lat1)
                target = _node_key(lon2, lat2)
                if source == target:
                    continue

                distance_m = _haversine_m(source, target)
                if distance_m < 0.05:
                    continue

                node_positions[source] = source
                node_positions[target] = target
                attributes = {
                    **common,
                    "distance_m": distance_m,
                    "travel_time_s": distance_m / speed_mps,
                }

                if direction == "forward":
                    _add_edge(graph, source, target, attributes)
                elif direction == "reverse":
                    _add_edge(graph, target, source, attributes)
                else:
                    _add_edge(graph, source, target, attributes)
                    _add_edge(graph, target, source, attributes)

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise RoutingError("Aus dem Kartenausschnitt konnte kein befahrbarer Graph erzeugt werden.")
    return graph, node_positions


def _nearest_nodes(
    node_positions: dict[tuple[float, float], tuple[float, float]],
    point_lat_lon: tuple[float, float],
    count: int = 12,
) -> list[tuple[tuple[float, float], float]]:
    import numpy as np
    from pyproj import Transformer

    nodes = list(node_positions)
    longitudes = np.asarray([node[0] for node in nodes], dtype=float)
    latitudes = np.asarray([node[1] for node in nodes], dtype=float)
    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    x, y = transformer.transform(longitudes, latitudes)
    point_x, point_y = transformer.transform(point_lat_lon[1], point_lat_lon[0])
    distances = np.hypot(x - point_x, y - point_y)
    nearest_indexes = np.argsort(distances)[: min(count, len(nodes))]
    return [(nodes[int(index)], float(distances[int(index)])) for index in nearest_indexes]


def _shortest_path_with_snapping(
    graph: Any,
    node_positions: dict[tuple[float, float], tuple[float, float]],
    start: tuple[float, float],
    target: tuple[float, float],
    max_snap_distance_m: float,
) -> tuple[list[Any], float, float]:
    import networkx as nx

    start_candidates = _nearest_nodes(node_positions, start)
    target_candidates = _nearest_nodes(node_positions, target)

    if not start_candidates or not target_candidates:
        raise RoutingError("Start oder Ziel konnte nicht an das Straßennetz angebunden werden.")
    if start_candidates[0][1] > max_snap_distance_m:
        raise RoutingError(
            f"Der Startpunkt liegt {start_candidates[0][1]:.0f} m vom Straßennetz entfernt."
        )
    if target_candidates[0][1] > max_snap_distance_m:
        raise RoutingError(
            f"Der Zielpunkt liegt {target_candidates[0][1]:.0f} m vom Straßennetz entfernt."
        )

    source = ("__route_source__", id(graph))
    sink = ("__route_sink__", id(graph))
    graph.add_node(source)
    graph.add_node(sink)

    for candidate, distance in start_candidates:
        graph.add_edge(
            source,
            candidate,
            travel_time_s=distance / 5.0,
            distance_m=distance,
            snap=True,
        )
    for candidate, distance in target_candidates:
        graph.add_edge(
            candidate,
            sink,
            travel_time_s=distance / 5.0,
            distance_m=distance,
            snap=True,
        )

    try:
        full_path = nx.shortest_path(
            graph,
            source=source,
            target=sink,
            weight="travel_time_s",
            method="dijkstra",
        )
    except nx.NetworkXNoPath as exc:
        raise RoutingError(
            "Zwischen Start und Ziel wurde in der gewählten Region keine befahrbare Route gefunden. "
            "Vergrößere gegebenenfalls den Regionsrand."
        ) from exc
    finally:
        graph.remove_node(source)
        graph.remove_node(sink)

    node_path = full_path[1:-1]
    start_snap = _haversine_m((start[1], start[0]), node_path[0])
    target_snap = _haversine_m((target[1], target[0]), node_path[-1])
    return node_path, start_snap, target_snap


def _load_signals(
    path: Path,
    bbox: tuple[float, float, float, float],
    route_nodes: list[tuple[float, float]],
    radius_m: float = 18.0,
) -> list[dict[str, float]]:
    import pyogrio
    from pyproj import Transformer
    from shapely.geometry import LineString, Point

    try:
        layers = pyogrio.list_layers(path)
        layer_names = [str(item[0]) for item in layers]
        signal_layer = next(
            (name for name in layer_names if name.lower() in {"signals", "traffic_signals"}),
            None,
        )
        if signal_layer is None:
            return []
        try:
            signals = pyogrio.read_dataframe(
                path, layer=signal_layer, bbox=bbox, use_arrow=True, force_2d=True
            )
        except (TypeError, ValueError):
            signals = pyogrio.read_dataframe(
                path, layer=signal_layer, bbox=bbox, force_2d=True
            )
    except Exception:
        return []

    if signals is None or signals.empty:
        return []

    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    metric_route = LineString([transformer.transform(lon, lat) for lon, lat in route_nodes])
    matches: list[dict[str, float]] = []

    for geometry in signals.geometry:
        if geometry is None:
            continue
        points = [geometry] if geometry.geom_type == "Point" else list(getattr(geometry, "geoms", []))
        for point in points:
            if point.geom_type != "Point":
                continue
            metric_point = Point(*transformer.transform(point.x, point.y))
            if metric_route.distance(metric_point) <= radius_m:
                matches.append(
                    {
                        "latitude": float(point.y),
                        "longitude": float(point.x),
                        "distance_from_start_m": float(metric_route.project(metric_point)),
                    }
                )

    matches.sort(key=lambda item: item["distance_from_start_m"])
    return matches


def calculate_route(
    roads_path: str | Path,
    start: tuple[float, float],
    target: tuple[float, float],
    bbox: dict[str, float],
    max_snap_distance_m: float = 2500.0,
) -> dict[str, Any]:
    """Calculate an offline route through a spatially filtered road dataset.

    Args:
        roads_path: FlatGeobuf/GeoPackage/other GDAL-readable road dataset.
        start: ``(latitude, longitude)``.
        target: ``(latitude, longitude)``.
        bbox: Mapping with ``west, south, east, north``.
    """

    path = Path(roads_path).expanduser().resolve()
    if not path.is_file():
        raise RoutingError(f"Straßendatei nicht gefunden: {path}")

    read_bbox = (
        float(bbox["west"]),
        float(bbox["south"]),
        float(bbox["east"]),
        float(bbox["north"]),
    )
    roads = _load_roads(path, read_bbox)
    graph, node_positions = _build_graph(roads)
    node_path, start_snap, target_snap = _shortest_path_with_snapping(
        graph,
        node_positions,
        start,
        target,
        max_snap_distance_m,
    )

    coordinates = [
        {"latitude": float(node[1]), "longitude": float(node[0])}
        for node in node_path
    ]
    segments: list[dict[str, Any]] = []
    distance_m = 0.0
    travel_time_s = 0.0

    for index, (source, destination) in enumerate(zip(node_path[:-1], node_path[1:])):
        edge = graph[source][destination]
        distance_m += float(edge["distance_m"])
        travel_time_s += float(edge["travel_time_s"])
        segments.append(
            {
                "from_index": index,
                "to_index": index + 1,
                "distance_m": float(edge["distance_m"]),
                "travel_time_s": float(edge["travel_time_s"]),
                "maxspeed_kmh": float(edge["maxspeed_kmh"]),
                "highway": edge.get("highway", ""),
                "surface": edge.get("surface", ""),
                "name": edge.get("name", ""),
                "ref": edge.get("ref", ""),
                "oneway": bool(edge.get("oneway", False)),
            }
        )

    signals = _load_signals(path, read_bbox, node_path)
    return {
        "coordinates": coordinates,
        "segments": segments,
        "traffic_signals": signals,
        "summary": {
            "distance_km": distance_m / 1000.0,
            "estimated_minutes": travel_time_s / 60.0,
            "route_points": len(coordinates),
            "road_segments": len(segments),
            "traffic_signals": len(signals),
            "loaded_features": int(len(roads)),
            "graph_nodes": int(graph.number_of_nodes()),
            "graph_edges": int(graph.number_of_edges()),
            "start_snap_m": start_snap,
            "target_snap_m": target_snap,
        },
    }
