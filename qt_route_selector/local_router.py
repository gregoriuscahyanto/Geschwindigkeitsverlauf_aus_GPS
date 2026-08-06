from __future__ import annotations

import json
import math
import re
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

_HSTORE_TAG = re.compile(r'"([^"]+)"=>"([^"]*)"')


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


def _is_pbf(path: Path) -> bool:
    return path.name.lower().endswith((".osm.pbf", ".pbf"))


def _parse_other_tags(value: Any) -> dict[str, str]:
    text = _text(value)
    if not text:
        return {}
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {str(key): str(item) for key, item in parsed.items()}
        except json.JSONDecodeError:
            pass
    return {key: item for key, item in _HSTORE_TAG.findall(text)}


def _enrich_record(record: dict[str, Any]) -> dict[str, Any]:
    tags = _parse_other_tags(record.get("other_tags"))
    if not tags:
        return record
    enriched = dict(record)
    for key, value in tags.items():
        if not _text(enriched.get(key)):
            enriched[key] = value
    return enriched


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
    return round(float(lon), 7), round(float(lat), 7)


def _record_value(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in record and _text(record[name]):
            return record[name]
    return None


def _list_layers(path: Path) -> list[tuple[str, str]]:
    import pyogrio

    try:
        return [(str(item[0]), str(item[1])) for item in pyogrio.list_layers(path)]
    except Exception as exc:
        raise RoutingError(f"Datenebenen konnten nicht gelesen werden: {exc}") from exc


def _choose_road_layer(path: Path) -> str | int | None:
    if _is_pbf(path):
        return "lines"
    layers = _list_layers(path)
    if not layers:
        return None
    preferred = {"highways", "roads", "streets", "lines"}
    for name, _geometry_type in layers:
        if name.lower() in preferred:
            return name
    for name, geometry_type in layers:
        if "line" in geometry_type.lower():
            return name
    return layers[0][0]


def _read_dataframe(
    path: Path,
    *,
    layer: str | int | None,
    bbox: tuple[float, float, float, float],
    where: str | None = None,
) -> Any:
    import pyogrio

    arguments: dict[str, Any] = {
        "layer": layer,
        "bbox": bbox,
        "force_2d": True,
    }
    if where:
        arguments["where"] = where
    if not _is_pbf(path):
        arguments["use_arrow"] = True

    try:
        return pyogrio.read_dataframe(path, **arguments)
    except (TypeError, ValueError):
        arguments.pop("use_arrow", None)
        return pyogrio.read_dataframe(path, **arguments)


def _load_roads(path: Path, bbox: tuple[float, float, float, float]) -> Any:
    layer = _choose_road_layer(path)
    where = "highway IS NOT NULL" if _is_pbf(path) else None
    try:
        roads = _read_dataframe(path, layer=layer, bbox=bbox, where=where)
    except Exception as exc:
        if _is_pbf(path) and where is not None:
            try:
                roads = _read_dataframe(path, layer=layer, bbox=bbox)
            except Exception:
                raise RoutingError(
                    f"OSM-PBF konnte nicht räumlich gelesen werden: {exc}"
                ) from exc
        else:
            raise RoutingError(f"Straßendaten konnten nicht gelesen werden: {exc}") from exc

    if roads is None or roads.empty:
        raise RoutingError("Im gewählten Kartenausschnitt wurden keine Straßen gefunden.")
    if "geometry" not in roads.columns:
        raise RoutingError("Die Straßendatei besitzt keine Geometriespalte.")
    if roads.crs is not None and not roads.crs.is_geographic:
        raise RoutingError(
            "Die Routingdatei muss geografische WGS84-Koordinaten verwenden (EPSG:4326)."
        )
    return roads


def _add_edge(graph: Any, source: Any, target: Any, attributes: dict[str, Any]) -> None:
    existing = graph.get_edge_data(source, target)
    if existing is None or attributes["travel_time_s"] < existing["travel_time_s"]:
        graph.add_edge(source, target, **attributes)


def _build_graph(roads: Any) -> tuple[Any, dict[tuple[float, float], tuple[float, float]]]:
    import networkx as nx

    graph = nx.DiGraph()
    node_positions: dict[tuple[float, float], tuple[float, float]] = {}

    for raw_record in roads.to_dict("records"):
        record = _enrich_record(raw_record)
        highway = _text(record.get("highway")).lower()
        if not highway or _is_blocked(record):
            continue

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
                source = _node_key(first[0], first[1])
                target = _node_key(second[0], second[1])
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
    indexes = np.argsort(distances)[: min(count, len(nodes))]
    return [(nodes[int(index)], float(distances[int(index)])) for index in indexes]


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
        graph.add_edge(source, candidate, travel_time_s=distance / 5.0)
    for candidate, distance in target_candidates:
        graph.add_edge(candidate, sink, travel_time_s=distance / 5.0)

    try:
        full_path = nx.shortest_path(
            graph,
            source=source,
            target=sink,
            weight="travel_time_s",
            method="dijkstra",
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise RoutingError(
            "Zwischen Start und Ziel wurde in der gewählten Region keine befahrbare Route gefunden. "
            "Vergrößere gegebenenfalls den Regionsrand."
        ) from exc
    finally:
        if graph.has_node(source):
            graph.remove_node(source)
        if graph.has_node(sink):
            graph.remove_node(sink)

    node_path = full_path[1:-1]
    if len(node_path) < 2:
        raise RoutingError("Start und Ziel liegen nach dem Snapping auf demselben Straßenknoten.")
    start_snap = _haversine_m((start[1], start[0]), node_path[0])
    target_snap = _haversine_m((target[1], target[0]), node_path[-1])
    return node_path, start_snap, target_snap


def _read_signal_features(
    path: Path,
    bbox: tuple[float, float, float, float],
) -> Any | None:
    if _is_pbf(path):
        try:
            return _read_dataframe(
                path,
                layer="points",
                bbox=bbox,
                where="highway = 'traffic_signals'",
            )
        except Exception:
            try:
                return _read_dataframe(path, layer="points", bbox=bbox)
            except Exception:
                return None

    layers = _list_layers(path)
    signal_layer = next(
        (name for name, _kind in layers if name.lower() in {"signals", "traffic_signals"}),
        None,
    )
    if signal_layer is None:
        return None
    try:
        return _read_dataframe(path, layer=signal_layer, bbox=bbox)
    except Exception:
        return None


def _load_signals(
    path: Path,
    bbox: tuple[float, float, float, float],
    route_nodes: list[tuple[float, float]],
    radius_m: float = 18.0,
) -> list[dict[str, float]]:
    from pyproj import Transformer
    from shapely.geometry import LineString, Point

    signals = _read_signal_features(path, bbox)
    if signals is None or signals.empty:
        return []

    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    metric_route = LineString([transformer.transform(lon, lat) for lon, lat in route_nodes])
    matches: list[dict[str, float]] = []

    for record in signals.to_dict("records"):
        record = _enrich_record(record)
        if _is_pbf(path) and _text(record.get("highway")) != "traffic_signals":
            continue
        geometry = record.get("geometry")
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
    """Calculate an offline route from a spatially filtered local dataset.

    FlatGeobuf or GeoPackage is recommended for repeated routing. OSM PBF is
    supported as a slower fallback because it is parsed sequentially by GDAL.
    Coordinates use ``(latitude, longitude)`` at the public interface.
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
            "source_type": "osm_pbf" if _is_pbf(path) else "spatial_vector",
        },
    }
