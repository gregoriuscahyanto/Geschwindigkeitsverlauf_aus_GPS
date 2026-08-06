from __future__ import annotations

import unittest

import numpy as np

from qt_route_selector.integrated_speed_profile import _osm_only_event_positions
from qt_route_selector.speed_simulation import prepare_route
from qt_route_selector.tests.test_speed_simulation import synthetic_route


class OSMOnlyTrafficLightTests(unittest.TestCase):
    def test_requested_count_is_clamped_to_osm_signals(self) -> None:
        route = prepare_route(synthetic_route(), sample_distance_m=5.0)
        selected = _osm_only_event_positions(
            route,
            requested=5,
            detected=route.detected_signal_distances_m,
            rng=np.random.default_rng(1),
        )
        self.assertEqual(len(selected), 1)
        np.testing.assert_allclose(selected, route.detected_signal_distances_m)

    def test_no_osm_signal_means_no_stop(self) -> None:
        route = prepare_route(synthetic_route(), sample_distance_m=5.0)
        selected = _osm_only_event_positions(
            route,
            requested=4,
            detected=np.empty(0),
            rng=np.random.default_rng(1),
        )
        self.assertEqual(len(selected), 0)

    def test_subset_uses_only_detected_positions(self) -> None:
        route = prepare_route(synthetic_route(), sample_distance_m=5.0)
        detected = np.asarray([100.0, 200.0, 300.0, 400.0])
        selected = _osm_only_event_positions(
            route,
            requested=2,
            detected=detected,
            rng=np.random.default_rng(1),
        )
        self.assertEqual(len(selected), 2)
        self.assertTrue(set(selected).issubset(set(detected)))


if __name__ == "__main__":
    unittest.main()
