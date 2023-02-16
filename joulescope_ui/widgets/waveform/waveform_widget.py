# Copyright 2019-2023 Jetperch LLC
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

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtWidgets import QWidget, QGraphicsView, QGraphicsScene
from PySide6.QtGui import QPen, QColor, QPolygonF, QPainter
from PySide6.QtCore import QPointF

from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name, tooltip_format
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from .line_segments import LineSegments, PointsF
import logging
import numpy as np
from PySide6.QtGui import QPainter, QPen, QBrush, QColor
from joulescope_ui.units import unit_prefix


_AUTO_RANGE_FRACT = 0.50  # autorange when current range smaller than existing range by this fractional amount.
_PLOT_TYPES = {
    'i': {
        'units': 'A',
        'name': N_('Current'),
    },
    'v': {
        'units': 'V',
        'name': N_('Voltage'),
    },
    'p': {
        'units': 'W',
        'name': N_('Power'),
    },
    'r': {
        'name': N_('Current range'),
    },
    '0': {
        'name': N_('General purpose input 0'),
    },
    '1': {
        'name': N_('General purpose input 1'),
    },
    '2': {
        'name': N_('General purpose input 2'),
    },
    '3': {
        'name': N_('General purpose input 3'),
    },
}


class _PlotWidget(QWidget):
    """The inner plot widget that simply calls back to the Waveform widget."""

    def __init__(self, parent):
        self._parent = parent
        super().__init__(parent)

    def paintEvent(self, event):
        size = self.width(), self.height()
        painter = QtGui.QPainter(self)
        painter.begin(self)
        self._parent.plot_paint(painter, size)
        painter.end()


def _tick_spacing(v_min, v_max, v_spacing_min):
    if v_spacing_min <= 0:
        return 0.0
    target_spacing = v_spacing_min
    power10 = 10 ** np.floor(np.log10(v_spacing_min))
    intervals = np.array([1., 2., 5., 10., 20., 50., 100.]) * power10
    for interval in intervals:
        if interval >= target_spacing:
            return interval
    raise RuntimeError('tick_spacing calculation failed')


def _ticks(v_min, v_max, v_spacing_min):
    major_interval = _tick_spacing(v_min, v_max, v_spacing_min)
    if major_interval <= 0:
        return None
    major_start = np.ceil(v_min / major_interval) * major_interval
    major = np.arange(major_start, v_max, major_interval, dtype=np.float64)
    minor_interval = major_interval / 10.0
    minor_start = major_start - major_interval
    minor = np.arange(minor_start, v_max, minor_interval, dtype=np.float64)

    k = 0
    sel_idx = np.zeros(len(minor), dtype=bool)
    sel_idx[:] = True
    sel_idx[0::10] = False
    while minor_start < v_min:
        sel_idx[k] = False
        minor_start += minor_interval
        k += 1
    minor = minor[sel_idx]

    label_max = max(abs(major[0]), abs(major[-1]))
    adjusted_value, prefix, scale = unit_prefix(label_max)
    labels = []
    for v in major:
        s = str(v * scale)
        if s.endswith('.0'):
            s = s[:-2]
        labels.append(s)

    return {
        'major': major,
        'minor': minor,
        'labels': labels,
        'unit_prefix': prefix,
    }
    return np.arange(start, v_max, interval, dtype=np.float64), interval


