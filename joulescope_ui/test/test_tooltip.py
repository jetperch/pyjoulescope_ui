# Copyright 2023 Jetperch LLC
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
Test joulescope_ui.tooltip
"""

import unittest
from joulescope_ui.tooltip import tooltip_format


class TestTooltipFormat(unittest.TestCase):

    def test_simple(self):
        html = tooltip_format('hello', 'world')
        self.assertEqual('<html><head/><body><h3>hello</h3>\n<p>world</p></body></html>', html)

    def test_text_body(self):
        html = tooltip_format('header', 'hello\nthere\n\nworld\n')
        self.assertEqual('<html><head/><body><h3>header</h3>\n<p>hello\nthere</p>\n<p>world</p></body></html>', html)

    def test_text_body_no_newline_at_end(self):
        html = tooltip_format('header', 'hello\nthere\n\nworld')
        self.assertEqual('<html><head/><body><h3>header</h3>\n<p>hello\nthere</p>\n<p>world</p></body></html>', html)

    def test_html_body(self):
        html = tooltip_format('header', '<p>hello there</p><p>world</p>')
        self.assertEqual('<html><head/><body><h3>header</h3><p>hello there</p><p>world</p></body></html>', html)
