from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from auto_data import (  # noqa: E402
    COPERNICUS_DEM_DIRECTORY,
    copernicus_tile_id,
    prepare_elevation_for_route,
)


class CopernicusGlobalFallbackTests(unittest.TestCase):
    def test_california_uses_western_tile_name(self) -> None:
        self.assertEqual(
            copernicus_tile_id(34.05, -118.25),
            "Copernicus_DSM_COG_10_N34_00_W119_00_DEM",
        )

    def test_missing_glo30_tile_falls_back_to_worldwide_glo90(self) -> None:
        calls: list[str] = []

        def fake_download(url, destination, progress, *, start_percent, end_percent):
            del progress, start_percent, end_percent
            calls.append(str(url))
            if "copernicus-dem-30m" in str(url):
                raise OSError("GLO-30 tile unavailable")
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fake-glo90")
            return path

        with tempfile.TemporaryDirectory() as tmp, patch(
            "auto_data._download",
            side_effect=fake_download,
        ):
            result = prepare_elevation_for_route(
                "baden_wuerttemberg",
                tmp,
                [{"latitude": 34.05, "longitude": -118.25}],
            )
            root = Path(tmp)
            fallback = (
                root
                / "elevation"
                / COPERNICUS_DEM_DIRECTORY
                / "Copernicus_DSM_COG_30_N34_00_W119_00_DEM.tif"
            )
            self.assertTrue(fallback.is_file())

        self.assertEqual(len(calls), 2)
        self.assertIn("copernicus-dem-30m.s3.amazonaws.com", calls[0])
        self.assertIn("copernicus-dem-90m.s3.amazonaws.com", calls[1])
        self.assertEqual(result["provider"], "copernicus_glo30_glo90_fallback")
        self.assertEqual(result["fallback_tile_count"], 1)

    def test_existing_glo90_fallback_is_reused_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fallback = (
                root
                / "elevation"
                / COPERNICUS_DEM_DIRECTORY
                / "Copernicus_DSM_COG_30_N34_00_W119_00_DEM.tif"
            )
            fallback.parent.mkdir(parents=True, exist_ok=True)
            fallback.write_bytes(b"cached-glo90")

            with patch("auto_data._download") as download:
                result = prepare_elevation_for_route(
                    "baden_wuerttemberg",
                    root,
                    [{"latitude": 34.05, "longitude": -118.25}],
                )

            download.assert_not_called()
            self.assertEqual(result["fallback_tile_count"], 1)


if __name__ == "__main__":
    unittest.main()
