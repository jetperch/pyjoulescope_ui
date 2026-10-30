#!/usr/bin/env python3
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

"""Benchmark the spectrum widget engine and worker.

Reports engine throughput as a fraction of one core at real-time rates,
then Qt event-loop latency while the worker processes real-time data.
See docs/plans/spectrum.md "Compute budget".

    python ci/spectrum_bench.py
"""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from joulescope_ui.spectrum_engine import SpectrumEngine  # noqa: E402
from joulescope_ui.widgets.spectrum.spectrum_worker import SpectrumWorker  # noqa: E402


_CHUNK = 1000  # samples per stream message, approximately JS220 at 1 MSPS
_CASES = [
    # fs, fft_length, overlap, decimate
    (1_000_000, 4096, 0.5, 1),
    (1_000_000, 4096, 0.75, 1),
    (1_000_000, 65536, 0.5, 1),
    (1_000_000, 1 << 20, 0.5, 1),
    (1_000_000, 4096, 0.5, 16),
    (2_000_000, 4096, 0.75, 1),
    (2_000_000, 65536, 0.5, 1),
]


def engine_load(fs, n, overlap, decimate, seconds=2.0):
    e = SpectrumEngine({'fft_length': n, 'overlap': overlap, 'decimate': decimate,
                        'row_period': 0.05})
    x = np.random.default_rng(0).normal(size=int(fs * seconds)).astype(np.float32)
    t0 = time.perf_counter()
    for idx in range(0, len(x), _CHUNK):
        e.process(idx, fs, x[idx:idx + _CHUNK])
        e.rows_pop()
    return (time.perf_counter() - t0) / seconds


def qt_latency(fs, n, overlap, decimate, seconds=3.0):
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    snapshots = [0]
    worker = SpectrumWorker(lambda s: snapshots.__setitem__(0, snapshots[0] + 1))
    if n:
        worker.configure({'fft_length': n, 'overlap': overlap, 'decimate': decimate})
        worker.start()
    x = np.random.default_rng(0).normal(size=int(fs)).astype(np.float32)
    state = {'t_prev': time.perf_counter(), 'latency': [], 'sample_id': 0,
             't_start': time.perf_counter()}

    def on_timer():
        t = time.perf_counter()
        state['latency'].append(t - state['t_prev'] - 0.001)
        state['t_prev'] = t
        # feed real-time data, like the pubsub stream callbacks
        target = int((t - state['t_start']) * fs)
        while n and state['sample_id'] + _CHUNK <= target:
            k = state['sample_id'] % (len(x) - _CHUNK)
            worker.push(state['sample_id'], fs, x[k:k + _CHUNK])
            state['sample_id'] += _CHUNK
        if t - state['t_start'] > seconds:
            app.quit()

    timer = QtCore.QTimer()
    timer.setTimerType(QtCore.Qt.PreciseTimer)
    timer.timeout.connect(on_timer)
    timer.start(1)
    app.exec()
    timer.stop()
    worker.stop()
    lat = np.array(state['latency'][10:]) * 1000
    return np.percentile(lat, 50), np.percentile(lat, 99), np.max(lat), worker.overruns, snapshots[0]


def main():
    print('Engine load (fraction of one core at real time)')
    print(f'{"fs":>10} {"N":>8} {"overlap":>7} {"dec":>4} {"load":>7}')
    for case in _CASES:
        load = engine_load(*case)
        print(f'{case[0]:>10} {case[1]:>8} {case[2]:>7} {case[3]:>4} {load * 100:6.1f}%')

    print('\nQt event-loop latency in ms (1 ms timer, real-time feed)')
    print(f'{"case":>34} {"p50":>6} {"p99":>6} {"max":>6} {"overruns":>8} {"frames":>6}')
    for case in [(1_000_000, 0, 0, 1)] + _CASES[:3] + _CASES[5:]:
        p50, p99, p_max, overruns, frames = qt_latency(*case)
        label = 'no worker' if not case[1] else str(case)
        print(f'{label:>34} {p50:6.2f} {p99:6.2f} {p_max:6.2f} {overruns:>8} {frames:>6}')


if __name__ == '__main__':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    main()
