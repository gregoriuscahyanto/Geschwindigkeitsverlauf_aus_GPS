from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qt_route_selector.runtime_paths import (
    data_dir,
    exports_dir,
    route_result_path,
    runtime_root,
    selected_region_path,
    state_dir,
)


class RuntimePathTests(unittest.TestCase):
    def test_override_keeps_runtime_files_outside_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            with patch.dict(os.environ, {"GPS_ROUTENPLANER_HOME": str(root)}):
                self.assertEqual(runtime_root(), root.resolve())
                self.assertEqual(data_dir(), root.resolve() / "data")
                self.assertEqual(state_dir(), root.resolve() / "state")
                self.assertEqual(exports_dir(), root.resolve() / "exports")
                self.assertEqual(route_result_path(), root.resolve() / "state" / "route_result.json")
                self.assertEqual(selected_region_path(), root.resolve() / "state" / "selected_region.json")
                self.assertTrue(data_dir().is_dir())
                self.assertTrue(state_dir().is_dir())
                self.assertTrue(exports_dir().is_dir())


if __name__ == "__main__":
    unittest.main()
