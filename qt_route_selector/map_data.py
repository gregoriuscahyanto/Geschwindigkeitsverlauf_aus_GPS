from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

try:
    from .local_router import (
        RoutingError,
        _enrich_record,
        _iter_lines,
        _load_roads,
        _text,
    )
except ImportError:  # Direct execution via qt_route_selector/main.py
    from local_router import (
        RoutingError,
        _enrich_record,
        _iter_lines,
        _load_roads,
        _text,
    )


ROAD_RANK = {
    "motorway": 9,
    "motorway_link": 8,
    "trunk": 8,
    "trunk_link": 7,
    "primary": 7,
    "primary_link": 6,
    "secondary": 6,
    "secondary_link": 5,
    "tertiary": 5,
    "tertiary_link": 4,
    "unclassified": 3,
    "residential": 3,
    "living_street": 2,
    "service": 1,
    "track": 0,
}

_MAP_CACHE: "OrderedDict[tuple[Any, ...], dict[str, Any]]" = OrderedDict()
_MAP_CACHE_LIMIT = 4


def _flat_coordinates(geometry: Any) -> list[float]:
    values: list[float] = []
    for coordinate in geometry.coords:
        values.extend((float(coordinate[1]), float(coordinate[0])))
    return values


def _source_key(path: Path) -> tuple[Any, ...]:
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


def _contains(container: dict[str, float], requested: dict[str, float]) -> bool:
    return (
        container["west"] <= requested["west"]
        and container["south"] <= requested["south"]
        and container["east"] >= requested["east"]
        and container["north"] >= requested["north"]
    )


def _expanded_bbox(
    bbox: dict[str, float], margin_fraction: float = 0.35
) -> dict[str, float]:
    width = max(1e-6, float(bbox["east"]) - float(bbox["west"]))
    height = max(1e-6, float(bbox["north"]) - float(bbox["south"]))
    dx = width * margin_fraction
    dy = height * margin_fraction
    return {
        "west": max(-180.0, float(bbox["west"]) - dx),
        "south": max(-85.0, float(bbox["south"]) - dy),
        "east": min(180.0, float(bbox["east"]) + dx),
        "north": min(85.0, float(bbox["north"]) + dy),
    }


def _minimum_rank(zoom_level: float) -> int:
    if zoom_level <= 7.5:
        return 7
    if zoom_level <= 9.5:
        return 6
    if zoom_level <= 11.5:
        return 5
    if zoom_level <= 13.5:
        return 3
    if zoom_level <= 15.0:
        return 2
    return 0


def load_map_features(
    roads_path: str | Path,
    bbox: dict[str, float],
    *,
    zoom_level: float = 12.0,
    max_features: int = 12_000,
    max_vertices: int = 120_000,
) -> dict[str, Any]:
    """Load and cache a display-friendly offline road layer."""

    path = Path(roads_path).expanduser().resolve()
    if not path.is_file():
        raise RoutingError(f"Straßendatei nicht gefunden: {path}")

    requested = {
        "west": float(bbox["west"]),
        "south": float(bbox["south"]),
        "east": float(bbox["east"]),
        "north": float(bbox["north"]),
    }
    minimum_rank = _minimum_rank(float(zoom_level))
    source_key = _source_key(path)

    for cache_key, cached in reversed(_MAP_CACHE.items()):
        if cache_key[:3] != source_key or cache_key[3] != minimum_rank:
            continue
        if _contains(cached["loaded_bbox"], requested):
            _MAP_CACHE.move_to_end(cache_key)
            result = {
                "features": cached["features"],
                "summary": dict(cached["summary"]),
            }
            result["summary"]["cache_hit"] = True
            result["summary"]["requested_zoom"] = float(zoom_level)
            return result

    loaded_bbox = _expanded_bbox(requested)
    read_bbox = (
        loaded_bbox["west"],
        loaded_bbox["south"],
        loaded_bbox["east"],
        loaded_bbox["north"],
    )
    roads = _load_roads(path, read_bbox)

    longitude_span = max(1e-7, read_bbox[2] - read_bbox[0])
    latitude_span = max(1e-7, read_bbox[3] - read_bbox[1])
    simplify_tolerance = max(longitude_span, latitude_span) / 2600.0

    candidates: list[tuple[int, dict[str, Any]]] = []
    original_vertices = 0

    for raw_record in roads.to_dict("records"):
        record = _enrich_record(raw_record)
        highway = _text(record.get("highway")).lower()
        if not highway:
            continue
        rank = ROAD_RANK.get(highway, 0)
        if rank < minimum_rank:
            continue

        for line in _iter_lines(record.get("geometry")):
            original_vertices += len(line.coords)
            display_line = line
            if len(line.coords) > 5 and simplify_tolerance > 0.0:
                display_line = line.simplify(
                    simplify_tolerance,
                    preserve_topology=False,
                )
            if display_line is None or len(display_line.coords) < 2:
                continue
            candidates.append(
                (
                    rank,
                    {
                        "highway": highway,
                        "rank": rank,
                        "name": _text(record.get("name")),
                        "coordinates": _flat_coordinates(display_line),
                    },
                )
            )

    candidates.sort(key=lambda item: item[0], reverse=True)

    features: list[dict[str, Any]] = []
    vertex_count = 0
    truncated = False
    for _rank, feature in candidates:
        feature_vertices = len(feature["coordinates"]) // 2
        if features and (
            len(features) >= max_features
            or vertex_count + feature_vertices > max_vertices
        ):
            truncated = True
            break
        features.append(feature)
        vertex_count += feature_vertices

    summary = {
        "source_features": int(len(roads)),
        "display_lines": len(features),
        "display_vertices": vertex_count,
        "original_vertices": original_vertices,
        "truncated": truncated,
        "cache_hit": False,
        "minimum_rank": minimum_rank,
        "requested_zoom": float(zoom_level),
        **loaded_bbox,
    }
    cache_key = (
        *source_key,
        minimum_rank,
        *(round(loaded_bbox[key], 4) for key in ("west", "south", "east", "north")),
    )
    _MAP_CACHE[cache_key] = {
        "loaded_bbox": loaded_bbox,
        "features": features,
        "summary": summary,
    }
    _MAP_CACHE.move_to_end(cache_key)
    while len(_MAP_CACHE) > _MAP_CACHE_LIMIT:
        _MAP_CACHE.popitem(last=False)

    return {"features": features, "summary": summary}
