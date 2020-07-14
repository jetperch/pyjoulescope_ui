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
Test the theme manager
"""

import shutil
import tempfile
import unittest
from joulescope_ui.themes import manager as mgr


class TestThemeManager(unittest.TestCase):

    def test_theme_name_parser(self):
        self.assertEqual(('theme', 'name'), mgr.theme_name_parser('theme.name'))
        self.assertEqual(('theme', 'name'), mgr.theme_name_parser('theme', 'name'))
        self.assertEqual(('theme', 'name'), mgr.theme_name_parser('theme.warning', 'name'))

    def test_theme_name_parser_invalid(self):
        with self.assertRaises(ValueError):
            mgr.theme_name_parser(None)
        with self.assertRaises(ValueError):
            mgr.theme_name_parser('')
        with self.assertRaises(ValueError):
            mgr.theme_name_parser('hello.there.world')

    def test_theme_index(self):
        index = mgr.theme_source_index('js1')
        self.assertEqual('js1', index['name'])
        self.assertIn('images', index)
        self.assertIn('colors', index)

    def test_theme_index_invalid(self):
        with self.assertRaises(ValueError):
            mgr.theme_source_index('__invalid__')


class TestThemeLoader(unittest.TestCase):

    def setUp(self):
        self.path = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.path, ignore_errors=True)

    def test_generate(self):
        mgr.theme_loader('js1', 'default', target_path=self.path)
