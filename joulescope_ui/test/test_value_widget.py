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
Test joulescope_ui.widgets.value.value_widget
"""

import os
import types
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from joulescope_ui.widgets.value.value_widget import _BaseWidget, _InnerWidget


class TestInnerWidget(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance()
        if cls._app is None:
            cls._app = QtWidgets.QApplication([])

    def test_statistics_schedules_paint(self):
        """Statistics must not paint synchronously on the Qt main thread."""
        widget = _InnerWidget(None)
        try:
            with mock.patch.object(widget, 'repaint') as repaint, \
                    mock.patch.object(widget, 'update') as update:
                widget._on_statistics({'time': {}})
            repaint.assert_not_called()
            update.assert_called_once_with()
        finally:
            widget.deleteLater()

    def test_displayed_text(self):
        inner = types.SimpleNamespace(_geometry={
            ('current', 'avg'): ((0, 0), (1, 1), '+1.23456 mA'),
            ('charge', 'duration'): ((0, 0), (1, 1), '5 s'),
        })
        widget = types.SimpleNamespace(_inner=inner)
        self.assertEqual({'current.avg': '+1.23456 mA', 'charge.duration': '5 s'},
                         _BaseWidget.displayed_text(widget))
        self.assertEqual({}, _BaseWidget.displayed_text(
            types.SimpleNamespace(_inner=types.SimpleNamespace(_geometry=None))))
