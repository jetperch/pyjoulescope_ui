# Copyright 2019-2023 Jetperch LLC
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
Test the software update file
"""

import unittest
from joulescope_ui import software_update


class TestUpdateCheck(unittest.TestCase):

    def test_is_newer(self):
        software_update.__version__ = "1.2.3"
        self.assertTrue(software_update.is_newer("1.2.4"))
        self.assertTrue(software_update.is_newer("1.3.0"))
        self.assertTrue(software_update.is_newer("2.0.0"))
        self.assertFalse(software_update.is_newer("1.2.3"))
        self.assertFalse(software_update.is_newer("1.2.2"))
        self.assertFalse(software_update.is_newer("1.1.4"))
        self.assertFalse(software_update.is_newer("0.9.9"))

    def test_fetch_invalid_channel(self):
        software_update.__version__ = "999999.0.0"
        with self.assertRaises(ValueError):
            software_update.fetch_info('__INVALID__')

    def test_fetch_no_update(self):
        software_update.__version__ = "999999.0.0"
        self.assertIsNone(software_update.fetch_info())
        self.assertIsNone(software_update.fetch_info('alpha'))
        self.assertIsNone(software_update.fetch_info('beta'))
        self.assertIsNone(software_update.fetch_info('stable'))

    def test_has_update(self):
        software_update.__version__ = "0.0.0"
        result = software_update.fetch_info()
        self.assertIsNotNone(result)
        self.assertEqual(software_update.__version__, result['current_version'])
