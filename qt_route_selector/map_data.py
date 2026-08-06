from __future__ import annotations

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


def _flat_coordinates(geometry: Any) -> list[float]:
    values: list[float] = []
    for coordinate in geometry.coords:
        values.extend((float(coordinate[1]), float(coordinate[0])))
    return values


def load_map_features(
    roads_path: str | Path,
    bbox: dict[str, float],
    *,
    max_features: int = 15_000,
    max_vertices: int = 120_000,
) -> dict[str, Any]:
    """Load a display-friendly road layer for the visible offline map area.

    The source is spatially filtered before Python receives the features. Lines
    are lightly simplified according to the visible extent and encoded as flat
    ``[lat, lon, lat, lon, ...]`` arrays to reduce Qt/QML transfer overhead.
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

    longitude_span = max(1e-7, read_bbox[2] - read_bbox[0])
    latitude_span = max(1e-7, read_bbox[3] - read_bbox[1])
    simplify_tolerance = max(longitude_span, latitude_span) / 3500.0

    candidates: list[tuple[int, dict[str, Any]]] = []
    original_vertices = 0

    for raw_record in roads.to_dict("records"):
        record = _enrich_record(raw_record)
        highway = _text(record.get("highway")).lower()
        if not highway:
            continue
        rank = ROAD_RANK.get(highway, 0)

        for line in _iter_lines(record.get("geometry")):
            original_vertices += len(line.coords)
            display_line = line
            if len(line.coords) > 6 and simplify_tolerance > 0.0:
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

    # Major roads are kept first when a very dense city extract exceeds the
    # safety limits. The painter sorts them back into background-to-foreground
    # order when drawing.
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

    return {
        "features": features,
        "summary": {
            "source_features": int(len(roads)),
            "display_lines": len(features),
            "display_vertices": vertex_count,
            "original_vertices": original_vertices,
            "truncated": truncated,
            "west": read_bbox[0],
            "south": read_bbox[1],
            "east": read_bbox[2],
            "north": read_bbox[3],
        },
    }
