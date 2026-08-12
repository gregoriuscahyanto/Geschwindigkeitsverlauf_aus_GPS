from __future__ import annotations

import hashlib
import math
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from routing_cache import build_routing_cache, default_cache_path


ProgressCallback = Callable[[str, int], None]


DATASETS = {
    "baden_wuerttemberg": {
        "label": "Baden-Württemberg",
        "osm_url": "https://download.geofabrik.de/europe/germany/baden-wuerttemberg-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/germany/baden-wuerttemberg-latest.osm.pbf.md5",
        "osm_filename": "baden-wuerttemberg-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/germany/baden-wuerttemberg.poly",
        "poly_filename": "baden-wuerttemberg.poly",
        "elevation_provider": "copernicus_glo30",
    },
    "bayern": {
        "label": "Bayern",
        "osm_url": "https://download.geofabrik.de/europe/germany/bayern-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/germany/bayern-latest.osm.pbf.md5",
        "osm_filename": "bayern-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/germany/bayern.poly",
        "poly_filename": "bayern.poly",
        "elevation_provider": "copernicus_glo30",
    },
    "hessen": {
        "label": "Hessen",
        "osm_url": "https://download.geofabrik.de/europe/germany/hessen-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/germany/hessen-latest.osm.pbf.md5",
        "osm_filename": "hessen-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/germany/hessen.poly",
        "poly_filename": "hessen.poly",
        "elevation_provider": "copernicus_glo30",
    },
    "switzerland": {
        "label": "Schweiz",
        "osm_url": "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf.md5",
        "osm_filename": "switzerland-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/switzerland.poly",
        "poly_filename": "switzerland.poly",
        "elevation_provider": "copernicus_glo30",
    },
    "austria": {
        "label": "Österreich – A10 / Großglockner",
        "osm_url": "https://download.geofabrik.de/europe/austria-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/austria-latest.osm.pbf.md5",
        "osm_filename": "austria-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/austria.poly",
        "poly_filename": "austria.poly",
        "elevation_provider": "austria_dgm10",
    },
    "dach": {
        "label": "DACH – grenzüberschreitend",
        "osm_url": "https://download.geofabrik.de/europe/dach-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/dach-latest.osm.pbf.md5",
        "osm_filename": "dach-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/dach.poly",
        "poly_filename": "dach.poly",
        "elevation_provider": "copernicus_glo30",
        "large_download": True,
    },
}

AUSTRIA_DEM_URL = "https://gis.ktn.gv.at/OGD/Geographie_Planung/ogd-10m-at.zip"
AUSTRIA_DEM_ARCHIVE = "austria-dgm10.zip"
AUSTRIA_DEM_DIRECTORY = "austria-dgm10"

COPERNICUS_DEM_DIRECTORY = "copernicus-glo30"
COPERNICUS_DEM_BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def _emit(progress: ProgressCallback | None, text: str, percent: int) -> None:
    if progress is not None:
        progress(text, max(0, min(100, int(percent))))


