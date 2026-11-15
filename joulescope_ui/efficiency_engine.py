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

"""Qt-free two-instrument efficiency computation.

Each instrument has a free-running sample clock, so the engine integrates
each sample stream over common UTC intervals using the stream time_map.
See docs/plans/efficiency.md for the design.
"""

import bisect
import math
import numpy as np
from joulescope_ui import time64
from joulescope_ui.spectrum_engine import sample_count


INSTRUMENTS = ('in', 'out')
SIGNALS = ('p', 'i', 'v')


class _Chunk:
    __slots__ = ['t_start', 'dt', 'n', 'cumsum', 'offset']

    def __init__(self, t_start, dt, data, offset):
        self.t_start = t_start  # UTC seconds of the first sample
        self.dt = dt            # seconds per sample
        self.n = len(data)
        c = np.empty(self.n + 1, dtype=np.float64)
        c[0] = 0.0
        np.cumsum(data, dtype=np.float64, out=c[1:])
        c *= dt
        self.cumsum = c         # integral from t_start, in units * s
        self.offset = offset    # integral before t_start

    @property
    def t_end(self):
        return self.t_start + self.n * self.dt

    def integral_at(self, t):
        u = (t - self.t_start) / self.dt
        u = min(max(u, 0.0), float(self.n))
        k = min(int(u), self.n - 1)
        c = self.cumsum
        return self.offset + c[k] + (u - k) * (c[k + 1] - c[k])


class SignalIntegrator:
    """Integrate one sample stream over arbitrary UTC intervals.

    Samples are piecewise constant over their sample period, so the
    integral is exact to a fraction of a sample at both interval edges.
    All times are float seconds relative to t_ref, because absolute UTC
    seconds in float64 only resolve about 30 ns.
    """

    def __init__(self, t_ref, history=10.0):
        """Construct a new instance.

        :param t_ref: The time64 reference for all times.
        :param history: The minimum retained duration, in seconds.
        """
        self.t_ref = int(t_ref)
        self.history = float(history)
        self._chunks = []
        self._starts = []
        self._gaps = []        # list of (t0, t1) UTC intervals without data
        self._next_origin = None
        self._total = 0.0

    def clear(self):
        self._chunks.clear()
        self._starts.clear()
        self._gaps.clear()
        self._next_origin = None
        self._total = 0.0

    @property
    def t_start(self):
        """The start of retained data, relative to t_ref, or None."""
        return self._chunks[0].t_start if self._chunks else None

    @property
    def t_end(self):
        """The end of received data, relative to t_ref, or None."""
        return self._chunks[-1].t_end if self._chunks else None

    def push(self, value):
        """Add a signal stream message.

        :param value: The CAPABILITIES.SIGNAL_STREAM_SOURCE !data message.
        """
        data = value['data']
        dtype = value.get('dtype', 'f32')
        if dtype != 'f32':
            raise ValueError(f'unsupported dtype {dtype}')
        n = sample_count(data, dtype)
        if n == 0:
            return
        dec = int(value.get('origin_decimate_factor', 1))
        origin = int(value.get('origin_sample_id', value['sample_id']))
        tm = value['time_map']
        rate = float(tm['counter_rate'])
        t_start = ((tm['offset_time'] - self.t_ref) / time64.SECOND
                   + (origin - tm['offset_counter']) / rate)
        dt = dec / rate
        if self._next_origin is not None and origin != self._next_origin and self._chunks:
            self._gaps.append((self._chunks[-1].t_end, t_start))
        self._next_origin = origin + n * dec
        chunk = _Chunk(t_start, dt, np.asarray(data, dtype=np.float32), self._total)
        self._total += chunk.cumsum[-1]
        self._chunks.append(chunk)
        self._starts.append(t_start)
        self._trim()

    def _trim(self):
        t_min = self.t_end - self.history
        k = 0
        while k < len(self._chunks) - 1 and self._chunks[k].t_end < t_min:
            k += 1
        if k:
            del self._chunks[:k]
            del self._starts[:k]
        t0 = self.t_start
        self._gaps = [g for g in self._gaps if g[1] > t0]

    def _integral_at(self, t):
        k = bisect.bisect_right(self._starts, t) - 1
        return self._chunks[max(k, 0)].integral_at(t)

    def has_gap(self, t0, t1):
        """Check for missing data in [t0, t1)."""
        return any(g0 < t1 and g1 > t0 for g0, g1 in self._gaps)

    def integral(self, t0, t1):
        """Integrate over [t0, t1).

        :return: The integral in units * seconds, or None when the interval
            is not fully covered by contiguous data.
        """
        if not self._chunks or t0 < self.t_start or t1 > self.t_end or self.has_gap(t0, t1):
            return None
        return self._integral_at(t1) - self._integral_at(t0)

    def integrals(self, t):
        """Integrate over each interval between successive times in t.

        :return: The array of len(t) - 1 integrals, or None when not covered.
        """
        t0, t1 = t[0], t[-1]
        if not self._chunks or t0 < self.t_start or t1 > self.t_end or self.has_gap(t0, t1):
            return None
        return np.diff([self._integral_at(x) for x in t])


