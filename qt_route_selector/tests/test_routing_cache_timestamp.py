from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from qt_route_selector.routing_cache import _keep_cache_not_older_than_source


class RoutingCacheTimestampTests(unittest.TestCase):
    def test_cache_is_raised_to_source_timestamp_after_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "california-260811.osm.pbf"
            cache = root / "california-260811_routing_v3.gpkg"
            source.write_bytes(b"pbf")
            cache.write_bytes(b"gpkg")

            future_ns = time.time_ns() + 10_000_000_000
            cache_ns = future_ns - 5_000_000_000
            os.utime(source, ns=(future_ns, future_ns))
            os.utime(cache, ns=(cache_ns, cache_ns))
            self.assertLess(cache.stat().st_mtime_ns, source.stat().st_mtime_ns)

            _keep_cache_not_older_than_source(source, cache)

            self.assertGreaterEqual(cache.stat().st_mtime_ns, source.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
