from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np


_FALSE_OSM_VALUES = {"", "0", "false", "no", "none", "nan"}


def _osm_true(value: Any) -> bool:
    if value is None:
        return False
    try:
        if math.isnan(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() not in _FALSE_OSM_VALUES


def _iter_lines(geometry: Any):
    if geometry is None or getattr(geometry, "is_empty", True):
        return
    kind = getattr(geometry, "geom_type", "")
    if kind == "LineString":
        yield geometry
    elif kind == "MultiLineString":
        yield from geometry.geoms


def _nearest_index(tree: Any, geometries: list[Any], point: Any) -> int | None:
    try:
        value = tree.nearest(point)
        index = int(value.item()) if hasattr(value, "item") else int(value)
        if 0 <= index < len(geometries):
            return index
    except (TypeError, ValueError, AttributeError):
        pass

    # Compatibility fallback for Shapely versions whose STRtree.nearest returns
    # a geometry instead of an integer index.
    try:
        nearest_geometry = tree.nearest(point)
    except Exception:
        return None
    for index, geometry in enumerate(geometries):
        if geometry is nearest_geometry or geometry.equals(nearest_geometry):
            return index
    return None


def _structure_mask(
    roads_path: str | Path,
    latitude: np.ndarray,
    longitude: np.ndarray,
    *,
    max_distance_m: float = 12.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-route-point tunnel and bridge masks from the routing GPKG."""

    tunnel_mask = np.zeros(latitude.size, dtype=bool)
    bridge_mask = np.zeros(latitude.size, dtype=bool)
    path = Path(roads_path).expanduser().resolve()
    if not path.is_file() or latitude.size == 0 or longitude.size != latitude.size:
        return tunnel_mask, bridge_mask

    finite = np.isfinite(latitude) & np.isfinite(longitude)
    if not np.any(finite):
        return tunnel_mask, bridge_mask

    try:
        import pyogrio
        from pyproj import Transformer
        from shapely.geometry import Point
        from shapely.strtree import STRtree
    except Exception:
        return tunnel_mask, bridge_mask

    lat = latitude[finite]
    lon = longitude[finite]
    mean_lat = math.radians(float(np.mean(lat)))
    lat_margin = max_distance_m * 4.0 / 111_320.0
    lon_scale = max(111_320.0 * math.cos(mean_lat), 1.0)
    lon_margin = max_distance_m * 4.0 / lon_scale
    bbox = (
        float(np.min(lon) - lon_margin),
        float(np.min(lat) - lat_margin),
        float(np.max(lon) + lon_margin),
        float(np.max(lat) + lat_margin),
    )

    # Cache format v3 contains these columns. Older caches deliberately fall
    # through here and are rebuilt by the normal dataset preparation logic.
    try:
        roads = pyogrio.read_dataframe(
            path,
            layer="roads",
            bbox=bbox,
            columns=["tunnel", "bridge", "geometry"],
            use_arrow=True,
        )
    except Exception:
        try:
            roads = pyogrio.read_dataframe(path, layer="roads", bbox=bbox)
        except Exception:
            return tunnel_mask, bridge_mask

    if roads is None or roads.empty or "geometry" not in roads.columns:
        return tunnel_mask, bridge_mask
    if "tunnel" not in roads.columns and "bridge" not in roads.columns:
        return tunnel_mask, bridge_mask

    geometries: list[Any] = []
    kinds: list[str] = []
    try:
        metric = roads.to_crs(epsg=3857)
    except Exception:
        return tunnel_mask, bridge_mask

    for record in metric.to_dict("records"):
        tunnel = _osm_true(record.get("tunnel"))
        bridge = _osm_true(record.get("bridge"))
        if not tunnel and not bridge:
            continue
        kind = "tunnel" if tunnel else "bridge"
        for line in _iter_lines(record.get("geometry")):
            geometries.append(line)
            kinds.append(kind)

    if not geometries:
        return tunnel_mask, bridge_mask

    tree = STRtree(geometries)
    transformer = Transformer.from_crs(4326, 3857, always_xy=True)
    x_values, y_values = transformer.transform(longitude.tolist(), latitude.tolist())
    for index, (x_value, y_value) in enumerate(zip(x_values, y_values)):
        if not (math.isfinite(float(x_value)) and math.isfinite(float(y_value))):
            continue
        point = Point(float(x_value), float(y_value))
        structure_index = _nearest_index(tree, geometries, point)
        if structure_index is None:
            continue
        try:
            distance = float(geometries[structure_index].distance(point))
        except Exception:
            continue
        if distance > max_distance_m:
            continue
        if kinds[structure_index] == "tunnel":
            tunnel_mask[index] = True
        else:
            bridge_mask[index] = True

    return tunnel_mask, bridge_mask


def _correct_runs(
    distance_m: np.ndarray,
    elevation_m: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, int]:
    corrected = np.asarray(elevation_m, dtype=float).copy()
    indexes = np.flatnonzero(mask)
    if indexes.size == 0:
        return corrected, 0

    runs: list[tuple[int, int]] = []
    start = int(indexes[0])
    previous = start
    for raw_index in indexes[1:]:
        index = int(raw_index)
        if index == previous + 1:
            previous = index
            continue
        runs.append((start, previous))
        start = previous = index
    runs.append((start, previous))

    applied = 0
    for start, end in runs:
        left = start - 1
        right = end + 1
        if left < 0 or right >= corrected.size:
            continue
        x0 = float(distance_m[left])
        x1 = float(distance_m[right])
        y0 = float(corrected[left])
        y1 = float(corrected[right])
        if not all(math.isfinite(value) for value in (x0, x1, y0, y1)) or x1 <= x0:
            continue
        query = np.asarray(distance_m[start : end + 1], dtype=float)
        corrected[start : end + 1] = y0 + (query - x0) * (y1 - y0) / (x1 - x0)
        applied += 1
    return corrected, applied


def correct_structure_elevation(
    roads_path: str | Path,
    distance_m: np.ndarray,
    latitude: np.ndarray,
    longitude: np.ndarray,
    elevation_m: np.ndarray,
    *,
    max_distance_m: float = 12.0,
) -> tuple[np.ndarray, dict[str, int]]:
    """Replace terrain DEM heights on tunnels/bridges by portal/end interpolation.

    DEM and GraphHopper elevation values describe the terrain surface. For a
    tunnel this is the mountain above the road, and for a bridge it is the
    terrain below the deck. OSM structure tags identify those sections. The
    driven elevation is approximated by a linear profile between the last
    sampled point before and the first sampled point after each structure.
    """

    distance = np.asarray(distance_m, dtype=float).reshape(-1)
    latitude = np.asarray(latitude, dtype=float).reshape(-1)
    longitude = np.asarray(longitude, dtype=float).reshape(-1)
    elevation = np.asarray(elevation_m, dtype=float).reshape(-1)
    size = distance.size
    if not (size and latitude.size == size and longitude.size == size and elevation.size == size):
        return elevation.copy(), {"tunnel_points": 0, "bridge_points": 0, "corrected_runs": 0}

    tunnel_mask, bridge_mask = _structure_mask(
        roads_path,
        latitude,
        longitude,
        max_distance_m=max_distance_m,
    )
    structure_mask = tunnel_mask | bridge_mask
    corrected, runs = _correct_runs(distance, elevation, structure_mask)
    return corrected, {
        "tunnel_points": int(np.count_nonzero(tunnel_mask)),
        "bridge_points": int(np.count_nonzero(bridge_mask)),
        "corrected_runs": int(runs),
    }
