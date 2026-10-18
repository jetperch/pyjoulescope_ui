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
Test joulescope_ui.widgets.waveform.waveform_widget
"""

import os
import types
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6 import QtWidgets
from joulescope_ui.widgets.waveform.waveform_widget import WaveformWidget, _PlotOpenGLWidget


class _Parent(QtWidgets.QWidget):
    pass


class TestWaveformWidgetRender(unittest.TestCase):
    """Rendering limits  #352."""

    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance()
        if cls._app is None:
            cls._app = QtWidgets.QApplication([])

    def _y_value_to_pixel(self, value):
        plot = {'y_map': (100, 1.0, 400.0)}  # y0=100 px at 1.0, 400 px per unit
        return WaveformWidget._y_value_to_pixel(None, plot, value, skip_transform=True)

    def test_y_value_to_pixel(self):
        self.assertEqual(500, self._y_value_to_pixel(0.0))
        np.testing.assert_array_equal([100, 500, -399900], self._y_value_to_pixel(np.array([1.0, 0.0, 1001.0])))

    def test_y_value_to_pixel_bounded(self):
        """Huge and infinite values stay within int range  #352."""
        y = self._y_value_to_pixel(np.array([1e300, -1e300, np.inf, -np.inf]))
        np.testing.assert_array_equal([-(1 << 40), 1 << 40, -(1 << 40), 1 << 40], y)
        self.assertEqual(-(1 << 40), self._y_value_to_pixel(np.inf))

    def test_plot_render_info(self):
        widget = types.SimpleNamespace(_paint_count=2, _y_geometry_info={
            'x_axis': [20, 0, 20], 'plot.0': [300, 20, 320], 'plot.1': [200, 320, 520]})
        self.assertEqual({'paint_count': 2, 'plots': {0: [300, 20, 320], 1: [200, 320, 520]}},
                         WaveformWidget.plot_render_info(widget))

    def test_plot_opengl_widget_requests_stencil(self):
        parent = _Parent()
        try:
            widget = _PlotOpenGLWidget(parent)
            self.assertGreaterEqual(widget.format().stencilBufferSize(), 8)
        finally:
            parent.deleteLater()
