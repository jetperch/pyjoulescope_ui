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

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from joulescope_ui.ui_util import prepare_for_opengl


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
