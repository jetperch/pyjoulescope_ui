# Copyright 2024 Jetperch LLC
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
Test the quantities
"""

import unittest
from joulescope_ui.widgets.waveform.quantities import quantities_format


_VALUES = {
    'avg': (0.005, 'A'),
    'min': (0.004, 'A'),
    'max': (0.006, 'A'),
    'p2p': (0.002, 'A'),
}


class TestQuantities(unittest.TestCase):

    def test_empty(self):
        v = quantities_format([], _VALUES)
        self.assertEqual(0, len(v))

    def test_quantity_missing(self):
        v = quantities_format(['__invalid__'], _VALUES)
        self.assertEqual(0, len(v))

    def test_single(self):
        v = quantities_format(['avg'], _VALUES)
        self.assertEqual([('avg', '+5.00000', 'mA')], v)

    def test_multiple(self):
        v = quantities_format(['p2p', 'min', 'avg', 'max'], _VALUES)
        self.assertEqual([
                ('p2p', '+2.00000', 'mA'),
                ('min', '+4.00000', 'mA'),
                ('avg', '+5.00000', 'mA'),
                ('max', '+6.00000', 'mA'),
            ],
            v)

    def test_preferred(self):
        self.assertEqual([('avg', '+5000.00', 'µA')], quantities_format(['avg'], _VALUES, prefix_preferred='µ'))
        self.assertEqual([('avg', '+5.00000', 'mA')], quantities_format(['avg'], _VALUES, prefix_preferred='n'))
        self.assertEqual([('avg', '+0.00500', 'A')], quantities_format(['avg'], _VALUES, prefix_preferred=''))

    def test_precision(self):
        self.assertEqual([('avg', '+5.00', 'mA')], quantities_format(['avg'], _VALUES, precision=3))
        self.assertEqual([('avg', '+5.000', 'mA')], quantities_format(['avg'], _VALUES, precision=4))
        self.assertEqual([('avg', '+5.0000', 'mA')], quantities_format(['avg'], _VALUES, precision=5))
        self.assertEqual([('avg', '+5.00000', 'mA')], quantities_format(['avg'], _VALUES, precision=6))
        self.assertEqual([('avg', '+50.0', 'mA')], quantities_format(['avg'], {'avg': (0.05, 'A')}, precision=3))
        self.assertEqual([('avg', '+500', 'mA')], quantities_format(['avg'], {'avg': (0.5, 'A')}, precision=3))
        self.assertEqual([('avg', '+5.00', 'A')], quantities_format(['avg'], {'avg': (5, 'A')}, precision=3))
