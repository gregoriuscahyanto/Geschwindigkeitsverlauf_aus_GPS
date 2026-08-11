from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qt_route_selector.matlab_table_loader import write_matlab_table_loader


class MatlabTableLoaderTest(unittest.TestCase):
    def test_loader_creates_native_table_and_timetable_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mat_path = Path(directory) / "speed profile result.mat"
            loader_path = write_matlab_table_loader(mat_path)

            self.assertEqual(loader_path.name, "load_speed_profile_result.m")
            source = loader_path.read_text(encoding="utf-8")
            self.assertIn("data = load(fullfile(loaderDir, 'speed profile result.mat'));", source)
            self.assertIn("distanceTable = array2table", source)
            self.assertIn("driveTable = array2table", source)
            self.assertIn("driveTimetable = table2timetable", source)
            self.assertIn("rowTime = seconds(driveTable.time_s);", source)
            self.assertIn("powerTimetable = driveTimetable(:, powerNames);", source)
            self.assertIn("trafficLightTable = array2table", source)
            self.assertIn("routeCoordinateTable = array2table", source)

    def test_loader_escapes_matlab_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mat_path = Path(directory) / "route's result.mat"
            loader_path = write_matlab_table_loader(mat_path)
            source = loader_path.read_text(encoding="utf-8")
            self.assertIn("'route''s result.mat'", source)


if __name__ == "__main__":
    unittest.main()
