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
Test the axis ticks
"""

import unittest
from joulescope_ui.widgets.waveform import axis_ticks as t
from joulescope_ui import time64
import numpy as np


class TestAxisTicksXOffset(unittest.TestCase):

    def test_microsecond(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.MICROSECOND * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.MICROSECOND + 5, time64.YEAR + time64.MICROSECOND * 6))
        self.assertEqual(time64.YEAR + int(20 * time64.SECOND * 1e-6),
                         t.x_offset(time64.YEAR + time64.MICROSECOND * 22 + 5, time64.YEAR + time64.MICROSECOND * 24))

    def test_millisecond(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.MILLISECOND * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.MILLISECOND + 5, time64.YEAR + time64.MILLISECOND * 6))

    def test_second(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.SECOND * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.SECOND + 5, time64.YEAR + time64.SECOND * 6))

    def test_minute(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.MINUTE * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.MINUTE + 5, time64.YEAR + time64.MINUTE * 6))

    def test_hour(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.HOUR * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.HOUR + 5, time64.YEAR + time64.HOUR * 6))

    def test_day(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.DAY * 6))
        self.assertEqual(time64.YEAR + time64.DAY, t.x_offset(time64.YEAR + time64.DAY + 5, time64.YEAR + time64.DAY * 6))

    def test_small(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + 6, time64.YEAR + 12))


class TestAxisXTicks(unittest.TestCase):

    def test_good(self):
        x0, x1 = 180025915120611983, 180025915208504625
        v = t.x_ticks(x0, x1, 13.857142857142858)
        z0 = v['offset'] + int(v['major'][0] * time64.SECOND)
        z1 = v['offset'] + int(v['major'][-1] * time64.SECOND)
        self.assertGreaterEqual(z0, x0)
        self.assertLessEqual(z1, x1)

    def test_bad(self):
        x0, x1 = 180027262723932739, 180027262785536828
        v = t.x_ticks(x0, x1, 13.857142857142858)
        #print((x0 - v['offset']) / time64.SECOND)
        z0 = v['offset'] + int(v['major'][0] * time64.SECOND)
        z1 = v['offset'] + int(v['major'][-1] * time64.SECOND)
        self.assertGreaterEqual(z0, x0)
        self.assertLessEqual(z1, x1)
        #print(v)


class TestTimeFormat(unittest.TestCase):

    def test_seconds(self):
        self.assertEqual(('0', 's'), t.time_fmt(0, 1, 1))
        self.assertEqual(('1', 's'), t.time_fmt(1, 1, 1))
        self.assertEqual(('1', 's'), t.time_fmt(1.2, 1, 1))
        self.assertEqual(('0:30', 'm:ss'), t.time_fmt(30, 60, 1))

    def test_minutes(self):
        self.assertEqual(('1:00', 'm:ss'), t.time_fmt(60, 120, 1))
        self.assertEqual(('1', 'm'), t.time_fmt(60, 120, 60))

    def test_days(self):
        day = 60 * 60 * 24
        self.assertEqual(('1', 'd'), t.time_fmt(day, 3 * day, day))
        self.assertEqual(('2', 'd'), t.time_fmt(2 * day, 3 * day, day))
        self.assertEqual(('1:00:00:01', 'd:hh:mm:ss'), t.time_fmt(day + 1, 3 * day, 1))


class TestAxisTicks(unittest.TestCase):

    def test_normal(self):
        ticks = t.ticks(0, 1.01, 0.2, 10)
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 6), ticks['major'])
        self.assertEqual(0.2, ticks['major_interval'])
        self.assertEqual(0.02, ticks['minor_interval'])
        self.assertEqual('', ticks['unit_prefix'])

    def test_major_max(self):
        ticks = t.ticks(0, 1.01, major_max=3)
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 3), ticks['major'])

    def test_major_max_override(self):
        ticks = t.ticks(0, 1.01, 0.2, 3)
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 3), ticks['major'])

    def test_preferred_prefix(self):
        ticks = t.ticks(0, 1.01, 0.2, prefix_preferred='m')
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 6), ticks['major'])
        self.assertEqual(['0', '200', '400', '600', '800', '1000'], ticks['labels'])
        self.assertEqual(0.2, ticks['major_interval'])
        self.assertEqual('m', ticks['unit_prefix'])
