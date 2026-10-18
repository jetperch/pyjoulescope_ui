# Copyright 2026 Jetperch LLC
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
Test joulescope_ui.tcp_server.bridge
"""

import asyncio
import unittest
from unittest import mock
from joulescope_ui.tcp_server import bridge
from joulescope_ui.tcp_server.protocol import MSG_QT_INSPECT


class _Server:

    def __init__(self):
        self.frames = []

    def send_to_client(self, client, frame):
        self.frames.append(frame)


class _StalledInspector:
    """Never completes the request, like a blocked Qt main thread."""

    def dispatch(self, msg_type, header, payload, future):
        pass


class TestQtTimeout(unittest.TestCase):

    def test_timeout_message(self):
        server = _Server()
        b = bridge.PubSubBridge(None, server)
        b._qt_inspector = _StalledInspector()
        with mock.patch.object(bridge, '_QT_TIMEOUT', 0.05):
            asyncio.run(b._handle_qt('client', MSG_QT_INSPECT, {'id': 7}, b''))
        self.assertEqual(1, len(server.frames))
        self.assertIn(b'Qt main thread did not respond within 0.05 s', server.frames[0])
        self.assertIn(b'"id":7', server.frames[0])