@register
@styled_widget(N_('Waveform'))
class WaveformWidget(QWidget):
    CAPABILITIES = ['widget@', CAPABILITIES.SIGNAL_BUFFER_SINK]

    SETTINGS = {
        'trace_width': {
            'dtype': 'int',
            'brief': N_('The trace width.'),
            'default': 1,
        },
        'show_min_max': {
            'dtype': 'bool',
            'brief': N_('Show the minimum and maximum extents fill.'),
            'default': True,
        },
        'x_range': {
            'dtype': 'obj',
            'brief': 'The x-axis range.',
            'default': [0, 30.0],
            'flags': ['hidden', 'ro'],
        },
        'state': {
            'dtype': 'obj',
            'brief': N_('The waveform state.'),
            'default': {
                'plots': [
                    {
                        'quantity': 'i',
                        'sources': ['a'],  # todo remove hack
                        'height': 200,
                        'range_mode': 'auto',
                        'range': [0.0, 1.0],
                        'scale': 'linear',
                    },
                    {
                        'quantity': 'v',
                        'sources': ['b'],  # todo remove hack
                        'height': 200,
                        'range_mode': 'auto',
                        'range': [0.0, 1.0],
                        'scale': 'linear',
                    },
                ]
            },
            'flags': ['hidden'],
        },
    }

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        super().__init__(parent)

        self._signals = {}
        self._data = {}
        self._x_map = (0, 0, 1.0)  # (pixel_offset, time_offset, time_to_pixel_scale)

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._graphics = _PlotWidget(self)
        self._layout.addWidget(self._graphics)

        # data hack
        x = np.arange(1000, dtype=np.float64)
        x *= 30 / 1000
        y1 = np.sin(x, dtype=np.float64)
        y2 = np.sin(x / 2, dtype=np.float64)
        self._data['a'] = {
            'x': x,
            'avg': y1,
            'std': 0.1,
            'min': y1 - 0.25,
            'max': y1 + 0.25,
        }
        self._data['b'] = {
            'x': x,
            'avg': y2,
            'std': 0.02,
            'min': y2 - 0.1,
            'max': y2 + 0.1,
        }

    def _x_time_to_pixel(self, time):
        pixel_offset, time_offset, time_to_pixel_scale = self._x_map
        return pixel_offset + (time - time_offset) * time_to_pixel_scale

    def _x_pixel_to_time(self, pixel):
        pixel_offset, time_offset, time_to_pixel_scale = self._x_map
        return time_offset + (pixel - pixel_offset) * (1.0 / time_to_pixel_scale)

    def _y_value_to_pixel(self, plot, value):
        pixel_offset, value_offset, value_to_pixel_scale = plot['y_map']
        return pixel_offset + (value_offset - value) * value_to_pixel_scale

    def _y_pixel_to_value(self, plot, pixel):
        pixel_offset, value_offset, value_to_pixel_scale = plot['y_map']
        return (pixel_offset - pixel) * (1.0 / value_to_pixel_scale) + value_offset

    def _draw_text(self, p, x, y, txt):
        """Draws text over existing items.

        :param p: The QPainter instance.
        :param x: The x-axis location.
        :param y: The y-axis location.
        :param txt: The text to draw
        """
        m = p.fontMetrics()
        r = m.boundingRect(txt)
        p.fillRect(x, y - m.ascent(), r.width(), r.height(), p.brush())
        p.drawText(x, y, txt)

    def _plot_range_auto_update(self, plot):
        if plot['range_mode'] != 'auto':
            return
        y_min = []
        y_max = []
        for source in plot['sources']:
            d = self._data.get(source)
            if d is None:
                continue
            sy_min = d['avg'] if d['min'] is None else d['min']
            sy_max = d['avg'] if d['max'] is None else d['max']
            y_min.append(np.min(sy_min))
            y_max.append(np.max(sy_max))
        y_min = min(y_min)
        y_max = max(y_max)
        r = plot['range']

        dy1 = y_max - y_min
        dy2 = r[1] - r[0]

        if y_min >= r[0] and y_max <= r[1] and dy1 / (dy2 + 1e-15) > _AUTO_RANGE_FRACT:
            return
        f = dy1 * 0.1
        plot['range'] = y_min - f/2, y_max + f

    def plot_paint(self, p, size):
        """Paint the plot.

        :param p: The QPainter instance.
        :param size: The (width, height) for the plot area.
        """
        v = self.style_manager_info['sub_vars']
        widget_w, widget_h = size

        # draw the background
        background_brush = QtGui.QBrush(color_as_qcolor(v['waveform.background']))
        p.fillRect(0, 0, widget_w, widget_h, background_brush)

        # compute dimensions
        margin = 2
        y_inner_spacing = 8  # includes line
        axis_font = font_as_qfont(v['waveform.axis_font'])
        text_pen = QtGui.QPen(color_as_qcolor(v['waveform.text_foreground']))
        text_brush = QtGui.QBrush(color_as_qcolor(v['waveform.text_background']))
        grid_major_pen = QtGui.QPen(color_as_qcolor(v['waveform.grid_major']))
        grid_minor_pen = QtGui.QPen(color_as_qcolor(v['waveform.grid_minor']))
        plot_border_pen = QtGui.QPen(color_as_qcolor(v['waveform.plot_border']))
        plot_separator_brush = QtGui.QBrush(color_as_qcolor(v['waveform.plot_separator']))

        plot1_trace = QPen(color_as_qcolor(v['waveform.plot1_trace']))
        plot1_trace.setWidth(self.trace_width)
        plot1_fill = QBrush(color_as_qcolor(v['waveform.plot1_fill']))

        axis_font_metrics = QtGui.QFontMetrics(axis_font)
        plot_label_size = axis_font_metrics.boundingRect('WW')
        y_tick_size = axis_font_metrics.boundingRect('888.888')
        y_tick_height_pixels_min = 1.5 * y_tick_size.height()
        x_tick_width_pixels_min = axis_font_metrics.boundingRect('888.888888').width()

        left_margin = margin + plot_label_size.width() + margin + y_tick_size.width() + margin
        right_margin = margin

        x_range = self.x_range
        x_range_d = x_range[1] - x_range[0]
        plot_width = widget_w - left_margin - margin
        x_size = widget_w - left_margin - right_margin
        x_gain = 0.0 if x_range_d <= 0 else x_size / x_range_d
        self._x_map = (left_margin, x_range[0], x_gain)

        # Draw top header: markers, UTC time, relative time
        x_tick_width_time_min = x_tick_width_pixels_min / self._x_map[-1] if x_gain else 0.0

        p.setPen(text_pen)
        p.setBrush(text_brush)
        p.setFont(axis_font)

        self._draw_text(p, 2, 2 + axis_font_metrics.ascent(), 'markers')
        self._draw_text(p, 2, 2 + plot_label_size.height() + axis_font_metrics.ascent(), 'UTC')
        self._draw_text(p, 2, 2 + 2 * plot_label_size.height() + axis_font_metrics.ascent(), 'relative')

        # compute total plot height
        top_margin = plot_label_size.height() * 3
        y_end = top_margin
        for plot in self.state['plots']:
            y_end += y_inner_spacing
            y_end += plot['height']

        y = plot_label_size.height() * 2
        x_grid = _ticks(x_range[0], x_range[1], x_tick_width_time_min)
        if x_grid is not None:
            for idx, x in enumerate(self._x_time_to_pixel(x_grid['major'])):
                p.setPen(text_pen)
                p.drawText(x + 2, y + axis_font_metrics.ascent(), x_grid['labels'][idx])
                p.setPen(grid_major_pen)
                p.drawLine(x, y, x, y_end)
            # todo unit_prefix

            y = top_margin
            p.setPen(grid_minor_pen)
            for x in self._x_time_to_pixel(x_grid['minor']):
                p.drawLine(x, y, x, y_end)
        y = top_margin

        # Draw each plot
        for plot in self.state['plots']:
            h = plot['height']

            # draw separator
            p.setPen(QtGui.Qt.NoPen)
            p.setBrush(plot_separator_brush)
            p.drawRect(0, y + 2, widget_w, y_inner_spacing - 4)
            y += y_inner_spacing

            # draw border
            p.setPen(plot_border_pen)
            p.setBrush(QtGui.Qt.NoBrush)
            p.drawRect(left_margin, y, plot_width, h)

            self._plot_range_auto_update(plot)
            # todo set clip bounds
            y_range = plot['range']
            y_scale = h / (y_range[1] - y_range[0])
            plot['y_map'] = (y, y_range[1], y_scale)

            # draw grid
            p.setFont(axis_font)
            y_tick_height_value_min = y_tick_height_pixels_min / plot['y_map'][-1]
            y_grid = _ticks(y_range[0], y_range[1], y_tick_height_value_min)
            if y_grid is not None:
                for idx, t in enumerate(self._y_value_to_pixel(plot, y_grid['major'])):
                    p.setPen(text_pen)

                    s = y_grid['labels'][idx]
                    w = axis_font_metrics.boundingRect(s).width()
                    p.drawText(left_margin - 4 - w, t + axis_font_metrics.ascent() // 2, s)
                    p.setPen(grid_major_pen)
                    p.drawLine(left_margin, t, left_margin + plot_width, t)

                #p.setPen(grid_minor_pen)
                #for t in self._y_value_to_pixel(plot, y_grid['minor']):
                #    p.drawLine(left_margin, t, left_margin + plot_width, t)

            # draw label
            plot_type = _PLOT_TYPES[plot['quantity']]
            p.setPen(text_pen)
            p.setFont(axis_font)
            plot_units = plot_type.get('units')
            if plot_units is None:
                s = plot['quantity']
            else:
                s = f"{y_grid['unit_prefix']}{plot_units}"
            p.drawText(2, y + (h + axis_font_metrics.ascent()) // 2, s)

            for source in plot['sources']:
                d = self._data.get(source)
                if d is None:
                    continue
                d_x = self._x_time_to_pixel(d['x'])

                if self.show_min_max and d['min'] is not None and d['max'] is not None:
                    d_y_min = self._y_value_to_pixel(plot, d['min'])
                    d_y_max = self._y_value_to_pixel(plot, d['max'])
                    if 'points_min_max' not in d:
                        d['points_min_max'] = PointsF()
                    segs, nsegs = d['points_min_max'].set_fill(d_x, d_y_min, d_y_max)
                    p.setPen(QtGui.Qt.NoPen)
                    p.setBrush(plot1_fill)
                    p.drawPolygon(segs)

                    d_y_std_min = self._y_value_to_pixel(plot, d['avg'] - d['std'])
                    d_y_std_max = self._y_value_to_pixel(plot, d['avg'] + d['std'])
                    if 'points_std' not in d:
                        d['points_std'] = PointsF()
                    segs, nsegs = d['points_std'].set_fill(d_x, d_y_std_min, d_y_std_max)
                    p.drawPolygon(segs)

                d_y = self._y_value_to_pixel(plot, d['avg'])
                if 'points_avg' not in d:
                    d['points_avg'] = PointsF()
                segs, nsegs = d['points_avg'].set_line(d_x, d_y)
                p.setPen(plot1_trace)
                p.drawPolyline(segs)

            y += h
