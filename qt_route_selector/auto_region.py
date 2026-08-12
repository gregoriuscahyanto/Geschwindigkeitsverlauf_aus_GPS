from __future__ import annotations

import math
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from auto_data import DATASETS, points_within_dataset
from routing_cache import default_cache_path

try:
    from .region_catalog import register_extra_datasets
except ImportError:
    from region_catalog import register_extra_datasets


register_extra_datasets(DATASETS)


# Prefer the smallest useful extract first. Country polygons are checked only
# after the supported German regional extracts. DACH is the final fallback and
# therefore now means that the selected points really span more than one DACH
# country instead of merely lying outside BW/Bayern/Hessen.
REGIONAL_DATASET_KEYS = (
    "baden_wuerttemberg",
    "bayern",
    "hessen",
    "rheinland_pfalz",
)

COUNTRY_DATASET_KEYS = (
    "austria",
    "germany",
    "switzerland",
)

DATASET_ORDER = (
    "germany",
    "austria",
    "switzerland",
    "baden_wuerttemberg",
    "bayern",
    "hessen",
    "rheinland_pfalz",
    "dach",
)

DISPLAY_LABELS = {
    "austria": "Österreich (gesamt)",
    "baden_wuerttemberg": "Baden-Württemberg",
    "bayern": "Bayern",
    "germany": "Deutschland (gesamt)",
    "hessen": "Hessen",
    "rheinland_pfalz": "Rheinland-Pfalz",
    "switzerland": "Schweiz",
    "dach": "DACH – grenzüberschreitend",
}


def dataset_label(dataset_key: str) -> str:
    return DISPLAY_LABELS.get(
        dataset_key,
        str(DATASETS.get(dataset_key, {}).get("label", dataset_key)),
    )


def _coordinate_pair(
    point: Mapping[str, object] | Sequence[float],
) -> tuple[float, float]:
    if isinstance(point, Mapping):
        return float(point["latitude"]), float(point["longitude"])
    return float(point[0]), float(point[1])


