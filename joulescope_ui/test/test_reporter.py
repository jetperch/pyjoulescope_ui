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
Test joulescope_ui.reporter
"""

import unittest
from joulescope_ui import reporter
import os


class TestReporter(unittest.TestCase):

    def test_create(self):
        path = reporter.create('user', description='my description')
        self.assertTrue(os.path.isfile(path))
        if False:
            reporter.publish()
            self.assertFalse(os.path.isfile(path))
        else:
            os.remove(path)

    def test_create_from_exception(self):
        try:
            raise RuntimeError('hi there!')
        except RuntimeError as ex:
            path = reporter.create('crash', exception=ex)
        self.assertTrue(os.path.isfile(path))
        reporter.update_description(path, 'my description')
        # os.remove(path)
