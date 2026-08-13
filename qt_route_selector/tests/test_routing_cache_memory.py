from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qt_route_selector.routing_cache import _location_index_spec


class _IndexModule:
    def __init__(self, types: list[str]) -> None:
        self._types = types

    def map_types(self) -> list[str]:
        return list(self._types)


class _OsmiumModule:
    def __init__(self, types: list[str]) -> None:
        self.index = _IndexModule(types)


class RoutingCacheMemoryTests(unittest.TestCase):
    def test_prefers_disk_backed_sparse_file_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.idx"
            spec, disk_backed = _location_index_spec(
                _OsmiumModule(["flex_mem", "sparse_file_array"]),
                path,
            )
        self.assertTrue(disk_backed)
        self.assertEqual(spec, f"sparse_file_array,{path}")

    def test_falls_back_to_flex_mem_if_file_index_is_unavailable(self) -> None:
        spec, disk_backed = _location_index_spec(
            _OsmiumModule(["flex_mem"]),
            Path("unused.idx"),
        )
        self.assertFalse(disk_backed)
        self.assertEqual(spec, "flex_mem")


if __name__ == "__main__":
    unittest.main()
