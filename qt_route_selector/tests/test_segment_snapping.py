from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry import LineString

from qt_route_selector.local_router import _GRAPH_CACHE, _haversine_m, calculate_route


class SegmentSnappingTests(unittest.TestCase):
    def setUp(self) -> None:
        _GRAPH_CACHE.clear()

    @staticmethod
    def _write_roads(directory: str, roads: gpd.GeoDataFrame) -> Path:
        path = Path(directory) / "roads.gpkg"
        pyogrio.write_dataframe(roads, path, layer="roads", driver="GPKG")
        return path

    def test_private_oneway_raceway_snaps_inside_long_segment(self) -> None:
        roads = gpd.GeoDataFrame(
            {
                "highway": ["raceway"],
                "maxspeed": [""],
                "oneway": ["yes"],
                "access": ["private"],
                "vehicle": ["private"],
                "motor_vehicle": ["private"],
                "surface": ["asphalt"],
                "ref": [""],
            },
            geometry=[
                LineString(
                    [
                        (17.8200, 40.320514),
                        (17.8300, 40.320514),
                    ]
                )
            ],
            crs="EPSG:4326",
        )
        start = (40.320514, 17.8240)
        target = (40.320514, 17.8280)
        bbox = {"west": 17.81, "south": 40.31, "east": 17.84, "north": 40.33}

        with tempfile.TemporaryDirectory() as directory:
            path = self._write_roads(directory, roads)
            result = calculate_route(
                path,
                start=start,
                target=target,
                bbox=bbox,
                routing_profile="shortest",
            )

        coordinates = result["coordinates"]
        self.assertAlmostEqual(coordinates[0]["latitude"], start[0], places=7)
        self.assertAlmostEqual(coordinates[0]["longitude"], start[1], places=7)
        self.assertAlmostEqual(coordinates[-1]["latitude"], target[0], places=7)
        self.assertAlmostEqual(coordinates[-1]["longitude"], target[1], places=7)
        self.assertEqual(result["summary"]["snapping"], "nearest_segment")
        self.assertLess(result["summary"]["start_snap_m"], 0.2)
        self.assertLess(result["summary"]["target_snap_m"], 0.2)

        expected_distance = _haversine_m((start[1], start[0]), (target[1], target[0]))
        self.assertAlmostEqual(
            result["summary"]["distance_km"] * 1000.0,
            expected_distance,
            delta=1.0,
        )
        driven = [segment for segment in result["segments"] if not segment["connector"]]
        self.assertTrue(driven)
        self.assertTrue(all(segment["highway"] == "raceway" for segment in driven))

    def test_nearby_parallel_road_node_does_not_pull_route_off_clicked_track(self) -> None:
        roads = gpd.GeoDataFrame(
            {
                "highway": ["raceway", "service"],
                "maxspeed": ["", "20"],
                "oneway": ["yes", "no"],
                "access": ["private", "yes"],
                "vehicle": ["private", "yes"],
                "motor_vehicle": ["private", "yes"],
                "surface": ["asphalt", "asphalt"],
                "ref": ["", ""],
            },
            geometry=[
                # The clicked track has no OSM node near the start: its only
                # nodes are the far endpoints of this long segment.
                LineString([(17.8200, 40.320514), (17.8300, 40.320514)]),
                # A parallel service road has a node almost next to the click.
                # Nearest-node snapping can therefore choose this road even
                # though the click lies exactly on the raceway geometry.
                LineString(
                    [
                        (17.8239, 40.320594),
                        (17.8240, 40.320594),
                        (17.8241, 40.320594),
                    ]
                ),
            ],
            crs="EPSG:4326",
        )
        start = (40.320514, 17.8240)
        target = (40.320514, 17.8280)
        bbox = {"west": 17.81, "south": 40.31, "east": 17.84, "north": 40.33}

        with tempfile.TemporaryDirectory() as directory:
            path = self._write_roads(directory, roads)
            result = calculate_route(
                path,
                start=start,
                target=target,
                bbox=bbox,
                routing_profile="shortest",
            )

        driven = [segment for segment in result["segments"] if not segment["connector"]]
        self.assertTrue(driven)
        self.assertTrue(all(segment["highway"] == "raceway" for segment in driven))
        self.assertAlmostEqual(result["coordinates"][0]["longitude"], start[1], places=7)
        self.assertLess(result["summary"]["start_snap_m"], 0.2)


if __name__ == "__main__":
    unittest.main()
