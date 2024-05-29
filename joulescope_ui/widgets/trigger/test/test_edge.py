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


class TestConditionDetectorEdge(unittest.TestCase):

    def test_analog_rising(self):
        fn = factory({'type': 'edge', 'signal': 'current', 'condition': 'rising', 'value1': 2.0})
        d = np.zeros(1000)
        self.assertIsNone(fn(1_000_000, d))
        d[500:] = 3
        self.assertEqual(500, fn(1_000_000, d))

    def test_analog_falling(self):
        fn = factory({'type': 'edge', 'signal': 'current', 'condition': 'falling', 'value1': 0.75})
        d = np.ones(1000)
        self.assertIsNone(fn(1_000_000, d))
        d[500:] = 0.6
        self.assertEqual(500, fn(1_000_000, d))

    def test_analog_both(self):
        fn = factory({'type': 'edge', 'signal': 'current', 'condition': 'both', 'value1': 0.75})
        d = np.ones(1000)
        self.assertIsNone(fn(1_000_000, d))
        d[500:] = 0.6
        self.assertEqual(500, fn(1_000_000, d))
        d[:100] = 0.1
        self.assertEqual(100, fn(1_000_000, d))

    def test_carryover(self):
        fn = factory({'type': 'edge', 'signal': 'current', 'condition': 'rising', 'value1': 0.75})
        d = np.ones(1000)
        d[-1] = 0.6
        self.assertIsNone(fn(1_000_000, d))
        d[:] = 1.0
        self.assertEqual(0, fn(1_000_000, d))

    def test_digital_rising(self):
        fn = factory({'type': 'edge', 'signal': '0', 'condition': 'rising'})
        d = np.zeros(1000, dtype=np.uint8)
        d[250:400] = 1
        d[500:700] = 1
        self.assertEqual(250, fn(1_000_000, d))
        self.assertEqual(500 - 300, fn(1_000_000, d[300:]))

    def test_digital_falling(self):
        fn = factory({'type': 'edge', 'signal': '0', 'condition': 'falling'})
        d = np.zeros(1000, dtype=np.uint8)
        d[250:400] = 1
        d[500:700] = 1
        self.assertEqual(400, fn(1_000_000, d))
        self.assertEqual(400 - 300, fn(1_000_000, d[300:]))

    def test_digital_both(self):
        fn = factory({'type': 'edge', 'signal': '0', 'condition': 'both'})
        d = np.zeros(1000, dtype=np.uint8)
        d[250:400] = 1
        d[500:700] = 1
        self.assertEqual(250, fn(1_000_000, d))
        self.assertEqual(400 - 300, fn(1_000_000, d[300:]))
