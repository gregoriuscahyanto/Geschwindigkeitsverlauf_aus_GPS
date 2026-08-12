from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

from qt_route_selector.local_router import _build_graph
from qt_route_selector.routing_cache import (
    ALLOWED_CAR_HIGHWAYS,
    ROUTING_CACHE_FORMAT_VERSION,
    default_cache_path,
)


class RacewayRoutingTests(unittest.TestCase):
    def test_raceway_is_included_in_pbf_routing_cache(self) -> None:
        self.assertIn("raceway", ALLOWED_CAR_HIGHWAYS)

    def test_cache_filename_is_versioned(self) -> None:
        source = Path(tempfile.gettempdir()) / "rheinland-pfalz-latest.osm.pbf"
        cache = default_cache_path(source)
        self.assertIn(f"_routing_v{ROUTING_CACHE_FORMAT_VERSION}.gpkg", cache.name)

    def test_raceway_edges_are_routable(self) -> None:
        roads = gpd.GeoDataFrame(
            {
                "highway": ["raceway"],
                "maxspeed": ["100"],
                "oneway": ["yes"],
                "access": ["customers"],
                "ref": [""],
            },
            geometry=[LineString([(6.9400, 50.3400), (6.9410, 50.3410)])],
            crs="EPSG:4326",
        )

        graph, _positions = _build_graph(roads)
        source = (6.94, 50.34)
        target = (6.941, 50.341)
        self.assertTrue(graph.has_edge(source, target))
        self.assertFalse(graph.has_edge(target, source))
        self.assertEqual(graph[source][target]["highway"], "raceway")


if __name__ == "__main__":
    unittest.main()
