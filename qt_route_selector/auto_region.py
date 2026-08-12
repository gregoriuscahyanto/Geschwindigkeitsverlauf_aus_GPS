from __future__ import annotations

import math
import re
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
# after the supported German regional extracts and locally discovered extracts.
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

STATIC_DATASET_ORDER = (
    "germany",
    "austria",
    "switzerland",
    "baden_wuerttemberg",
    "bayern",
    "hessen",
    "rheinland_pfalz",
    "dach",
)

# Kept mutable so consumers that import DATASET_ORDER once also see datasets
# discovered later while the application is already running.
DATASET_ORDER = list(STATIC_DATASET_ORDER)
_DYNAMIC_DATASET_KEYS: set[str] = set()

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


def _dynamic_dataset_key(base_name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", base_name.lower()).strip("_")
    return key or "local_dataset"


def _dynamic_dataset_label(poly_path: Path, base_name: str) -> str:
    try:
        first_line = poly_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines()[0].strip()
    except (OSError, IndexError):
        first_line = ""

    candidate = first_line if first_line and len(first_line) <= 80 else base_name
    if candidate.lower() in {"polygon", "poly"}:
        candidate = base_name
    return candidate.replace("_", " ").replace("-", " ").strip().title()


def _local_pbf_for_poly(osm_directory: Path, poly_path: Path) -> Path | None:
    """Return the preferred local PBF belonging to one ``<name>.poly`` file.

    Standard Geofabrik ``<name>-latest.osm.pbf`` is preferred. Dated or otherwise
    versioned files such as ``california-260811.osm.pbf`` are accepted as well.
    If several versioned files are present, the newest local file is selected.
    """

    base_name = poly_path.stem
    latest_path = osm_directory / f"{base_name}-latest.osm.pbf"
    if latest_path.is_file() and latest_path.stat().st_size > 0:
        return latest_path

    candidates = [
        path
        for path in osm_directory.glob(f"{base_name}-*.osm.pbf")
        if path.is_file() and path.stat().st_size > 0
    ]
    plain_path = osm_directory / f"{base_name}.osm.pbf"
    if plain_path.is_file() and plain_path.stat().st_size > 0:
        candidates.append(plain_path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name.lower()))


