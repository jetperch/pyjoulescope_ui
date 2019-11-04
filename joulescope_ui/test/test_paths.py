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
Test the paths
"""

import unittest
from joulescope_ui import paths
import json
import os
import shutil


class TestPaths(unittest.TestCase):

    def setUp(self):
        self.app = f'joulescope_unittest_{os.getpid()}'
        self.paths = paths.paths_current(app=self.app)

    def tearDown(self):
        for path in self.paths['dirs'].values():
            if os.path.isdir(path):
                shutil.rmtree(path)

    def test_contents(self):
        for d in paths.DIRS:
            self.assertIn(d, self.paths['dirs'])
        for f in paths.FILES:
            self.assertIn(f, self.paths['files'])

    def test_basic(self):
        for x in self.paths['dirs'].values():
            self.assertFalse(os.path.isdir(x))
        paths.initialize(self.paths)
        for x in self.paths['dirs'].values():
            self.assertTrue(os.path.isdir(x))
        paths.clear(self.app)
        for name, x in self.paths['dirs'].items():
            if name == 'data':
                self.assertTrue(os.path.isdir(x))
            else:
                self.assertFalse(os.path.isdir(x))

    def test_migrate_1_to_2(self):
        cfg = {'hello': 'world'}
        paths_old = paths.paths_v1(self.app)
        paths.initialize(paths_old)
        with open(paths_old['files']['config'], 'w') as f:
            json.dump(cfg, f)
        paths.migrate_1_to_2(self.app)
        for x in self.paths['dirs'].values():
            self.assertTrue(os.path.isdir(x))
