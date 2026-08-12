from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from auto_data import DATASETS  # noqa: E402
from auto_region import dataset_label, discover_local_datasets  # noqa: E402


class DatasetLabelTests(unittest.TestCase):
    def test_dynamic_label_ignores_poly_header_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            osm = root / "osm"
            osm.mkdir(parents=True)
            (osm / "california.poly").write_text(
                "None\n"
                "1\n"
                " -125.0 32.0\n"
                " -113.0 32.0\n"
                " -113.0 43.0\n"
                " -125.0 43.0\n"
                " -125.0 32.0\n"
                "END\n"
                "END\n",
                encoding="utf-8",
            )
            (osm / "california-260811.osm.pbf").write_bytes(b"test-pbf")

            discover_local_datasets(root)
            self.assertIn("california", DATASETS)
            self.assertEqual(dataset_label("california"), "California")

            DATASETS.pop("california", None)

    def test_builtin_labels_also_come_from_poly_filename(self) -> None:
        self.assertEqual(dataset_label("austria"), "Austria")
        self.assertEqual(dataset_label("baden_wuerttemberg"), "Baden Wuerttemberg")
        self.assertEqual(dataset_label("rheinland_pfalz"), "Rheinland Pfalz")
        self.assertEqual(dataset_label("dach"), "Dach")


if __name__ == "__main__":
    unittest.main()
