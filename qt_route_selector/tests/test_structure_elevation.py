from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from qt_route_selector.routing_cache import ROUTING_CACHE_FORMAT_VERSION, _CACHE_COLUMNS
from qt_route_selector.structure_elevation import correct_structure_elevation


class StructureElevationTests(unittest.TestCase):
    def test_routing_cache_preserves_structure_tags(self) -> None:
        self.assertGreaterEqual(ROUTING_CACHE_FORMAT_VERSION, 3)
        for column in ("tunnel", "bridge", "layer", "covered"):
            self.assertIn(column, _CACHE_COLUMNS)

    def test_tunnel_terrain_hump_is_replaced_by_portal_interpolation(self) -> None:
        distance = np.asarray([0.0, 100.0, 200.0, 300.0, 400.0])
        latitude = np.linspace(47.0, 47.004, 5)
        longitude = np.linspace(12.0, 12.004, 5)
        # The middle value represents a mountain surface above a tunnel.
        elevation = np.asarray([100.0, 180.0, 320.0, 190.0, 140.0])
        tunnel = np.asarray([False, True, True, True, False])
        bridge = np.zeros(5, dtype=bool)

        with patch(
            "qt_route_selector.structure_elevation._structure_mask",
            return_value=(tunnel, bridge),
        ):
            corrected, stats = correct_structure_elevation(
                "unused.gpkg", distance, latitude, longitude, elevation
            )

        np.testing.assert_allclose(corrected, [100.0, 110.0, 120.0, 130.0, 140.0])
        self.assertEqual(stats["tunnel_points"], 3)
        self.assertEqual(stats["bridge_points"], 0)
        self.assertEqual(stats["corrected_runs"], 1)

    def test_bridge_valley_is_replaced_by_deck_interpolation(self) -> None:
        distance = np.asarray([0.0, 50.0, 100.0, 150.0, 200.0])
        latitude = np.linspace(48.0, 48.004, 5)
        longitude = np.linspace(9.0, 9.004, 5)
        # Terrain below a bridge drops sharply, while the road deck continues.
        elevation = np.asarray([200.0, 160.0, 80.0, 165.0, 220.0])
        tunnel = np.zeros(5, dtype=bool)
        bridge = np.asarray([False, True, True, True, False])

        with patch(
            "qt_route_selector.structure_elevation._structure_mask",
            return_value=(tunnel, bridge),
        ):
            corrected, stats = correct_structure_elevation(
                "unused.gpkg", distance, latitude, longitude, elevation
            )

        np.testing.assert_allclose(corrected, [200.0, 205.0, 210.0, 215.0, 220.0])
        self.assertEqual(stats["bridge_points"], 3)
        self.assertEqual(stats["corrected_runs"], 1)


if __name__ == "__main__":
    unittest.main()