class Curve:
    """Efficiency vs load, accumulated in log-spaced bins.

    Bins are centered on 10 ** (k / bins_per_decade), so round load values
    such as 10 mA fall in a bin center, not on an edge.
    """

    def __init__(self, bins_per_decade=20):
        self.bins_per_decade = int(bins_per_decade)
        self._bins = {}

    def clear(self):
        self._bins.clear()

    def bin_index(self, x):
        return int(math.floor(math.log10(x) * self.bins_per_decade + 0.5))

    def bin_edges(self, index):
        bpd = self.bins_per_decade
        return 10 ** ((index - 0.5) / bpd), 10 ** ((index + 0.5) / bpd)

    def add(self, x, e_in, e_out, duration):
        """Add one steady window.

        :return: True if added, False if x is out of range.
        """
        if not (x > 0 and e_in > 0 and math.isfinite(x)):
            return False
        eta = e_out / e_in
        k = self.bin_index(x)
        b = self._bins.get(k)
        if b is None:
            self._bins[k] = [e_in, e_out, duration, 1, eta, eta, x * duration]
        else:
            b[0] += e_in
            b[1] += e_out
            b[2] += duration
            b[3] += 1
            b[4] = min(b[4], eta)
            b[5] = max(b[5], eta)
            b[6] += x * duration
        return True

    def bins(self):
        """Get the bins sorted by x.

        :return: The list of dicts with keys x (duration-weighted mean),
            x_min, x_max (bin edges), efficiency (energy weighted),
            efficiency_min, efficiency_max, e_in, e_out, duration, count.
        """
        result = []
        for k in sorted(self._bins):
            e_in, e_out, duration, count, eta_min, eta_max, xd = self._bins[k]
            x_min, x_max = self.bin_edges(k)
            result.append({
                'x': xd / duration,
                'x_min': x_min,
                'x_max': x_max,
                'efficiency': e_out / e_in,
                'efficiency_min': eta_min,
                'efficiency_max': eta_max,
                'e_in': e_in,
                'e_out': e_out,
                'duration': duration,
                'count': count,
            })
        return result


class _Grid:
    """Emit consecutive windows [k*period, (k+1)*period) on the UTC grid."""

    def __init__(self, period, t_last=None):
        self.period = float(period)
        self.k = None
        self.t_last = t_last  # end of the last emitted window, kept across period changes

    def reset(self):
        self.k = None
        self.t_last = None


_CONFIG_DEFAULTS = {
    'period': 0.5,              # display window, 1 / statistics_frequency
    'curve_period': None,       # curve window, None for period
    'curve_x': 'current',       # current or power
    'bins_per_decade': 20,
    'steady_threshold': 0.05,   # (max - min) / mean of sub-window power
    'steady_segments': 10,
    'history': 10.0,            # retained seconds per signal
    'signals': ['in.p', 'out.p'],  # the 'instrument.signal' streams each window requires
}


