from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from routing_cache import build_routing_cache, default_cache_path


ProgressCallback = Callable[[str, int], None]


DATASETS = {
    "austria": {
        "label": "Österreich (A10 / Großglockner)",
        "osm_url": "https://download.geofabrik.de/europe/austria-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/austria-latest.osm.pbf.md5",
        "osm_filename": "austria-latest.osm.pbf",
    },
    "alps": {
        "label": "Alpen grenzüberschreitend",
        "osm_url": "https://download.geofabrik.de/europe/alps-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/alps-latest.osm.pbf.md5",
        "osm_filename": "alps-latest.osm.pbf",
    },
}

# Österreichweites 10-m-DGM aus Airborne-Laserscan-Daten, veröffentlicht über
# data.gv.at / Geoland. Das Archiv enthält GeoTIFF-Höhendaten.
AUSTRIA_DEM_URL = "https://gis.ktn.gv.at/OGD/Geographie_Planung/ogd-10m-at.zip"
AUSTRIA_DEM_ARCHIVE = "austria-dgm10.zip"
AUSTRIA_DEM_DIRECTORY = "austria-dgm10"


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
            "User-Agent": "GeschwindigkeitsverlaufAusGPS/0.4 (Qt research application)",
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
            headers={"User-Agent": "GeschwindigkeitsverlaufAusGPS/0.4"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            expected = response.read().decode("ascii", errors="ignore").strip().split()[0].lower()
    except Exception:
        # Der Datenbestand ist auch ohne MD5-Datei verwendbar. Eine fehlende
        # Prüfsumme soll den Offline-Workflow nicht blockieren.
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

    # Falls das Archiv mehrere GeoTIFFs enthält, bevorzugen wir die größte
    # Rasterdatei als landesweites Mosaik.
    return max(candidates, key=lambda path: path.stat().st_size)


def prepare_dataset(
    dataset_key: str,
    data_root: str | Path,
    progress: ProgressCallback | None = None,
) -> dict[str, str]:
    if dataset_key not in DATASETS:
        raise ValueError(f"Unbekannter Datensatz: {dataset_key}")

    dataset = DATASETS[dataset_key]
    root = Path(data_root).expanduser().resolve()
    osm_directory = root / "osm"
    elevation_directory = root / "elevation"
    osm_directory.mkdir(parents=True, exist_ok=True)
    elevation_directory.mkdir(parents=True, exist_ok=True)

    _emit(progress, f"Bereite {dataset['label']} vor …", 0)
    pbf_path = _download(
        dataset["osm_url"],
        osm_directory / dataset["osm_filename"],
        progress,
        start_percent=1,
        end_percent=55,
    )
    _verify_geofabrik_md5(pbf_path, dataset["osm_md5_url"], progress)

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

    dem_archive = _download(
        AUSTRIA_DEM_URL,
        elevation_directory / AUSTRIA_DEM_ARCHIVE,
        progress,
        start_percent=80,
        end_percent=96,
    )
    dem_path = _extract_dem(
        dem_archive,
        elevation_directory / AUSTRIA_DEM_DIRECTORY,
        progress,
    )

    _emit(progress, "OSM- und Höhendaten sind einsatzbereit.", 100)
    return {
        "dataset": dataset_key,
        "pbf_file": str(pbf_path),
        "roads_file": str(cache_path),
        "dem_file": str(dem_path.resolve()),
        "data_root": str(root),
    }
