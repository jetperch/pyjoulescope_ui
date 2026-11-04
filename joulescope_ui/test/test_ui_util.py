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
Test joulescope_ui.ui_util
"""

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from joulescope_ui.ui_util import NormalSizeTracker, prepare_for_opengl


class TestPrepareForOpengl(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance()
        if cls._app is None:
            cls._app = QtWidgets.QApplication([])

    def setUp(self):
        self.widget = QtWidgets.QWidget()

    def tearDown(self):
        self.widget.deleteLater()

    def _dummies(self):
        return [c for c in self.widget.children() if isinstance(c, QOpenGLWidget)]

    def test_adds_invisible_opengl_child(self):
        dummy = prepare_for_opengl(self.widget)
        self.assertIsInstance(dummy, QOpenGLWidget)
        self.assertIs(dummy.parent(), self.widget)
        self.assertFalse(dummy.isVisible())
        self.assertEqual([dummy], self._dummies())

    def test_idempotent(self):
        dummy1 = prepare_for_opengl(self.widget)
        dummy2 = prepare_for_opengl(self.widget)
        self.assertIs(dummy1, dummy2)
        self.assertEqual(1, len(self._dummies()))


class TestNormalSizeTracker(unittest.TestCase):

    def setUp(self):
        self.window = Mock()
        self.t = NormalSizeTracker(self.window)

    def _resize(self, width, height, is_normal=True):
        self.t.on_resize(width, height, is_normal)

    def test_resize_available_before_settle(self):
        self._resize(1000, 700)
        self.assertEqual([1000, 700], self.t.size)
        self.t.settle()
        self.assertEqual([1000, 700], self.t.size)

    def test_window_manager_maximize_resize_ignored(self):
        self._resize(1000, 700)
        self.t.settle()
        self._resize(1920, 1048)  # arrives before the state change
        self.t.on_state(False)
        self.assertEqual([1000, 700], self.t.size)

    def test_resize_while_maximized_ignored(self):
        self._resize(1000, 700)
        self.t.settle()
        self.t.on_state(False)
        self._resize(1920, 1048, is_normal=False)
        self.assertEqual([1000, 700], self.t.size)

    def test_leaving_maximized_applies_size(self):
        self._resize(1000, 700)
        self.t.settle()
        self.t.on_state(False)
        self.window.resize.assert_not_called()
        self.t.on_state(True)
        self.window.resize.assert_called_once_with(1000, 700)

    def test_normal_state_does_not_resize(self):  # a user drag must not fight this
        self._resize(1000, 700)
        self.t.settle()
        self.t.on_state(True)
        self.window.resize.assert_not_called()

    def test_view_restore_while_maximized(self):
        self.t.on_state(False)
        self.t.size = [800, 600]
        self.t.on_state(True)
        self.window.resize.assert_called_once_with(800, 600)

    def test_set_replaces_pending(self):
        self._resize(1920, 1048)
        self.t.size = [800, 600]
        self.t.settle()
        self.assertEqual([800, 600], self.t.size)

    def test_unknown_size(self):
        self.t.size = None
        self.assertIsNone(self.t.size)
        self.t.on_state(False)
        self.t.on_state(True)
        self.window.resize.assert_not_called()
