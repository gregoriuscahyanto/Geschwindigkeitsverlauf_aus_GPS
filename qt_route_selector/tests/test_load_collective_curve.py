from __future__ import annotations

import unittest

import numpy as np

from load_collective_curve import cumulative_load_curve


class CumulativeLoadCurveTests(unittest.TestCase):
    def test_signed_branches_start_with_extreme_at_zero_time(self) -> None:
        time_s = np.asarray([0.0, 1.0, 2.0, 4.0, 7.0])
        load = np.asarray([5.0, 10.0, 2.0, 8.0, -3.0])
        curve = cumulative_load_curve(time_s, load)

        positive_x = curve["positive_time_share_pct"]
        positive_y = curve["positive_load"]
        negative_x = curve["negative_time_share_pct"]
        negative_y = curve["negative_load"]

        self.assertGreater(len(positive_x), 0)
        self.assertGreater(len(negative_x), 0)
        self.assertAlmostEqual(float(positive_x[0]), 0.0, places=9)
        self.assertAlmostEqual(float(negative_x[0]), 0.0, places=9)
        self.assertAlmostEqual(float(positive_y[0]), 10.0, places=9)
        self.assertAlmostEqual(float(negative_y[0]), -3.0, places=9)

        # Positive loads accumulate from the highest value down towards zero.
        self.assertTrue(np.all(np.diff(positive_x) >= 0.0))
        self.assertTrue(np.all(np.diff(positive_y) <= 0.0))
        # Negative loads accumulate from the most negative value up towards zero.
        self.assertTrue(np.all(np.diff(negative_x) >= 0.0))
        self.assertTrue(np.all(np.diff(negative_y) >= 0.0))

        # Both branches use total trip time as denominator: their occupied time
        # shares therefore sum to 100 % here because there is no finite-duration
        # zero-load sample in this test signal.
        self.assertAlmostEqual(
            float(positive_x[-1] + negative_x[-1]),
            100.0,
            places=6,
        )

    def test_positive_only_and_normalized_modes(self) -> None:
        time_s = np.arange(0.0, 6.0)
        load = np.asarray([-10.0, 0.0, 5.0, 20.0, 10.0, 2.0])
        curve = cumulative_load_curve(
            time_s,
            load,
            positive_only=True,
            normalize=True,
        )
        self.assertGreater(len(curve["positive_load"]), 0)
        self.assertEqual(len(curve["negative_load"]), 0)
        self.assertAlmostEqual(float(curve["positive_time_share_pct"][0]), 0.0, places=9)
        self.assertTrue(np.all(curve["positive_load"] > 0.0))
        self.assertLessEqual(float(np.max(curve["positive_load"])), 1.0)
        self.assertAlmostEqual(float(np.max(curve["positive_load"])), 1.0, places=6)

    def test_common_normalization_preserves_sign_and_relative_peak_size(self) -> None:
        time_s = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0])
        load = np.asarray([0.0, 20.0, 10.0, -40.0, -5.0])
        curve = cumulative_load_curve(time_s, load, normalize=True)
        self.assertAlmostEqual(float(curve["positive_load"][0]), 0.5, places=6)
        self.assertAlmostEqual(float(curve["negative_load"][0]), -1.0, places=6)


if __name__ == "__main__":
    unittest.main()
