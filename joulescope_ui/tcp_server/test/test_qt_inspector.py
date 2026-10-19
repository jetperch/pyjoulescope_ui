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
from unittest import mock

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


class TestRoot(unittest.TestCase):
    """The inspector root, which paths and key events resolve against."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.inspector = QtInspector(pubsub=None)
        self.main = QtWidgets.QMainWindow()
        self.main.show()
        self.dialog = QtWidgets.QDialog(self.main)
        QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok, self.dialog).accepted.connect(
                self.dialog.accept)
        self.dialog.open()  # window modal, as the range tools open theirs
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.main.close()
        self.app.processEvents()

    def test_modal_dialog_without_active_window(self):
        # macOS never activates a UI that a background process launched
        # (the HIL farm runner), so activeWindow() stays None while the
        # dialog is open.  The dialog must still be the root.
        with mock.patch.object(QtWidgets.QApplication, 'activeWindow',
                               return_value=None):
            info = self.inspector._inspect({'path': '', 'max_depth': 0})
            self.assertEqual('QDialog', info['class'])
            self.inspector._action({'action': 'key', 'key': 'Return'})
        self.assertEqual(QtWidgets.QDialog.DialogCode.Accepted,
                         self.dialog.result())

    def test_main_window_without_dialog(self):
        self.dialog.close()
        self.app.processEvents()
        with mock.patch.object(QtWidgets.QApplication, 'activeWindow',
                               return_value=None):
            info = self.inspector._inspect({'path': '', 'max_depth': 0})
        self.assertEqual('QMainWindow', info['class'])
