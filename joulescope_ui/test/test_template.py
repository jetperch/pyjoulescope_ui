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
Test the CSS template.
"""

import unittest
from joulescope_ui.template import render


class TestTemplate(unittest.TestCase):

    def test_simple(self):
        self.assertEqual('world', render('{%hello%}', hello='world'))
        self.assertEqual('world', render('{% hello%}', hello='world'))
        self.assertEqual('world', render('{%hello %}', hello='world'))
        self.assertEqual('world', render('{%   hello   %}', hello='world'))

    def test_multiple_replace(self):
        self.assertEqual('1 2 1', render('{% a %} {% b %} {%a%}', a='1', b='2'))

    def test_argument_not_found(self):
        with self.assertRaises(KeyError):
            render('{% a %}')

    def test_argument_not_used(self):
        self.assertEqual('1', render('{% a %}', a='1', b='2'))
