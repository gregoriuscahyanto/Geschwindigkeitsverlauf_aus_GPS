from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Import auto_region first: it registers the additional Germany/Rheinland-Pfalz
# datasets in the shared auto_data.DATASETS catalog.
from auto_region import (  # noqa: E402
    detect_dataset_for_points,
    discover_local_datasets,
    ensure_region_boundaries,
)
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
            "rheinland_pfalz",
            "germany",
            "switzerland",
            "austria",
            "dach",
        }
        self.assertTrue(expected.issubset(DATASETS))
        for key in expected:
            dataset = DATASETS[key]
            self.assertTrue(str(dataset["osm_url"]).endswith("-latest.osm.pbf"))
            self.assertTrue(str(dataset["poly_url"]).endswith(".poly"))

    def test_new_local_poly_pbf_pair_is_discovered_and_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            osm = root / "osm"
            osm.mkdir(parents=True)
            poly = osm / "italy.poly"
            pbf = osm / "italy-latest.osm.pbf"
            poly.write_text(
                "italy\n"
                "1\n"
                " 7.0 36.0\n"
                " 19.0 36.0\n"
                " 19.0 48.0\n"
                " 7.0 48.0\n"
                " 7.0 36.0\n"
                "END\n"
                "END\n",
                encoding="utf-8",
            )
            pbf.write_bytes(b"test-pbf")

            discovered = discover_local_datasets(root)
            self.assertIn("italy", discovered)
            self.assertEqual(DATASETS["italy"]["osm_filename"], pbf.name)
            self.assertEqual(DATASETS["italy"]["poly_filename"], poly.name)
            self.assertTrue(DATASETS["italy"]["local_discovered"])

            with patch("auto_region.ensure_region_boundaries"):
                selected = detect_dataset_for_points(
                    [(41.9, 12.5), (45.4, 9.2)],
                    root,
                )
            self.assertEqual(selected, "italy")

            pbf.unlink()
            poly.unlink()
            discover_local_datasets(root)
            self.assertNotIn("italy", DATASETS)

    def test_rheinland_pfalz_is_selected_instead_of_dach(self) -> None:
        points = [
            (50.3356, 6.9475),  # Nürburgring area
            (50.3790, 6.9490),
        ]
        with patch("auto_region.ensure_region_boundaries"), patch(
            "auto_region.points_within_dataset",
            side_effect=lambda key, _root, _points: key == "rheinland_pfalz",
        ):
            self.assertEqual(detect_dataset_for_points(points, "unused"), "rheinland_pfalz")

    def test_other_german_area_uses_germany_not_dach(self) -> None:
        points = [(50.9, 6.9), (51.2, 7.1)]
        with patch("auto_region.ensure_region_boundaries"), patch(
            "auto_region.points_within_dataset",
            side_effect=lambda key, _root, _points: key == "germany",
        ):
            self.assertEqual(detect_dataset_for_points(points, "unused"), "germany")

    def test_dach_is_only_final_cross_country_fallback(self) -> None:
        points = [(47.6, 9.2), (47.4, 9.7)]
        with patch("auto_region.ensure_region_boundaries"), patch(
            "auto_region.points_within_dataset",
            side_effect=lambda key, _root, _points: key == "dach",
        ):
            self.assertEqual(detect_dataset_for_points(points, "unused"), "dach")

    def test_offline_local_region_is_used_without_any_download(self) -> None:
        points = [(50.3356, 6.9475), (50.3790, 6.9490)]

        def local_membership(key: str, _root: object, _points: object) -> bool | None:
            if key == "rheinland_pfalz":
                return True
            return None

        with patch(
            "auto_region.points_within_dataset",
            side_effect=local_membership,
        ), patch("auto_region._download_boundary") as download:
            self.assertEqual(
                detect_dataset_for_points(points, "offline-data"),
                "rheinland_pfalz",
            )
            download.assert_not_called()

    def test_boundary_download_failure_is_best_effort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "auto_region._download_boundary",
            side_effect=OSError("firewall"),
        ) as download:
            ensure_region_boundaries(tmp)
            # After the first network failure all remaining missing boundaries
            # are skipped instead of causing repeated firewall timeouts.
            self.assertEqual(download.call_count, 1)

    def test_missing_offline_boundaries_have_actionable_error(self) -> None:
        points = [(50.3356, 6.9475), (50.3790, 6.9490)]
        with patch("auto_region.ensure_region_boundaries"), patch(
            "auto_region.points_within_dataset",
            return_value=None,
        ):
            with self.assertRaisesRegex(ValueError, r"\.poly"):
                detect_dataset_for_points(points, "offline-data")

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