class EfficiencyEngine:
    """Compute efficiency from the input and output instrument streams.

    Call :meth:`push` with each stream message and then :meth:`process`
    to get the newly completed display windows.  The curve accumulates
    independently on its own window grid.
    """

    def __init__(self, **config):
        self.config = dict(_CONFIG_DEFAULTS)
        self._integrators = {}
        self.t_ref = None  # time64, integer seconds
        self._signals = [('in', 'p'), ('out', 'p')]
        self._history = self.config['history']
        self._grid = _Grid(self.config['period'])
        self._curve_grid = _Grid(self.config['period'])
        self.curve = Curve(self.config['bins_per_decade'])
        self._totals_clear()
        self.configure(**config)

    def configure(self, **config):
        """Update the configuration.

        Changing the curve settings clears the curve.  Changing the period
        restarts the window grid but keeps the cumulative totals.
        """
        for key in config:
            if key not in _CONFIG_DEFAULTS:
                raise KeyError(f'unsupported config {key}')
        prev = self.config
        c = dict(prev)
        c.update(config)
        if c['period'] <= 0:
            raise ValueError('period must be > 0')
        curve_period = c['curve_period'] or c['period']
        if c['curve_x'] not in ('current', 'power'):
            raise ValueError(f'unsupported curve_x {c["curve_x"]}')
        signals = [tuple(x.split('.')) for x in c['signals']]
        for instrument, signal in signals:
            if instrument not in INSTRUMENTS or signal not in SIGNALS:
                raise ValueError(f'unsupported signal {instrument}.{signal}')
        for key in [('in', 'p'), ('out', 'p')]:
            if key not in signals:
                signals.append(key)
        self.config = c  # validated
        self._signals = signals
        curve_required = [('out', 'i')] if c['curve_x'] == 'current' else []
        for key in list(self._integrators):
            if key not in signals and key not in curve_required:
                del self._integrators[key]  # stale data would stall the windows
        if self._grid.period != c['period']:
            self._grid = _Grid(c['period'], self._grid.t_last)
        if self._curve_grid.period != curve_period:
            self._curve_grid = _Grid(curve_period, self._curve_grid.t_last)
        curve_keys = ['curve_period', 'curve_x', 'bins_per_decade', 'steady_threshold',
                      'steady_segments']
        if any(prev[k] != c[k] for k in curve_keys) or prev['period'] != c['period']:
            self.curve = Curve(c['bins_per_decade'])
            self.rejected = 0
        history = max(c['history'], 4 * max(c['period'], curve_period))
        for integrator in self._integrators.values():
            integrator.history = history
        self._history = history

    def _totals_clear(self):
        self.totals = {'e_in': 0.0, 'e_out': 0.0, 'duration': 0.0,
                       'windows': 0, 'invalid': 0}
        self.rejected = 0

    def clear(self):
        """Clear the cumulative totals and curve, but keep the stream data."""
        self._totals_clear()
        self.curve.clear()

    def reset(self):
        """Clear all state including received stream data."""
        self._integrators.clear()
        self.t_ref = None
        self._grid.reset()
        self._curve_grid.reset()
        self.clear()

    def integrator(self, instrument, signal):
        return self._integrators.get((instrument, signal))

    def push(self, instrument, signal, value):
        """Add a signal stream message.

        :param instrument: 'in' or 'out'.
        :param signal: 'p', 'i' or 'v'.
        :param value: The SIGNAL_STREAM_SOURCE !data message.

        Each window waits for every configured signal, so push only the
        configured signals, plus 'out.i' for the current curve.
        """
        if instrument not in INSTRUMENTS:
            raise ValueError(f'unsupported instrument {instrument}')
        if signal not in SIGNALS:
            raise ValueError(f'unsupported signal {signal}')
        key = (instrument, signal)
        integrator = self._integrators.get(key)
        if integrator is None:
            if self.t_ref is None:
                t = value['time_map']['offset_time']
                self.t_ref = (t // time64.SECOND) * time64.SECOND
            integrator = SignalIntegrator(self.t_ref, self._history)
            self._integrators[key] = integrator
        integrator.push(value)

    @property
    def efficiency_cumulative(self):
        t = self.totals
        return t['e_out'] / t['e_in'] if t['e_in'] > 0 else None

    def _coverage(self, signals):
        """Get the common (t_start, t_end) over the required integrators."""
        starts, ends = [], []
        for key in signals:
            integrator = self._integrators.get(key)
            if integrator is None or integrator.t_end is None:
                return None
            starts.append(integrator.t_start)
            ends.append(integrator.t_end)
        return max(starts), min(ends)

    def _advance(self, grid, signals):
        """Yield the (t0, t1, skipped) windows now complete on grid."""
        coverage = self._coverage(signals)
        if coverage is None:
            return
        t_start, t_end = coverage
        period = grid.period
        if grid.t_last is not None:
            t_start = max(t_start, grid.t_last)
        k_first = math.ceil(t_start / period - 1e-9)
        if grid.k is None:
            grid.k = k_first
        elif grid.k < k_first:
            if (k_first + 1) * period > t_end:
                return  # wait until both instruments overlap again
            # data needed for windows k .. k_first was discarded
            yield grid.k * period, k_first * period, True
            grid.k = k_first
            grid.t_last = k_first * period
        while (grid.k + 1) * period <= t_end:
            yield grid.k * period, (grid.k + 1) * period, False
            grid.k += 1
            grid.t_last = grid.k * period

    def _mean(self, instrument, signal, t0, t1):
        integrator = self._integrators.get((instrument, signal))
        if integrator is None:
            return None
        x = integrator.integral(t0, t1)
        return None if x is None else x / (t1 - t0)

    def _steady(self, t0, t1):
        segments = int(self.config['steady_segments'])
        t = np.linspace(t0, t1, segments + 1)
        for instrument in INSTRUMENTS:
            e = self._integrators[(instrument, 'p')].integrals(t)
            if e is None:
                return False
            mean = np.mean(e)
            if mean <= 0 or (np.max(e) - np.min(e)) / mean > self.config['steady_threshold']:
                return False
        return True

    def _utc(self, t):
        return self.t_ref + int(round(t * time64.SECOND))

    def _window(self, t0, t1):
        e_in = self._integrators[('in', 'p')].integral(t0, t1)
        e_out = self._integrators[('out', 'p')].integral(t0, t1)
        duration = t1 - t0
        w = {'t0': t0, 't1': t1, 'utc': self._utc(t0), 'e_in': e_in, 'e_out': e_out,
             'p_in': None, 'p_out': None, 'p_loss': None, 'efficiency': None,
             'valid': e_in is not None and e_out is not None}
        if w['valid']:
            w['p_in'] = e_in / duration
            w['p_out'] = e_out / duration
            w['p_loss'] = w['p_in'] - w['p_out']
            if e_in > 0:
                w['efficiency'] = e_out / e_in
        for instrument in INSTRUMENTS:
            for signal in ('i', 'v'):
                key = (instrument, signal)
                w[f'{signal}_{instrument}'] = self._mean(*key, t0, t1) if key in self._signals else None
        return w

    def process(self):
        """Process received data.

        :return: The list of newly completed display windows, each a dict
            with keys t0, t1 (seconds relative to t_ref), utc (time64 of
            t0), e_in, e_out (J), p_in, p_out,
            p_loss (W), efficiency, valid, and the optional means i_in, v_in,
            i_out, v_out (None when not subscribed).  Invalid windows have
            None values, and also mark data discarded while one instrument
            was missing.
        """
        windows = []
        p_signals = [('in', 'p'), ('out', 'p')]
        for t0, t1, skipped in self._advance(self._grid, self._signals):
            w = self._window(t0, t1) if not skipped else {
                't0': t0, 't1': t1, 'utc': self._utc(t0), 'valid': False, 'efficiency': None}
            if w['valid']:
                self.totals['e_in'] += w['e_in']
                self.totals['e_out'] += w['e_out']
                self.totals['duration'] += t1 - t0
                self.totals['windows'] += 1
            else:
                self.totals['invalid'] += 1
            windows.append(w)

        curve_x = self.config['curve_x']
        curve_signals = list(p_signals)
        if curve_x == 'current':
            curve_signals.append(('out', 'i'))
        for t0, t1, skipped in self._advance(self._curve_grid, curve_signals):
            if skipped:
                continue
            e_in = self._integrators[('in', 'p')].integral(t0, t1)
            e_out = self._integrators[('out', 'p')].integral(t0, t1)
            if e_in is None or e_out is None:
                continue
            if curve_x == 'current':
                x = self._mean('out', 'i', t0, t1)
            else:
                x = e_out / (t1 - t0)
            if x is None or not self._steady(t0, t1) or not self.curve.add(x, e_in, e_out, t1 - t0):
                self.rejected += 1
        return windows


class WindowHistory:
    """The efficiency history for display, as a bounded ring buffer.

    Each entry is a window end time (time64) and its efficiency, NaN for
    invalid windows so that plots show a gap.
    """

    def __init__(self, capacity=1024):
        self._t = np.zeros(0, dtype=np.int64)
        self._y = np.zeros(0, dtype=np.float64)
        self._count = 0
        self._head = 0  # next write index
        self.reset(capacity)

    def __len__(self):
        return self._count

    @property
    def capacity(self):
        return len(self._t)

    def clear(self):
        self._count = 0
        self._head = 0

    def reset(self, capacity):
        """Change the capacity, keeping the newest entries."""
        capacity = max(2, int(capacity))
        if capacity == self.capacity:
            return
        t, y = self.newest()
        t, y = t[-capacity:], y[-capacity:]
        self._t = np.zeros(capacity, dtype=np.int64)
        self._y = np.full(capacity, np.nan, dtype=np.float64)
        n = len(t)
        self._t[:n] = t
        self._y[:n] = y
        self._count = n
        self._head = n % capacity

    def append(self, windows):
        """Append engine windows, see :meth:`EfficiencyEngine.process`."""
        for w in windows:
            eta = w.get('efficiency')
            self._t[self._head] = w['utc'] + int(round((w['t1'] - w['t0']) * time64.SECOND))
            self._y[self._head] = eta if (w['valid'] and eta is not None) else np.nan
            self._head = (self._head + 1) % self.capacity
            self._count = min(self._count + 1, self.capacity)

    def newest(self):
        """Get the entries, oldest first.

        :return: (t, y) arrays of window end time64 and efficiency.
        """
        n = self._count
        idx = (self._head - n + np.arange(n)) % max(1, self.capacity)
        return self._t[idx], self._y[idx]
