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
Test joulescope_ui.versioned_file
"""

import unittest
from joulescope_ui import versioned_file
import tempfile
import os
import shutil


class TestVersionedFile(unittest.TestCase):

    def setUp(self):
        self._path = tempfile.mkdtemp(prefix='jsuitvf_')

    def tearDown(self) -> None:
        shutil.rmtree(self._path)

    def test_write_revert(self):
        path = os.path.join(self._path, 'myfile.txt')
        self.assertFalse(os.path.isfile(path))
        for n in range(20):
            with versioned_file.open(path, 'wt') as f:
                f.write(str(n))
        for n in range(19, 9, -1):
            with versioned_file.open(path, 'rt') as f:
                self.assertEqual(str(n), f.read())
            versioned_file.revert(path)

        versioned_file.revert(path)
        self.assertFalse(os.path.isfile(path))

    def test_remove(self):
        path = os.path.join(self._path, 'myfile.txt')
        for n in range(20):
            with versioned_file.open(path, 'wt') as f:
                f.write(str(n))
        versioned_file.remove(path)
        self.assertFalse(os.path.isfile(path))
        self.assertFalse(os.path.isfile(versioned_file.version_path(path, 1)))
        versioned_file.remove(path)

    def test_revertN(self):
        path = os.path.join(self._path, 'myfile.txt')
        self.assertFalse(os.path.isfile(path))
        for n in range(20):
            with versioned_file.open(path, 'wt') as f:
                f.write(str(n))
        versioned_file.revert(path, 5)
        with versioned_file.open(path, 'rt') as f:
            self.assertEqual(str(14), f.read())

    def test_version_count_0(self):
        path = os.path.join(self._path, 'myfile.txt')
        with versioned_file.open(path, 'wt', version_count=0) as f:
            f.write('hello world')
        self.assertTrue(os.path.isfile(path))
        versioned_file.revert(path)
        self.assertFalse(os.path.isfile(path))

    def test_remove_revert(self):
        path = os.path.join(self._path, 'myfile.txt')
        for n in range(2):
            with versioned_file.open(path, 'wt') as f:
                f.write(str(n))
        os.remove(path)
        versioned_file.revert(path)
        with versioned_file.open(path, 'rt') as f:
            self.assertEqual('0', f.read())
