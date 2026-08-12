from __future__ import annotations

import json
import math
import re
from collections import OrderedDict
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
    "track": 15.0,
    # A motor-racing circuit without an OSM maxspeed must not acquire a
    # fabricated public-road limit. The simulation can then be constrained by
    # driver/curve dynamics. Routing itself uses a separate finite assumption.
    "raceway": math.inf,
}

ROUTING_ASSUMED_SPEED_KMH = {
    "raceway": 100.0,
}

ROAD_PRIORITY_FACTOR = {
    "motorway": 0.72,
    "motorway_link": 0.80,
    "trunk": 0.80,
    "trunk_link": 0.86,
    "primary": 0.88,
    "primary_link": 0.94,
    "secondary": 0.98,
    "secondary_link": 1.02,
    "tertiary": 1.07,
    "tertiary_link": 1.10,
    "unclassified": 1.18,
    "residential": 1.30,
    "living_street": 1.50,
    "service": 1.55,
    "track": 1.80,
    # Keep raceways less attractive than normal roads for the default
    # 'preferred' profile; deliberate track routes still work when points are
    # placed on the circuit, and 'shortest' remains purely geometric.
    "raceway": 1.65,
}

ROUTING_PROFILE_WEIGHTS = {
    "preferred": "preferred_time_s",
    "fastest": "travel_time_s",
    "shortest": "distance_m",
}

_HSTORE_TAG = re.compile(r'"([^"]+)"=>"([^"]*)"')
_REF_TOKEN = re.compile(r"(?:^|[;,/\s])([ABLK])\s*([0-9]+)", re.IGNORECASE)
_GRAPH_CACHE: "OrderedDict[tuple[Any, ...], tuple[Any, Any, Any, int]]" = OrderedDict()
_GRAPH_CACHE_LIMIT = 2


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


def _routing_speed_kmh(maxspeed_kmh: float, highway: str) -> float:
    if math.isfinite(maxspeed_kmh):
        return max(5.0, float(maxspeed_kmh))
    return max(5.0, float(ROUTING_ASSUMED_SPEED_KMH.get(highway, 100.0)))


def _is_blocked(record: dict[str, Any]) -> bool:
    highway = _text(record.get("highway")).lower()
    motor_vehicle = _text(record.get("motor_vehicle")).lower()
    vehicle = _text(record.get("vehicle")).lower()
    access = _text(record.get("access")).lower()
    blocked = {"no", "private"}
    allowed = {"yes", "permissive", "destination", "customers", "delivery"}

    # A dedicated raceway is inherently not an ordinary public road. For the
    # simulation use case, a generic access=private must therefore not remove
    # the entire circuit from the graph. Explicit vehicle/motor_vehicle blocks
    # and access=no are still respected.
    if highway == "raceway":
        for value in (motor_vehicle, vehicle):
            if value in allowed:
                return False
            if value in blocked:
                return True
        if access == "no":
            return True
        return False

    for value in (motor_vehicle, vehicle, access):
        if value in allowed:
            return False
        if value in blocked:
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
    except (TypeError, ValueError, RuntimeError):
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


def _road_reference_kind(reference: str) -> str:
    match = _REF_TOKEN.search(reference.upper())
    return match.group(1).upper() if match else ""


def _road_category(highway: str, reference: str) -> str:
    if highway == "raceway":
        return "raceway"
    ref_kind = _road_reference_kind(reference)
    if highway.startswith("motorway") or ref_kind == "A":
        return "autobahn"
    if ref_kind == "B":
        return "bundesstrasse"
    if ref_kind == "L":
        return "landstrasse"
    if ref_kind == "K":
        return "kreisstrasse"
    if highway in {"trunk", "trunk_link", "primary", "primary_link"}:
        return "hauptstrasse"
    if highway in {"secondary", "secondary_link", "tertiary", "tertiary_link"}:
        return "regionalstrasse"
    return "seitenstrasse"


def _road_priority_factor(highway: str, reference: str) -> float:
    factor = ROAD_PRIORITY_FACTOR.get(highway, 1.35)
    ref_kind = _road_reference_kind(reference)
    if ref_kind == "A":
        return min(factor, 0.72)
    if ref_kind == "B":
        return min(factor, 0.88)
    if ref_kind == "L":
        return min(factor, 0.98)
    if ref_kind == "K":
        return min(factor, 1.06)
    return factor


