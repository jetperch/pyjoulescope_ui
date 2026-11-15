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

"""Test the Qt-free efficiency engine."""

import math
import unittest
import numpy as np
from joulescope_ui import time64
from joulescope_ui.efficiency_engine import SignalIntegrator, Curve, EfficiencyEngine


T0 = 260_000_000  # realistic time64 UTC seconds (2026), integer
T0_64 = T0 * time64.SECOND

# All test times are seconds relative to T0, the engine reference.


def constant(value):
    return lambda t: value * t


def square(lo, hi, freq, duty=0.5, phase=0.0):
    """Get the integral function of a square wave."""
    def fn(t):
        t = np.asarray(t, dtype=np.float64) + phase
        c = np.floor(t * freq)
        f = t * freq - c
        return lo * t + (hi - lo) * (c * duty + np.minimum(f, duty)) / freq
    return fn


def steps(levels, step_duration, t_step0=0.0):
    """Get the integral function of a staircase.

    The first level extends back before t_step0 + step_duration.
    """
    levels = np.asarray(levels, dtype=np.float64)
    cum = np.concatenate([[0.0], np.cumsum(levels) * step_duration])

    def fn(t):
        u = (np.asarray(t, dtype=np.float64) - t_step0) / step_duration
        k = np.clip(np.floor(u).astype(np.int64), 0, len(levels) - 1)
        return cum[k] + (u - k) * step_duration * levels[k]
    return fn


class Stream:
    """Generate SIGNAL_STREAM_SOURCE messages for one instrument signal.

    Each sample is the exact average of the true signal over its UTC
    interval, so integrals over any UTC interval are exact.
    """

    def __init__(self, integral_fn, counter_rate, decimate, chunk, t_start=0.0123,
                 origin_offset=1000):
        self.fn = integral_fn
        self.rate = float(counter_rate)
        self.dec = int(decimate)
        self.chunk = int(chunk)
        self.offset_time = T0_64 + int(round(t_start * time64.SECOND))
        self.t_start = (self.offset_time - T0_64) / time64.SECOND
        self.origin_offset = origin_offset
        self.k = 0  # next decimated sample

    @property
    def t_next(self):
        return self.t_start + self.k * self.dec / self.rate

    def message(self, k=None, n=None):
        k = self.k if k is None else k
        n = self.chunk if n is None else n
        dt = self.dec / self.rate
        edges = self.t_start + (k + np.arange(n + 1)) * dt
        e = self.fn(edges)
        data = (np.diff(e) / dt).astype(np.float32)
        return {
            'sample_id': (self.origin_offset + k * self.dec) // self.dec,
            'sample_freq': self.rate / self.dec,
            'origin_sample_id': self.origin_offset + k * self.dec,
            'origin_decimate_factor': self.dec,
            'data': data,
            'dtype': 'f32',
            'time_map': {
                'offset_counter': self.origin_offset,
                'offset_time': self.offset_time,
                'counter_rate': self.rate,
            },
        }

    def next(self):
        msg = self.message()
        self.k += self.chunk
        return msg

    def skip(self):
        self.k += self.chunk

    def until(self, t):
        msgs = []
        while self.t_next < t:
            msgs.append(self.next())
        return msgs


def js220(fn, **kwargs):
    # 2 MHz counter, decimate 2 -> 1 MSPS; clock 12 ppm slow
    return Stream(fn, 2_000_000 * (1 - 12e-6), 2, 20_000, **kwargs)


def js320(fn, **kwargs):
    # 16 MHz counter, decimate 16 -> 1 MSPS; clock 3 ppm fast; different chunking
    return Stream(fn, 16_000_000 * (1 + 3e-6), 16, 25_000, t_start=0.0371, **kwargs)


def feed(engine, streams, t_end, step=0.05):
    """Interleave streams like the UI does, and collect windows."""
    windows = []
    t = min(s.t_next for _, _, s in streams)
    while t < t_end:
        t += step
        for instrument, signal, s in streams:
            for msg in s.until(t):
                engine.push(instrument, signal, msg)
        windows.extend(engine.process())
    return windows


