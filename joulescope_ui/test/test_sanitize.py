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

"""
Test joulescope_ui.sanitize
"""

import unittest
from joulescope_ui import sanitize


class TestStrToFilename(unittest.TestCase):

    def test_valid(self):
        valid_filenames = [
            'hello',
            'hello_world',
            'unicode_\u00b1\u26a0',
            'unicode_\u03A9',
        ]
        for s in valid_filenames:
            self.assertEqual(s, sanitize.str_to_filename(s))

    def test_normalized(self):
        conversions = [
            ['\u00B5', '\u03BC'],
        ]
        for s, expect in conversions:
            self.assertEqual(expect, sanitize.str_to_filename(s))

    def test_invalid(self):
        conversions = [
            ['hello/there\\world', 'hello_there_world'],
            ['hello world', 'hello_world'],
            ['hello.world', 'hello_world'],
            ['../../world', '______world'],
            ['hello<>world', 'hello__world'],
            ['?%*:|"world', '______world'],
            ['hello\x00world\x10\x1f', 'hello_world__'],
        ]
        for s, expect in conversions:
            self.assertEqual(expect, sanitize.str_to_filename(s))

    def test_truncate_default(self):
        s_in = 'h' * 1024
        s = sanitize.str_to_filename(s_in)
        self.assertEqual(255 - 16, len(s))
        self.assertEqual(s_in[:175], s[:175])
        self.assertNotEqual(s_in, s)

    def test_truncate_short(self):
        s = sanitize.str_to_filename('h' * 256, maxlen=16)
        self.assertEqual(16, len(s))
        self.assertNotEqual('h' * 16, s)

    def test_windows_reserved(self):
        conversions = [
            ['CON', '_CON'],
            ['con', '_con'],
            ['cOn', '_cOn'],
            ['CON.txt', 'CON_txt'],
        ]
        for s, expect in conversions:
            self.assertEqual(expect, sanitize.str_to_filename(s))

    def test_leading_dash(self):
        self.assertEqual('_-hello', sanitize.str_to_filename('--hello'))
