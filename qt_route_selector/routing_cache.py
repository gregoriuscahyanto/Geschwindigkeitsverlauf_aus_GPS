from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable


# Bump when the set of cached road classes/columns changes. Existing GPKGs
# without the matching marker are rebuilt automatically from the local PBF.
ROUTING_CACHE_FORMAT_VERSION = 2

ALLOWED_CAR_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
    # OSM uses highway=raceway for dedicated motor-racing circuits such as
    # the Nürburgring Nordschleife. These must be present in the graph when a
    # user deliberately places routing points on the circuit.
    "raceway",
}

_CACHE_COLUMNS = (
    "osm_id",
    "highway",
    "name",
    "ref",
    "maxspeed",
    "maxspeed_forward",
    "maxspeed_backward",
    "surface",
    "smoothness",
    "oneway",
    "junction",
    "access",
    "vehicle",
    "motor_vehicle",
    "lanes",
)


def default_cache_path(source: str | Path) -> Path:
    path = Path(source).expanduser().resolve()
    base = path.name
    if base.lower().endswith(".osm.pbf"):
        base = base[:-8]
    elif base.lower().endswith(".pbf"):
        base = base[:-4]
    return path.with_name(f"{base}_routing.gpkg")


def _cache_version_path(cache_path: str | Path) -> Path:
    path = Path(cache_path).expanduser().resolve()
    return path.with_name(path.name + ".version")


def routing_cache_is_current(source: str | Path, cache_path: str | Path | None = None) -> bool:
    """Return True only for a current PBF-derived cache with matching format version."""

    source_path = Path(source).expanduser().resolve()
    cache = (
        Path(cache_path).expanduser().resolve()
        if cache_path is not None
        else default_cache_path(source_path)
    )
    if not source_path.is_file() or source_path.stat().st_size <= 0:
        return False
    if not cache.is_file() or cache.stat().st_size <= 0:
        return False
    if cache.stat().st_mtime_ns < source_path.stat().st_mtime_ns:
        return False

    marker = _cache_version_path(cache)
    if not marker.is_file():
        return False
    try:
        version = int(marker.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return False
    return version == ROUTING_CACHE_FORMAT_VERSION


def _write_cache_version(cache_path: Path) -> None:
    marker = _cache_version_path(cache_path)
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(str(ROUTING_CACHE_FORMAT_VERSION), encoding="ascii")
    os.replace(temporary, marker)


def build_routing_cache(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    progress: Callable[[str], None] | None = None,
    batch_size: int = 15_000,
) -> Path:
    """Convert one OSM PBF into a spatially indexed GeoPackage in one scan."""

    import geopandas as gpd
    import osmium
    import pyogrio
    from shapely.geometry import LineString, Point

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    output_path = (
        Path(destination).expanduser().resolve()
        if destination
        else default_cache_path(source_path)
    )
    temporary_path = output_path.with_name(
        output_path.stem + ".building" + output_path.suffix
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if temporary_path.exists():
        temporary_path.unlink()

    def notify(message: str) -> None:
        if progress is not None:
            progress(message)

    class CacheHandler(osmium.SimpleHandler):
        def __init__(self) -> None:
            super().__init__()
            self.ways_seen = 0
            self.roads_written = 0
            self._roads_layer_exists = False
            self.road_records: list[dict[str, Any]] = []
            self.road_geometries: list[Any] = []
            self.signal_records: list[dict[str, Any]] = []
            self.signal_geometries: list[Any] = []

        def node(self, node: Any) -> None:
            if node.tags.get("highway") != "traffic_signals":
                return
            if not node.location.valid():
                return
            self.signal_records.append(
                {"osm_id": int(node.id), "highway": "traffic_signals"}
            )
            self.signal_geometries.append(
                Point(float(node.location.lon), float(node.location.lat))
            )

        def way(self, way: Any) -> None:
            self.ways_seen += 1
            if self.ways_seen % 100_000 == 0:
                notify(
                    f"PBF-Index: {self.ways_seen:,} Wege gelesen, "
                    f"{self.roads_written + len(self.road_records):,} Straßen übernommen …"
                )

            highway = way.tags.get("highway")
            if highway not in ALLOWED_CAR_HIGHWAYS:
                return
            if way.tags.get("area") == "yes":
                return

            coordinates: list[tuple[float, float]] = []
            for node_ref in way.nodes:
                if not node_ref.location.valid():
                    return
                coordinates.append(
                    (float(node_ref.location.lon), float(node_ref.location.lat))
                )
            if len(coordinates) < 2:
                return

            record: dict[str, Any] = {"osm_id": int(way.id)}
            for column in _CACHE_COLUMNS[1:]:
                osm_key = column.replace("_forward", ":forward").replace(
                    "_backward", ":backward"
                )
                record[column] = way.tags.get(osm_key, "")
            self.road_records.append(record)
            self.road_geometries.append(LineString(coordinates))
            if len(self.road_records) >= batch_size:
                self.flush_roads()

        def flush_roads(self) -> None:
            if not self.road_records:
                return
            frame = gpd.GeoDataFrame(
                self.road_records,
                geometry=self.road_geometries,
                crs="EPSG:4326",
            )
            kwargs: dict[str, Any] = {
                "layer": "roads",
                "driver": "GPKG",
                "append": self._roads_layer_exists,
            }
            if not self._roads_layer_exists:
                kwargs["layer_options"] = {"SPATIAL_INDEX": "YES"}
            pyogrio.write_dataframe(frame, temporary_path, **kwargs)
            self.roads_written += len(frame)
            self._roads_layer_exists = True
            self.road_records.clear()
            self.road_geometries.clear()
            notify(f"PBF-Index: {self.roads_written:,} Straßen geschrieben …")

        def finish(self) -> None:
            self.flush_roads()
            if not self._roads_layer_exists:
                raise RuntimeError(
                    "Die PBF enthält keine unterstützten befahrbaren Straßen."
                )
            if self.signal_records:
                signals = gpd.GeoDataFrame(
                    self.signal_records,
                    geometry=self.signal_geometries,
                    crs="EPSG:4326",
                )
                pyogrio.write_dataframe(
                    signals,
                    temporary_path,
                    layer="signals",
                    driver="GPKG",
                    append=False,
                    layer_options={"SPATIAL_INDEX": "YES"},
                )
            notify(
                f"PBF-Index fertig: {self.roads_written:,} Straßen und "
                f"{len(self.signal_records):,} Ampeln."
            )

    notify(
        "PBF-Index wird einmalig aufgebaut. Das kann mehrere Minuten dauern …"
    )
    handler = CacheHandler()
    try:
        handler.apply_file(str(source_path), locations=True, idx="flex_mem")
        handler.finish()
        os.replace(temporary_path, output_path)
        _write_cache_version(output_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return output_path
