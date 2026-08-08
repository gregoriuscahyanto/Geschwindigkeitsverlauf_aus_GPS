from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry import LineString

from qt_route_selector.local_router import (
    _GRAPH_CACHE,
    _build_graph,
    _parse_maxspeed,
    _parse_other_tags,
    _road_priority_factor,
    _shortest_path_with_snapping,
    calculate_route,
)


class LocalRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        _GRAPH_CACHE.clear()

    def test_parse_maxspeed(self) -> None:
        self.assertAlmostEqual(_parse_maxspeed("50", "residential"), 50.0)
        self.assertAlmostEqual(_parse_maxspeed("30 mph", "residential"), 48.28032)
        self.assertAlmostEqual(_parse_maxspeed(None, "motorway"), 120.0)

    def test_parse_other_tags(self) -> None:
        tags = _parse_other_tags('"maxspeed"=>"70","surface"=>"asphalt"')
        self.assertEqual(tags["maxspeed"], "70")
        self.assertEqual(tags["surface"], "asphalt")

    def test_major_road_priority(self) -> None:
        self.assertLess(
            _road_priority_factor("motorway", "A 8"),
            _road_priority_factor("residential", ""),
        )
        self.assertLess(
            _road_priority_factor("primary", "B 10"),
            _road_priority_factor("secondary", "L 1192"),
        )
        self.assertLess(
            _road_priority_factor("secondary", "L 1192"),
            _road_priority_factor("residential", ""),
        )

    def test_oneway_graph_direction(self) -> None:
        roads = gpd.GeoDataFrame(
            {
                "highway": ["residential"],
                "maxspeed": ["30"],
                "oneway": ["yes"],
                "ref": [""],
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
                "ref": ["", "B 10"],
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
            weight="preferred_time_s",
        )

        self.assertEqual(path, [(9.0, 48.0), (9.001, 48.0), (9.002, 48.0)])
        self.assertLess(start_snap, 0.1)
        self.assertLess(target_snap, 0.1)
        self.assertEqual(graph[(9.001, 48.0)][(9.002, 48.0)]["maxspeed_kmh"], 70.0)

    def test_multiple_waypoints_and_graph_cache(self) -> None:
        roads = gpd.GeoDataFrame(
            {
                "highway": ["residential", "primary", "secondary"],
                "maxspeed": ["30", "70", "60"],
                "oneway": ["no", "no", "no"],
                "surface": ["asphalt", "asphalt", "asphalt"],
                "ref": ["", "B 10", "L 100"],
            },
            geometry=[
                LineString([(9.0, 48.0), (9.001, 48.0)]),
                LineString([(9.001, 48.0), (9.002, 48.0)]),
                LineString([(9.002, 48.0), (9.003, 48.0)]),
            ],
            crs="EPSG:4326",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roads.gpkg"
            pyogrio.write_dataframe(roads, path, layer="roads", driver="GPKG")
            bbox = {"west": 8.99, "south": 47.99, "east": 9.01, "north": 48.01}
            points = [(48.0, 9.0), (48.0, 9.002), (48.0, 9.003)]

            first = calculate_route(
                path,
                points=points,
                bbox=bbox,
                routing_profile="preferred",
            )
            second = calculate_route(
                path,
                points=points,
                bbox=bbox,
                routing_profile="fastest",
            )

        self.assertEqual(first["summary"]["waypoints"], 1)
        self.assertEqual(first["summary"]["legs"], 2)
        self.assertEqual(len(first["legs"]), 2)
        self.assertGreaterEqual(len(first["coordinates"]), 4)
        self.assertFalse(first["summary"]["graph_cache_hit"])
        self.assertTrue(second["summary"]["graph_cache_hit"])


if __name__ == "__main__":
    unittest.main()
