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
Test the capabilities
"""

import unittest
from joulescope_ui.capabilities import CAPABILITIES


class TestCapabilities(unittest.TestCase):

    def test_basic(self):
        self.assertEqual('signal_stream.source', CAPABILITIES.SIGNAL_STREAM_SOURCE.value)
        self.assertEqual('signal_stream.source', str(CAPABILITIES.SIGNAL_STREAM_SOURCE))

    def test_in(self):
        self.assertEqual('widget.class', str(CAPABILITIES('widget.class')))
        with self.assertRaises(ValueError):
            CAPABILITIES('invalid')
