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

"""Test the QtInspector actions that do not require a live UI."""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from joulescope_ui.tcp_server.qt_inspector import QtInspector


class TestCursorAction(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.inspector = QtInspector(pubsub=None)

    def test_cursor_reports_position(self):
        result = self.inspector._action({'action': 'cursor'})
        self.assertTrue(result['ok'])
        self.assertEqual('cursor', result['action'])
        self.assertEqual(2, len(result['pos']))
        self.assertIn('widget', result)

    def test_cursor_widget_under_cursor(self):
        w = QtWidgets.QWidget()
        w.setObjectName('cursor_target')
        w.setGeometry(0, 0, 4000, 4000)  # covers any offscreen cursor position
        w.show()
        self.app.processEvents()
        try:
            result = self.inspector._action({'action': 'cursor'})
            self.assertTrue(result['ok'])
            if result['widget'] is not None:  # offscreen platform dependent
                self.assertEqual('cursor_target', result['widget']['objectName'])
                self.assertEqual(2, len(result['widget']['window_local']))
        finally:
            w.close()
