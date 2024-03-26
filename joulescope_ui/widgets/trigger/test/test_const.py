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


class TestConditionDetectorConst(unittest.TestCase):

    def test_always(self):
        fn = factory({'type': 'duration', 'signal': 'always', 'duration': 0.001})
        self.assertEqual(1000, fn(1_000_000, np.zeros(2000)))

    def test_always_in_parts(self):
        fn = factory({'type': 'duration', 'signal': 'always', 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, np.zeros(800)))
        self.assertEqual(200, fn(1_000_000, np.zeros(800)))

    def test_never(self):
        fn = factory({'type': 'duration', 'signal': 'never', 'duration': 0.001})
        self.assertIsNone(fn(1_000_000, np.zeros(2000)))
