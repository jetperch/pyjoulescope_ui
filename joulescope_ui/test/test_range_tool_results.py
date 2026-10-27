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
Test the Frequency and Histogram range tool computations and progress.
"""

import types
import unittest

import numpy as np
from joulescope_ui.range_tools.frequency import FrequencyRangeTool
from joulescope_ui.range_tools.plugin_helpers import calculate_histogram

_FS = 1000
_START = 5_000_000  # absolute sample ids, as from a live buffer


class _Source:
    """A fake range tool: serves ``data`` and records progress and publishes."""

    def __init__(self, data):
        self.data = np.asarray(data, dtype=np.float32)
        self.progress_values = []
        self.published = []
        self.pubsub = types.SimpleNamespace(publish=lambda t, v: self.published.append(v))

    def request(self, signal, time_type, start, end, length, timeout=None):
        if time_type == 'utc':
            d = self.data
            return {'response_type': 'summary',
                    'data': np.array([[d.mean(), d.std(), d.min(), d.max()]]),
                    'info': {'time_map': {'counter_rate': _FS},
                             'time_range_samples': {'start': _START,
                                                    'end': _START + len(d) - 1}}}
        x = self.data[start - _START:start - _START + length]
        return {'response_type': 'samples', 'data_type': 'f32', 'data': x,
                'info': {'time_range_samples': {'start': start, 'length': len(x)}}}

    def progress(self, value):
        self.progress_values.append(value)


def _reference_psd(x, nfft, overlap):
    """One-sided PSD with a hamming window, DC and Nyquist not doubled."""
    w = np.hamming(nfft)
    step = nfft - int(overlap * nfft)
    segments = np.lib.stride_tricks.sliding_window_view(x, nfft)[::step]
    z = np.fft.rfft(segments * w, axis=1)
    psd = np.mean(np.abs(z) ** 2, axis=0) * 2.0 / (_FS * np.sum(w * w))
    psd[0] /= 2
    psd[-1] /= 2
    return psd


class TestFrequency(unittest.TestCase):

    def test_psd_db_and_progress(self):
        x = np.random.default_rng(3).normal(0.5, 0.1, 5 * _FS)
        src = _Source(x)
        tool = FrequencyRangeTool.__new__(FrequencyRangeTool)
        tool.kwargs = {'signal': 's.d.i', 'window': 'hamming', 'nfft': 256, 'overlap': 0.25}
        tool.x_range = [0, 1]
        tool.request, tool.progress, tool.pubsub = src.request, src.progress, src.pubsub
        tool._run()
        y = src.published[0]['kwargs']['data']['y']
        expect = _reference_psd(src.data.astype(np.float64), 256, 0.25)
        np.testing.assert_allclose(10 ** (y / 10), expect, rtol=1e-4)
        self.assertEqual(sorted(src.progress_values), src.progress_values)
        self.assertAlmostEqual(1.0, src.progress_values[-1])


class TestHistogram(unittest.TestCase):

    def test_progress(self):
        src = _Source(np.random.default_rng(4).normal(size=250_000))
        hist, _ = calculate_histogram(src, {'x_range': [0, 1]}, 's.d.i', 20)
        self.assertEqual(250_000, hist.sum())
        self.assertEqual([0.4, 0.8, 1.0], [round(p, 3) for p in src.progress_values])


if __name__ == '__main__':
    unittest.main()
