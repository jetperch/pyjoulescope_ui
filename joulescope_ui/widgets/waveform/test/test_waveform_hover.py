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

"""Test WaveformWidget._draw_hover coordinate guards  #333."""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6 import QtGui, QtWidgets

from joulescope_ui import time64
from joulescope_ui.widgets.waveform.waveform_widget import WaveformWidget


_T0 = time64.YEAR * 55          # arbitrary nonzero base time
_PLOT_X = (700.0, 100.0, 800.0)  # width, x0, x1
_PLOT_Y = (180.0, 20.0, 200.0)   # height, y0, y1
_PX_PER_SECOND = 700.0


class TestDrawHover(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        w = WaveformWidget(None)
        w.show_hover = True
        w.hover_time = 'view_rel'
        w.precision = 6
        w.trace_priority = [0]
        w.trace_subsources = ['src.dev']
        w._mouse_pos = (400, 100)
        w._x_geometry_info = {'plot': _PLOT_X}
        w._y_geometry_info = {'plot.0': _PLOT_Y}
        w.state = {'plots': [{
            'quantity': 'i',
            'units': 'A',
            'y_map': (110.0, 0.0, 100.0),  # pixel_offset, value_offset, value_to_pixel_scale
        }]}
        font = QtGui.QFont()
        w._style_cache = {
            'waveform.hover': QtGui.QBrush(QtGui.QColor(255, 255, 0)),
            'axis_font': font,
            'axis_font_metrics': QtGui.QFontMetrics(font),
            'text_pen': QtGui.QPen(QtGui.QColor(255, 255, 255)),
            'text_brush': QtGui.QBrush(QtGui.QColor(64, 64, 64)),
        }
        w._x_map.update(_PLOT_X[1], _T0, _PX_PER_SECOND / time64.SECOND)
        w._x_map.trel_offset = _T0
        self.widget = w

    def tearDown(self):
        self.widget.close()

    def _data_set(self, x_offset):
        """Populate signal data, 1 second of samples starting at _T0 + x_offset."""
        x = _T0 + x_offset + np.linspace(0, time64.SECOND, 100, dtype=np.int64)
        avg = np.full(len(x), 0.5)
        self.widget._signals_data = {'src.dev.i': {'data': {'x': x, 'avg': avg}}}

    def _paint(self):
        """Call _draw_hover and return True if it drew anything."""
        img = QtGui.QImage(900, 300, QtGui.QImage.Format.Format_ARGB32)
        img.fill(QtGui.QColor(0, 0, 0))
        baseline = img.copy()
        p = QtGui.QPainter(img)
        try:
            self.widget._draw_hover(p)
        finally:
            p.end()
        return img != baseline

    def test_sample_in_view(self):
        self._data_set(0)
        self.assertTrue(self._paint())

    def test_sample_stale(self):
        # data lags the time map: nearest sample maps off-plot, skip hover
        self._data_set(-time64.HOUR)
        self.assertFalse(self._paint())

    def test_sample_stale_beyond_int32(self):
        # pixel coordinate exceeds int32: fillRect raised OverflowError  #333
        offset = 40 * time64.DAY  # 700 px/s * 40 days > 2**31 pixels
        self._data_set(offset)
        self.assertFalse(self._paint())

    def test_y_value_beyond_clip_limit(self):
        plot = self.widget.state['plots'][0]
        plot['y_map'] = (110.0, 0.0, 1e6)  # y_pixels far below the plot region
        self._data_set(0)
        self.assertFalse(self._paint())


if __name__ == '__main__':
    unittest.main()