def _add_edge(graph: Any, source: Any, target: Any, attributes: dict[str, Any]) -> None:
    existing = graph.get_edge_data(source, target)
    if existing is None or (
        attributes["travel_time_s"], attributes["distance_m"]
    ) < (existing["travel_time_s"], existing["distance_m"]):
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

        reference = _text(record.get("ref"))
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
        speed_mps = _routing_speed_kmh(maxspeed, highway) / 3.6
        direction = _oneway_mode(record)
        priority_factor = _road_priority_factor(highway, reference)
        common = {
            "highway": highway,
            "maxspeed_kmh": maxspeed,
            "surface": _text(record.get("surface")),
            "name": _text(record.get("name")),
            "ref": reference,
            "oneway": direction != "both",
            "road_category": _road_category(highway, reference),
            "priority_factor": priority_factor,
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
                travel_time_s = distance_m / speed_mps
                attributes = {
                    **common,
                    "distance_m": distance_m,
                    "travel_time_s": travel_time_s,
                    "preferred_time_s": travel_time_s * priority_factor,
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


def _build_node_index(
    node_positions: dict[tuple[float, float], tuple[float, float]],
) -> tuple[list[tuple[float, float]], Any, Any]:
    import numpy as np
    from pyproj import Transformer

    nodes = list(node_positions)
    longitudes = np.asarray([node[0] for node in nodes], dtype=float)
    latitudes = np.asarray([node[1] for node in nodes], dtype=float)
    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    x, y = transformer.transform(longitudes, latitudes)
    return nodes, np.asarray(x), np.asarray(y)


def _nearest_nodes(
    node_positions: dict[tuple[float, float], tuple[float, float]],
    point_lat_lon: tuple[float, float],
    count: int = 12,
    node_index: tuple[list[tuple[float, float]], Any, Any] | None = None,
) -> list[tuple[tuple[float, float], float]]:
    import numpy as np
    from pyproj import Transformer

    nodes, x, y = node_index or _build_node_index(node_positions)
    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
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
    *,
    weight: str = "travel_time_s",
    node_index: tuple[list[tuple[float, float]], Any, Any] | None = None,
) -> tuple[list[Any], float, float]:
    import networkx as nx

    start_candidates = _nearest_nodes(node_positions, start, node_index=node_index)
    target_candidates = _nearest_nodes(node_positions, target, node_index=node_index)
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

    source = ("__route_source__", id(graph), id(start))
    sink = ("__route_sink__", id(graph), id(target))
    graph.add_node(source)
    graph.add_node(sink)
    for candidate, distance in start_candidates:
        snap_time = distance / 5.0
        graph.add_edge(
            source,
            candidate,
            travel_time_s=snap_time,
            preferred_time_s=snap_time,
            distance_m=distance,
        )
    for candidate, distance in target_candidates:
        snap_time = distance / 5.0
        graph.add_edge(
            candidate,
            sink,
            travel_time_s=snap_time,
            preferred_time_s=snap_time,
            distance_m=distance,
        )

    try:
        full_path = nx.shortest_path(
            graph,
            source=source,
            target=sink,
            weight=weight,
            method="dijkstra",
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise RoutingError(
            "Zwischen zwei gewählten Punkten wurde in der Region keine befahrbare Route gefunden. "
            "Vergrößere gegebenenfalls den Regionsrand."
        ) from exc
    finally:
        if graph.has_node(source):
            graph.remove_node(source)
        if graph.has_node(sink):
            graph.remove_node(sink)

    node_path = full_path[1:-1]
    if len(node_path) < 2:
        raise RoutingError("Zwei Punkte liegen nach dem Snapping auf demselben Straßenknoten.")
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
    route_segments: list[dict[str, Any]],
    radius_m: float = 8.0,
    duplicate_distance_m: float = 12.0,
) -> list[dict[str, float]]:
    """Match OSM signals to the actually driven road edges.

    A signal merely close to the route is not sufficient. This prevents nodes
    on parallel roads, crossings or roads below/above a motorway from becoming
    false stops. Signals whose nearest driven edge is an Autobahn edge are
    discarded entirely. Multiple signal nodes at one junction are collapsed to
    one stop.
    """
    from pyproj import Transformer
    from shapely.geometry import LineString, Point

    signals = _read_signal_features(path, bbox)
    if signals is None or signals.empty or len(route_nodes) < 2:
        return []

    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    metric_nodes = [transformer.transform(lon, lat) for lon, lat in route_nodes]
    metric_route = LineString(metric_nodes)

    metric_segments: list[tuple[Any, str, str]] = []
    for segment in route_segments:
        try:
            from_index = int(segment["from_index"])
            to_index = int(segment["to_index"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= from_index < len(metric_nodes) and 0 <= to_index < len(metric_nodes)):
            continue
        if from_index == to_index:
            continue
        line = LineString([metric_nodes[from_index], metric_nodes[to_index]])
        metric_segments.append(
            (
                line,
                _text(segment.get("highway")).lower(),
                _text(segment.get("road_category")).lower(),
            )
        )

    if not metric_segments:
        return []

    candidates: list[dict[str, float]] = []
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

            nearest_distance = math.inf
            nearest_highway = ""
            nearest_category = ""
            for segment_line, highway, road_category in metric_segments:
                distance = float(segment_line.distance(metric_point))
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_highway = highway
                    nearest_category = road_category

            if nearest_distance > radius_m:
                continue
            if nearest_highway in {"motorway", "motorway_link"} or nearest_category == "autobahn":
                continue

            candidates.append(
                {
                    "latitude": float(point.y),
                    "longitude": float(point.x),
                    "distance_from_start_m": float(metric_route.project(metric_point)),
                    "_lateral_distance_m": nearest_distance,
                }
            )

    candidates.sort(key=lambda item: item["distance_from_start_m"])
    matches: list[dict[str, float]] = []
    for candidate in candidates:
        if matches and (
            candidate["distance_from_start_m"] - matches[-1]["distance_from_start_m"]
            <= duplicate_distance_m
        ):
            if candidate["_lateral_distance_m"] < matches[-1]["_lateral_distance_m"]:
                matches[-1] = candidate
            continue
        matches.append(candidate)

    for match in matches:
        match.pop("_lateral_distance_m", None)
    return matches


def _graph_cache_key(
    path: Path,
    bbox: tuple[float, float, float, float],
) -> tuple[Any, ...]:
    stat = path.stat()
    return (
        str(path),
        stat.st_mtime_ns,
        stat.st_size,
        *(round(value, 4) for value in bbox),
    )


def _get_graph(
    path: Path,
    bbox: tuple[float, float, float, float],
) -> tuple[Any, dict[tuple[float, float], tuple[float, float]], Any, int, bool]:
    key = _graph_cache_key(path, bbox)
    cached = _GRAPH_CACHE.get(key)
    if cached is not None:
        _GRAPH_CACHE.move_to_end(key)
        graph, node_positions, node_index, loaded_features = cached
        return graph, node_positions, node_index, loaded_features, True

    roads = _load_roads(path, bbox)
    graph, node_positions = _build_graph(roads)
    node_index = _build_node_index(node_positions)
    value = (graph, node_positions, node_index, int(len(roads)))
    _GRAPH_CACHE[key] = value
    _GRAPH_CACHE.move_to_end(key)
    while len(_GRAPH_CACHE) > _GRAPH_CACHE_LIMIT:
        _GRAPH_CACHE.popitem(last=False)
    return graph, node_positions, node_index, int(len(roads)), False


def _profile_weight(profile: str) -> str:
    return ROUTING_PROFILE_WEIGHTS.get(profile, ROUTING_PROFILE_WEIGHTS["preferred"])


def calculate_route(
    roads_path: str | Path,
    start: tuple[float, float] | None = None,
    target: tuple[float, float] | None = None,
    bbox: dict[str, float] | None = None,
    max_snap_distance_m: float = 2500.0,
    *,
    points: list[tuple[float, float]] | None = None,
    routing_profile: str = "preferred",
) -> dict[str, Any]:
    """Calculate a local route through two or more ordered GPS points."""

    selected_points = list(points or [])
    if not selected_points and start is not None and target is not None:
        selected_points = [start, target]
    if len(selected_points) < 2:
        raise RoutingError("Für eine Route werden mindestens zwei GPS-Punkte benötigt.")
    if bbox is None:
        raise RoutingError("Für das lokale Routing fehlt die räumliche Begrenzung.")

    path = Path(roads_path).expanduser().resolve()
    if not path.is_file():
        raise RoutingError(f"Straßendatei nicht gefunden: {path}")

    read_bbox = (
        float(bbox["west"]),
        float(bbox["south"]),
        float(bbox["east"]),
        float(bbox["north"]),
    )
    graph, node_positions, node_index, loaded_features, cache_hit = _get_graph(
        path, read_bbox
    )
    weight = _profile_weight(routing_profile)

    route_nodes: list[tuple[float, float]] = []
    segments: list[dict[str, Any]] = []
    legs: list[dict[str, Any]] = []
    total_distance_m = 0.0
    total_travel_time_s = 0.0
    snap_distances: list[float] = []

    for leg_index, (leg_start, leg_target) in enumerate(
        zip(selected_points[:-1], selected_points[1:])
    ):
        node_path, start_snap, target_snap = _shortest_path_with_snapping(
            graph,
            node_positions,
            leg_start,
            leg_target,
            max_snap_distance_m,
            weight=weight,
            node_index=node_index,
        )
        snap_distances.extend((start_snap, target_snap))
        leg_distance_m = 0.0
        leg_travel_time_s = 0.0

        if not route_nodes:
            route_nodes.extend(node_path)
            base_index = 0
        elif route_nodes[-1] == node_path[0]:
            base_index = len(route_nodes) - 1
            route_nodes.extend(node_path[1:])
        else:
            connector_source = route_nodes[-1]
            connector_target = node_path[0]
            connector_distance = _haversine_m(connector_source, connector_target)
            connector_time = connector_distance / 5.0
            connector_from = len(route_nodes) - 1
            route_nodes.append(connector_target)
            segments.append(
                {
                    "from_index": connector_from,
                    "to_index": connector_from + 1,
                    "leg_index": leg_index,
                    "distance_m": connector_distance,
                    "travel_time_s": connector_time,
                    "maxspeed_kmh": 18.0,
                    "highway": "waypoint_connector",
                    "surface": "",
                    "name": "Zwischenziel-Anbindung",
                    "ref": "",
                    "oneway": False,
                    "road_category": "connector",
                    "priority_factor": 1.0,
                    "connector": True,
                }
            )
            total_distance_m += connector_distance
            total_travel_time_s += connector_time
            leg_distance_m += connector_distance
            leg_travel_time_s += connector_time
            base_index = len(route_nodes) - 1
            route_nodes.extend(node_path[1:])

        for local_index, (source, destination) in enumerate(
            zip(node_path[:-1], node_path[1:])
        ):
            edge = graph[source][destination]
            distance_m = float(edge["distance_m"])
            travel_time_s = float(edge["travel_time_s"])
            total_distance_m += distance_m
            total_travel_time_s += travel_time_s
            leg_distance_m += distance_m
            leg_travel_time_s += travel_time_s
            segments.append(
                {
                    "from_index": base_index + local_index,
                    "to_index": base_index + local_index + 1,
                    "leg_index": leg_index,
                    "distance_m": distance_m,
                    "travel_time_s": travel_time_s,
                    "maxspeed_kmh": float(edge["maxspeed_kmh"]),
                    "highway": edge.get("highway", ""),
                    "surface": edge.get("surface", ""),
                    "name": edge.get("name", ""),
                    "ref": edge.get("ref", ""),
                    "oneway": bool(edge.get("oneway", False)),
                    "road_category": edge.get("road_category", ""),
                    "priority_factor": float(edge.get("priority_factor", 1.0)),
                    "connector": False,
                }
            )

        legs.append(
            {
                "index": leg_index,
                "from_point_index": leg_index,
                "to_point_index": leg_index + 1,
                "distance_km": leg_distance_m / 1000.0,
                "estimated_minutes": leg_travel_time_s / 60.0,
                "start_snap_m": start_snap,
                "target_snap_m": target_snap,
            }
        )

    coordinates = [
        {"latitude": float(node[1]), "longitude": float(node[0])}
        for node in route_nodes
    ]
    signals = _load_signals(path, read_bbox, route_nodes, segments)
    return {
        "coordinates": coordinates,
        "segments": segments,
        "legs": legs,
        "traffic_signals": signals,
        "summary": {
            "distance_km": total_distance_m / 1000.0,
            "estimated_minutes": total_travel_time_s / 60.0,
            "route_points": len(coordinates),
            "road_segments": len(segments),
            "traffic_signals": len(signals),
            "loaded_features": loaded_features,
            "graph_nodes": int(graph.number_of_nodes()),
            "graph_edges": int(graph.number_of_edges()),
            "start_snap_m": snap_distances[0] if snap_distances else 0.0,
            "target_snap_m": snap_distances[-1] if snap_distances else 0.0,
            "max_snap_m": max(snap_distances, default=0.0),
            "waypoints": max(0, len(selected_points) - 2),
            "legs": len(legs),
            "routing_profile": routing_profile,
            "graph_cache_hit": cache_hit,
            "source_type": "osm_pbf" if _is_pbf(path) else "spatial_vector",
        },
    }
