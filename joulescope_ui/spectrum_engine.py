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

"""Qt-free spectrum computation.

All spectra are kept in "power" units: units² per bin for amplitude
scaling (the squared RMS amplitude) and units²/Hz for PSD scaling.
See docs/plans/spectrum.md for the design.
"""

import numpy as np


def _cosine_sum(coef):
    def fn(n):
        if n < 2:
            return np.ones(n)
        k = np.arange(n) * (2.0 * np.pi / (n - 1))
        w = np.zeros(n)
        for idx, a in enumerate(coef):
            w += ((-1) ** idx) * a * np.cos(idx * k)
        return w
    return fn


WINDOWS = {
    'rectangular': np.ones,
    'hann': np.hanning,
    'hamming': np.hamming,
    'blackman': np.blackman,
    'blackman_harris': _cosine_sum([0.35875, 0.48829, 0.14128, 0.01168]),
    'flattop': _cosine_sum([0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368]),
    'bartlett': np.bartlett,
}

WINDOW_NAMES = {
    'rectangular': 'Rectangular',
    'hann': 'Hann',
    'hamming': 'Hamming',
    'blackman': 'Blackman',
    'blackman_harris': 'Blackman-Harris',
    'flattop': 'Flat top',
    'bartlett': 'Bartlett',
}

WINDOW_PEAK_INTERPOLATE = {k: k != 'flattop' for k in WINDOWS}
"""Interpolate the peak value.  A flat-top peak already gives the amplitude."""

WINDOW_MAIN_LOBE_BINS = {
    'rectangular': 1,
    'hann': 2,
    'hamming': 2,
    'blackman': 3,
    'blackman_harris': 4,
    'flattop': 5,
    'bartlett': 2,
}
"""The main lobe half-width in bins, to the first null.  A tone between bins
spans several nearly equal bins within this distance."""

SCALINGS = ['amplitude', 'psd']
AVERAGE_MODES = ['off', 'exponential', 'cumulative']
DETECTORS = ['average', 'max']

DECIMATE_ROLLOFF = 0.9
"""Fraction of each decimated Nyquist band that is alias-free."""

DB_FLOOR = -400.0
"""dB value for zero power, which keeps log10 finite."""


def window(name, n):
    """Get the window coefficients.

    :param name: The window name, one of WINDOWS.
    :param n: The window length.
    :return: The float64 window.
    """
    return np.asarray(WINDOWS[name](n), dtype=np.float64)


def enbw(w):
    """Get the equivalent noise bandwidth in bins."""
    s1 = np.sum(w)
    return len(w) * np.sum(w * w) / (s1 * s1)


def unpack(data, dtype, length=None):
    """Convert sample data to a float array.

    :param data: The sample data, packed for u1 and u4.
    :param dtype: The data type: f32, f64, u8, u4, or u1.
    :param length: The number of samples.  None uses all packed samples.
    :return: The np.ndarray of samples.
    """
    if dtype in ('f32', 'f64', 'u8'):
        y = data
    elif dtype == 'u1':
        y = np.unpackbits(np.asarray(data, dtype=np.uint8), bitorder='little')
    elif dtype == 'u4':
        x = np.asarray(data, dtype=np.uint8)
        y = np.empty(len(x) * 2, dtype=np.uint8)
        y[0::2] = np.bitwise_and(x, 0x0f)
        y[1::2] = np.right_shift(x, 4)
    else:
        raise ValueError(f'unsupported data_type {dtype}')
    if length is not None:
        y = y[:length]
    return y


def sample_count(data, dtype):
    """Get the number of samples in data, see :func:`unpack`."""
    return len(data) * (8 if dtype == 'u1' else (2 if dtype == 'u4' else 1))


def hop_length(n, overlap):
    """Get the samples between successive FFTs of length n."""
    overlap = min(0.95, max(0.0, float(overlap)))
    return max(1, n - int(round(overlap * n)))


