from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Iterable

from local_router import (
    RoutingError,
    _enrich_record,
    _haversine_m,
    _load_roads,
    _load_signals,
    _oneway_mode,
    _parse_maxspeed,
    _record_value,
    _road_category,
    _road_priority_factor,
    _routing_speed_kmh,
    _text,
)


ProgressCallback = Callable[[str, int], None]


def _emit(progress: ProgressCallback | None, text: str, percent: int) -> None:
    if progress is not None:
        progress(text, max(0, min(100, int(percent))))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, name: str) -> str:
    target = name.lower()
    for child in element:
        if _local_name(child.tag) == target:
            return (child.text or "").strip()
    return ""


def parse_gpx_track(path: str | Path) -> dict[str, Any]:
    """Read a GPX track/route while preserving GraphHopper elevations."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    try:
        root = ET.parse(source).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"GPX ist kein gültiges XML: {exc}") from exc

    creator = str(root.attrib.get("creator", "") or "").strip()
    track_name = ""
    raw_points: list[ET.Element] = []

    tracks = [child for child in root.iter() if _local_name(child.tag) == "trk"]
    for track in tracks:
        if not track_name:
            track_name = _child_text(track, "name")
        for segment in track:
            if _local_name(segment.tag) != "trkseg":
                continue
            raw_points.extend(
                child for child in segment if _local_name(child.tag) == "trkpt"
            )

    # Some GPX exporters use rte/rtept instead of trk/trkpt.
    if not raw_points:
        routes = [child for child in root.iter() if _local_name(child.tag) == "rte"]
        for route in routes:
            if not track_name:
                track_name = _child_text(route, "name")
            raw_points.extend(
                child for child in route if _local_name(child.tag) == "rtept"
            )

    points: list[dict[str, float]] = []
    for raw in raw_points:
        try:
            latitude = float(raw.attrib["lat"])
            longitude = float(raw.attrib["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        ):
            continue

        point: dict[str, float] = {
            "latitude": latitude,
            "longitude": longitude,
        }
        elevation_text = _child_text(raw, "ele")
        if elevation_text:
            try:
                elevation = float(elevation_text)
            except ValueError:
                elevation = math.nan
            if math.isfinite(elevation):
                point["elevation_m"] = elevation

        # Consecutive duplicate positions can create zero-length simulation
        # segments. Keep one coordinate and retain the newest elevation value.
        if points:
            previous = points[-1]
            if (
                abs(previous["latitude"] - latitude) < 1e-12
                and abs(previous["longitude"] - longitude) < 1e-12
            ):
                if "elevation_m" in point:
                    previous["elevation_m"] = point["elevation_m"]
                continue
        points.append(point)

    if len(points) < 2:
        raise ValueError(
            "Die GPX-Datei enthält weniger als zwei gültige Trackpunkte "
            "(trkpt/rtept)."
        )

    return {
        "source_file": str(source),
        "creator": creator,
        "name": track_name or source.stem,
        "coordinates": points,
        "elevation_points": sum(1 for point in points if "elevation_m" in point),
    }


def _bbox_for_coordinates(
    coordinates: Iterable[dict[str, float]], margin_m: float = 250.0
) -> tuple[float, float, float, float]:
    points = list(coordinates)
    latitudes = [float(point["latitude"]) for point in points]
    longitudes = [float(point["longitude"]) for point in points]
    mean_latitude = math.radians(sum(latitudes) / len(latitudes))
    lat_margin = margin_m / 111_320.0
    lon_scale = max(111_320.0 * math.cos(mean_latitude), 1.0)
    lon_margin = margin_m / lon_scale
    return (
        min(longitudes) - lon_margin,
        min(latitudes) - lat_margin,
        max(longitudes) + lon_margin,
        max(latitudes) + lat_margin,
    )


def _road_matcher(roads: Any) -> tuple[Any, list[dict[str, Any]], list[Any]]:
    try:
        from shapely.strtree import STRtree
    except Exception as exc:
        raise RoutingError(f"Shapely-STRtree für GPX-Abgleich fehlt: {exc}") from exc

    try:
        metric = roads.to_crs(epsg=3857)
    except Exception as exc:
        raise RoutingError(
            f"Straßendaten konnten nicht metrisch transformiert werden: {exc}"
        ) from exc

    geometries: list[Any] = []
    records: list[dict[str, Any]] = []
    for raw_record in metric.to_dict("records"):
        geometry = raw_record.get("geometry")
        if geometry is None or getattr(geometry, "is_empty", True):
            continue
        lines = (
            [geometry]
            if getattr(geometry, "geom_type", "") == "LineString"
            else list(getattr(geometry, "geoms", []))
        )
        for line in lines:
            if getattr(line, "geom_type", "") != "LineString" or line.is_empty:
                continue
            record = dict(raw_record)
            record["geometry"] = line
            geometries.append(line)
            records.append(_enrich_record(record))

    if not geometries:
        raise RoutingError(
            "Im GPX-Korridor wurden keine befahrbaren Straßenlinien gefunden."
        )
    return STRtree(geometries), records, geometries


def _candidate_indexes(tree: Any, geometry: Any, count: int) -> list[int]:
    """Return STRtree indexes (Shapely 2.x)."""

    try:
        result = tree.query(geometry)
        indexes = [int(item) for item in result]
        if indexes:
            return [index for index in indexes if 0 <= index < count]
    except (TypeError, ValueError):
        pass

    try:
        nearest = tree.nearest(geometry)
        value = int(nearest.item()) if hasattr(nearest, "item") else int(nearest)
        return [value] if 0 <= value < count else []
    except Exception:
        return []


def _matched_record(
    tree: Any,
    records: list[dict[str, Any]],
    geometries: list[Any],
    track_line: Any,
    midpoint: Any,
    *,
    search_radius_m: float,
) -> tuple[dict[str, Any] | None, float]:
    candidates = _candidate_indexes(
        tree, track_line.buffer(search_radius_m), len(geometries)
    )
    if not candidates:
        candidates = _candidate_indexes(tree, track_line, len(geometries))
    if not candidates:
        return None, math.inf

    boundary = track_line.boundary
    boundary_points = list(getattr(boundary, "geoms", []))
    start = boundary_points[0] if boundary_points else midpoint
    end = boundary_points[-1] if boundary_points else midpoint

    best_index = -1
    best_score = math.inf
    best_midpoint_distance = math.inf
    for index in candidates:
        road = geometries[index]
        midpoint_distance = float(road.distance(midpoint))
        # A crossing road can have distance ~= 0 at an intersection. Endpoint
        # distances prefer the road actually followed by the GPX segment.
        score = midpoint_distance + 0.25 * (
            float(road.distance(start)) + float(road.distance(end))
        )
        if score < best_score:
            best_score = score
            best_index = index
            best_midpoint_distance = midpoint_distance

    if best_index < 0 or best_midpoint_distance > search_radius_m:
        return None, best_midpoint_distance
    return records[best_index], best_midpoint_distance


def build_route_from_gpx(
    roads_path: str | Path,
    gpx_path: str | Path,
    *,
    progress: ProgressCallback | None = None,
    max_match_distance_m: float = 60.0,
) -> dict[str, Any]:
    """Keep the GPX geometry and enrich it with the active local OSM dataset."""

    _emit(progress, "Lese GraphHopper-GPX …", 5)
    parsed = parse_gpx_track(gpx_path)
    coordinates = list(parsed["coordinates"])
    road_source = Path(roads_path).expanduser().resolve()
    if not road_source.is_file():
        raise RoutingError(f"Lokale Routingdatei nicht gefunden: {road_source}")

    read_bbox = _bbox_for_coordinates(
        coordinates,
        margin_m=max(250.0, max_match_distance_m * 3.0),
    )
    _emit(progress, "Lade lokale OSM-Straßen entlang des GPX-Tracks …", 15)
    roads = _load_roads(road_source, read_bbox)
    tree, records, geometries = _road_matcher(roads)

    from pyproj import Transformer
    from shapely.geometry import LineString, Point

    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    metric_points = [
        transformer.transform(float(point["longitude"]), float(point["latitude"]))
        for point in coordinates
    ]

    segments: list[dict[str, Any]] = []
    total_distance_m = 0.0
    total_travel_time_s = 0.0
    unmatched = 0
    matched_distances: list[float] = []
    segment_count = max(1, len(coordinates) - 1)

    for index, (first, second) in enumerate(zip(coordinates[:-1], coordinates[1:])):
        source = (float(first["longitude"]), float(first["latitude"]))
        target = (float(second["longitude"]), float(second["latitude"]))
        distance_m = max(0.1, _haversine_m(source, target))

        p1 = metric_points[index]
        p2 = metric_points[index + 1]
        track_line = LineString([p1, p2])
        midpoint = Point((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
        record, match_distance_m = _matched_record(
            tree,
            records,
            geometries,
            track_line,
            midpoint,
            search_radius_m=max_match_distance_m,
        )

        if record is None:
            unmatched += 1
            highway = "gpx_track"
            reference = ""
            maxspeed = 30.0
            surface = ""
            name = ""
            oneway = False
            road_category = "gpx_track"
            priority_factor = 1.0
        else:
            matched_distances.append(match_distance_m)
            highway = _text(record.get("highway")).lower() or "road"
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
            surface = _text(record.get("surface"))
            name = _text(record.get("name"))
            oneway = _oneway_mode(record) != "both"
            road_category = _road_category(highway, reference)
            priority_factor = _road_priority_factor(highway, reference)

        travel_time_s = distance_m / (_routing_speed_kmh(maxspeed, highway) / 3.6)
        total_distance_m += distance_m
        total_travel_time_s += travel_time_s
        segments.append(
            {
                "from_index": index,
                "to_index": index + 1,
                "leg_index": 0,
                "distance_m": distance_m,
                "travel_time_s": travel_time_s,
                "maxspeed_kmh": float(maxspeed),
                "highway": highway,
                "surface": surface,
                "name": name,
                "ref": reference,
                "oneway": bool(oneway),
                "road_category": road_category,
                "priority_factor": float(priority_factor),
                "connector": False,
                "gpx_match_distance_m": (
                    None if record is None else float(match_distance_m)
                ),
            }
        )

        if index % 100 == 0 or index + 1 == segment_count:
            percent = 20 + int(60 * (index + 1) / segment_count)
            _emit(
                progress,
                f"GPX/OSM-Abgleich: {index + 1} / {segment_count} Segmente …",
                percent,
            )

    route_nodes = [
        (float(point["longitude"]), float(point["latitude"]))
        for point in coordinates
    ]
    _emit(progress, "Suche OSM-Ampeln auf dem importierten Track …", 85)
    signals = _load_signals(road_source, read_bbox, route_nodes, segments)

    elevation_points = int(parsed["elevation_points"])
    matched = len(segments) - unmatched
    summary = {
        "distance_km": total_distance_m / 1000.0,
        "estimated_minutes": total_travel_time_s / 60.0,
        "route_points": len(coordinates),
        "road_segments": len(segments),
        "traffic_signals": len(signals),
        "loaded_features": int(len(roads)),
        "graph_nodes": 0,
        "graph_edges": 0,
        "start_snap_m": 0.0,
        "target_snap_m": 0.0,
        "max_snap_m": max(matched_distances, default=0.0),
        "waypoints": 0,
        "legs": 1,
        "routing_profile": "graphhopper_gpx",
        "graph_cache_hit": False,
        "source_type": "gpx_import",
        "gpx_creator": str(parsed["creator"]),
        "gpx_name": str(parsed["name"]),
        "gpx_elevation_points": elevation_points,
        "gpx_matched_segments": matched,
        "gpx_unmatched_segments": unmatched,
    }
    _emit(
        progress,
        f"GPX bereit: {len(coordinates)} Punkte, "
        f"{matched}/{len(segments)} Segmente OSM-zugeordnet.",
        100,
    )

    return {
        "coordinates": coordinates,
        "segments": segments,
        "legs": [
            {
                "index": 0,
                "from_point_index": 0,
                "to_point_index": 1,
                "distance_km": total_distance_m / 1000.0,
                "estimated_minutes": total_travel_time_s / 60.0,
                "start_snap_m": 0.0,
                "target_snap_m": 0.0,
            }
        ],
        "traffic_signals": signals,
        "summary": summary,
        "import": {
            "format": "gpx",
            "source_file": str(parsed["source_file"]),
            "creator": str(parsed["creator"]),
            "name": str(parsed["name"]),
            "elevation_points": elevation_points,
        },
    }
