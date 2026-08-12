from __future__ import annotations

from typing import Any


EXTRA_DATASETS: dict[str, dict[str, Any]] = {
    "rheinland_pfalz": {
        "label": "Rheinland-Pfalz",
        "osm_url": "https://download.geofabrik.de/europe/germany/rheinland-pfalz-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/germany/rheinland-pfalz-latest.osm.pbf.md5",
        "osm_filename": "rheinland-pfalz-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/germany/rheinland-pfalz.poly",
        "poly_filename": "rheinland-pfalz.poly",
        "elevation_provider": "copernicus_glo30",
    },
    "germany": {
        "label": "Deutschland (gesamt)",
        "osm_url": "https://download.geofabrik.de/europe/germany-latest.osm.pbf",
        "osm_md5_url": "https://download.geofabrik.de/europe/germany-latest.osm.pbf.md5",
        "osm_filename": "germany-latest.osm.pbf",
        "poly_url": "https://download.geofabrik.de/europe/germany.poly",
        "poly_filename": "germany.poly",
        "elevation_provider": "copernicus_glo30",
        "large_download": True,
        "large_download_kind": "germany",
    },
}


def register_extra_datasets(datasets: dict[str, dict[str, Any]]) -> None:
    """Register additional Geofabrik datasets without replacing existing entries."""

    for key, definition in EXTRA_DATASETS.items():
        datasets.setdefault(key, dict(definition))
