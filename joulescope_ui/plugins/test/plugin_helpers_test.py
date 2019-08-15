# Copyright 2019 Jetperch LLC
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
Test the plugin_helpers module.
"""

import unittest
from joulescope_ui.plugins import plugin_helpers
import numpy as np


class RangeToolIterate:

    def __init__(self, data, signal, samples_per_iteration):
        self._data = data
        self._signal = signal
        self._samples_per_iteration = 10 if samples_per_iteration is None else int(samples_per_iteration)
        self._x_next = 0
        self._x_stop = len(data)

    def __iter__(self):
        return self

    def __next__(self):
        if self._x_next >= self._x_stop:
            raise StopIteration()
        x_next = self._x_next + self._samples_per_iteration
        if x_next > self._x_stop:
            x_next = self._x_stop
        data = {self._signal: {'value': self._data[self._x_next: x_next]}}
        self._x_next = x_next
        return data


class RangeToolData:

    def __init__(self, data, signal):
        self._data = data
        self._signal = signal
        self.sample_count = len(data)
        self.sample_frequency = 2000000.0

    def __iter__(self):
        self._iterable = self.iterate()
        return self._iterable

    def __next__(self):
        try:
            return self._iterable.__next__()
        except StopIteration:
            self._iterable = None
            raise

    def iterate(self, samples_per_iteration=None):
        return RangeToolIterate(data=self._data, signal=self._signal, samples_per_iteration=samples_per_iteration)

    def progress(self, fraction):
        pass

    def samples_get(self):
        return {self._signal: {'value': self._data}}

    def marker_single_add(self, x):
        pass

    def marker_dual_add(self, x1, x2):
        pass


class TestPluginHelpers_max_sum_in_window(unittest.TestCase):

    def test_constant(self):
        d = RangeToolData(np.zeros(100000), 'current')
        v, start, end = plugin_helpers.max_sum_in_window(d, 'current', 0.001)
        self.assertEqual(0, start)
        self.assertEqual(2000, end)

    def test_monotonic(self):
        d = RangeToolData(np.arange(100000), 'current')
        v, start, end = plugin_helpers.max_sum_in_window(d, 'current', 0.001)
        self.assertEqual(100000 - 1 - 2000, start)
        self.assertEqual(100000 - 1, end)

    def test_peak(self):
        d = RangeToolData(np.sin(np.pi * np.arange(100000) / 100000), 'current')
        v, start, end = plugin_helpers.max_sum_in_window(d, 'current', 0.001)
        self.assertEqual(50000 - 1000, start)
        self.assertEqual(50000 + 1000, end)

    @unittest.SkipTest
    def test_timeit(self):
        import timeit
        d = RangeToolData(np.zeros(100000), 'current')
        t = timeit.timeit(lambda: plugin_helpers.max_sum_in_window(d, 'current', 0.001), number=10)
        print(t)
