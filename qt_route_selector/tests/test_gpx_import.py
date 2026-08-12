from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from gpx_import import build_route_from_gpx, parse_gpx_track  # noqa: E402


class GraphHopperGpxImportTests(unittest.TestCase):
    @staticmethod
    def _write_graphhopper_gpx(path: Path) -> None:
        path.write_text(
            "<?xml version='1.0' encoding='UTF-8'?>\n"
            "<gpx xmlns='http://www.topografix.com/GPX/1/1' creator='GraphHopper' version='1.1'>\n"
            "  <trk><name>GraphHopper Track</name><trkseg>\n"
            "    <trkpt lat='48.000000' lon='9.000000'><ele>500.0</ele></trkpt>\n"
            "    <trkpt lat='48.000000' lon='9.001000'><ele>501.5</ele></trkpt>\n"
            "    <trkpt lat='48.000000' lon='9.002000'><ele>503.0</ele></trkpt>\n"
            "  </trkseg></trk>\n"
            "</gpx>\n",
            encoding="utf-8",
        )

    def test_graphhopper_track_and_elevation_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gpx = Path(tmp) / "route.gpx"
            self._write_graphhopper_gpx(gpx)
            parsed = parse_gpx_track(gpx)

            self.assertEqual(parsed["creator"], "GraphHopper")
            self.assertEqual(parsed["name"], "GraphHopper Track")
            self.assertEqual(len(parsed["coordinates"]), 3)
            self.assertEqual(parsed["elevation_points"], 3)
            self.assertEqual(parsed["coordinates"][1]["elevation_m"], 501.5)

    def test_track_is_enriched_without_recalculating_geometry(self) -> None:
        import geopandas as gpd
        from shapely.geometry import LineString

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpx = root / "route.gpx"
            roads_path = root / "routing.gpkg"
            roads_path.write_bytes(b"placeholder")
            self._write_graphhopper_gpx(gpx)

            roads = gpd.GeoDataFrame(
                [
                    {
                        "highway": "residential",
                        "maxspeed": "50",
                        "surface": "asphalt",
                        "name": "Teststraße",
                        "ref": "",
                        "oneway": "no",
                        "junction": "",
                        "geometry": LineString(
                            [(9.0, 48.0), (9.001, 48.0), (9.002, 48.0)]
                        ),
                    }
                ],
                geometry="geometry",
                crs="EPSG:4326",
            )

            with patch("gpx_import._load_roads", return_value=roads), patch(
                "gpx_import._load_signals", return_value=[]
            ):
                result = build_route_from_gpx(roads_path, gpx)

            coordinates = result["coordinates"]
            self.assertEqual(len(coordinates), 3)
            self.assertEqual(coordinates[0]["longitude"], 9.0)
            self.assertEqual(coordinates[-1]["longitude"], 9.002)
            self.assertEqual(coordinates[-1]["elevation_m"], 503.0)

            segments = result["segments"]
            self.assertEqual(len(segments), 2)
            self.assertTrue(all(segment["maxspeed_kmh"] == 50.0 for segment in segments))
            self.assertTrue(all(segment["highway"] == "residential" for segment in segments))
            self.assertTrue(all(segment["surface"] == "asphalt" for segment in segments))

            summary = result["summary"]
            self.assertEqual(summary["source_type"], "gpx_import")
            self.assertEqual(summary["gpx_matched_segments"], 2)
            self.assertEqual(summary["gpx_unmatched_segments"], 0)
            self.assertEqual(summary["gpx_elevation_points"], 3)


if __name__ == "__main__":
    unittest.main()
