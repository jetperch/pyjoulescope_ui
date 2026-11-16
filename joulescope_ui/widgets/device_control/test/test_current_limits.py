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

"""Test the current range limits widget."""

import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6 import QtWidgets
from joulescope_ui.widgets.device_control.current_limits import CurrentLimits


class TestCurrentLimits(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_values_set_either_order(self):
        w = CurrentLimits(None)
        changes = []
        w.values_changed.connect(lambda v0, v1: changes.append(sorted([v0, v1])))
        for value in ([0, 5], [5, 0], [1, 3], [3, 1]):
            w.values_set(value)
            self.assertEqual(sorted(value, reverse=True), list(w.values))
        # the published [low, high] form matches the setting default [0, 5]
        self.assertTrue(all(c == sorted(c) for c in changes))
        w.close()
