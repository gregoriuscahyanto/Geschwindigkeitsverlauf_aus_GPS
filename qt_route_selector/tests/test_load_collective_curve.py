from __future__ import annotations

import unittest

import numpy as np

from load_collective_curve import cumulative_load_curve


class CumulativeLoadCurveTests(unittest.TestCase):
    def test_curve_is_sorted_and_reaches_full_time_share(self) -> None:
        time_s = np.asarray([0.0, 1.0, 2.0, 4.0, 7.0])
        load = np.asarray([5.0, 10.0, 2.0, 8.0, -3.0])
        curve = cumulative_load_curve(time_s, load)
        x = curve["time_share_pct"]
        y = curve["load"]
        self.assertGreater(len(x), 0)
        self.assertTrue(np.all(np.diff(x) >= 0.0))
        self.assertTrue(np.all(np.diff(y) <= 0.0))
        self.assertAlmostEqual(float(x[-1]), 100.0, places=6)

    def test_positive_only_and_normalized_modes(self) -> None:
        time_s = np.arange(0.0, 6.0)
        load = np.asarray([-10.0, 0.0, 5.0, 20.0, 10.0, 2.0])
        curve = cumulative_load_curve(
            time_s,
            load,
            positive_only=True,
            normalize=True,
        )
        self.assertTrue(np.all(curve["load"] > 0.0))
        self.assertLessEqual(float(np.max(curve["load"])), 1.0)
        self.assertAlmostEqual(float(np.max(curve["load"])), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
