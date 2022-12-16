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
from joulescope_ui.styles import color_file

f1 = """\
# Comment 1
color.red = #ff0000
color.green = #00ff00
color.blue = #0000FF
transparent.blue = #0000F080

# Comment 2
color.comment = #ffffff   # with a comment
"""


class TestColorFile(unittest.TestCase):

    def test_parser_basics(self):
        self.assertEqual({}, color_file.parse_str(''))
        self.assertEqual({}, color_file.parse_str('# comment\n'))
        self.assertEqual({'red': '#ff0000ff'}, color_file.parse_str('red = #ff0000\n'))
        self.assertEqual({'red': '#ff0000ff'}, color_file.parse_str('red = #ff0000ff\n'))
        self.assertEqual({'red': '#ff0000ff'}, color_file.parse_str('red = #ff0000   # comment\n'))
        self.assertEqual({'red': '#ff0000ff'}, color_file.parse_str('   red   =    #ff0000   # comment   \n'))
        self.assertEqual({'red': '#ff0000ff'}, color_file.parse_str('red=#ff0000# comment\n'))

    def test_parser_invalid_lines(self):
        with self.assertRaises(ValueError):
            color_file.parse_str('Hi')
        with self.assertRaises(ValueError):
            color_file.parse_str('hi = ')
        with self.assertRaises(ValueError):
            color_file.parse_str(' = #ff0000')
        with self.assertRaises(ValueError):
            color_file.parse_str('hi = #ff')
        with self.assertRaises(ValueError):
            color_file.parse_str('hi = #fffffff')
        with self.assertRaises(ValueError):
            color_file.parse_str('hi = #12345z')

    def test_updater_basic(self):
        colors = {
            'red': '#800000',
            'green': '#008000',
            'blue': '#000080',
        }
        self.assertEqual('# comment\n', color_file.update_str('# comment\n', colors))
        self.assertEqual('red = #800000\n', color_file.update_str('red = #ff0000\n', colors))
        self.assertEqual('  red  =  #800000  \n', color_file.update_str('  red  =  #ff0000  \n', colors))
        self.assertEqual('  red  =  #800000  # c \n', color_file.update_str('  red  =  #ff0000  # c \n', colors))
        self.assertEqual('red=#800000\ngreen=#008000\n', color_file.update_str('red=#ff0000\ngreen=#00ff00\n', colors))

