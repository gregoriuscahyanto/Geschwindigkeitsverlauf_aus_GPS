from __future__ import annotations

import math
import uuid
from typing import Any


_INDEX_KEY = "_segment_snap_index_v1"
_ZERO_DISTANCE_M = 0.05


def _coordinate_node(node: Any) -> bool:
    if not isinstance(node, tuple) or len(node) != 2:
        return False
    try:
        float(node[0])
        float(node[1])
    except (TypeError, ValueError):
        return False
    return True


def _segment_index(graph: Any) -> dict[str, Any]:
    cached = graph.graph.get(_INDEX_KEY)
    if isinstance(cached, dict):
        return cached

    import numpy as np
    from pyproj import Transformer

    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    seen: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    for raw_source, raw_target in graph.edges():
        if not (_coordinate_node(raw_source) and _coordinate_node(raw_target)):
            continue
        source = (float(raw_source[0]), float(raw_source[1]))
        target = (float(raw_target[0]), float(raw_target[1]))
        pair = (source, target) if source <= target else (target, source)
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)

    if not pairs:
        raise RuntimeError("Der Routinggraph enthält keine projizierbaren Straßensegmente.")

    lon1 = np.asarray([pair[0][0] for pair in pairs], dtype=float)
    lat1 = np.asarray([pair[0][1] for pair in pairs], dtype=float)
    lon2 = np.asarray([pair[1][0] for pair in pairs], dtype=float)
    lat2 = np.asarray([pair[1][1] for pair in pairs], dtype=float)
    to_metric = Transformer.from_crs(4326, 3857, always_xy=True)
    x1, y1 = to_metric.transform(lon1, lat1)
    x2, y2 = to_metric.transform(lon2, lat2)

    index = {
        "pairs": pairs,
        "x1": np.asarray(x1, dtype=float),
        "y1": np.asarray(y1, dtype=float),
        "x2": np.asarray(x2, dtype=float),
        "y2": np.asarray(y2, dtype=float),
        "to_metric": to_metric,
        "to_geo": Transformer.from_crs(3857, 4326, always_xy=True),
    }
    graph.graph[_INDEX_KEY] = index
    return index


def _snap_to_segment(
    router: Any,
    graph: Any,
    point_lat_lon: tuple[float, float],
    max_snap_distance_m: float,
) -> dict[str, Any]:
    import numpy as np

    index = _segment_index(graph)
    point_lat = float(point_lat_lon[0])
    point_lon = float(point_lat_lon[1])
    point_x, point_y = index["to_metric"].transform(point_lon, point_lat)

    x1 = index["x1"]
    y1 = index["y1"]
    dx = index["x2"] - x1
    dy = index["y2"] - y1
    length_sq = dx * dx + dy * dy
    safe_length_sq = np.where(length_sq > 1e-12, length_sq, 1.0)
    fraction_metric = np.clip(
        ((point_x - x1) * dx + (point_y - y1) * dy) / safe_length_sq,
        0.0,
        1.0,
    )
    snap_x = x1 + fraction_metric * dx
    snap_y = y1 + fraction_metric * dy
    distance_sq = (snap_x - point_x) ** 2 + (snap_y - point_y) ** 2
    segment_index = int(np.argmin(distance_sq))

    pair = index["pairs"][segment_index]
    snapped_lon, snapped_lat = index["to_geo"].transform(
        float(snap_x[segment_index]), float(snap_y[segment_index])
    )
    snapped = (float(snapped_lon), float(snapped_lat))
    raw_lon_lat = (point_lon, point_lat)
    snap_distance_m = float(router._haversine_m(raw_lon_lat, snapped))
    if snap_distance_m > float(max_snap_distance_m):
        raise router.RoutingError(
            f"Der gewählte Punkt liegt {snap_distance_m:.0f} m vom Straßennetz entfernt."
        )

    source, target = pair
    source_distance = float(router._haversine_m(source, snapped))
    target_distance = float(router._haversine_m(snapped, target))
    total = source_distance + target_distance
    if total <= 1e-9:
        fraction = 0.0
    else:
        fraction = max(0.0, min(1.0, source_distance / total))

    return {
        "source": source,
        "target": target,
        "fraction": fraction,
        "coordinate": snapped,
        "distance_m": snap_distance_m,
    }


