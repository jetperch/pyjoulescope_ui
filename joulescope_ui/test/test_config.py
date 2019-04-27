# Copyright 2018 Jetperch LLC
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
Test the configuration file
"""

import unittest
import os
import io
import tempfile
import shutil
from joulescope_ui.config import load_config_def, load_config, save_config

MYPATH = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.dirname(MYPATH)


def load_def():
    path = os.path.join(PATH, 'config_def.json5')
    return load_config_def(path)


class TestConfig(unittest.TestCase):

    def test_load_config_def(self):
        d = load_def()
        self.assertIn('info', d)
        self.assertIn('children', d)

    def test_load_config_def_default(self):
        d = load_config_def()
        self.assertIn('info', d)
        self.assertIn('children', d)

    def test_file_not_found(self):
        d = load_def()
        c = load_config(d, '/path/to/nothing.json5')
        self.assertIn('General', c)
        self.assertIn('data_path', c['General'])
        self.assertNotEqual('__APP_PATH__', c['General']['data_path'])
        self.assertIn('Device', c)
        self.assertIn('i_range', c['Device'])
        self.assertEqual('auto', c['Device']['i_range'])

    def test_load_filehandle(self):
        d = load_def()
        f = io.BytesIO("""{'Device': {'i_range': 'auto'}}""".encode('utf-8'))
        c = load_config(d, f)
        self.assertEqual('auto', c['Device']['i_range'])

    def test_load_bad_option(self):
        d = load_def()
        f = io.BytesIO("""{'Device': {'i_range': '__invalid__'}}""".encode('utf-8'))
        with self.assertRaises(ValueError):
            c = load_config(d, f)

    def test_load_default(self):
        d = load_def()
        f = io.BytesIO("""{'Device': {}}""".encode('utf-8'))
        c = load_config(d, f)
        self.assertEqual('auto', c['Device']['i_range'])

    def test_load_alias(self):
        d = load_def()
        f = io.BytesIO("""{'Device': {'i_range': '2'}}""".encode('utf-8'))
        c = load_config(d, f)
        self.assertEqual('180 mA', c['Device']['i_range'])

    def test_filename(self):
        d = load_def()
        fname = os.path.join(MYPATH, 'cfg1.json5')
        c = load_config(d, fname)
        self.assertEqual('180 mA', c['Device']['i_range'])


class TestConfigSave(unittest.TestCase):

    def setUp(self):
        self._tempdir = tempfile.mkdtemp()
        self._filename1 = os.path.join(self._tempdir, 'joulescope_config.json5')

    def tearDown(self):
        shutil.rmtree(self._tempdir)

    def test_load_save_load_path(self):
        d = load_def()
        fname = os.path.join(MYPATH, 'cfg1.json5')
        c1 = load_config(d, fname)
        save_config(c1, self._filename1)
        c2 = load_config(d, self._filename1)
        self.assertEqual(c1, c2)

    def test_load_save_load_filehandle(self):
        d = load_def()
        fname = os.path.join(MYPATH, 'cfg1.json5')
        c1 = load_config(d, fname)
        with open(self._filename1, 'w') as f:
            save_config(c1, f)
        with open(self._filename1, 'r') as f:
            c2 = load_config(d, f)
        self.assertEqual(c1, c2)
