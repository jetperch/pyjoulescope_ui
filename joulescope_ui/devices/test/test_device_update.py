# Copyright 2024 Jetperch LLC
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
Test the device update module.
"""

import unittest
from joulescope_ui.devices.device_update import is_js220_update_available


class TestDeviceUpdate(unittest.TestCase):

    def test_js220_update_available_empty(self):
        self.assertFalse(is_js220_update_available(None))
        self.assertFalse(is_js220_update_available({}))

    def test_js220_update_available_false(self):
        self.assertFalse(is_js220_update_available({'fw': ['1.2.1', '1.2.1'], 'fpga': ['1.2.1', '1.2.1']}))
        self.assertFalse(is_js220_update_available({'fw': ['1.3.0', '1.2.1'], 'fpga': ['2.2.1', '1.2.1']}))

    def test_js220_update_available_true(self):
        self.assertTrue(is_js220_update_available({'fw': ['1.2.0', '1.2.1'], 'fpga': ['1.2.1', '1.2.1']}))
        self.assertTrue(is_js220_update_available({'fw': ['1.1.1', '1.2.1'], 'fpga': ['1.2.1', '1.2.1']}))
        self.assertTrue(is_js220_update_available({'fw': ['1.2.1', '2.2.1'], 'fpga': ['1.2.1', '1.2.1']}))
        self.assertTrue(is_js220_update_available({'fw': ['1.2.0', '1.2.1'], 'fpga': ['1.2.1', '2.2.1']}))
