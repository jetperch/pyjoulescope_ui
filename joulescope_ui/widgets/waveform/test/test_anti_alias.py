# Copyright 2026 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Test the waveform anti-aliasing filter.
"""

import unittest
import numpy as np
from joulescope_ui.widgets.waveform import anti_alias
from joulescope_ui.widgets.waveform.anti_alias import OVERSAMPLE as N
from joulescope_ui import time64


_FS_HIGH = 1e15  # samples per pixel always high for these tests


def _summary(samples, bins):
    """Reduce samples into equal-count summary bins."""
    s = np.asarray(samples, dtype=np.float64).reshape((bins, -1))
    return {
        'x': np.arange(bins, dtype=np.int64) * 1000,
        'avg': np.mean(s, axis=1),
        'std': np.std(s, axis=1),
        'min': np.min(s, axis=1),
        'max': np.max(s, axis=1),
    }


def _sub_bins(avg):
    """Construct sub-bin data from per-sub-bin averages."""
    avg = np.asarray(avg, dtype=np.float64)
    return {
        'x': np.arange(len(avg), dtype=np.int64) * 1000,
        'avg': avg,
        'std': np.zeros(len(avg)),
        'min': avg.copy(),
        'max': avg.copy(),
    }


class TestKernel(unittest.TestCase):

    def test_unit_sum(self):
        self.assertAlmostEqual(1.0, np.sum(anti_alias.kernel()), places=14)

    def test_symmetric(self):
        g = anti_alias.kernel()
        np.testing.assert_allclose(g, g[::-1], rtol=0, atol=1e-16)

    def test_polyphase_sums(self):
        for n in [1, 2, 3, 4, 8]:
            for sigma in [0.25, 0.5, 1.0, 1.5]:
                g = anti_alias.kernel(n, sigma)
                for phase in range(n):
                    self.assertAlmostEqual(1.0 / n, np.sum(g[phase::n]), places=14,
                                           msg=f'n={n} sigma={sigma} phase={phase}')


class TestRequestRange(unittest.TestCase):

    def test_pad_both(self):
        pad = anti_alias.PAD_PIXELS
        start, end, length, pixels = anti_alias.request_range(
            [10_000, 20_000], [0, 100_000], 100, _FS_HIGH)
        self.assertEqual(100 + 2 * pad, pixels)
        self.assertEqual(10_000 - 100 * pad, start)
        self.assertEqual(20_000 + 100 * pad, end)
        self.assertEqual(pixels * N, length)

    def test_clamp_to_extent(self):
        start, end, length, pixels = anti_alias.request_range(
            [10_000, 20_000], [9_850, 20_000], 100, _FS_HIGH)
        self.assertEqual(101, pixels)
        self.assertEqual(9_900, start)
        self.assertEqual(20_000, end)
        self.assertEqual(101 * N, length)

    def test_length_limit(self):
        x = [0, time64.SECOND]
        _, _, length, pixels = anti_alias.request_range(x, x, 3000, _FS_HIGH)
        self.assertEqual(3000, pixels)
        self.assertLessEqual(length, anti_alias.REQUEST_LENGTH_MAX)
        self.assertEqual(0, length % pixels)
        _, _, length, pixels = anti_alias.request_range(x, x, 9000, _FS_HIGH)
        self.assertEqual(pixels, length)  # oversample >= 1

    def test_degenerate(self):
        self.assertIsNone(anti_alias.request_range([5, 5], [0, 10], 0, _FS_HIGH))
        self.assertIsNone(anti_alias.request_range([5, 5], [0, 10], 10, _FS_HIGH))
        self.assertIsNone(anti_alias.request_range([0, 10], [0, 10], 10, None))
        self.assertIsNone(anti_alias.request_range([0, 10], [0, 10], 10, 0))

    def _oversample(self, samples_per_pixel, width=100):
        fs = 1_000_000
        x1 = int(round(width * samples_per_pixel * time64.SECOND / fs))
        req = anti_alias.request_range([0, x1], [0, x1], width, fs)
        return None if req is None else req[2] // req[3]

    def test_zoomed_in(self):
        """No anti-aliasing at or below one sample per pixel, or without summaries."""
        for spp in [0.01, 0.5, 1.0, 1.5, 2.0, 2.4]:
            self.assertIsNone(self._oversample(spp), msg=f'spp={spp}')

    def test_oversample_keeps_summary(self):
        """Oversampling never drops below SUB_BIN_SAMPLES_MIN samples per sub-bin."""
        for spp, expect in [(2.51, 1), (4.9, 1), (5.01, 2), (7.51, 3), (10.01, 4), (1000, 4)]:
            n = self._oversample(spp)
            self.assertEqual(expect, n, msg=f'spp={spp}')
            self.assertGreaterEqual(spp / n, anti_alias.SUB_BIN_SAMPLES_MIN)


class TestTrim(unittest.TestCase):

    def test_samples(self):
        d = {'x': np.arange(10, dtype=np.int64) * 10, 'avg': np.arange(10.0), 'std': None,
             'min': None, 'max': None, 'time_range_utc': {'start': 0}}
        t = anti_alias.trim(d, (20, 50))
        np.testing.assert_array_equal([20, 30, 40, 50], t['x'])
        np.testing.assert_array_equal([2, 3, 4, 5], t['avg'])
        self.assertIsNone(t['std'])
        self.assertEqual({'start': 0}, t['time_range_utc'])


class TestDecimate(unittest.TestCase):

    def test_too_short(self):
        self.assertIsNone(anti_alias.decimate(_sub_bins(np.zeros(4)), 10))
        self.assertIsNone(anti_alias.decimate(_sub_bins(np.zeros(4)), 0))

    def test_stats_match_direct_reduction(self):
        rng = np.random.default_rng(1)
        pixels, m = 56, 8
        samples = rng.normal(size=pixels * N * m)
        d = anti_alias.decimate(_summary(samples, pixels * N), pixels)
        ref = _summary(samples, pixels)
        for key in ['avg', 'std', 'min', 'max']:
            np.testing.assert_allclose(d[key], ref[key], rtol=1e-12, atol=1e-12, err_msg=key)
        self.assertEqual(pixels, len(d['x']))
        self.assertEqual(pixels, len(d['avg_aa']))
        self.assertTrue(np.all(np.diff(d['x']) > 0))

    def test_extra_entries(self):
        """Sources return more entries than requested: drop the oldest remainder."""
        pixels = 50
        s = np.arange(pixels * N + 7, dtype=np.float64)
        d = anti_alias.decimate(_sub_bins(s), pixels)
        self.assertEqual((pixels * N + 7) // N, len(d['avg']))
        self.assertEqual(np.mean(s[-N:]), d['avg'][-1])
        s = np.arange(pixels * 6, dtype=np.float64)  # 6 per pixel
        d = anti_alias.decimate(_sub_bins(s), pixels)
        self.assertEqual(pixels, len(d['avg']))
        np.testing.assert_allclose(d['avg'], np.mean(s.reshape((pixels, 6)), axis=1))

    def test_trim_to_x_range(self):
        pixels = 20
        d = anti_alias.decimate(_sub_bins(np.zeros(pixels * N)), pixels)
        x = d['x']
        d = anti_alias.decimate(_sub_bins(np.zeros(pixels * N)), pixels, (x[3], x[16]))
        np.testing.assert_array_equal(x[3:17], d['x'])
        self.assertEqual(14, len(d['avg_aa']))

    def test_mean_preserving(self):
        rng = np.random.default_rng(2)
        pixels = 100
        margin = 3 * anti_alias.PAD_PIXELS * N
        for offset in range(N):  # every sub-pixel phase
            s = np.zeros(pixels * N)
            s[margin + offset:-margin] = rng.normal(size=pixels * N - 2 * margin - offset)
            d = anti_alias.decimate(_sub_bins(s), pixels)
            self.assertAlmostEqual(np.sum(d['avg']), np.sum(d['avg_aa']), places=12,
                                   msg=f'offset={offset}')
            self.assertAlmostEqual(np.sum(s) / N, np.sum(d['avg_aa']), places=12)

    def test_constant(self):
        pixels = 40
        s = np.full(pixels * N, 2.5)
        d = anti_alias.decimate(_sub_bins(s), pixels)
        np.testing.assert_allclose(d['avg_aa'], 2.5, rtol=1e-14)

    def test_constant_with_nan_gap(self):
        pixels = 40
        s = np.full(pixels * N, -1.25)
        s[20 * N + 1:25 * N + 2] = np.nan
        d = anti_alias.decimate(_sub_bins(s), pixels)
        nan_idx = np.isnan(d['avg'])
        np.testing.assert_array_equal(nan_idx, np.isnan(d['avg_aa']))
        self.assertTrue(np.any(nan_idx))
        np.testing.assert_allclose(d['avg_aa'][~nan_idx], -1.25, rtol=1e-14)

    def test_pulse_sweep(self):
        """A half-pixel pulse sliding across pixels: energy constant, ripple reduced."""
        pixels, m = 32, 16  # m samples per sub-bin
        spp = N * m  # samples per pixel
        pulse = spp // 2
        peak_aa, peak_box, sums = [], [], []
        for shift in range(spp):
            samples = np.zeros(pixels * spp)
            k = (pixels // 2) * spp + shift
            samples[k:k + pulse] = 1.0
            d = anti_alias.decimate(_summary(samples, pixels * N), pixels)
            peak_aa.append(np.max(d['avg_aa']))
            peak_box.append(np.max(d['avg']))
            sums.append(np.sum(d['avg_aa']))
            np.testing.assert_allclose(d['max'][d['max'] > 0], 1.0)  # min/max unaffected
        np.testing.assert_allclose(sums, 0.5, rtol=1e-12)
        ripple_box = 1 - min(peak_box) / max(peak_box)
        ripple_aa = 1 - min(peak_aa) / max(peak_aa)
        self.assertGreater(ripple_box, 0.45)
        self.assertLess(ripple_aa, 0.15)


if __name__ == '__main__':
    unittest.main()
