from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import auto_data  # noqa: E402


class LocalPbfChecksumTests(unittest.TestCase):
    def test_existing_local_pbf_is_not_checked_against_current_online_md5(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            osm = root / "osm"
            osm.mkdir(parents=True)

            dataset = auto_data.DATASETS["baden_wuerttemberg"]
            pbf = osm / str(dataset["osm_filename"])
            poly = osm / str(dataset["poly_filename"])
            pbf.write_bytes(b"older-but-valid-local-snapshot")
            poly.write_text(
                "baden-wuerttemberg\n1\n 8 47\n 10 47\n 10 50\n 8 50\n 8 47\nEND\nEND\n",
                encoding="utf-8",
            )

            cache = auto_data.default_cache_path(pbf)
            cache.write_bytes(b"routing-cache")
            cache.touch()

            with patch("auto_data._verify_geofabrik_md5") as verify, patch(
                "auto_data.build_routing_cache",
                return_value=cache,
            ):
                result = auto_data.prepare_dataset("baden_wuerttemberg", root)

            verify.assert_not_called()
            self.assertTrue(pbf.is_file())
            self.assertEqual(Path(result["pbf_file"]), pbf.resolve())


if __name__ == "__main__":
    unittest.main()
