# Copyright 2020 Jetperch LLC
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
Test the UI units module.
"""

import unittest
from joulescope_ui import units
import numpy as np


class TestUnits(unittest.TestCase):

    def test_prefix_to_scale(self):
        self.assertEqual(1e3, units.prefix_to_scale('k'))
        self.assertEqual(1, units.prefix_to_scale(''))
        self.assertEqual(1e-3, units.prefix_to_scale('m'))
        self.assertEqual(1e-6, units.prefix_to_scale('µ'))
        self.assertEqual(1e-6, units.prefix_to_scale('u'))
        self.assertEqual(1e-6, units.prefix_to_scale('µ'))  # \u03BC greek small letter mu
        self.assertEqual(1e-9, units.prefix_to_scale('n'))

    def test_charge(self):
        self.assertEqual((1, 'C'), units.convert_units(1, 'C', 'SI'))
        self.assertEqual((1 / 3600, 'Ah'), units.convert_units(1, 'C', 'Xh'))

    def test_energy(self):
        self.assertEqual((1, 'J'), units.convert_units(1, 'J', 'J'))
        self.assertEqual((1 / 3600, 'Wh'), units.convert_units(1, 'J', 'Xh'))

    def test_elapsed_time_formatter(self):
        self.assertEqual(('1.00000', 's'), units.elapsed_time_formatter(1))
        self.assertEqual(('1', 's'), units.elapsed_time_formatter(1, trim_trailing_zeros=True))
        self.assertEqual(('1.10000', 's'), units.elapsed_time_formatter(1.1))
        self.assertEqual(('1.1', 's'), units.elapsed_time_formatter(1.1, trim_trailing_zeros=True))
        self.assertEqual(('1.1', 's'), units.elapsed_time_formatter(1.11111111111111, precision=2))
        self.assertEqual(('1.11111', 's'), units.elapsed_time_formatter(1.11111111111111))
        self.assertEqual(('1000.10', 's'), units.elapsed_time_formatter(1000.1))
        self.assertEqual(('2:01.000', 'm:ss'), units.elapsed_time_formatter(121, fmt='standard'))
        self.assertEqual(('2:01', 'm:ss'), units.elapsed_time_formatter(121, fmt='standard', precision=0))
        self.assertEqual(('20:01.00', 'mm:ss'), units.elapsed_time_formatter(1201, fmt='standard'))
        self.assertEqual(('1:02:03.00', 'h:mm:ss'), units.elapsed_time_formatter(3723, fmt='standard'))
        self.assertEqual(('2:05:49:44', 'D:hh:mm:ss'), units.elapsed_time_formatter(193784, fmt='standard'))

    def assertClose(self, expected, actual):
        np.testing.assert_almost_equal(expected[0], actual[0])
        self.assertEqual(expected[1], actual[1])
        np.testing.assert_almost_equal(expected[2], actual[2])

    def test_no_change(self):
        self.assertClose((0.0, '', 1), units.unit_prefix(0.0))
        self.assertClose((1.0, '', 1), units.unit_prefix(1.0))
        self.assertClose((5.0, '', 1), units.unit_prefix(5.0))

    def test_scaled(self):
        self.assertClose((10.0, 'G', 1e9), units.unit_prefix(10e9))
        self.assertClose((10.0, 'M', 1e6), units.unit_prefix(10e6))
        self.assertClose((10.0, 'k', 1e3), units.unit_prefix(10e3))
        self.assertClose((100.0, 'm', 0.001), units.unit_prefix(0.1))
        self.assertClose((100.0, 'µ', 0.000001), units.unit_prefix(0.0001))
        self.assertClose((10.0, 'n', 1e-9), units.unit_prefix(10e-9))
        self.assertClose((10.0, 'p', 1e-12), units.unit_prefix(10e-12))

    def test_three_sig_figs_no_units(self):
        self.assertEqual('1.50', units.three_sig_figs(1.5))
        self.assertEqual('150m', units.three_sig_figs(0.15))
        self.assertEqual('150µ', units.three_sig_figs(0.00015))
        self.assertEqual('1.50k', units.three_sig_figs(1500))
        self.assertEqual('1.50M', units.three_sig_figs(1500000))

    def test_three_sig_figs_with_units(self):
        self.assertEqual('1.50 A', units.three_sig_figs(1.5, 'A'))
        self.assertEqual('150 mA', units.three_sig_figs(0.15, 'A'))
        self.assertEqual('15.0 mA', units.three_sig_figs(0.015, 'A'))
        self.assertEqual('1.50 mA', units.three_sig_figs(0.0015, 'A'))
        self.assertEqual('150 µA', units.three_sig_figs(0.00015, 'A'))

    def test_three_sig_figs_boundary(self):
        self.assertEqual('1.00 A', units.three_sig_figs(1.0, 'A'))
        self.assertEqual('100 mA', units.three_sig_figs(0.10, 'A'))
        self.assertEqual('10.0 mA', units.three_sig_figs(0.010, 'A'))
        self.assertEqual('1.00 mA', units.three_sig_figs(0.0010, 'A'))
        self.assertEqual('100 µA', units.three_sig_figs(0.00010, 'A'))

    def test_convert_number(self):
        self.assertEqual(1, units.str_to_number('1'))
        self.assertEqual(-1, units.str_to_number('-1'))
        self.assertEqual(1000, units.str_to_number('1000'))
        self.assertEqual(1000, units.str_to_number('1k'))
        self.assertEqual(1000, units.str_to_number('1kOhm'))
        self.assertEqual(1000, units.str_to_number('1 kOhm'))
        self.assertEqual(1e-6, units.str_to_number('1uF'))

    def test_negative_numbers(self):
        self.assertEqual('-1.50 A', units.three_sig_figs(-1.5, 'A'))
        self.assertEqual('-150 mA', units.three_sig_figs(-0.15, 'A'))
        self.assertEqual('-15.0 mA', units.three_sig_figs(-0.015, 'A'))
        self.assertEqual('-1.50 mA', units.three_sig_figs(-0.0015, 'A'))