class TestSignalIntegrator(unittest.TestCase):

    def test_constant(self):
        s = js220(constant(2.0))
        x = SignalIntegrator(T0_64)
        for msg in s.until(1.0):
            x.push(msg)
        for t0, t1 in [(0.1, 0.2), (0.0123, 0.9), (0.13333, 0.13334)]:
            self.assertAlmostEqual(2.0 * (t1 - t0), x.integral(t0, t1), delta=1e-9)

    def test_fractional_edges(self):
        fn = square(1.0, 3.0, 1234.567)
        s = js320(fn)
        x = SignalIntegrator(T0_64)
        for msg in s.until(0.5):
            x.push(msg)
        rng = np.random.default_rng(1)
        for _ in range(50):
            t0, t1 = np.sort(rng.uniform(0.04, 0.48, 2))
            expect = fn(t1) - fn(t0)
            self.assertAlmostEqual(expect, x.integral(t0, t1), delta=1e-7)

    def test_out_of_range(self):
        s = js220(constant(1.0))
        x = SignalIntegrator(T0_64)
        self.assertIsNone(x.integral(0.0, 1))
        for msg in s.until(0.2):
            x.push(msg)
        self.assertIsNone(x.integral(0.0, 0.1))  # before data
        self.assertIsNone(x.integral(0.1, 1.0))  # after data

    def test_gap(self):
        s = js220(constant(1.0))
        x = SignalIntegrator(T0_64)
        for msg in s.until(0.1):
            x.push(msg)
        t_gap0 = s.t_next
        s.skip()
        t_gap1 = s.t_next
        for msg in s.until(0.3):
            x.push(msg)
        self.assertIsNone(x.integral(t_gap0 - 0.01, t_gap1 + 0.01))
        self.assertIsNone(x.integral(t_gap0 + 0.001, t_gap0 + 0.002))
        self.assertAlmostEqual(0.01, x.integral(t_gap1 + 0.01, t_gap1 + 0.02), delta=1e-9)
        self.assertAlmostEqual(0.01, x.integral(t_gap0 - 0.02, t_gap0 - 0.01), delta=1e-9)

    def test_history_bounded(self):
        s = js220(constant(1.0))
        x = SignalIntegrator(T0_64, history=2.0)
        for msg in s.until(20.0):
            x.push(msg)
        self.assertLess(x.t_end - x.t_start, 2.1)
        self.assertLess(len(x._chunks), 2.1 * 1e6 / 20_000 + 2)
        self.assertAlmostEqual(1.0, x.integral(x.t_end - 1.0, x.t_end), delta=1e-9)

    def test_unsupported_dtype(self):
        msg = js220(constant(1.0)).next()
        msg['dtype'] = 'u1'
        with self.assertRaises(ValueError):
            SignalIntegrator(T0_64).push(msg)


class TestCurve(unittest.TestCase):

    def test_bins(self):
        c = Curve(bins_per_decade=10)
        self.assertTrue(c.add(0.0105, 1.0, 0.9, 0.5))
        self.assertTrue(c.add(0.0110, 3.0, 2.4, 0.5))
        self.assertTrue(c.add(0.1, 1.0, 0.95, 1.0))
        self.assertFalse(c.add(0.0, 1.0, 0.9, 0.5))
        self.assertFalse(c.add(-1.0, 1.0, 0.9, 0.5))
        self.assertFalse(c.add(1.0, 0.0, 0.9, 0.5))
        bins = c.bins()
        self.assertEqual(2, len(bins))
        b = bins[0]
        self.assertEqual(2, b['count'])
        self.assertAlmostEqual(3.3 / 4.0, b['efficiency'])  # energy weighted
        self.assertAlmostEqual(0.8, b['efficiency_min'])
        self.assertAlmostEqual(0.9, b['efficiency_max'])
        self.assertAlmostEqual(0.01075, b['x'])
        self.assertLessEqual(b['x_min'], b['x'])
        self.assertLess(b['x'], b['x_max'])
        self.assertAlmostEqual(0.95, bins[1]['efficiency'])
        c.clear()
        self.assertEqual([], c.bins())


