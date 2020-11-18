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


class TestUnits(unittest.TestCase):

    def test_charge(self):
        self.assertEqual({'value': 1, 'units': 'C'}, units.convert_units(1, 'C', 'C'))
        self.assertEqual({'value': 1 / 3600, 'units': 'Ah'}, units.convert_units(1, 'C', 'Ah'))
        self.assertEqual({'value': 1, 'units': 'Ah'}, units.convert_units(1, 'Ah', 'Ah'))
        self.assertEqual({'value': 3600, 'units': 'C'}, units.convert_units(1, 'Ah', 'C'))

    def test_energy(self):
        self.assertEqual({'value': 1, 'units': 'J'}, units.convert_units(1, 'J', 'J'))
        self.assertEqual({'value': 1 / 3600, 'units': 'Wh'}, units.convert_units(1, 'J', 'Wh'))
        self.assertEqual({'value': 1, 'units': 'Wh'}, units.convert_units(1, 'Wh', 'Wh'))
        self.assertEqual({'value': 3600, 'units': 'J'}, units.convert_units(1, 'Wh', 'J'))

    def test_elapsed_time_formatter(self):
        self.assertEqual('1 s', units.elapsed_time_formatter(1))
        self.assertEqual('1000 s', units.elapsed_time_formatter(1000.1))
        self.assertEqual('2:01', units.elapsed_time_formatter(121, fmt='standard'))
        self.assertEqual('20:01', units.elapsed_time_formatter(1201, fmt='standard'))
        self.assertEqual('1:02:03', units.elapsed_time_formatter(3723, fmt='standard'))
        self.assertEqual('1:02:03:04', units.elapsed_time_formatter(93784, fmt='standard'))
