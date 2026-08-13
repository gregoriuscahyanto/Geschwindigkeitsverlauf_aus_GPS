from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from qt_route_selector.runtime_paths import next_route_result_path


class TimestampedRouteProjectTests(unittest.TestCase):
    def test_route_filename_contains_date_time_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"GPS_ROUTENPLANER_HOME": tmp},
        ):
            when = datetime(2026, 8, 13, 13, 57, 42)
            first = next_route_result_path(when=when)
            self.assertEqual(first.name, "route_result_20260813_135742.json")
            first.parent.mkdir(parents=True, exist_ok=True)
            first.write_text("{}", encoding="utf-8")

            second = next_route_result_path(when=when)
            self.assertEqual(second.name, "route_result_20260813_135742_02.json")
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, Path(tmp).resolve() / "state")


if __name__ == "__main__":
    unittest.main()
