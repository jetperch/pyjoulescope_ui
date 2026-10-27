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
Test joulescope_ui.range_tools.max_window.
"""

import unittest

import numpy as np
from joulescope_ui.range_tools.max_window import max_window_index


class TestMaxWindowIndex(unittest.TestCase):

    def test_peak_in_middle(self):
        data = np.zeros(1000, dtype=np.float32)
        data[600:610] = 1.0
        self.assertEqual(600, max_window_index(data, 10))

    def test_peak_at_start_and_end(self):
        data = np.zeros(100, dtype=np.float32)
        data[:5] = 1.0
        self.assertEqual(0, max_window_index(data, 5))
        data[:] = 0.0
        data[-5:] = 1.0
        self.assertEqual(95, max_window_index(data, 5))

    def test_negative_values(self):
        data = -np.ones(50, dtype=np.float32)
        data[20:23] = -0.5
        self.assertEqual(20, max_window_index(data, 3))

    def test_matches_brute_force(self):
        data = np.random.default_rng(1).normal(size=2000).astype(np.float32)
        width = 37
        sums = [np.sum(data[i:i + width], dtype=np.float64) for i in range(len(data) - width + 1)]
        self.assertEqual(int(np.argmax(sums)), max_window_index(data, width))


if __name__ == '__main__':
    unittest.main()