class TestEfficiencyEngine(unittest.TestCase):

    def _streams(self, fn_in, fn_out, current_out=None):
        streams = [('in', 'p', js220(fn_in)), ('out', 'p', js320(fn_out))]
        if current_out is not None:
            streams.append(('out', 'i', js320(current_out)))
        return streams

    def test_constant_efficiency(self):
        e = EfficiencyEngine(period=0.5)
        windows = feed(e, self._streams(constant(1.0), constant(0.85)), 5.0)
        self.assertGreaterEqual(len(windows), 8)
        for w in windows:
            self.assertTrue(w['valid'])
            self.assertAlmostEqual(0.85, w['efficiency'], delta=1e-7)
            self.assertAlmostEqual(1.0, w['p_in'], delta=1e-7)
            self.assertAlmostEqual(0.15, w['p_loss'], delta=1e-7)
            self.assertIsNone(w['i_out'])
        self.assertAlmostEqual(0.85, e.efficiency_cumulative, delta=1e-7)

    def test_grid_alignment(self):
        e = EfficiencyEngine(period=0.1)
        windows = feed(e, self._streams(constant(1.0), constant(0.9)), 2.0)
        for w0, w1 in zip(windows[:-1], windows[1:]):
            self.assertEqual(w0['t1'], w1['t0'])
        for w in windows:
            k = w['t0'] / 0.1
            self.assertAlmostEqual(k, round(k), delta=1e-6)
        # first window starts after both instruments have data
        self.assertGreaterEqual(windows[0]['t0'], 0.0371)

    def test_square_wave_load_aligned(self):
        # The load changes many times within each window.  Windows integrate
        # both instruments over the same UTC interval, so the ratio is exact.
        p_in = square(0.1, 1.0, 37.3)
        p_out = lambda t: 0.8 * p_in(t)
        e = EfficiencyEngine(period=0.05)
        windows = feed(e, self._streams(p_in, p_out), 3.0)
        self.assertGreater(len(windows), 50)
        for w in windows:
            self.assertAlmostEqual(0.8, w['efficiency'], delta=1e-6)

    def test_efficiency_with_current(self):
        e = EfficiencyEngine(period=0.25)
        windows = feed(e, self._streams(constant(2.0), constant(1.5), constant(0.45)), 2.0)
        for w in windows:
            self.assertAlmostEqual(0.75, w['efficiency'], delta=1e-7)
            self.assertAlmostEqual(0.45, w['i_out'], delta=1e-7)
            self.assertIsNone(w['v_out'])

    def test_gap_invalidates_window(self):
        e = EfficiencyEngine(period=0.1)
        streams = self._streams(constant(1.0), constant(0.9))
        windows = feed(e, streams, 1.0)
        out = streams[1][2]
        t_gap0 = out.t_next
        out.skip()
        windows += feed(e, streams, 2.0)
        invalid = [w for w in windows if not w['valid']]
        self.assertGreaterEqual(len(invalid), 1)
        self.assertLessEqual(len(invalid), 2)
        for w in invalid:
            self.assertLess(w['t0'], t_gap0 + 0.025 + 1e-6)
            self.assertGreater(w['t1'], t_gap0)
        for w in windows:
            if w['valid']:
                self.assertAlmostEqual(0.9, w['efficiency'], delta=1e-7)
        self.assertEqual(len(invalid), e.totals['invalid'])
        self.assertAlmostEqual(0.9, e.efficiency_cumulative, delta=1e-7)

    def test_missing_instrument(self):
        e = EfficiencyEngine(period=0.5, history=2.0)
        s_in, s_out = js220(constant(1.0)), js320(constant(0.9))
        streams = [('in', 'p', s_in), ('out', 'p', s_out)]
        windows = feed(e, streams, 3.0)
        n_before = len(windows)
        # output instrument stops for 10 s
        for msg in s_in.until(13.0):
            e.push('in', 'p', msg)
            windows.extend(e.process())
        self.assertEqual(n_before, len(windows))  # stalls, no windows
        s_out.k = int(round((13.0 - s_out.t_start) * s_out.rate / s_out.dec))
        windows += feed(e, streams, 16.0)
        skipped = [w for w in windows[n_before:] if not w['valid']]
        self.assertEqual(1, len(skipped))
        self.assertLess(skipped[0]['t0'], 4.0)
        self.assertGreater(skipped[0]['t1'], 12.9)
        valid_after = [w for w in windows[n_before:] if w['valid']]
        self.assertGreaterEqual(len(valid_after), 4)
        for w0, w1 in zip(windows[:-1], windows[1:]):
            self.assertAlmostEqual(w0['t1'], w1['t0'], delta=1e-9)
        # integrator memory stays bounded while waiting
        self.assertLess(len(e.integrator('in', 'p')._chunks), 200)

    def test_configure_does_not_repeat_windows(self):
        e = EfficiencyEngine(period=0.1)
        streams = self._streams(constant(1.0), constant(0.9))
        windows = feed(e, streams, 1.0)
        e.configure(steady_threshold=0.1)
        windows += feed(e, streams, 2.0)
        e.configure(period=0.25)
        windows += feed(e, streams, 3.0)
        for w0, w1 in zip(windows[:-1], windows[1:]):
            self.assertLessEqual(w0['t1'], w1['t0'] + 1e-9)
            self.assertLess(w1['t0'] - w0['t1'], 0.25 + 1e-6)
        self.assertAlmostEqual(0.25, windows[-1]['t1'] - windows[-1]['t0'], delta=1e-9)

    def test_clear(self):
        e = EfficiencyEngine(period=0.1)
        streams = self._streams(constant(1.0), constant(0.9), constant(0.3))
        feed(e, streams, 1.0)
        self.assertGreater(len(e.curve.bins()), 0)
        e.clear()
        self.assertIsNone(e.efficiency_cumulative)
        self.assertEqual([], e.curve.bins())
        windows = feed(e, streams, 1.5)
        self.assertGreater(len(windows), 0)
        self.assertAlmostEqual(0.9, e.efficiency_cumulative, delta=1e-7)

    def test_curve_staircase(self):
        # load steps through a converter with efficiency that depends on load
        currents = [0.001, 0.003, 0.01, 0.03, 0.1]
        eta = [0.6, 0.75, 0.85, 0.9, 0.88]
        v_out = 3.3
        step = 1.0
        p_out = [i * v_out for i in currents]
        p_in = [p / n for p, n in zip(p_out, eta)]
        e = EfficiencyEngine(period=0.1, bins_per_decade=10)
        # steps land mid-window, so windows spanning a step are not steady
        args = (step, 0.05)
        streams = self._streams(steps(p_in, *args), steps(p_out, *args), steps(currents, *args))
        feed(e, streams, step * len(currents) - 0.05)
        bins = e.curve.bins()
        self.assertEqual(len(currents), len(bins))
        for b, i, n in zip(bins, currents, eta):
            self.assertAlmostEqual(i, b['x'], delta=i * 1e-6)
            self.assertAlmostEqual(n, b['efficiency'], delta=1e-6)
            self.assertGreaterEqual(b['count'], 7)
        # windows spanning a step are not steady
        self.assertGreaterEqual(e.rejected, len(currents) - 1)

    def test_curve_power_axis(self):
        e = EfficiencyEngine(period=0.1, curve_x='power')
        feed(e, self._streams(constant(1.0), constant(0.9)), 1.0)
        bins = e.curve.bins()
        self.assertEqual(1, len(bins))
        self.assertAlmostEqual(0.9, bins[0]['x'], delta=1e-7)

    def test_curve_rejects_unsteady(self):
        p_in = square(0.1, 1.0, 3.0)
        e = EfficiencyEngine(period=0.5)
        windows = feed(e, self._streams(p_in, lambda t: 0.8 * p_in(t), constant(0.1)), 3.0)
        self.assertGreater(len(windows), 4)
        self.assertEqual([], e.curve.bins())
        self.assertGreaterEqual(e.rejected, 4)

    def test_curve_period(self):
        # A short curve window captures steady load levels that the display
        # window spans.
        currents = [0.01, 0.1] * 10
        p_out = [3.3 * i for i in currents]
        p_in = [p / 0.9 for p in p_out]
        e = EfficiencyEngine(period=0.5, curve_period=0.02)
        args = (0.2, 0.01)
        streams = self._streams(steps(p_in, *args), steps(p_out, *args), steps(currents, *args))
        windows = feed(e, streams, 3.9)
        bins = e.curve.bins()
        self.assertEqual(2, len(bins))
        for b in bins:
            self.assertAlmostEqual(0.9, b['efficiency'], delta=1e-6)
            self.assertGreater(b['count'], 50)
        self.assertGreaterEqual(e.rejected, 15)
        for w in windows:
            self.assertAlmostEqual(0.5, w['t1'] - w['t0'], delta=1e-9)

    def test_invalid_config(self):
        with self.assertRaises(KeyError):
            EfficiencyEngine(window=1)
        with self.assertRaises(ValueError):
            EfficiencyEngine(period=0)
        with self.assertRaises(ValueError):
            EfficiencyEngine(curve_x='voltage')
        e = EfficiencyEngine()
        with self.assertRaises(ValueError):
            e.push('mid', 'p', {})
        with self.assertRaises(ValueError):
            e.push('in', 'q', {})


if __name__ == '__main__':
    unittest.main()