def _download(
    url: str,
    destination: Path,
    progress: ProgressCallback | None,
    *,
    start_percent: int,
    end_percent: int,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        _emit(progress, f"Bereits vorhanden: {destination.name}", end_percent)
        return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GeschwindigkeitsverlaufAusGPS/0.6 (Qt research application)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as target:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                target.write(block)
                downloaded += len(block)
                if total > 0:
                    fraction = min(1.0, downloaded / total)
                    percent = start_percent + int((end_percent - start_percent) * fraction)
                    _emit(
                        progress,
                        f"Lade {destination.name}: {downloaded / 1024**2:.0f} / {total / 1024**2:.0f} MiB",
                        percent,
                    )
                else:
                    _emit(
                        progress,
                        f"Lade {destination.name}: {downloaded / 1024**2:.0f} MiB",
                        start_percent,
                    )
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    _emit(progress, f"Download abgeschlossen: {destination.name}", end_percent)
    return destination


def _verify_geofabrik_md5(
    file_path: Path,
    md5_url: str,
    progress: ProgressCallback | None,
) -> None:
    _emit(progress, f"Prüfe {file_path.name} …", 57)
    try:
        request = urllib.request.Request(
            md5_url,
            headers={"User-Agent": "GeschwindigkeitsverlaufAusGPS/0.6"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            expected = response.read().decode("ascii", errors="ignore").strip().split()[0].lower()
    except Exception:
        return

    digest = hashlib.md5()
    with file_path.open("rb") as source:
        while True:
            block = source.read(4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    actual = digest.hexdigest().lower()
    if expected and actual != expected:
        file_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Prüfsummenfehler bei {file_path.name}. Bitte den Download erneut starten."
        )


def _extract_dem(
    archive_path: Path,
    output_directory: Path,
    progress: ProgressCallback | None,
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_directory.rglob("*.tif")) + sorted(output_directory.rglob("*.tiff"))
    if existing:
        selected = max(existing, key=lambda path: path.stat().st_size)
        _emit(progress, f"Höhenmodell bereits vorhanden: {selected.name}", 100)
        return selected

    _emit(progress, "Entpacke österreichisches 10-m-Höhenmodell …", 97)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(output_directory)

    candidates = sorted(output_directory.rglob("*.tif")) + sorted(output_directory.rglob("*.tiff"))
    if not candidates:
        raise RuntimeError("Das DGM-Archiv enthält keine GeoTIFF-Datei.")
    return max(candidates, key=lambda path: path.stat().st_size)


def _dataset_paths(dataset_key: str, data_root: str | Path) -> tuple[Path, Path, Path]:
    dataset = DATASETS[dataset_key]
    root = Path(data_root).expanduser().resolve()
    pbf_path = root / "osm" / str(dataset["osm_filename"])
    poly_path = root / "osm" / str(dataset["poly_filename"])
    return root, pbf_path, poly_path


def cached_dataset(dataset_key: str, data_root: str | Path) -> dict[str, str] | None:
    if dataset_key not in DATASETS:
        return None
    dataset = DATASETS[dataset_key]
    root, pbf_path, poly_path = _dataset_paths(dataset_key, data_root)
    if not pbf_path.is_file() or pbf_path.stat().st_size <= 0:
        return None
    cache_path = Path(default_cache_path(pbf_path)).resolve()
    if not cache_path.is_file() or cache_path.stat().st_size <= 0:
        return None

    dem_path = ""
    if dataset.get("elevation_provider") == "austria_dgm10":
        dem_dir = root / "elevation" / AUSTRIA_DEM_DIRECTORY
        candidates = []
        if dem_dir.is_dir():
            candidates = sorted(dem_dir.rglob("*.tif")) + sorted(dem_dir.rglob("*.tiff"))
        if candidates:
            dem_path = str(max(candidates, key=lambda path: path.stat().st_size).resolve())
    else:
        dem_dir = root / "elevation" / COPERNICUS_DEM_DIRECTORY
        if dem_dir.is_dir() and any(dem_dir.glob("*.tif")):
            dem_path = str(dem_dir.resolve())

    return {
        "dataset": dataset_key,
        "pbf_file": str(pbf_path.resolve()),
        "roads_file": str(cache_path),
        "poly_file": str(poly_path.resolve()) if poly_path.is_file() else "",
        "dem_file": dem_path,
        "data_root": str(root),
    }


def prepare_dataset(
    dataset_key: str,
    data_root: str | Path,
    progress: ProgressCallback | None = None,
) -> dict[str, str]:
    if dataset_key not in DATASETS:
        raise ValueError(f"Unbekannter Datensatz: {dataset_key}")

    dataset = DATASETS[dataset_key]
    root, pbf_path, poly_path = _dataset_paths(dataset_key, data_root)
    osm_directory = root / "osm"
    elevation_directory = root / "elevation"
    osm_directory.mkdir(parents=True, exist_ok=True)
    elevation_directory.mkdir(parents=True, exist_ok=True)

    _emit(progress, f"Bereite {dataset['label']} vor …", 0)

    # A local PBF may intentionally be an older snapshot of a Geofabrik
    # "*-latest" extract, especially on an enterprise/offline laptop. Comparing
    # such a snapshot with today's online *.md5 would falsely classify it as
    # corrupt and, worse, delete a valid local file. Only verify a PBF when this
    # preparation run actually had to download it.
    pbf_was_present = pbf_path.is_file() and pbf_path.stat().st_size > 0
    pbf_path = _download(
        str(dataset["osm_url"]),
        pbf_path,
        progress,
        start_percent=1,
        end_percent=52,
    )
    if not pbf_was_present:
        md5_url = str(dataset.get("osm_md5_url", "") or "").strip()
        if md5_url:
            _verify_geofabrik_md5(pbf_path, md5_url, progress)
    else:
        _emit(
            progress,
            f"Lokale PBF wird unverändert verwendet: {pbf_path.name}",
            57,
        )

    try:
        _download(
            str(dataset["poly_url"]),
            poly_path,
            progress,
            start_percent=53,
            end_percent=54,
        )
    except Exception:
        pass

    cache_path = default_cache_path(pbf_path)
    cache_current = (
        cache_path.exists()
        and cache_path.stat().st_size > 0
        and cache_path.stat().st_mtime_ns >= pbf_path.stat().st_mtime_ns
    )
    if cache_current:
        _emit(progress, f"Routingindex bereits vorhanden: {cache_path.name}", 78)
    else:
        _emit(progress, "Erzeuge lokalen Routing-Schnellindex …", 60)
        cache_path = build_routing_cache(
            str(pbf_path),
            progress=lambda message: _emit(progress, message, 68),
        )
        cache_path = Path(cache_path).resolve()
        _emit(progress, f"Routingindex bereit: {cache_path.name}", 78)

    dem_path = ""
    if dataset.get("elevation_provider") == "austria_dgm10":
        try:
            dem_archive = _download(
                AUSTRIA_DEM_URL,
                elevation_directory / AUSTRIA_DEM_ARCHIVE,
                progress,
                start_percent=80,
                end_percent=96,
            )
            dem_path = str(
                _extract_dem(
                    dem_archive,
                    elevation_directory / AUSTRIA_DEM_DIRECTORY,
                    progress,
                ).resolve()
            )
        except Exception as exc:
            _emit(progress, f"Österreich-DGM nicht verfügbar ({exc}); Route nutzt später Copernicus-Fallback.", 100)
    else:
        (elevation_directory / COPERNICUS_DEM_DIRECTORY).mkdir(parents=True, exist_ok=True)
        _emit(progress, "Routing bereit; Höhenkacheln werden automatisch für die konkrete Route geladen.", 100)

    return {
        "dataset": dataset_key,
        "pbf_file": str(pbf_path.resolve()),
        "roads_file": str(Path(cache_path).resolve()),
        "poly_file": str(poly_path.resolve()) if poly_path.is_file() else "",
        "dem_file": dem_path,
        "data_root": str(root),
    }


def _coordinate_pair(point: Mapping[str, object] | Sequence[float]) -> tuple[float, float]:
    if isinstance(point, Mapping):
        return float(point["latitude"]), float(point["longitude"])
    return float(point[0]), float(point[1])


def copernicus_tile_id(latitude: float, longitude: float) -> str:
    lat_floor = math.floor(float(latitude))
    lon_floor = math.floor(float(longitude))
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00_DEM"


def copernicus_tiles_for_route(
    points: Iterable[Mapping[str, object] | Sequence[float]],
) -> list[str]:
    tiles: set[str] = set()
    for point in points:
        latitude, longitude = _coordinate_pair(point)
        if math.isfinite(latitude) and math.isfinite(longitude):
            tiles.add(copernicus_tile_id(latitude, longitude))
    return sorted(tiles)


def prepare_elevation_for_route(
    dataset_key: str,
    data_root: str | Path,
    route_points: Iterable[Mapping[str, object] | Sequence[float]],
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    if dataset_key not in DATASETS:
        raise ValueError(f"Unbekannter Datensatz: {dataset_key}")

    dataset = DATASETS[dataset_key]
    root = Path(data_root).expanduser().resolve()

    if dataset.get("elevation_provider") == "austria_dgm10":
        cached = cached_dataset(dataset_key, root)
        if cached is not None and cached.get("dem_file"):
            _emit(progress, "Österreichisches 10-m-Höhenmodell bereits lokal vorhanden.", 100)
            return {
                "dataset": dataset_key,
                "dem_file": cached["dem_file"],
                "provider": "austria_dgm10",
                "tile_count": 1,
            }

    tiles = copernicus_tiles_for_route(route_points)
    if not tiles:
        raise ValueError("Die Route enthält keine gültigen GPS-Koordinaten für das Höhenmodell.")

    dem_directory = root / "elevation" / COPERNICUS_DEM_DIRECTORY
    dem_directory.mkdir(parents=True, exist_ok=True)
    total = len(tiles)
    for index, tile_id in enumerate(tiles):
        start = int(index / total * 100)
        end = int((index + 1) / total * 100)
        filename = f"{tile_id}.tif"
        url = f"{COPERNICUS_DEM_BASE_URL}/{tile_id}/{filename}"
        _download(
            url,
            dem_directory / filename,
            progress,
            start_percent=start,
            end_percent=end,
        )

    _emit(progress, f"{total} Copernicus-Höhenkachel(n) für die Route sind lokal bereit.", 100)
    return {
        "dataset": dataset_key,
        "dem_file": str(dem_directory.resolve()),
        "provider": "copernicus_glo30",
        "tile_count": total,
    }


def _parse_poly(path: Path) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    outers: list[list[tuple[float, float]]] = []
    holes: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    current_hole = False
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines[1:]:
        line = raw.strip()
        if not line:
            continue
        if line == "END":
            if current:
                (holes if current_hole else outers).append(current)
            current = None
            current_hole = False
            continue
        if current is None:
            current = []
            current_hole = line.startswith("!")
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
            except ValueError:
                continue
            current.append((lon, lat))
    return outers, holes


def _point_in_ring(longitude: float, latitude: float, ring: Sequence[tuple[float, float]]) -> bool:
    inside = False
    if len(ring) < 3:
        return False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > latitude) != (yj > latitude)) and (
            longitude < (xj - xi) * (latitude - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def points_within_dataset(
    dataset_key: str,
    data_root: str | Path,
    points: Iterable[Mapping[str, object] | Sequence[float]],
) -> bool | None:
    """Return True/False when a cached Geofabrik polygon is available, else None."""
    if dataset_key not in DATASETS:
        return None
    root, _pbf, poly_path = _dataset_paths(dataset_key, data_root)
    del root
    if not poly_path.is_file():
        return None
    try:
        outers, holes = _parse_poly(poly_path)
    except OSError:
        return None
    if not outers:
        return None

    for point in points:
        latitude, longitude = _coordinate_pair(point)
        inside_outer = any(_point_in_ring(longitude, latitude, ring) for ring in outers)
        inside_hole = any(_point_in_ring(longitude, latitude, ring) for ring in holes)
        if not inside_outer or inside_hole:
            return False
    return True