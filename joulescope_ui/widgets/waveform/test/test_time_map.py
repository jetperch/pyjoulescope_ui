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
from joulescope_ui.widgets.waveform.time_map import TimeMap, time64


class TestTimeMap(unittest.TestCase):

    def test_unity_zero(self):
        tm = TimeMap()
        self.assertEqual(0.0, tm.trel_offset())
        self.assertEqual(0, tm.time64_to_pixel(0))
        self.assertEqual(0, tm.pixel_to_time64(0))
        self.assertEqual(0.0, tm.time64_to_trel(0))
        self.assertEqual(0, tm.trel_to_time64(0.0))
        self.assertEqual(0, tm.trel_to_pixel(0.0))

    def test_unity_nonzero(self):
        tm = TimeMap()
        self.assertEqual(0.0, tm.trel_offset())
        self.assertEqual(2, tm.time64_to_pixel(2))
        self.assertEqual(2, tm.pixel_to_time64(2))
        self.assertEqual(1.0, tm.time64_to_trel(time64.SECOND))
        self.assertEqual(time64.SECOND, tm.trel_to_time64(1.0))
        self.assertEqual(time64.SECOND, tm.trel_to_pixel(1.0))

    def test_normal(self):
        tm = TimeMap()