def _scaled_edge(attributes: dict[str, Any], factor: float) -> dict[str, Any]:
    result = dict(attributes)
    scale = max(0.0, min(1.0, float(factor)))
    for key in ("distance_m", "travel_time_s", "preferred_time_s"):
        if key in result:
            result[key] = float(result[key]) * scale
    return result


def _connector_attributes(distance_m: float, name: str) -> dict[str, Any]:
    distance = max(0.0, float(distance_m))
    travel_time = distance / 5.0
    return {
        "distance_m": distance,
        "travel_time_s": travel_time,
        "preferred_time_s": travel_time,
        "maxspeed_kmh": 18.0,
        "highway": "snap_connector",
        "surface": "",
        "name": name,
        "ref": "",
        "oneway": False,
        "road_category": "connector",
        "priority_factor": 1.0,
        "connector": True,
    }


def _add_scaled_edge(
    graph: Any,
    source: Any,
    target: Any,
    attributes: dict[str, Any],
    factor: float,
) -> None:
    graph.add_edge(source, target, **_scaled_edge(attributes, factor))


def _same_pair(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return (
        first["source"] == second["source"]
        and first["target"] == second["target"]
    )


def _compact_path(
    router: Any,
    coordinates: list[tuple[float, float]],
    edge_attributes: list[dict[str, Any]],
) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    if not coordinates:
        return [], []
    compact_coordinates = [coordinates[0]]
    compact_edges: list[dict[str, Any]] = []
    for attributes, coordinate in zip(edge_attributes, coordinates[1:]):
        distance = float(router._haversine_m(compact_coordinates[-1], coordinate))
        if distance <= _ZERO_DISTANCE_M and float(attributes.get("distance_m", 0.0)) <= _ZERO_DISTANCE_M:
            continue
        compact_edges.append(dict(attributes))
        compact_coordinates.append(coordinate)
    return compact_coordinates, compact_edges


def _route_leg(
    router: Any,
    graph: Any,
    start: tuple[float, float],
    target: tuple[float, float],
    max_snap_distance_m: float,
    weight: str,
) -> dict[str, Any]:
    import networkx as nx

    start_snap = _snap_to_segment(router, graph, start, max_snap_distance_m)
    target_snap = _snap_to_segment(router, graph, target, max_snap_distance_m)

    token = uuid.uuid4().hex
    start_node = ("__segment_snap_start__", token)
    target_node = ("__segment_snap_target__", token)
    graph.add_node(start_node)
    graph.add_node(target_node)

    start_source = start_snap["source"]
    start_target = start_snap["target"]
    start_fraction = float(start_snap["fraction"])
    target_source = target_snap["source"]
    target_target = target_snap["target"]
    target_fraction = float(target_snap["fraction"])

    try:
        if graph.has_edge(start_source, start_target):
            _add_scaled_edge(
                graph,
                start_node,
                start_target,
                graph[start_source][start_target],
                1.0 - start_fraction,
            )
        if graph.has_edge(start_target, start_source):
            _add_scaled_edge(
                graph,
                start_node,
                start_source,
                graph[start_target][start_source],
                start_fraction,
            )

        if graph.has_edge(target_source, target_target):
            _add_scaled_edge(
                graph,
                target_source,
                target_node,
                graph[target_source][target_target],
                target_fraction,
            )
        if graph.has_edge(target_target, target_source):
            _add_scaled_edge(
                graph,
                target_target,
                target_node,
                graph[target_target][target_source],
                1.0 - target_fraction,
            )

        # Two selected points may lie on the very same long OSM segment. Without
        # this direct partial edge a one-way segment would force Dijkstra to run
        # to an endpoint and possibly around an entire circuit before reaching
        # the second point.
        if _same_pair(start_snap, target_snap):
            source = start_snap["source"]
            destination = start_snap["target"]
            if start_fraction <= target_fraction and graph.has_edge(source, destination):
                _add_scaled_edge(
                    graph,
                    start_node,
                    target_node,
                    graph[source][destination],
                    target_fraction - start_fraction,
                )
            if start_fraction >= target_fraction and graph.has_edge(destination, source):
                _add_scaled_edge(
                    graph,
                    start_node,
                    target_node,
                    graph[destination][source],
                    start_fraction - target_fraction,
                )

        try:
            path = nx.shortest_path(
                graph,
                source=start_node,
                target=target_node,
                weight=weight,
                method="dijkstra",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
            raise router.RoutingError(
                "Zwischen zwei gewählten Punkten wurde in der Region keine befahrbare Route gefunden. "
                "Prüfe Fahrtrichtung und Straßenzugang oder vergrößere den Regionsrand."
            ) from exc

        coordinates: list[tuple[float, float]] = []
        for node in path:
            if node == start_node:
                coordinates.append(start_snap["coordinate"])
            elif node == target_node:
                coordinates.append(target_snap["coordinate"])
            else:
                coordinates.append((float(node[0]), float(node[1])))
        edge_attributes = [
            dict(graph[source][destination])
            for source, destination in zip(path[:-1], path[1:])
        ]
    finally:
        if graph.has_node(start_node):
            graph.remove_node(start_node)
        if graph.has_node(target_node):
            graph.remove_node(target_node)

    coordinates, edge_attributes = _compact_path(router, coordinates, edge_attributes)
    if not coordinates:
        raise router.RoutingError("Die gesnappte Route enthält keine Geometrie.")

    raw_start = (float(start[1]), float(start[0]))
    raw_target = (float(target[1]), float(target[0]))
    start_distance = float(start_snap["distance_m"])
    target_distance = float(target_snap["distance_m"])

    if start_distance > _ZERO_DISTANCE_M:
        coordinates.insert(0, raw_start)
        edge_attributes.insert(0, _connector_attributes(start_distance, "Start-Anbindung"))
    else:
        coordinates[0] = raw_start

    if target_distance > _ZERO_DISTANCE_M:
        coordinates.append(raw_target)
        edge_attributes.append(_connector_attributes(target_distance, "Ziel-Anbindung"))
    else:
        coordinates[-1] = raw_target

    return {
        "coordinates": coordinates,
        "edges": edge_attributes,
        "start_snap_m": start_distance,
        "target_snap_m": target_distance,
    }


def _test_track_aware_blocked(router: Any, original: Any, record: dict[str, Any]) -> bool:
    highway = router._text(record.get("highway")).lower()
    if highway != "raceway":
        return bool(original(record))

    # A dedicated raceway/test track is expected to be non-public. Users of this
    # application intentionally place route points on it, so "private" must not
    # make the whole circuit disappear. Explicit prohibitions remain respected.
    for key in ("motor_vehicle", "vehicle", "access"):
        if router._text(record.get(key)).lower() == "no":
            return True
    return False


def _calculate_route(
    router: Any,
    roads_path: str | Any,
    start: tuple[float, float] | None = None,
    target: tuple[float, float] | None = None,
    bbox: dict[str, float] | None = None,
    max_snap_distance_m: float = 2500.0,
    *,
    points: list[tuple[float, float]] | None = None,
    routing_profile: str = "preferred",
) -> dict[str, Any]:
    from pathlib import Path

    selected_points = list(points or [])
    if not selected_points and start is not None and target is not None:
        selected_points = [start, target]
    if len(selected_points) < 2:
        raise router.RoutingError("Für eine Route werden mindestens zwei GPS-Punkte benötigt.")
    if bbox is None:
        raise router.RoutingError("Für das lokale Routing fehlt die räumliche Begrenzung.")

    path = Path(roads_path).expanduser().resolve()
    if not path.is_file():
        raise router.RoutingError(f"Straßendatei nicht gefunden: {path}")

    read_bbox = (
        float(bbox["west"]),
        float(bbox["south"]),
        float(bbox["east"]),
        float(bbox["north"]),
    )
    graph, _node_positions, _node_index, loaded_features, cache_hit = router._get_graph(
        path, read_bbox
    )
    weight = router._profile_weight(routing_profile)

    route_coordinates: list[tuple[float, float]] = []
    segments: list[dict[str, Any]] = []
    legs: list[dict[str, Any]] = []
    total_distance_m = 0.0
    total_travel_time_s = 0.0
    snap_distances: list[float] = []

    for leg_index, (leg_start, leg_target) in enumerate(
        zip(selected_points[:-1], selected_points[1:])
    ):
        leg = _route_leg(
            router,
            graph,
            leg_start,
            leg_target,
            max_snap_distance_m,
            weight,
        )
        leg_coordinates = list(leg["coordinates"])
        leg_edges = list(leg["edges"])
        start_snap = float(leg["start_snap_m"])
        target_snap = float(leg["target_snap_m"])
        snap_distances.extend((start_snap, target_snap))

        if not route_coordinates:
            base_index = 0
            route_coordinates.extend(leg_coordinates)
        else:
            join_distance = router._haversine_m(route_coordinates[-1], leg_coordinates[0])
            if join_distance <= _ZERO_DISTANCE_M:
                base_index = len(route_coordinates) - 1
                route_coordinates.extend(leg_coordinates[1:])
            else:
                # Ordered legs share the same user waypoint. This branch is a
                # defensive fallback for tiny numerical projection differences.
                connector_from = len(route_coordinates) - 1
                route_coordinates.append(leg_coordinates[0])
                connector = _connector_attributes(join_distance, "Zwischenziel-Anbindung")
                segments.append(
                    {
                        "from_index": connector_from,
                        "to_index": connector_from + 1,
                        "leg_index": leg_index,
                        **connector,
                    }
                )
                total_distance_m += float(connector["distance_m"])
                total_travel_time_s += float(connector["travel_time_s"])
                base_index = len(route_coordinates) - 1
                route_coordinates.extend(leg_coordinates[1:])

        leg_distance_m = 0.0
        leg_travel_time_s = 0.0
        for local_index, edge in enumerate(leg_edges):
            distance_m = float(edge.get("distance_m", 0.0))
            travel_time_s = float(edge.get("travel_time_s", 0.0))
            leg_distance_m += distance_m
            leg_travel_time_s += travel_time_s
            total_distance_m += distance_m
            total_travel_time_s += travel_time_s
            segments.append(
                {
                    "from_index": base_index + local_index,
                    "to_index": base_index + local_index + 1,
                    "leg_index": leg_index,
                    "distance_m": distance_m,
                    "travel_time_s": travel_time_s,
                    "maxspeed_kmh": float(edge.get("maxspeed_kmh", 18.0)),
                    "highway": edge.get("highway", ""),
                    "surface": edge.get("surface", ""),
                    "name": edge.get("name", ""),
                    "ref": edge.get("ref", ""),
                    "oneway": bool(edge.get("oneway", False)),
                    "road_category": edge.get("road_category", ""),
                    "priority_factor": float(edge.get("priority_factor", 1.0)),
                    "connector": bool(edge.get("connector", False)),
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
        for node in route_coordinates
    ]
    signals = router._load_signals(path, read_bbox, route_coordinates, segments)
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
            "source_type": "osm_pbf" if router._is_pbf(path) else "spatial_vector",
            "snapping": "nearest_segment",
        },
    }


def install_segment_snapping(router: Any) -> None:
    """Install exact edge snapping and deliberate private-raceway support."""
    if bool(getattr(router, "_segment_snapping_installed", False)):
        return

    original_blocked = router._is_blocked

    def blocked(record: dict[str, Any]) -> bool:
        return _test_track_aware_blocked(router, original_blocked, record)

    def calculate_route(
        roads_path: str | Any,
        start: tuple[float, float] | None = None,
        target: tuple[float, float] | None = None,
        bbox: dict[str, float] | None = None,
        max_snap_distance_m: float = 2500.0,
        *,
        points: list[tuple[float, float]] | None = None,
        routing_profile: str = "preferred",
    ) -> dict[str, Any]:
        return _calculate_route(
            router,
            roads_path,
            start=start,
            target=target,
            bbox=bbox,
            max_snap_distance_m=max_snap_distance_m,
            points=points,
            routing_profile=routing_profile,
        )

    router._is_blocked = blocked
    router.calculate_route = calculate_route
    cache = getattr(router, "_GRAPH_CACHE", None)
    if hasattr(cache, "clear"):
        cache.clear()
    router._segment_snapping_installed = True


__all__ = ["install_segment_snapping"]
