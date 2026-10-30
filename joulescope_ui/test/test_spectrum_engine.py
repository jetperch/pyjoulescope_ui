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
Test joulescope_ui.spectrum_engine
"""

import unittest
import numpy as np
from joulescope_ui import spectrum_engine as se


FS = 1000.0


def _tone(f, amplitude_rms, n, fs=FS, phase=0.3):
    t = np.arange(n) / fs
    return np.sqrt(2) * amplitude_rms * np.sin(2 * np.pi * f * t + phase)


class TestWindows(unittest.TestCase):

    def test_enbw(self):
        expect = {
            'rectangular': 1.0,
            'hann': 1.5,
            'hamming': 1.363,
            'blackman': 1.727,
            'blackman_harris': 2.004,
            'flattop': 3.77,
        }
        for name, value in expect.items():
            self.assertAlmostEqual(value, se.enbw(se.window(name, 4096)), delta=0.01, msg=name)

    def test_unpack(self):
        np.testing.assert_equal([1, 0, 1, 1, 0, 0, 0, 0], se.unpack(np.array([0x0d], dtype=np.uint8), 'u1'))
        np.testing.assert_equal([0x3, 0xa, 0xf], se.unpack(np.array([0xa3, 0x5f], dtype=np.uint8), 'u4', 3))
        x = np.arange(4, dtype=np.float32)
        self.assertIs(x, se.unpack(x, 'f32'))
        with self.assertRaises(ValueError):
            se.unpack(x, 'c64')


class TestEngine(unittest.TestCase):

    def _engine(self, **kwargs):
        cfg = {'fft_length': 1024, 'average_mode': 'cumulative'}
        cfg.update(kwargs)
        return se.SpectrumEngine(cfg)

    def test_tone_bin_center_amplitude(self):
        e = self._engine(window='hann')
        f = 125 * FS / 1024
        e.process(0, FS, _tone(f, 0.5, 8192))
        db = se.to_db(e.average)
        k = int(np.argmax(db))
        self.assertEqual(125, k)
        self.assertAlmostEqual(20 * np.log10(0.5), db[k], delta=0.01)

    def test_tone_between_bins_flattop(self):
        e = self._engine(window='flattop')
        f = 100.5 * FS / 1024
        e.process(0, FS, _tone(f, 0.25, 16384))
        db = se.to_db(e.average)
        self.assertAlmostEqual(20 * np.log10(0.25), np.max(db), delta=0.1)
        peaks = se.find_peaks(db, 1, x=e.frequencies())
        self.assertAlmostEqual(f, peaks[0][0], delta=FS / 1024)

    def test_white_noise_psd_parseval(self):
        rng = np.random.default_rng(1)
        sigma = 0.1
        x = rng.normal(0, sigma, 1024 * 256)
        for name in ['rectangular', 'hann', 'blackman_harris', 'flattop']:
            e = self._engine(window=name, scaling='psd', dc_remove=False)
            e.process(0, FS, x)
            expect = sigma ** 2 / (FS / 2)
            measured = np.mean(e.average[1:-1])
            self.assertAlmostEqual(1.0, measured / expect, delta=0.03, msg=name)
            # Parseval: integrated PSD equals the variance
            total = np.sum(e.average) * (FS / 1024)
            self.assertAlmostEqual(1.0, total / sigma ** 2, delta=0.03, msg=name)

    def test_overlap_segment_count(self):
        for overlap, expect in [(0.0, 8), (0.5, 15), (0.75, 29)]:
            e = self._engine(overlap=overlap)
            e.process(0, FS, np.zeros(1024 * 8))
            self.assertEqual(expect, e.count, msg=str(overlap))

    def test_chunking_invariance(self):
        rng = np.random.default_rng(2)
        x = rng.normal(0, 1, 50_000) + _tone(77.0, 1.0, 50_000)
        for decimate in [1, 4]:
            e1 = self._engine(overlap=0.5, decimate=decimate)
            e1.process(0, FS, x)
            e2 = self._engine(overlap=0.5, decimate=decimate)
            idx = 0
            for size in rng.integers(1, 3000, 1000):
                if idx >= len(x):
                    break
                e2.process(idx, FS, x[idx:idx + size])
                idx += size
            self.assertEqual(e1.count, e2.count)
            np.testing.assert_allclose(e1.average, e2.average, rtol=1e-9)
            np.testing.assert_allclose(e1.max, e2.max, rtol=1e-9)

    def test_gap_resets_segment(self):
        e = self._engine(overlap=0.0)
        e.process(0, FS, np.zeros(1000))
        e.process(2000, FS, np.zeros(1000))  # gap: 1000 + 1000 never form a segment
        self.assertEqual(0, e.count)
        e.process(3000, FS, np.zeros(24))
        self.assertEqual(1, e.count)

    def test_rate_change_clears(self):
        e = self._engine(overlap=0.0)
        e.process(0, FS, np.ones(2048))
        self.assertEqual(2, e.count)
        e.process(2048, 2 * FS, np.ones(1024))
        self.assertEqual(1, e.count)
        self.assertEqual(2 * FS, e.fs)

    def test_dc_remove(self):
        x = 5.0 + _tone(50.0, 0.001, 4096)
        e = self._engine(dc_remove=True)
        e.process(0, FS, x)
        self.assertLess(se.to_db(e.average)[0], -60)
        e = self._engine(dc_remove=False)
        e.process(0, FS, x)
        self.assertAlmostEqual(20 * np.log10(5.0), se.to_db(e.average)[0], delta=0.01)

    def test_max_min_live(self):
        e = self._engine(overlap=0.0, dc_remove=False)
        x = np.concatenate([np.full(1024, 1.0), np.full(1024, 3.0)])
        e.process(0, FS, x)
        db0 = se.to_db(np.array([e.min[0], e.max[0], e.live[0]]))
        np.testing.assert_allclose([0.0, 20 * np.log10(3), 20 * np.log10(3)], db0, atol=1e-9)

    def test_exponential_average(self):
        x = np.arange(20, dtype=np.float64).reshape((20, 1))
        a = se.average_update(None, 0, x, 4)
        # reference: sequential
        r, k = None, 0
        for v in x:
            k += 1
            alpha = 1.0 / min(k, 4)
            r = v.copy() if r is None else r + alpha * (v - r)
        np.testing.assert_allclose(r, a)
        # batched in pieces matches
        b = se.average_update(None, 0, x[:7], 4)
        b = se.average_update(b, 7, x[7:], 4)
        np.testing.assert_allclose(r, b)

    def test_cumulative_average(self):
        x = np.random.default_rng(3).normal(size=(30, 5))
        a = se.average_update(None, 0, x[:11], None)
        a = se.average_update(a, 11, x[11:], None)
        np.testing.assert_allclose(np.mean(x, axis=0), a)

    def test_average_off(self):
        e = self._engine(average_mode='off')
        e.process(0, FS, np.ones(4096))
        self.assertIsNone(e.average)
        self.assertIsNotNone(e.live)

    def test_rows(self):
        e = self._engine(overlap=0.0, row_period=1024 * 2 / FS, detector='average', dc_remove=False)
        e.process(0, FS, np.full(1024 * 7, 2.0))
        rows = e.rows_pop()
        # segment end ids 1024..7168, rows of 2048 samples: rows 0..2 complete
        self.assertEqual(3, len(rows))
        self.assertAlmostEqual(20 * np.log10(2.0), rows[1]['db'][0], places=4)
        self.assertEqual(np.float32, rows[0]['db'].dtype)
        self.assertEqual([], e.rows_pop())

    def test_rows_max_detector(self):
        e = self._engine(overlap=0.0, row_period=1024 * 4 / FS, detector='max', dc_remove=False)
        x = np.concatenate([np.full(1024, 1.0), np.full(1024, 4.0), np.full(1024 * 3, 1.0)])
        e.process(0, FS, x)
        rows = e.rows_pop()
        self.assertEqual(1, len(rows))
        self.assertAlmostEqual(20 * np.log10(4.0), rows[0]['db'][0], places=4)

    def test_rows_gap_flag(self):
        e = self._engine(overlap=0.0, row_period=1024 / FS)
        e.process(0, FS, np.ones(2048))
        e.process(10000, FS, np.ones(4096))
        rows = e.rows_pop()
        self.assertEqual([False, False, True], [r['gap'] for r in rows][:3])

    def test_invalid_config(self):
        for cfg in [{'fft_length': 3}, {'scaling': 'x'}, {'average_mode': 'x'}, {'detector': 'x'},
                    {'decimate': 3}]:
            with self.assertRaises(ValueError):
                se.SpectrumEngine(cfg)

    def test_rbw(self):
        e = self._engine(window='hann', decimate=4)
        e.process(0, FS, np.zeros(16))
        self.assertAlmostEqual(FS / 4, e.fs)
        self.assertAlmostEqual(1.5 * FS / 4 / 1024, e.rbw, delta=0.001)


class TestDecimator(unittest.TestCase):

    def _response_db(self, factor, f, n=1 << 16, fs=FS):
        d = se.Decimator(factor)
        y = d.process(np.sin(2 * np.pi * f * np.arange(n) / fs))
        y = y[len(y) // 4:]  # skip filter transient
        return 20 * np.log10(np.sqrt(2) * np.std(y))

    def test_passband(self):
        for factor in [2, 8]:
            band = DecimateBand(factor)
            for f in np.linspace(1.0, band, 9):
                self.assertAlmostEqual(0.0, self._response_db(factor, f), delta=0.01,
                                       msg=f'{factor} {f}')

    def test_alias_rejection(self):
        for factor in [2, 4]:
            nyquist = FS / 2 / factor
            # frequencies that alias into the retained band
            for f in np.linspace(2 * nyquist - nyquist * se.DECIMATE_ROLLOFF, FS / 2 - 1, 7):
                self.assertLess(self._response_db(factor, f), -80, msg=f'{factor} {f}')

    def test_block_invariance(self):
        x = np.random.default_rng(4).normal(size=10_000)
        y1 = se.Decimator(4).process(x)
        d = se.Decimator(4)
        y2 = np.concatenate([d.process(x[i:i + 333]) for i in range(0, len(x), 333)])
        np.testing.assert_allclose(y1, y2[:len(y1)], atol=1e-12)
        self.assertLessEqual(abs(len(y1) - len(y2)), 2)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            se.Decimator(6)


def DecimateBand(factor):
    return FS / 2 / factor * se.DECIMATE_ROLLOFF


class TestPeaks(unittest.TestCase):

    def test_order_threshold_separation(self):
        y = np.zeros(100)
        y[10], y[12], y[50], y[80] = 5, 6, 9, 1
        p = se.find_peaks(y, 10, threshold=2, separation=5)
        self.assertEqual([50, 12], [k[2] for k in p])

    def test_excursion(self):
        y = np.zeros(100)
        y[20:27] = [20, 18, 16, 17, 12, 8, 4]  # tall peak, skirt bump at 23
        y[60] = 5                               # small isolated peak
        p = se.find_peaks(y, 10, separation=3, excursion=3)
        self.assertEqual([20, 60], [k[2] for k in p])

    def test_sliding(self):
        y = np.random.default_rng(5).normal(size=103)
        for w in [1, 2, 7, 103]:
            expect = [np.max(y[i:i + w]) for i in range(len(y) - w + 1)]
            np.testing.assert_equal(expect, se._sliding(y, w, np.maximum))
            expect = [np.min(y[i:i + w]) for i in range(len(y) - w + 1)]
            np.testing.assert_equal(expect, se._sliding(y, w, np.minimum))

    def test_tone_skirt_does_not_hide_second_tone(self):
        # many local maxima on a strong tone's skirt must not crowd out a real tone
        y = np.full(2000, -100.0)
        y[100:200] = -40 - np.abs(np.arange(100) - 50) * 0.5 + np.tile([0, 1.0], 50)
        y[150] = -10
        y[1500] = -60
        p = se.find_peaks(y, 2, separation=4, excursion=10)
        self.assertEqual([150, 1500], [k[2] for k in p])

    def test_parabolic(self):
        x = np.arange(20, dtype=float)
        y = -(x - 7.3) ** 2
        p = se.find_peaks(y, 1, x=x * 2)
        self.assertAlmostEqual(14.6, p[0][0], places=6)
        self.assertAlmostEqual(0.0, p[0][1], places=6)
        p = se.find_peaks(y, 1, x=x * 2, y_interpolate=False)
        self.assertAlmostEqual(-0.09, p[0][1], places=6)

    def test_empty(self):
        self.assertEqual([], se.find_peaks(np.zeros(2), 3))
        self.assertEqual([], se.find_peaks(np.arange(10), 3))


class TestColumns(unittest.TestCase):

    def test_reduce_dense(self):
        f = np.arange(100, dtype=float)
        y = np.arange(100, dtype=float)
        cmap = se.column_map(f, np.linspace(0, 100, 11))
        np.testing.assert_equal(np.arange(9, 100, 10), se.column_reduce(y, cmap))
        np.testing.assert_equal(np.arange(0, 100, 10), se.column_reduce(y, cmap, np.minimum))

    def test_reduce_sparse(self):
        f = np.arange(10, dtype=float)
        y = np.arange(10, dtype=float) * 10
        cmap = se.column_map(f, np.linspace(2, 4, 9))
        r = se.column_reduce(y, cmap)
        self.assertEqual(8, len(r))
        self.assertTrue(np.all(np.diff(r) >= 0))
        self.assertEqual(20, r[0])
        self.assertEqual(40, r[-1])

    def test_reduce_2d_log(self):
        f = np.arange(1025, dtype=float)
        rows = np.tile(np.arange(1025, dtype=float), (3, 1))
        edges = np.logspace(0, np.log10(1024), 51)
        r = se.column_reduce(rows, se.column_map(f, edges))
        self.assertEqual((3, 50), r.shape)
        self.assertTrue(np.all(np.diff(r[0]) >= 0))
        self.assertLessEqual(r[0, -1], 1024)

    def test_outside(self):
        f = np.arange(10, dtype=float)
        cmap = se.column_map(f, np.linspace(20, 30, 4))
        r = se.column_reduce(np.arange(10.0), cmap)
        np.testing.assert_equal([9, 9, 9], r)


if __name__ == '__main__':
    unittest.main()