def _download_boundary(
    dataset_key: str,
    data_root: str | Path,
) -> Path:
    dataset = DATASETS[dataset_key]
    root = Path(data_root).expanduser().resolve()
    destination = root / "osm" / str(dataset["poly_filename"])
    if destination.is_file() and destination.stat().st_size > 0:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        str(dataset["poly_url"]),
        headers={
            "User-Agent": "GeschwindigkeitsverlaufAusGPS/0.7 (automatic region detection)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as target:
            while True:
                block = response.read(64 * 1024)
                if not block:
                    break
                target.write(block)
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return destination


def ensure_region_boundaries(
    data_root: str | Path,
    progress: Any | None = None,
) -> None:
    keys = REGIONAL_DATASET_KEYS + COUNTRY_DATASET_KEYS + ("dach",)
    total = len(keys)
    for index, dataset_key in enumerate(keys, start=1):
        if progress is not None:
            progress(
                f"Prüfe Gebietsgrenze: {dataset_label(dataset_key)} …",
                int((index - 1) / total * 90),
            )
        _download_boundary(dataset_key, data_root)
    if progress is not None:
        progress("Gebietsgrenzen sind lokal verfügbar.", 100)


def detect_dataset_for_points(
    points: Iterable[Mapping[str, object] | Sequence[float]],
    data_root: str | Path,
    progress: Any | None = None,
) -> str:
    selected = list(points)
    if len(selected) < 2:
        raise ValueError("Für die automatische Gebietserkennung werden mindestens zwei Punkte benötigt.")

    ensure_region_boundaries(data_root, progress=progress)

    # Small extracts first: this keeps downloads and routing indexes compact.
    for dataset_key in REGIONAL_DATASET_KEYS:
        if points_within_dataset(dataset_key, data_root, selected) is True:
            return dataset_key

    # Then distinguish the three countries. In particular, points elsewhere in
    # Germany must resolve to Germany and must never be labelled cross-border.
    for dataset_key in COUNTRY_DATASET_KEYS:
        if points_within_dataset(dataset_key, data_root, selected) is True:
            return dataset_key

    # Only points that do not fit into one country but still lie inside the
    # combined DACH polygon are genuinely cross-border.
    if points_within_dataset("dach", data_root, selected) is True:
        return "dach"

    coordinates = [
        f"{_coordinate_pair(point)[0]:.5f}, {_coordinate_pair(point)[1]:.5f}"
        for point in selected
    ]
    raise ValueError(
        "Mindestens ein Punkt liegt außerhalb der derzeit automatisch unterstützten "
        "Gebiete (Deutschland, Österreich, Schweiz bzw. DACH). "
        f"Punkte: {'; '.join(coordinates)}"
    )


def dataset_storage_state(
    dataset_key: str,
    data_root: str | Path,
) -> dict[str, object]:
    dataset = DATASETS[dataset_key]
    root = Path(data_root).expanduser().resolve()
    osm_directory = root / "osm"

    poly_path = osm_directory / str(dataset["poly_filename"])
    poly_ready = poly_path.is_file() and poly_path.stat().st_size > 0

    pbf_path = osm_directory / str(dataset["osm_filename"])
    pbf_ready = pbf_path.is_file() and pbf_path.stat().st_size > 0

    cache_path = Path(default_cache_path(pbf_path)).resolve()
    gpkg_exists = cache_path.is_file() and cache_path.stat().st_size > 0
    gpkg_current = (
        pbf_ready
        and gpkg_exists
        and cache_path.stat().st_mtime_ns >= pbf_path.stat().st_mtime_ns
    )

    if gpkg_current:
        status = "gpkg_ready"
        status_text = "Routing-GPKG bereit"
    elif gpkg_exists:
        status = "gpkg_stale"
        status_text = "GPKG vorhanden, aber älter als PBF"
    elif pbf_ready:
        status = "pbf_only"
        status_text = "OSM-PBF vorhanden, GPKG fehlt"
    elif poly_ready:
        status = "poly_only"
        status_text = "nur Gebietsgrenze (.poly) vorhanden"
    else:
        status = "missing"
        status_text = "noch nicht lokal"

    return {
        "dataset": dataset_key,
        "label": dataset_label(dataset_key),
        "status": status,
        "status_text": status_text,
        "poly_file": str(poly_path.resolve()),
        "pbf_file": str(pbf_path.resolve()),
        "gpkg_file": str(cache_path),
        "poly_ready": poly_ready,
        "pbf_ready": pbf_ready,
        "gpkg_exists": gpkg_exists,
        "gpkg_ready": gpkg_current,
    }


def _poly_outer_rings(path: Path) -> list[list[tuple[float, float]]]:
    """Read outer rings from a Geofabrik .poly file as (latitude, longitude)."""

    if not path.is_file():
        return []

    rings: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    current_is_hole = False

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines[1:]:
        line = raw.strip()
        if not line:
            continue
        if line == "END":
            if current and not current_is_hole and len(current) >= 3:
                rings.append(current)
            current = None
            current_is_hole = False
            continue
        if current is None:
            current = []
            current_is_hole = line.startswith("!")
            continue

        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            longitude = float(parts[0])
            latitude = float(parts[1])
        except ValueError:
            continue
        if math.isfinite(latitude) and math.isfinite(longitude):
            current.append((latitude, longitude))

    return rings


def _decimate_ring(
    ring: list[tuple[float, float]],
    *,
    max_points: int = 1200,
) -> list[tuple[float, float]]:
    if len(ring) <= max_points:
        return ring
    step = max(1, math.ceil(len(ring) / max_points))
    reduced = ring[::step]
    if reduced[-1] != ring[-1]:
        reduced.append(ring[-1])
    return reduced


def coverage_snapshot(
    data_root: str | Path,
    *,
    active_dataset_key: str = "",
) -> list[dict[str, object]]:
    """Return local-only polygon payloads for the data-coverage map.

    No downloads are started here. A region is drawable only when its .poly file
    is already present locally. Broad DACH/Germany polygons are emitted first so
    the smaller regional polygons remain visible above them.
    """

    root = Path(data_root).expanduser().resolve()
    render_order = ("dach",) + tuple(key for key in DATASET_ORDER if key != "dach")
    payload: list[dict[str, object]] = []

    for dataset_key in render_order:
        state = dataset_storage_state(dataset_key, root)
        if not bool(state["poly_ready"]):
            continue

        level = "poly"
        if bool(state["gpkg_ready"]):
            level = "gpkg"
        elif bool(state["gpkg_exists"]):
            level = "stale"
        elif bool(state["pbf_ready"]):
            level = "pbf"

        poly_path = Path(str(state["poly_file"]))
        for ring_index, ring in enumerate(_poly_outer_rings(poly_path)):
            points = _decimate_ring(ring)
            if len(points) < 3:
                continue
            payload.append(
                {
                    "dataset": dataset_key,
                    "label": str(state["label"]),
                    "ring": ring_index,
                    "level": level,
                    "active": dataset_key == active_dataset_key,
                    "path": [
                        {"latitude": float(latitude), "longitude": float(longitude)}
                        for latitude, longitude in points
                    ],
                }
            )

    return payload
