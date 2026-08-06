from __future__ import annotations

import unittest

import geopandas as gpd
from shapely.geometry import LineString

from qt_route_selector.local_router import (
    _build_graph,
    _parse_maxspeed,
    _parse_other_tags,
    _shortest_path_with_snapping,
)


class LocalRouterTests(unittest.TestCase):
    def test_parse_maxspeed(self) -> None:
        self.assertAlmostEqual(_parse_maxspeed("50", "residential"), 50.0)
        self.assertAlmostEqual(_parse_maxspeed("30 mph", "residential"), 48.28032)
        self.assertAlmostEqual(_parse_maxspeed(None, "motorway"), 120.0)

    def test_parse_other_tags(self) -> None:
        tags = _parse_other_tags('"maxspeed"=>"70","surface"=>"asphalt"')
        self.assertEqual(tags["maxspeed"], "70")
        self.assertEqual(tags["surface"], "asphalt")

    def test_oneway_graph_direction(self) -> None:
        roads = gpd.GeoDataFrame(
            {
                "highway": ["residential"],
                "maxspeed": ["30"],
                "oneway": ["yes"],
            },
            geometry=[LineString([(9.0, 48.0), (9.001, 48.0)])],
            crs="EPSG:4326",
        )

        graph, _positions = _build_graph(roads)
        source = (9.0, 48.0)
        target = (9.001, 48.0)
        self.assertTrue(graph.has_edge(source, target))
        self.assertFalse(graph.has_edge(target, source))

    def test_route_through_connected_segments(self) -> None:
        roads = gpd.GeoDataFrame(
            {
                "highway": ["residential", "primary"],
                "maxspeed": ["30", "70"],
                "oneway": ["no", "no"],
                "surface": ["asphalt", "asphalt"],
            },
            geometry=[
                LineString([(9.0, 48.0), (9.001, 48.0)]),
                LineString([(9.001, 48.0), (9.002, 48.0)]),
            ],
            crs="EPSG:4326",
        )

        graph, positions = _build_graph(roads)
        path, start_snap, target_snap = _shortest_path_with_snapping(
            graph,
            positions,
            start=(48.0, 9.0),
            target=(48.0, 9.002),
            max_snap_distance_m=100.0,
        )

        self.assertEqual(path, [(9.0, 48.0), (9.001, 48.0), (9.002, 48.0)])
        self.assertLess(start_snap, 0.1)
        self.assertLess(target_snap, 0.1)
        self.assertEqual(graph[(9.001, 48.0)][(9.002, 48.0)]["maxspeed_kmh"], 70.0)


if __name__ == "__main__":
    unittest.main()
