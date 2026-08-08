from __future__ import annotations

import unittest

from qt_route_selector.offline_map import geo_to_world, world_to_geo


class OfflineMapProjectionTests(unittest.TestCase):
    def test_web_mercator_round_trip(self) -> None:
        samples = [
            (48.743, 9.320, 12.0),
            (0.0, 0.0, 4.0),
            (-33.8688, 151.2093, 10.0),
            (60.1699, 24.9384, 15.0),
        ]
        for latitude, longitude, zoom in samples:
            with self.subTest(latitude=latitude, longitude=longitude, zoom=zoom):
                world = geo_to_world(latitude, longitude, zoom)
                result_latitude, result_longitude = world_to_geo(
                    world.x(),
                    world.y(),
                    zoom,
                )
                self.assertAlmostEqual(result_latitude, latitude, places=7)
                self.assertAlmostEqual(result_longitude, longitude, places=7)

    def test_world_axis_directions(self) -> None:
        center = geo_to_world(48.0, 9.0, 12.0)
        east = geo_to_world(48.0, 9.1, 12.0)
        north = geo_to_world(48.1, 9.0, 12.0)
        self.assertGreater(east.x(), center.x())
        self.assertLess(north.y(), center.y())


if __name__ == "__main__":
    unittest.main()
