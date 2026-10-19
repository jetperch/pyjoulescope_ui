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


class TestWaveformWidgetYZoom(unittest.TestCase):
    """Repeated y-axis zoom must not collapse the range to a point, then NaN."""

    def _widget(self, y_range, range_mode='manual'):
        plot = {'index': 0, 'quantity': 'i', 'scale': 'linear',
                'range_mode': range_mode, 'range': list(y_range), 'range_bounds': [-50, 50]}
        widget = types.SimpleNamespace(
            unique_id='WaveformWidget:test', state={'plots': [plot]},
            _log=types.SimpleNamespace(info=lambda *args: None), _repaint_request=False)
        widget._y_transform_fwd = lambda plot, value: WaveformWidget._y_transform_fwd(widget, plot, value)
        return widget, plot

    def test_zoom_in_bounded_at_float_resolution(self):
        widget, plot = self._widget([0.0, 0.01])
        for steps in [1, 2, 3, 2.0 / 15]:
            for _ in range(200):
                y0, y1 = plot['range']
                center = y0 + (y1 - y0) * 0.37
                WaveformWidget.on_action_y_zoom(widget, [0, steps, center])
                y0, y1 = plot['range']
                self.assertTrue(np.isfinite(y0) and np.isfinite(y1))
                self.assertLess(y0, y1)
        self.assertGreaterEqual(y1 - y0, 0.99e-12 * y1)

    def test_zoom_ignores_invalid_range(self):
        for y_range in [[np.nan, np.nan], [0.005, 0.005], [0.006, 0.005]]:
            widget, plot = self._widget(y_range, range_mode='auto')
            self.assertIsNone(WaveformWidget.on_action_y_zoom(widget, [0, 2, 0.005]))
            self.assertEqual('auto', plot['range_mode'])
            np.testing.assert_array_equal(y_range, plot['range'])
