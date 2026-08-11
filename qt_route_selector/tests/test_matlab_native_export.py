from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qt_route_selector.matlab_native_export import (
    _build_matlab_statement,
    _matlab_quote,
    convert_to_native_matlab_tables,
)


class MatlabNativeExportTest(unittest.TestCase):
    def test_statement_creates_native_tables_and_timetable_in_final_mat(self) -> None:
        raw = Path(r"C:\Temp\raw export.mat")
        output = Path(r"C:\Temp\final export.mat")
        statement = _build_matlab_statement(raw, output)

        self.assertIn("distanceTable=array2table", statement)
        self.assertIn("driveTable=array2table", statement)
        self.assertIn("driveTimetable=table2timetable", statement)
        self.assertIn("rowTime=seconds(driveTable.time_s)", statement)
        self.assertIn("powerTimetable=driveTimetable(:,powerNames)", statement)
        self.assertIn("trafficLightTable=array2table", statement)
        self.assertIn("routeCoordinateTable=array2table", statement)
        self.assertIn("save('C:\\Temp\\final export.mat','-struct','S','-v7.3')", statement)
        self.assertIn(
            "save('C:\\Temp\\final export.mat','distanceTable','driveTable','driveTimetable'",
            statement,
        )

    def test_matlab_path_quote_escapes_apostrophes(self) -> None:
        self.assertEqual(_matlab_quote("route's result.mat"), "'route''s result.mat'")

    def test_conversion_invokes_matlab_batch_and_returns_only_final_mat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.mat"
            raw.write_bytes(b"raw")
            output = root / "result.mat"
            matlab = root / "matlab.exe"
            matlab.write_bytes(b"stub")

            def fake_run(args, **kwargs):
                self.assertEqual(args[0], str(matlab.resolve()))
                self.assertEqual(args[1], "-batch")
                self.assertIn("distanceTable=array2table", args[2])
                output.write_bytes(b"native-mat")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch("qt_route_selector.matlab_native_export.subprocess.run", side_effect=fake_run):
                result = convert_to_native_matlab_tables(
                    raw,
                    output,
                    matlab_executable=matlab,
                    timeout_s=30,
                )

            self.assertEqual(result, output.resolve())
            self.assertTrue(output.is_file())
            self.assertEqual(list(root.glob("*.m")), [])


if __name__ == "__main__":
    unittest.main()
