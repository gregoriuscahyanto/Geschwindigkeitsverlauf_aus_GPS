from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Point

from qt_route_selector.local_router import _load_signals


class TrafficSignalFilterTests(unittest.TestCase):
    @staticmethod
    def _signals(*coordinates: tuple[float, float]) -> gpd.GeoDataFrame:
        return gpd.GeoDataFrame(
            {"highway": ["traffic_signals"] * len(coordinates)},
            geometry=[Point(lon, lat) for lon, lat in coordinates],
            crs="EPSG:4326",
        )

    @staticmethod
    def _segment(highway: str, category: str) -> dict[str, object]:
        return {
            "from_index": 0,
            "to_index": 1,
            "highway": highway,
            "road_category": category,
        }

    def test_signal_on_motorway_is_rejected(self) -> None:
        route_nodes = [(9.0, 48.0), (9.002, 48.0)]
        signals = self._signals((9.001, 48.0))
        with patch("qt_route_selector.local_router._read_signal_features", return_value=signals):
            matches = _load_signals(
                Path("roads.gpkg"),
                (8.9, 47.9, 9.1, 48.1),
                route_nodes,
                [self._segment("motorway", "autobahn")],
            )
        self.assertEqual(matches, [])

    def test_signal_on_normal_routed_road_is_kept(self) -> None:
        route_nodes = [(9.0, 48.0), (9.002, 48.0)]
        signals = self._signals((9.001, 48.0))
        with patch("qt_route_selector.local_router._read_signal_features", return_value=signals):
            matches = _load_signals(
                Path("roads.gpkg"),
                (8.9, 47.9, 9.1, 48.1),
                route_nodes,
                [self._segment("primary", "hauptstrasse")],
            )
        self.assertEqual(len(matches), 1)
        self.assertAlmostEqual(matches[0]["longitude"], 9.001)

    def test_parallel_road_signal_outside_tight_radius_is_rejected(self) -> None:
        route_nodes = [(9.0, 48.0), (9.002, 48.0)]
        signals = self._signals((9.001, 48.00012))
        with patch("qt_route_selector.local_router._read_signal_features", return_value=signals):
            matches = _load_signals(
                Path("roads.gpkg"),
                (8.9, 47.9, 9.1, 48.1),
                route_nodes,
                [self._segment("primary", "hauptstrasse")],
            )
        self.assertEqual(matches, [])

    def test_multiple_signal_nodes_at_one_junction_become_one_stop(self) -> None:
        route_nodes = [(9.0, 48.0), (9.002, 48.0)]
        signals = self._signals((9.001, 48.0), (9.00105, 48.0))
        with patch("qt_route_selector.local_router._read_signal_features", return_value=signals):
            matches = _load_signals(
                Path("roads.gpkg"),
                (8.9, 47.9, 9.1, 48.1),
                route_nodes,
                [self._segment("primary", "hauptstrasse")],
            )
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