def discover_local_datasets(data_root: str | Path) -> tuple[str, ...]:
    """Register local POLY/PBF pairs as routing datasets.

    A pair is detected from ``<name>.poly`` plus either the normal Geofabrik
    ``<name>-latest.osm.pbf`` or a dated/versioned variant such as
    ``<name>-260811.osm.pbf``. The logical dataset name always comes from the
    POLY basename, so ``california-260811.osm.pbf`` + ``california.poly`` is
    registered as ``california``.
    """

    root = Path(data_root).expanduser().resolve()
    osm_directory = root / "osm"
    osm_directory.mkdir(parents=True, exist_ok=True)

    # Remove dynamically registered datasets whose local pair has been deleted.
    for dataset_key in tuple(_DYNAMIC_DATASET_KEYS):
        dataset = DATASETS.get(dataset_key, {})
        pbf_path = osm_directory / str(dataset.get("osm_filename", ""))
        poly_path = osm_directory / str(dataset.get("poly_filename", ""))
        if (
            pbf_path.is_file()
            and pbf_path.stat().st_size > 0
            and poly_path.is_file()
            and poly_path.stat().st_size > 0
        ):
            continue
        _DYNAMIC_DATASET_KEYS.discard(dataset_key)
        DATASETS.pop(dataset_key, None)
        while dataset_key in DATASET_ORDER:
            DATASET_ORDER.remove(dataset_key)

    filename_to_key: dict[tuple[str, str], str] = {}
    dynamic_by_poly: dict[str, str] = {}
    for dataset_key, definition in DATASETS.items():
        poly_filename = str(definition.get("poly_filename", ""))
        filename_to_key[
            (
                str(definition.get("osm_filename", "")).lower(),
                poly_filename.lower(),
            )
        ] = dataset_key
        if dataset_key in _DYNAMIC_DATASET_KEYS and poly_filename:
            dynamic_by_poly[poly_filename.lower()] = dataset_key

    for poly_path in sorted(osm_directory.glob("*.poly")):
        if not poly_path.is_file() or poly_path.stat().st_size <= 0:
            continue
        pbf_path = _local_pbf_for_poly(osm_directory, poly_path)
        if pbf_path is None:
            continue

        existing_key = filename_to_key.get(
            (pbf_path.name.lower(), poly_path.name.lower())
        )
        if existing_key:
            if existing_key not in DATASET_ORDER:
                DATASET_ORDER.append(existing_key)
            continue

        # If this POLY was already registered dynamically and a newer dated PBF
        # appeared, keep the stable logical key and simply point it to the newer
        # local PBF instead of creating a duplicate dataset entry.
        dynamic_key = dynamic_by_poly.get(poly_path.name.lower())
        if dynamic_key and dynamic_key in DATASETS:
            DATASETS[dynamic_key]["osm_filename"] = pbf_path.name
            filename_to_key[(pbf_path.name.lower(), poly_path.name.lower())] = dynamic_key
            continue

        base_name = poly_path.stem
        dataset_key = _dynamic_dataset_key(base_name)
        if dataset_key in DATASETS:
            original_key = dataset_key
            counter = 2
            while dataset_key in DATASETS:
                dataset_key = f"local_{original_key}_{counter}"
                counter += 1

        DATASETS[dataset_key] = {
            "label": _dynamic_dataset_label(poly_path, base_name),
            "osm_url": "",
            "osm_md5_url": "",
            "osm_filename": pbf_path.name,
            "poly_url": "",
            "poly_filename": poly_path.name,
            "elevation_provider": "copernicus_glo30",
            "local_discovered": True,
        }
        _DYNAMIC_DATASET_KEYS.add(dataset_key)
        DATASET_ORDER.append(dataset_key)
        dynamic_by_poly[poly_path.name.lower()] = dataset_key
        filename_to_key[(pbf_path.name.lower(), poly_path.name.lower())] = dataset_key

    return tuple(
        key
        for key in DATASET_ORDER
        if key in _DYNAMIC_DATASET_KEYS
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
        with urllib.request.urlopen(request, timeout=8) as response, partial.open("wb") as target:
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
    """Best-effort boundary preparation for the built-in DACH catalog."""

    keys = REGIONAL_DATASET_KEYS + COUNTRY_DATASET_KEYS + ("dach",)
    total = len(keys)
    root = Path(data_root).expanduser().resolve()
    network_unavailable = False
    missing: list[str] = []

    for index, dataset_key in enumerate(keys, start=1):
        dataset = DATASETS[dataset_key]
        boundary_path = root / "osm" / str(dataset["poly_filename"])
        percent = int((index - 1) / total * 90)

        if boundary_path.is_file() and boundary_path.stat().st_size > 0:
            if progress is not None:
                progress(f"Gebietsgrenze lokal: {dataset_label(dataset_key)}", percent)
            continue

        missing.append(dataset_key)
        if network_unavailable:
            if progress is not None:
                progress(
                    f"Gebietsgrenze fehlt lokal: {dataset_label(dataset_key)}",
                    percent,
                )
            continue

        if progress is not None:
            progress(
                f"Gebietsgrenze fehlt lokal, versuche Download: {dataset_label(dataset_key)} …",
                percent,
            )
        try:
            _download_boundary(dataset_key, root)
        except Exception:
            network_unavailable = True
            if progress is not None:
                progress(
                    "Kein Zugriff auf Gebietsgrenzen im Internet – verwende nur lokale POLY-Dateien.",
                    percent,
                )
        else:
            missing.pop()

    if progress is not None:
        if missing:
            progress(
                f"Lokale Gebietsgrenzen geprüft; {len(missing)} Grenze(n) fehlen.",
                100,
            )
        else:
            progress("Gebietsgrenzen sind lokal verfügbar.", 100)


def _match_cached_boundaries(
    selected: list[Mapping[str, object] | Sequence[float]],
    data_root: str | Path,
) -> tuple[str, list[str]]:
    """Return a safe match from currently available local polygons only."""

    dynamic_keys = discover_local_datasets(data_root)
    missing: list[str] = []

    # Locally added extracts are checked first. This also lets a dated local PBF
    # for a built-in region win over a broad fallback whose POLY happens to exist.
    for dataset_key in dynamic_keys:
        result = points_within_dataset(dataset_key, data_root, selected)
        if result is True:
            return dataset_key, missing

    for dataset_key in REGIONAL_DATASET_KEYS:
        result = points_within_dataset(dataset_key, data_root, selected)
        if result is True:
            return dataset_key, missing
        if result is None:
            missing.append(dataset_key)

    for dataset_key in COUNTRY_DATASET_KEYS:
        result = points_within_dataset(dataset_key, data_root, selected)
        if result is True:
            return dataset_key, missing
        if result is None:
            missing.append(dataset_key)

    dach_result = points_within_dataset("dach", data_root, selected)
    if dach_result is None:
        missing.append("dach")
    elif dach_result is True:
        missing_countries = set(missing).intersection(COUNTRY_DATASET_KEYS)
        if not missing_countries:
            return "dach", missing

    return "", missing


def detect_dataset_for_points(
    points: Iterable[Mapping[str, object] | Sequence[float]],
    data_root: str | Path,
    progress: Any | None = None,
) -> str:
    selected = list(points)
    if len(selected) < 2:
        raise ValueError("Für die automatische Gebietserkennung werden mindestens zwei Punkte benötigt.")

    dataset_key, missing = _match_cached_boundaries(selected, data_root)
    if dataset_key:
        return dataset_key

    if missing:
        ensure_region_boundaries(data_root, progress=progress)
        dataset_key, missing = _match_cached_boundaries(selected, data_root)
        if dataset_key:
            return dataset_key

    coordinates = [
        f"{_coordinate_pair(point)[0]:.5f}, {_coordinate_pair(point)[1]:.5f}"
        for point in selected
    ]

    if missing:
        missing_labels = ", ".join(dataset_label(key) for key in missing)
        raise ValueError(
            "Gebiet konnte offline nicht sicher automatisch bestimmt werden. "
            f"Folgende eingebaute Gebietsgrenzen (.poly) fehlen lokal: {missing_labels}. "
            "Alternativ kann ein eigenes Paar <gebiet>.poly + "
            "<gebiet>-*.osm.pbf in data\\osm kopiert werden. "
            f"Punkte: {'; '.join(coordinates)}"
        )

    raise ValueError(
        "Keines der lokal verfügbaren Gebiete enthält alle gewählten Punkte. "
        "Lege für ein weiteres Gebiet die passende .poly- und .osm.pbf-Datei "
        "gemeinsam in data\\osm ab. "
        f"Punkte: {'; '.join(coordinates)}"
    )


def dataset_storage_state(
    dataset_key: str,
    data_root: str | Path,
) -> dict[str, object]:
    discover_local_datasets(data_root)
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
    """Return local-only polygon payloads for the data-coverage map."""

    root = Path(data_root).expanduser().resolve()
    discover_local_datasets(root)
    render_order = ("dach",) + tuple(key for key in DATASET_ORDER if key != "dach")
    payload: list[dict[str, object]] = []

    for dataset_key in render_order:
        if dataset_key not in DATASETS:
            continue
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