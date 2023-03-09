# Copyright 2023 Jetperch LLC
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
Test joulescope_ui.widgets.waveform.time_map
"""

import unittest
from joulescope_ui.time_map import TimeMap, time64
import numpy as np


class TestTimeMap(unittest.TestCase):

    def test_unity_zero(self):
        tm = TimeMap()
        self.assertEqual(0.0, tm.trel_offset)
        self.assertEqual(0, tm.time64_to_counter(0))
        self.assertEqual(0, tm.counter_to_time64(0))
        self.assertEqual(0.0, tm.time64_to_trel(0))
        self.assertEqual(0, tm.trel_to_time64(0.0))
        self.assertEqual(0, tm.trel_to_counter(0.0))

    def test_unity_nonzero(self):
        tm = TimeMap()
        self.assertEqual(0.0, tm.trel_offset)
        self.assertEqual(2, tm.time64_to_counter(2))
        self.assertEqual(2, tm.counter_to_time64(2))
        self.assertEqual(1.0, tm.time64_to_trel(time64.SECOND))
        self.assertEqual(time64.SECOND, tm.trel_to_time64(1.0))
        self.assertEqual(time64.SECOND, tm.trel_to_counter(1.0))

    def _convert(self, trel_offset, z_p, w_p, z_t, w_t):
        tm = TimeMap()
        tm.trel_offset = trel_offset
        t0 = (z_t - trel_offset) / time64.SECOND
        t1 = t0 + w_t / time64.SECOND
        tm.update(z_p, z_t, w_p / w_t)

        self.assertEqual(trel_offset, tm.trel_offset)
        self.assertEqual(z_p, tm.time64_to_counter(z_t))
        self.assertEqual(z_t, tm.counter_to_time64(z_p))
        self.assertEqual(t0, tm.time64_to_trel(z_t))
        self.assertEqual(z_t, tm.trel_to_time64(t0))
        self.assertEqual(z_p, tm.trel_to_counter(t0))

        self.assertEqual(z_p + w_p, tm.time64_to_counter(z_t + w_t))
        self.assertEqual(z_t + w_t, tm.counter_to_time64(z_p + w_p))
        self.assertEqual(t1, tm.time64_to_trel(z_t + w_t))
        self.assertEqual(z_t + w_t, tm.trel_to_time64(t1))
        self.assertEqual(z_p + w_p, tm.trel_to_counter(t1))

        return tm

    def test_normal(self):
        self._convert(time64.YEAR, 100, 200, time64.YEAR + time64.SECOND, time64.SECOND)

    def test_zoom_millisecond(self):
        self._convert(time64.YEAR, 100, 200, time64.YEAR + time64.MILLISECOND, time64.MILLISECOND)

    def test_zoom_microsecond(self):
        self._convert(time64.YEAR, 100, 200, time64.YEAR + time64.MICROSECOND, time64.MICROSECOND)

    def test_numpy(self):
        tm = TimeMap()
        tm.trel_offset = time64.YEAR
        z_p, w_p = 100, 200
        z_t, w_t = time64.YEAR + time64.SECOND, time64.SECOND
        tm.update(z_p, z_t, w_p / w_t)
        p1 = np.arange(z_p, z_p + w_p + 1, 10, dtype=np.uint64)
        t1 = tm.counter_to_time64(p1)
        self.assertEqual(z_t, t1[0])
        self.assertEqual(z_t + w_t, t1[-1])
        p2 = tm.time64_to_counter(t1)
        np.testing.assert_allclose(p1, p2, atol=1e-6)

    def test_conversion_chains(self):
        tm = TimeMap()
        tm.trel_offset = time64.YEAR
        z_p, w_p = 100, 200
        z_t, w_t = time64.YEAR + time64.SECOND, time64.MILLISECOND
        tm.update(z_p, z_t, w_p / w_t)

        p1 = np.arange(z_p, z_p + w_p + 1, 10, dtype=np.uint64)
        p2 = tm.trel_to_counter(tm.time64_to_trel(tm.counter_to_time64(p1)))
        np.testing.assert_allclose(p1, p2, atol=1e-4)

        t1 = np.linspace(z_t, z_t + w_t, 9, dtype=np.uint64)
        p1 = tm.time64_to_counter(t1)
        p2 = tm.trel_to_counter(tm.time64_to_trel(t1))
        np.testing.assert_allclose(p1, p2, atol=1e-4)