def bin_frequencies(fs, n):
    """Get the rfft bin frequencies in Hz."""
    return np.arange(n // 2 + 1) * (fs / n)


def to_db(p):
    """Convert power to dB."""
    with np.errstate(divide='ignore', invalid='ignore'):
        y = 10.0 * np.log10(p)
    return np.nan_to_num(y, nan=DB_FLOOR, neginf=DB_FLOOR, posinf=-DB_FLOOR)


def halfband_taps(attenuation_db=90.0, transition=0.05):
    """Design a Kaiser-window half-band lowpass filter.

    :param attenuation_db: The stopband attenuation in dB.
    :param transition: The transition width in cycles/sample, centered
        on 0.25.
    :return: The filter taps with odd center index and unity DC gain.
    """
    beta = 0.1102 * (attenuation_db - 8.7)
    order = int(np.ceil((attenuation_db - 7.95) / (2.285 * 2 * np.pi * transition)))
    c = order // 2
    if c % 2 == 0:  # odd center: all nonzero non-center taps have even index
        c += 1
    n = np.arange(2 * c + 1) - c
    h = 0.5 * np.sinc(n / 2.0) * np.kaiser(2 * c + 1, beta)
    h[(n != 0) & (n % 2 == 0)] = 0.0
    return h / np.sum(h)


class HalfBandDecimator:
    """Decimate by 2 using a polyphase half-band FIR with block state."""

    def __init__(self):
        h = np.append(halfband_taps(), 0.0)  # even length for the two phases
        self._h_e = h[0::2].copy()
        h_o = h[1::2]  # half-band: the odd phase is only the center tap
        self._o_idx = int(np.flatnonzero(h_o)[0])
        self._o_value = h_o[self._o_idx]
        self._le = len(self._h_e)
        self.reset()

    def reset(self):
        self._buf = np.zeros(2 * self._le)

    def process(self, x):
        """Process samples.

        :param x: The input samples.
        :return: The decimated output samples.
        """
        buf = np.concatenate((self._buf, x))
        e, o = buf[0::2], buf[1::2]
        le = self._le
        m_max = min(len(e) - 1, len(o))
        if m_max < le:
            self._buf = buf
            return np.zeros(0)
        y = np.convolve(e[:m_max + 1], self._h_e, mode='valid')[1:]
        k = self._o_idx
        y += self._o_value * o[le - k - 1:m_max - k]
        drop = m_max + 1 - le
        self._buf = buf[2 * drop:]
        return y


class Decimator:
    """Decimate by a power of 2 using a half-band cascade."""

    def __init__(self, factor):
        factor = int(factor)
        if factor < 1 or (factor & (factor - 1)):
            raise ValueError(f'decimate factor must be a power of 2: {factor}')
        self.factor = factor
        self._stages = [HalfBandDecimator() for _ in range(factor.bit_length() - 1)]

    def reset(self):
        for stage in self._stages:
            stage.reset()

    def process(self, x):
        for stage in self._stages:
            x = stage.process(x)
        return x


class Segmenter:
    """Split a sample stream into overlapping segments."""

    def __init__(self, length, hop):
        if hop < 1 or hop > length:
            raise ValueError('invalid hop')
        self.length = length
        self.hop = hop
        self._buf = np.zeros(2 * length)
        self.reset()

    def reset(self):
        self._start = 0      # index of the oldest retained sample in self._buf
        self._end = 0        # index after the newest sample in self._buf
        self._buf_id = None  # sample id of self._buf[self._start]

    def _append(self, x):
        k = len(x)
        size = self._end - self._start
        if self._end + k > len(self._buf):
            if size + k > len(self._buf):
                buf = np.empty(max(2 * len(self._buf), size + k))
            else:
                buf = self._buf
            buf[:size] = self._buf[self._start:self._end]
            self._buf, self._start, self._end = buf, 0, size
        self._buf[self._end:self._end + k] = x
        self._end += k

    def push(self, sample_id, x):
        """Add samples.

        :param sample_id: The sample id of x[0].
        :param x: The samples, contiguous with prior pushes.
        :return: (segments, sample_ids) where segments is a 2-D view with
            shape (M, length) and sample_ids holds each segment start id.
            The view is only valid until the next call.
        """
        if self._buf_id is None or self._end == self._start:
            self._buf_id = sample_id - (self._end - self._start)
        self._append(x)
        n, hop = self.length, self.hop
        size = self._end - self._start
        if size < n:
            return np.zeros((0, n)), np.zeros(0, dtype=np.int64)
        m = (size - n) // hop + 1
        buf = self._buf[self._start:self._end]
        segments = np.lib.stride_tricks.sliding_window_view(buf, n)[::hop][:m]
        ids = self._buf_id + np.arange(m, dtype=np.int64) * hop
        consumed = m * hop
        self._start += consumed
        self._buf_id += consumed
        return segments, ids


def average_update(a, k, x, n):
    """Update a running average with a batch of spectra.

    :param a: The present average or None.
    :param k: The number of spectra already in the average.
    :param x: The new spectra with shape (M, bins).
    :param n: The exponential averaging count, or None for cumulative.
    :return: The new average.

    The first n spectra form a cumulative average, then each new
    spectrum has weight 1/n.
    """
    m = len(x)
    if not m:
        return a
    idx = k + np.arange(m, dtype=np.float64) + 1
    if n is not None:
        idx = np.minimum(idx, float(n))
    alpha = 1.0 / idx
    beta = 1.0 - alpha
    suffix = np.cumprod(beta[::-1])[::-1]       # prod over i >= j
    after = np.append(suffix[1:], 1.0)          # prod over i > j
    # elementwise, not matmul: BLAS threads spin and waste CPU on small products
    y = np.sum((alpha * after)[:, np.newaxis] * x, axis=0)
    if a is not None and suffix[0] != 0.0:
        y += suffix[0] * a
    return y


def _sliding(y, w, op):
    """Reduce each length-w window: out[i] = op over y[i:i + w].

    van Herk / Gil-Werman: O(n) regardless of w.
    """
    n = len(y) - w + 1
    k = -(-len(y) // w) * w
    pad = np.full(k, np.inf if op is np.minimum else -np.inf)
    pad[:len(y)] = y
    blocks = pad.reshape((-1, w))
    prefix = op.accumulate(blocks, axis=1).ravel()
    suffix = op.accumulate(blocks[:, ::-1], axis=1)[:, ::-1].ravel()
    return op(suffix[:n], prefix[w - 1:w - 1 + n])


def find_peaks(y, count, threshold=None, separation=1, x=None, excursion=0.0, y_interpolate=True):
    """Find the largest local maxima.

    :param y: The values, usually in dB.
    :param count: The maximum number of peaks.
    :param threshold: Ignore peaks below this value.
    :param separation: The minimum separation in samples between peaks.
    :param x: The optional x-axis values for each y, uniformly spaced.
    :param excursion: The minimum rise of a peak above the lowest value
        within separation samples on both sides, like a spectrum
        analyzer's peak excursion.
    :param y_interpolate: Interpolate the peak value, see
        :data:`WINDOW_PEAK_INTERPOLATE`.
    :return: List of (x, y, index) sorted by decreasing y, where x and y
        use parabolic interpolation.
    """
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    if count <= 0 or n < 3:
        return []
    sep = max(1, int(separation))
    inf = np.full(sep, np.inf)
    c = y[1:-1]
    keep = np.zeros(n, dtype=bool)
    keep[1:-1] = (c > y[:-2]) & (c >= y[2:]) & np.isfinite(c)
    # the largest value within separation on both sides
    keep &= y >= _sliding(np.concatenate((-inf, y, -inf)), 2 * sep + 1, np.maximum)
    if threshold is not None:
        keep &= y >= threshold
    if excursion > 0:
        left = _sliding(np.concatenate((inf, y[:-1])), sep, np.minimum)       # y[i-sep:i]
        right = _sliding(np.concatenate((y[1:], inf)), sep, np.minimum)       # y[i+1:i+1+sep]
        keep &= y - np.maximum(left, right) >= excursion
    idx = np.flatnonzero(keep)
    idx = idx[np.argsort(-y[idx], kind='stable')]
    selected = []
    for i in idx:  # equal values within separation both survive the window test
        if all(abs(i - j) >= sep for j in selected):
            selected.append(int(i))
            if len(selected) >= count:
                break
    result = []
    for i in selected:
        a, b, c = y[i - 1], y[i], y[i + 1]
        d = a - 2 * b + c
        p = 0.0 if d == 0 else 0.5 * (a - c) / d
        p = min(0.5, max(-0.5, p))
        yp = b - 0.25 * (a - c) * p if y_interpolate else b
        if x is None:
            xp = i + p
        else:
            xp = x[i] + p * (x[1] - x[0])
        result.append((xp, yp, i))
    return result


def column_map(f, edges):
    """Map spectrum bins to display columns.

    :param f: The bin frequencies, uniformly spaced and increasing.
    :param edges: The column edges with length columns + 1, increasing.
    :return: The opaque map for :func:`column_reduce`.
    """
    f = np.asarray(f)
    edges = np.asarray(edges, dtype=np.float64)
    start = np.searchsorted(f, edges[:-1], 'left')
    end = np.searchsorted(f, edges[1:], 'left')
    empty = end <= start
    if len(f) > 1:
        df = f[1] - f[0]
        center = 0.5 * (edges[:-1] + edges[1:])
        nearest = np.clip(np.round((center - f[0]) / df).astype(np.int64), 0, len(f) - 1)
    else:
        nearest = np.zeros(len(start), dtype=np.int64)
    end_max = int(np.max(end)) if len(end) else 0
    start = np.minimum(start, max(end_max - 1, 0))
    return {
        'start': start,
        'empty': empty,
        'nearest': nearest,
        'end': end_max,
    }


def column_reduce(y, cmap, op=np.maximum):
    """Reduce spectrum bins to display columns.

    :param y: The values with bins on the last axis.
    :param cmap: The map from :func:`column_map`.
    :param op: The reduction ufunc, such as np.maximum or np.minimum.
    :return: The values with columns on the last axis.
    """
    end = cmap['end']
    if end <= 0:
        return y[..., cmap['nearest']]
    out = op.reduceat(y[..., :end], cmap['start'], axis=-1)
    empty = cmap['empty']
    out[..., empty] = y[..., cmap['nearest'][empty]]
    return out


class SpectrumEngine:
    """Compute live spectra, trace holds, and waterfall rows.

    :param config: The configuration dict, see :attr:`CONFIG_DEFAULT`.
    """

    CONFIG_DEFAULT = {
        'fft_length': 4096,
        'window': 'hann',
        'overlap': 0.5,
        'scaling': 'amplitude',
        'dc_remove': True,
        'decimate': 1,
        'average_mode': 'exponential',
        'average_count': 16,
        'row_period': 0.05,
        'detector': 'average',
    }

    def __init__(self, config=None):
        self.config = dict(self.CONFIG_DEFAULT)
        if config:
            self.config.update(config)
        cfg = self.config
        n = int(cfg['fft_length'])
        if n < 4 or n % 2:
            raise ValueError(f'invalid fft_length {n}')
        if cfg['scaling'] not in SCALINGS:
            raise ValueError(f'invalid scaling {cfg["scaling"]}')
        if cfg['average_mode'] not in AVERAGE_MODES:
            raise ValueError(f'invalid average_mode {cfg["average_mode"]}')
        if cfg['detector'] not in DETECTORS:
            raise ValueError(f'invalid detector {cfg["detector"]}')
        self.n = n
        self.hop = hop_length(n, cfg['overlap'])
        self.window = window(cfg['window'], n)
        self.enbw = enbw(self.window)
        self._s1 = np.sum(self.window)
        self._s2 = np.sum(self.window * self.window)
        self._decimator = Decimator(cfg['decimate'])
        self._segmenter = Segmenter(n, self.hop)
        self.fs_in = None
        self.fs = None
        self._sample_id_next = None  # expected next input sample id
        self._out_id = 0             # decimated output sample id of next output
        self._row_samples = 1
        self.clear()

    @property
    def bins(self):
        return self.n // 2 + 1

    @property
    def decimate(self):
        return self._decimator.factor

    def frequencies(self):
        """The bin frequencies in Hz."""
        if self.fs is None:
            return None
        return bin_frequencies(self.fs, self.n)

    @property
    def rbw(self):
        """The resolution bandwidth (ENBW) in Hz."""
        if self.fs is None:
            return None
        return self.enbw * self.fs / self.n

    def clear(self):
        """Clear the traces and waterfall, but keep the input state."""
        self.live = None
        self.average = None
        self.max = None
        self.min = None
        self.count = 0
        self._rows = []
        self._row_idx = None
        self._row_acc = None
        self._row_count = 0
        self._row_gap = False

    def _resync(self):
        """Discard partial data at an input discontinuity.

        Callers count upstream sample loss themselves: they know which
        discontinuities they caused, such as hold or dropped data.
        """
        self._decimator.reset()
        self._segmenter.reset()
        self._sample_id_next = None
        if self._row_idx is not None:
            self._row_emit()
        self._row_gap = True

    def _scale(self):
        if self.config['scaling'] == 'psd':
            k = 2.0 / (self.fs * self._s2)
        else:
            k = 2.0 / (self._s1 * self._s1)
        scale = np.full(self.bins, k)
        scale[0] *= 0.5
        if self.n % 2 == 0:
            scale[-1] *= 0.5
        return scale

    def process(self, sample_id, fs, x):
        """Process input samples.

        :param sample_id: The input sample id of x[0].  A discontinuity
            discards partial data and starts new segments.
        :param fs: The input sample rate in Hz.  A change clears all state.
        :param x: The input samples.
        :return: The number of new spectra.
        """
        if self.fs_in != fs:
            self.fs_in = fs
            self.fs = fs / self.decimate
            self._scale_k = self._scale()
            self._row_samples = max(1, int(round((self.config['row_period'] or 0) * self.fs)))
            self._decimator.reset()
            self._segmenter.reset()
            self._sample_id_next = None
            self.clear()
        elif self._sample_id_next is not None and sample_id != self._sample_id_next:
            self._resync()
        if self._sample_id_next is None:
            self._out_id = sample_id // self.decimate
        self._sample_id_next = sample_id + len(x)
        x = np.asarray(x, dtype=np.float64)
        if self.decimate > 1:
            x = self._decimator.process(x)
        segments, ids = self._segmenter.push(self._out_id, x)
        self._out_id += len(x)
        m = len(segments)
        if not m:
            return 0
        if self.config['dc_remove']:
            segments = segments - np.mean(segments, axis=1, keepdims=True)
        z = np.fft.rfft(segments * self.window, axis=-1)
        p = (z.real * z.real + z.imag * z.imag) * self._scale_k
        self._traces_update(p)
        if self.config['row_period']:
            self._rows_update(p, ids + self.n)
        return m

    def _traces_update(self, p):
        self.live = p[-1].copy()
        p_max, p_min = np.max(p, axis=0), np.min(p, axis=0)
        if self.max is None:
            self.max, self.min = p_max, p_min
        else:
            np.maximum(self.max, p_max, out=self.max)
            np.minimum(self.min, p_min, out=self.min)
        mode = self.config['average_mode']
        if mode != 'off':
            n = int(self.config['average_count']) if mode == 'exponential' else None
            self.average = average_update(self.average, self.count, p, n)
        self.count += len(p)

    def _rows_update(self, p, end_ids):
        row_idx = end_ids // self._row_samples
        is_max = self.config['detector'] == 'max'
        starts = np.flatnonzero(np.diff(row_idx, prepend=row_idx[0] - 1))
        if is_max:
            values = np.maximum.reduceat(p, starts, axis=0)
        else:
            values = np.add.reduceat(p, starts, axis=0)
        counts = np.diff(np.append(starts, len(p)))
        for k, start in enumerate(starts):
            idx = int(row_idx[start])
            if self._row_idx is not None and idx != self._row_idx:
                self._row_emit()
            if self._row_idx is None or idx != self._row_idx:
                self._row_idx = idx
                self._row_acc = values[k].copy()
                self._row_count = int(counts[k])
            elif is_max:
                np.maximum(self._row_acc, values[k], out=self._row_acc)
            else:
                self._row_acc += values[k]
                self._row_count += int(counts[k])

    def _row_emit(self):
        acc = self._row_acc
        if self.config['detector'] == 'average':
            acc = acc / self._row_count
        self._rows.append({
            'gap': self._row_gap,
            'db': to_db(acc).astype(np.float32),
        })
        self._row_gap = False
        self._row_idx = None
        self._row_acc = None
        self._row_count = 0

    def rows_pop(self):
        """Get and remove the completed waterfall rows.

        :return: The list of row dicts with keys gap (True if a
            discontinuity preceded the row) and db (float32 dB values).
        """
        rows, self._rows = self._rows, []
        return rows
