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

"""Test the shared QPainter plot helpers."""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui.widgets import plot_base
from joulescope_ui.widgets.spectrum.spectrum_widget import SpectrumWidget
from joulescope_ui.widgets.waveform import axis_ticks


def _app():
    app = QtWidgets.QApplication.instance()
    return app if app is not None else QtWidgets.QApplication([])


class _Painter:
    """Paint into an image with a plot rect inset for axis labels."""

    def __init__(self, width=400, height=300):
        self.image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32)
        self.image.fill(QtGui.QColor(0, 0, 0))
        self.rect = QtCore.QRectF(60, 10, width - 70, height - 50)

    def __enter__(self):
        self.p = QtGui.QPainter(self.image)
        return self.p

    def __exit__(self, *args):
        self.p.end()

    def changed(self, rect):
        """True if any pixel in rect is not the background."""
        r = rect.toRect().intersected(self.image.rect())
        for y in range(r.top(), r.bottom() + 1):
            for x in range(r.left(), r.right() + 1):
                if self.image.pixelColor(x, y) != QtGui.QColor(0, 0, 0):
                    return True
        return False


class TestPlotBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()
        w = SpectrumWidget()
        try:
            cls.style_vars = plot_base.style_vars(w)
        finally:
            w._worker.stop()
            w.deleteLater()
        cls.style = plot_base.style_build(cls.style_vars, 'spectrum')

    def test_style(self):
        for key in ['background_brush', 'text_pen', 'text_bg_brush', 'grid_major_pen', 'grid_minor_pen',
                    'border_pen', 'hover_pen', 'warning_pen', 'font', 'font_metrics']:
            self.assertIn(key, self.style)
        self.assertGreater(self.style['font_height'], 0)
        with self.assertRaises(KeyError):
            plot_base.style_build(self.style_vars, 'nonexistent')

    def test_autoscale_hysteresis(self):
        r = plot_base.autoscale_hysteresis(None, -73.0, -21.0, 10.0)
        self.assertEqual([-80.0, -10.0], r)
        self.assertEqual(r, plot_base.autoscale_hysteresis(r, -70.0, -25.0, 10.0))  # small moves keep it
        self.assertEqual([-80.0, 10.0], plot_base.autoscale_hysteresis(r, -70.0, 2.0, 10.0))  # above
        self.assertEqual([-100.0, -10.0], plot_base.autoscale_hysteresis(r, -95.0, -21.0, 10.0))  # below
        self.assertEqual([-80.0, -50.0], plot_base.autoscale_hysteresis(r, -73.0, -58.0, 10.0))  # shrink
        self.assertEqual([-20.0, 0.0], plot_base.autoscale_hysteresis([-20.0, 0.0], -10.0, -10.0, 10.0))

    def test_minor_visible(self):
        self.assertFalse(plot_base.minor_visible(None))
        self.assertFalse(plot_base.minor_visible(np.array([1.0])))
        self.assertFalse(plot_base.minor_visible(np.array([0.0, 5.0, 10.0])))
        self.assertTrue(plot_base.minor_visible(np.array([0.0, 6.0, 12.0])))

    def test_lines_clipped_to_rect(self):
        rect = QtCore.QRectF(10, 20, 100, 50)
        lines = plot_base.v_lines(np.array([5.0, 10.0, 60.0, 110.0, 111.0]), rect)
        self.assertEqual([10.0, 60.0, 110.0], [line.x1() for line in lines])
        self.assertEqual((20.0, 70.0), (lines[0].y1(), lines[0].y2()))
        self.assertEqual([], plot_base.v_lines(None, rect))
        lines = plot_base.h_lines(np.array([0.0, 20.0, 45.0, 70.0, 71.0]), rect)
        self.assertEqual([20.0, 45.0, 70.0], [line.y1() for line in lines])

    def test_draw_axes(self):
        d = _Painter()
        rect = d.rect
        x_ticks = axis_ticks.log_ticks(1e-5, 1e-1)
        y_ticks = axis_ticks.ticks(60.0, 100.0, major_max=5)

        def x_to_pixel(x):
            u = (np.log10(x) + 5) / 4
            return rect.left() + u * rect.width()

        def y_to_pixel(y):
            return rect.bottom() - (np.asarray(y) - 60.0) / 40.0 * rect.height()

        with d as p:
            p.setFont(self.style['font'])
            y_text = plot_base.draw_x_axis(p, rect, self.style, x_ticks, x_to_pixel)
            prefix = plot_base.draw_y_axis(p, rect, self.style, y_ticks, y_to_pixel)
            plot_base.draw_border(p, rect, self.style)
        self.assertGreater(y_text, rect.bottom())
        self.assertEqual('', prefix)
        self.assertTrue(d.changed(QtCore.QRectF(rect.left(), rect.bottom() + 2, rect.width(), 20)))
        self.assertTrue(d.changed(QtCore.QRectF(0, rect.top(), rect.left() - 2, rect.height())))

    def test_draw_axes_none(self):
        d = _Painter()
        with d as p:
            y_text = plot_base.draw_x_axis(p, d.rect, self.style, None, lambda x: x)
            prefix = plot_base.draw_y_axis(p, d.rect, self.style, None, lambda y: y)
        self.assertEqual(d.rect.bottom() + self.style['font_height'], y_text)
        self.assertEqual('', prefix)
        self.assertFalse(d.changed(QtCore.QRectF(d.image.rect())))

    def test_text_box_and_line(self):
        d = _Painter()
        with d as p:
            p.setFont(self.style['font'])
            plot_base.draw_text_box(p, self.style, [], 100, 100, False)
            plot_base.draw_text_box(p, self.style, ['line 1', 'a longer line 2'], 390, 20, True)
            plot_base.draw_v_line(p, d.rect, self.style['hover_pen'], 100)
        self.assertFalse(d.changed(QtCore.QRectF(60, 100, 30, 30)))
        self.assertTrue(d.changed(QtCore.QRectF(300, 22, 88, 10)))
        self.assertTrue(d.changed(QtCore.QRectF(100, 200, 1, 1)))


if __name__ == '__main__':
    unittest.main()
