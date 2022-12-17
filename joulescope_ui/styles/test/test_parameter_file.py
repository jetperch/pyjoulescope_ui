# Copyright 2022 Jetperch LLC
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

import unittest
from joulescope_ui.styles import parameter_file as pf


class TestFontFile(unittest.TestCase):

    def test_parser_basics(self):
        self.assertEqual({}, pf.parse_str(''))
        self.assertEqual({}, pf.parse_str('# comment\n'))
        self.assertEqual({'font': 'bold 24 Arial'}, pf.parse_str('font = bold 24 Arial\n'))
        self.assertEqual({'font': 'bold 24 Arial'}, pf.parse_str('   font   =   bold 24 Arial   \n'))
        self.assertEqual({'font': 'bold 24 Arial'}, pf.parse_str('font = bold 24 Arial   # comment\n'))
        self.assertEqual({'font': 'bold 24 Arial'}, pf.parse_str('   font = bold 24 Arial   # comment   \n'))

    def test_updater_basic(self):
        p = {
            'font1': 'bold 24 Arial',
            'font2': 'bold 26 Arial',
            'font3': 'bold 28 Arial',
        }
        self.assertEqual('# comment\n', pf.update_str('# comment\n', p))
        self.assertEqual('font1 = bold 24 Arial\n', pf.update_str('font1 = value\n', p))
        self.assertEqual('  font1  =  bold 24 Arial  \n', pf.update_str('  font1  =  value  \n', p))
        self.assertEqual('  font1  =  bold 24 Arial  # c \n', pf.update_str('  font1  =  value  # c \n', p))
        self.assertEqual('font1=bold 24 Arial\nfont2=bold 26 Arial\n',
                         pf.update_str('font1=v1\nfont2=v2\n', p))
