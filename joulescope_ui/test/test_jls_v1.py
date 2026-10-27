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
Test joulescope_ui.jls_v1.
"""

import logging
import unittest

import numpy as np
from joulescope_ui import time64
from joulescope_ui.jls_v1 import JlsV1
from joulescope_ui.range_tool import rsp_as_f32
from joulescope_ui.time_map import TimeMap


def _jls_v1(signals):
    """A JlsV1 whose reader returns ``signals`` (name -> array) for any range."""
    v1 = JlsV1.__new__(JlsV1)
    v1._log = logging.getLogger(__name__)
    v1._jls = object()
    v1._time_map = TimeMap()
    v1._time_map.update(0, 0, 1000 / time64.SECOND)
    v1._samples_get_inner = lambda start, end: {
        'signals': {name: {'value': value[start:end]} for name, value in signals.items()}}
    return v1


class TestJlsV1(unittest.TestCase):

    def _samples(self, quantity, data):
        name = {'i': 'current', 'r': 'current_range', '0': 'current_lsb'}[quantity]
        v1 = _jls_v1({name: data})
        return v1.process({'signal_id': f'JlsSource:1.dev.{quantity}', 'time_type': 'samples',
                           'start': 0, 'end': 0, 'length': 4})

    def test_float_samples_data_type(self):
        rsp = self._samples('i', np.arange(10, dtype=np.float32))
        self.assertEqual('f32', rsp['data_type'])

    def test_uint8_samples_data_type(self):
        # The exporter declares the JLS signal type from data_type, so it must
        # match the uint8 data, or writing the samples raises.
        for quantity in ['r', '0']:
            rsp = self._samples(quantity, np.arange(10, dtype=np.uint8))
            self.assertEqual('u8', rsp['data_type'])
            np.testing.assert_array_equal(np.arange(4, dtype=np.uint8), rsp_as_f32(rsp))


if __name__ == '__main__':
    unittest.main()
