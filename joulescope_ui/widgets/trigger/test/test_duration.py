# Copyright 2024 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import numpy as np
from joulescope_ui.widgets.trigger.condition_detector import condition_detector_factory as factory


class TestConditionDetectorDurationDigital(unittest.TestCase):

    def test_ones(self):
        fn = factory({'type': 'duration', 'signal': '0', 'condition': '1', 'duration': 0.001})
        self.assertEqual(1000, fn(1_000_000, np.ones(2000)))

    def test_ones_reset(self):
        fn = factory({'type': 'duration', 'signal': '0', 'condition': '1', 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, np.ones(800)))
        self.assertIsNone(fn(1_000_000, np.zeros(2000)))
        self.assertEqual(1000, fn(1_000_000, np.ones(2000)))

    def test_ones_in_parts(self):
        fn = factory({'type': 'duration', 'signal': '0', 'condition': '1', 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, np.zeros(2000)))
        self.assertIsNone(fn(1_000_000, np.ones(800)))
        self.assertEqual(200, fn(1_000_000, np.ones(2000)))

    def test_ones_segments(self):
        fn = factory({'type': 'duration', 'signal': '0', 'condition': '1', 'duration': 0.001})
        data = np.zeros(2000, dtype=np.uint8)
        data[10:100] = 1
        data[210:500] = 1
        data[1000:] = 1
        self.assertEqual(2000, fn(1_000_000, data))

    def test_zeros(self):
        fn = factory({'type': 'duration', 'signal': '0', 'condition': '0', 'duration': 0.001})
        self.assertEqual(1000, fn(1_000_000, np.zeros(2000)))


class TestConditionDetectorDurationAnalog(unittest.TestCase):

    def test_greater_than_match(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': '>', 'value1': 0.5, 'duration': 0.001})
        self.assertEqual(1000, fn(1_000_000, np.ones(2000)))

    def test_greater_than_when_equal(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': '>', 'value1': 1.0, 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, np.ones(2000)))

    def test_less_than_match(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': '<', 'value1': -0.5, 'duration': 0.001})
        self.assertEqual(1000, fn(1_000_000, -np.ones(2000)))

    def test_less_than_when_equal(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': '<', 'value1': -1.0, 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, -np.ones(2000)))

    def test_between_match_equal_bottom(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': 'between',
                      'value1': 1.0, 'value2': 2.0, 'duration': 0.001})
        self.assertEqual(1000, fn(1_000_000, np.ones(2000)))

    def test_between_match_equal_top(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': 'between',
                      'value1': 1.0, 'value2': 2.0, 'duration': 0.001})
        data = np.empty(2000)
        data[:] = 2.0
        self.assertEqual(1000, fn(1_000_000, data))

    def test_between_when_outside(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': 'between',
                      'value1': 1.0, 'value2': 2.0, 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, np.zeros(2000)))

    def test_outside_equal_bottom(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': 'outside',
                      'value1': 1.0, 'value2': 2.0, 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, np.ones(2000)))

    def test_outside_equal_top(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': 'outside',
                      'value1': 1.0, 'value2': 2.0, 'duration': 0.001})
        data = np.empty(2000)
        data[:] = 2.0
        self.assertIsNone(fn(1_000_000, data))

    def test_outside_bottom(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': 'outside',
                      'value1': 1.0, 'value2': 2.0, 'duration': 0.001})
        self.assertEqual(1000, fn(1_000_000, np.zeros(2000)))

    def test_outside_top(self):
        fn = factory({'type': 'duration', 'signal': 'current', 'condition': 'outside',
                      'value1': 1.0, 'value2': 2.0, 'duration': 0.001})
        data = np.empty(2000)
        data[:] = 3.0
        self.assertEqual(1000, fn(1_000_000, data))
