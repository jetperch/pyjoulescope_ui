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
Test joulescope_ui.widgets.spectrum.spectrum_worker
"""

import queue
import threading
import time
import unittest
import numpy as np
from joulescope_ui.widgets.spectrum.spectrum_worker import SpectrumWorker


FS = 10_000.0


class TestWorker(unittest.TestCase):

    def setUp(self):
        self.snapshots = queue.Queue()
        self.w = SpectrumWorker(self.snapshots.put, frame_period=0.01)

    def tearDown(self):
        self.w.stop()

    def _wait(self, predicate, timeout=2.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            try:
                s = self.snapshots.get(timeout=0.05)
            except queue.Empty:
                continue
            if predicate(s):
                return s
        self.fail('timeout')

    def test_start_stop(self):
        threads = threading.active_count()
        self.w.start()
        self.assertTrue(self.w.is_running)
        self.assertEqual(threads + 1, threading.active_count())
        self.w.stop()
        self.assertFalse(self.w.is_running)
        self.assertEqual(threads, threading.active_count())
        self.w.stop()  # idempotent

    def test_tone(self):
        self.w.start()
        gen = self.w.configure({'fft_length': 256, 'window': 'hann', 'average_mode': 'cumulative'})
        f = 32 * FS / 256
        x = (np.sqrt(2) * np.sin(2 * np.pi * f * np.arange(4096) / FS)).astype(np.float32)
        self.assertTrue(self.w.push(0, FS, x))
        s = self._wait(lambda s: s.get('count', 0) >= 31)
        self.assertEqual(gen, s['generation'])
        self.assertEqual(32, int(np.argmax(s['average'])))
        self.assertAlmostEqual(1.0, s['average'][32], delta=0.01)
        self.assertEqual(FS, s['fs'])

    def test_config_ordering(self):
        self.w.start()
        self.w.configure({'fft_length': 64})
        self.w.push(0, FS, np.zeros(1024, dtype=np.float32))
        gen = self.w.configure({'fft_length': 128})
        s = self._wait(lambda s: s['generation'] == gen)
        self.assertNotIn('n', s)  # no data yet for the new configuration
        self.w.push(1024, FS, np.zeros(1024, dtype=np.float32))
        s = self._wait(lambda s: s['generation'] == gen and 'n' in s)
        self.assertEqual(128, s['n'])

    def test_clear(self):
        self.w.start()
        self.w.configure({'fft_length': 64})
        self.w.push(0, FS, np.ones(1024, dtype=np.float32))
        self._wait(lambda s: s.get('count', 0) > 0)
        self.w.clear()
        s = self._wait(lambda s: s.get('count', -1) == 0)
        self.assertIsNone(s['live'])

    def test_overrun(self):
        # not started: nothing drains the queue
        self.w.configure({'fft_length': 64})
        x = np.zeros(int(FS / 4), dtype=np.float32)
        results = [self.w.push(k * len(x), FS, x) for k in range(6)]
        self.assertEqual([True] * 4 + [False] * 2, results)
        self.assertEqual(2, self.w.overruns)
        self.w.start()
        s = self._wait(lambda s: s.get('count', 0) > 0)
        self.assertEqual(2, s['overruns'])
        self.assertTrue(self.w.push(0, FS, x))  # drained

    def test_digital(self):
        self.w.start()
        self.w.configure({'fft_length': 64, 'dc_remove': False, 'average_mode': 'cumulative'})
        self.w.push(0, FS, np.full(64, 0xff, dtype=np.uint8), 'u1')
        s = self._wait(lambda s: s.get('count', 0) >= 1)
        self.assertGreater(s['average'][0], 0.1)

    def test_invalid_config(self):
        self.w.start()
        with self.assertLogs('joulescope_ui.widgets.spectrum.spectrum_worker', 'ERROR'):
            gen = self.w.configure({'fft_length': 3})
            self._wait(lambda s: s['generation'] == gen)
        self.w.push(0, FS, np.zeros(1024, dtype=np.float32))  # ignored, no crash
        gen = self.w.configure({'fft_length': 64})
        self.w.push(0, FS, np.zeros(1024, dtype=np.float32))
        self._wait(lambda s: s['generation'] == gen and s.get('count', 0) > 0)

    def test_rows(self):
        self.w.start()
        self.w.configure({'fft_length': 64, 'overlap': 0, 'row_period': 64 / FS})
        self.w.push(0, FS, np.ones(64 * 10, dtype=np.float32))
        rows = []
        t_end = time.monotonic() + 2
        while len(rows) < 9 and time.monotonic() < t_end:
            try:
                rows.extend(self.snapshots.get(timeout=0.05)['rows'])
            except queue.Empty:
                pass
        self.assertEqual(9, len(rows))


if __name__ == '__main__':
    unittest.main()
