from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from auto_data import (  # noqa: E402
    DATASETS,
    copernicus_tile_id,
    copernicus_tiles_for_route,
    points_within_dataset,
)


class AutomaticRegionDataTests(unittest.TestCase):
    def test_requested_regions_are_available(self) -> None:
        expected = {
            "baden_wuerttemberg",
            "bayern",
            "hessen",
            "switzerland",
            "austria",
            "dach",
        }
        self.assertTrue(expected.issubset(DATASETS))
        for key in expected:
            dataset = DATASETS[key]
            self.assertTrue(str(dataset["osm_url"]).endswith("-latest.osm.pbf"))
            self.assertTrue(str(dataset["poly_url"]).endswith(".poly"))

    def test_copernicus_tile_name_for_stuttgart(self) -> None:
        self.assertEqual(
            copernicus_tile_id(48.78, 9.18),
            "Copernicus_DSM_COG_10_N48_00_E009_00_DEM",
        )

    def test_route_tiles_are_deduplicated(self) -> None:
        points = [
            {"latitude": 48.7, "longitude": 9.1},
            {"latitude": 48.9, "longitude": 9.8},
            {"latitude": 49.1, "longitude": 10.2},
        ]
        self.assertEqual(
            copernicus_tiles_for_route(points),
            [
                "Copernicus_DSM_COG_10_N48_00_E009_00_DEM",
                "Copernicus_DSM_COG_10_N49_00_E010_00_DEM",
            ],
        )

    def test_cached_poly_detects_boundary_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            poly_path = root / "osm" / str(DATASETS["baden_wuerttemberg"]["poly_filename"])
            poly_path.parent.mkdir(parents=True)
            poly_path.write_text(
                "test\n"
                "1\n"
                " 8.0 48.0\n"
                " 10.0 48.0\n"
                " 10.0 50.0\n"
                " 8.0 50.0\n"
                " 8.0 48.0\n"
                "END\n"
                "END\n",
                encoding="utf-8",
            )
            self.assertTrue(
                points_within_dataset(
                    "baden_wuerttemberg",
                    root,
                    [(48.5, 9.0), (49.5, 9.5)],
                )
            )
            self.assertFalse(
                points_within_dataset(
                    "baden_wuerttemberg",
                    root,
                    [(48.5, 9.0), (50.5, 9.5)],
                )
            )


if __name__ == "__main__":
    unittest.main()
