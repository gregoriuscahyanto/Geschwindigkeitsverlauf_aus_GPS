from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from auto_data import DATASETS, points_within_dataset
from routing_cache import default_cache_path


REGIONAL_DATASET_KEYS = (
    "baden_wuerttemberg",
    "bayern",
    "hessen",
    "switzerland",
    "austria",
)

DATASET_ORDER = (
    "austria",
    "baden_wuerttemberg",
    "bayern",
    "hessen",
    "switzerland",
    "dach",
)

DISPLAY_LABELS = {
    "austria": "Österreich (gesamt)",
    "baden_wuerttemberg": "Baden-Württemberg",
    "bayern": "Bayern",
    "hessen": "Hessen",
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
    keys = REGIONAL_DATASET_KEYS + ("dach",)
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

    for dataset_key in REGIONAL_DATASET_KEYS:
        if points_within_dataset(dataset_key, data_root, selected) is True:
            return dataset_key

    if points_within_dataset("dach", data_root, selected) is True:
        return "dach"

    coordinates = [
        f"{_coordinate_pair(point)[0]:.5f}, {_coordinate_pair(point)[1]:.5f}"
        for point in selected
    ]
    raise ValueError(
        "Mindestens ein Punkt liegt außerhalb der derzeit automatisch unterstützten "
        "Gebiete (Baden-Württemberg, Bayern, Hessen, Schweiz, Österreich bzw. DACH). "
        f"Punkte: {'; '.join(coordinates)}"
    )


def dataset_storage_state(
    dataset_key: str,
    data_root: str | Path,
) -> dict[str, object]:
    dataset = DATASETS[dataset_key]
    root = Path(data_root).expanduser().resolve()
    pbf_path = root / "osm" / str(dataset["osm_filename"])
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
        status_text = "GPKG bereit"
    elif gpkg_exists:
        status = "gpkg_stale"
        status_text = "GPKG vorhanden, aber älter als PBF"
    elif pbf_ready:
        status = "pbf_only"
        status_text = "PBF vorhanden, GPKG fehlt"
    else:
        status = "missing"
        status_text = "noch nicht lokal"

    return {
        "dataset": dataset_key,
        "label": dataset_label(dataset_key),
        "status": status,
        "status_text": status_text,
        "pbf_file": str(pbf_path.resolve()),
        "gpkg_file": str(cache_path),
        "pbf_ready": pbf_ready,
        "gpkg_ready": gpkg_current,
    }
