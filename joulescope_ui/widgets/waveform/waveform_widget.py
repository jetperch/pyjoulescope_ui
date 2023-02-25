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

from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name, tooltip_format, time64
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.widget_tools import settings_action_create
from .line_segments import PointsF
import logging
import numpy as np
import os
import time
from PySide6.QtGui import QPainter, QPen, QBrush, QColor
from joulescope_ui.units import unit_prefix


_WHEEL_TO_DEGREES = 1.0 / 8.0  # https://doc.qt.io/qt-6/qwheelevent.html#angleDelta
_WHEEL_TICK_DEGREES = 15.0   # Standard convention
_AUTO_RANGE_FRACT = 0.50  # autorange when current range smaller than existing range by this fractional amount.
_BINARY_RANGE = [-0.1, 1.1]
_MARGIN = 2             # from the outside edges
_Y_INNER_SPACING = 8    # vertical spacing between plots (includes line)
_Y_INNER_LINE = 4
_Y_PLOT_MIN = 16
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
        'range': _BINARY_RANGE,
    },
    '1': {
        'name': N_('General purpose input 1'),
        'range': _BINARY_RANGE,
    },
    '2': {
        'name': N_('General purpose input 2'),
        'range': _BINARY_RANGE,
    },
    '3': {
        'name': N_('General purpose input 3'),
        'range': _BINARY_RANGE,
    },
    'T': {
        'name': N_('Trigger input'),
        'range': _BINARY_RANGE,
    },
}


class _PlotWidget(QWidget):
    """The inner plot widget that simply calls back to the Waveform widget."""

    def __init__(self, parent):
        self._parent = parent
        super().__init__(parent)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        size = self.width(), self.height()
        painter = QtGui.QPainter(self)  # calls begin()
        self._parent.plot_paint(painter, size)
        # painter.end()  Automatically called by destructor

    def mousePressEvent(self, event):
        self._parent.plot_mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._parent.plot_mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self._parent.plot_mouseMoveEvent(event)

    def wheelEvent(self, event):
        self._parent.plot_wheelEvent(event)


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
    if not len(minor):
        return None

    k = 0
    sel_idx = np.zeros(len(minor), dtype=bool)
    sel_idx[:] = True
    sel_idx[0::10] = False
    while minor_start < v_min:
        sel_idx[k] = False
        minor_start += minor_interval
        k += 1
    minor = minor[sel_idx]

    labels = []
    prefix = ''
    if len(major):
        label_max = max(abs(major[0]), abs(major[-1]))
        zero_max = label_max / 10_000.0
        adjusted_value, prefix, scale = unit_prefix(label_max)
        scale = 1.0 / scale
        for v in major:
            v *= scale
            if abs(v) < zero_max:
                v = 0
            s = f'{v:g}'
            if s == '-0':
                s = '0'
            labels.append(s)

    return {
        'major': major,
        'minor': minor,
        'labels': labels,
        'unit_prefix': prefix,
    }
    return np.arange(start, v_max, interval, dtype=np.float64), interval


def _target_lookup_by_pos(targets, pos):
    v = 0
    for sz, name in targets:
        v += sz
        if pos < v:
            break
    return name


def _target_lookup_by_name(targets, name):
    v = 0
    for sz, n in targets:
        v_next = v + sz
        if name == n:
            return v, v_next
        v = v_next
    raise ValueError(f'target name {name} not found')


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
            'dtype': 'int',
            'brief': N_('Show the minimum and maximum extents fill.'),
            'options': [
                [0, 'off'],
                [1, 'lines'],
                [2, 'fill'],
                [3, 'fill + std'],
            ],
            'default': 3,
        },
        'show_fps': {
            'dtype': 'bool',
            'brief': N_('Show the frames per second.'),
            'default': False,
        },
        'x_range': {
            'dtype': 'obj',
            'brief': 'The x-axis range.',
            'default': [0, 30 * time64.SECOND],
            'flags': ['hidden', 'ro', 'skip_undo'],  # publish only
        },
        'state': {
            'dtype': 'obj',
            'brief': N_('The waveform state.'),
            'default': {
                'plots': [
                    {
                        'quantity': 'i',
                        'signals': [],  # list of (buffer_unique_id, signal_id)
                        'height': 200,
                        'range_mode': 'auto',
                        'range': [-0.1, 1.1],
                        'scale': 'linear',
                    },
                    {
                        'quantity': 'v',
                        'signals': [],
                        'height': 200,
                        'range_mode': 'auto',
                        'range': [-0.1, 1.1],
                        'scale': 'linear',
                    },
                ]
            },
            'flags': ['hidden'],
        },
    }

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        self.pubsub = None
        super().__init__(parent)

        # Cache Qt default instances to prevent memory leak in Pyside6 6.4.2
        self._NO_PEN = QtGui.QPen(QtGui.Qt.NoPen)  # prevent memory leak
        self._NO_BRUSH = QtGui.QBrush(QtGui.Qt.NoBrush)  # prevent memory leak
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_VER = QtGui.QCursor(QtGui.Qt.SizeVerCursor)
        self._CURSOR_CROSS = QtGui.QCursor(QtGui.Qt.CrossCursor)

        self._on_signal_range_fn = self._on_signal_range
        self._menu = None
        self._dialog = None
        self._x_map = (0, 0, 0, 1.0)  # (pixel_offset, time64_label_offset, time64_zero_offset, time_to_pixel_scale)
        self._mouse_pos = None
        self._wheel_accum_degrees = np.zeros(2, dtype=np.float64)
        self._margin = _MARGIN

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._graphics = _PlotWidget(self)
        self._layout.addWidget(self._graphics)
        self._x_geometry_info = []
        self._y_geometry_info = []
        self._mouse_action = None
        self._clipboard_image = None
        self._signals = {}
        self._signals_by_rsp_id = {}
        self._signals_rsp_id_next = 1

        self._refresh_timer = QtCore.QTimer()
        self._refresh_timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)
        self._refresh_timer.start(50)  # = 1 / render_frame_rate
        self._repaint_request = False
        self._fps = {
            'start': time.time(),
            'times': [],
            'str': '',
        }

    def on_pubsub_register(self):
        sources = self.pubsub.query('registry_manager/capabilities/signal_buffer.source/list')
        if not len(sources):
            self._log.warning('No default source available')
            self._data_hack()
            return
        source = sources[0]
        topic = get_topic_name(source)
        signals = self.pubsub.enumerate(f'{topic}/settings/signals')
        plots = self.state['plots']
        for signal in signals:
            item = (source, signal)
            source_id, quantity = signal.split('.')
            for plot in plots:
                if plot['quantity'] == quantity:
                    if item not in plot['signals']:
                        plot['signals'].append(item)
                        self.pubsub.subscribe(f'{topic}/settings/signals/{signal}/range',
                                              self._on_signal_range_fn, ['pub', 'retain'])

    def _update_fps(self):
        t = time.time()
        self._fps['times'].append(t)
        if t - self._fps['start'] >= 1.0:
            x = np.array(self._fps['times'])
            x = np.diff(x)
            self._fps['start'] = t
            self._fps['times'].clear()
            if len(x):
                t_avg = np.mean(x)
                t_min = np.min(x)
                t_max = np.max(x)
                self._fps['str'] = f'{1/t_avg:.2f} Hz (min={t_min*1000:.2f}, max={t_max*1000:.2f} ms)'
        return None

    def _on_signal_range(self, topic, value):
        # self._log.info('_on_signal_range(%s, %s)', topic, value)
        if value is None:
            return
        topic_parts = topic.split('/')
        source = topic_parts[1]
        signal_id = topic_parts[-2]
        item = (source, signal_id)
        d = self._signals.get(item)
        if d is None:
            d = {
                'item': item,
                'source': source,
                'signal_id': signal_id,
                'rsp_id': self._signals_rsp_id_next,
                'data': None,
                'range': [0, 0],
            }
            self._signals[item] = d
            self._signals_by_rsp_id[self._signals_rsp_id_next] = d
            self._signals_rsp_id_next += 1
        if value != d['range']:
            d['range'] = value
            d['changed'] = time.time()
            self._repaint_request = True
        return None

    def _on_refresh_timer(self):
        if self._repaint_request:
            self.repaint()

    def _request_data(self):
        x_min = []
        x_max = []
        for signal in self._signals.values():
            x_range = signal['range']
            x_min.append(x_range[0])
            x_max.append(x_range[1])
        if 0 == len(x_min):
            return
        x_min, x_max = min(x_min), max(x_max)
        self.x_range = (x_min, x_max)
        for signal in self._signals.values():
            if signal['changed'] is None:
                continue
            signal['changed'] = None
            topic_req = f'registry/{signal["source"]}/actions/!request'
            topic_rsp = f'{get_topic_name(self)}/callbacks/!response'
            req = {
                'signal_id': signal['signal_id'],
                'time_type': 'utc',
                'rsp_topic': topic_rsp,
                'rsp_id': signal['rsp_id'],
                'start': x_min,
                'end': x_max,
                'length': 1000,  # todo adjust based upon widget size
            }
            self.pubsub.publish(topic_req, req)

    def on_cbk_response(self, topic, value):
        utc = value['info']['time_range_utc']
        if utc['length'] == 0:
            return
        x = np.linspace(utc['start'], utc['end'], utc['length'], dtype=np.int64)
        response_type = value['response_type']
        rsp_id = value['rsp_id']
        signal = self._signals_by_rsp_id.get(rsp_id)
        if signal is None:
            self._log.warning('Unknown signal rsp_id %s', rsp_id)
            return

        self._repaint_request = True
        if response_type == 'samples':
            # self._log.info(f'response samples {length}')
            y = value['data']
            data_type = value['data_type']
            if data_type == 'f32':
                pass
            elif data_type == 'u1':
                y = np.unpackbits(y, bitorder='little')
            elif data_type == 'u4':
                d = np.empty(len(y) * 2, dtype=np.uint8)
                d[0::2] = np.logical_and(y, 0x0f)
                d[1::2] = np.logical_and(np.right_shift(y, 4), 0x0f)
                y = d
            else:
                self._log.warning('Unsupported sample data type: %s', data_type)
                return
            signal['data'] = {
                'x': x,
                'avg': y,
                'std': None,
                'min': None,
                'max': None,
            }
        elif response_type == 'summary':
            # self._log.info(f'response summary {length}')
            y = value['data']
            signal['data'] = {
                'x': x,
                'avg': y[:, 0],
                'std': y[:, 1],
                'min': y[:, 2],
                'max': y[:, 3],
            }
        else:
            self._log.warning('unsupported response type: %s', response_type)

    def _data_hack(self):
        x = np.arange(1000, dtype=np.float64)
        x *= 30 / 1000
        y1 = np.sin(x, dtype=np.float64)
        y1[:100] = np.nan
        y1[300:400] = np.nan
        y1[900:] = np.nan
        y2 = np.sin(x / 2, dtype=np.float64)

        x64 = np.empty(len(x), dtype=np.int64)
        x64[:] = time64.now()
        x64 += (x * time64.SCALE).astype(np.int64)
        self.x_range = [x64[0], x64[-1]]

        self._data['a'] = {
            'x': x64,
            'avg': y1,
            'std': np.full(x64.shape, 0.1),
            'min': y1 - 0.25,
            'max': y1 + 0.25,
        }
        self._data['b'] = {
            'x': x64,
            'avg': y2,
            'std': np.full(x64.shape, 0.02),
            'min': y2 - 0.1,
            'max': y2 + 0.1,
        }

    def _x_trel_offset(self):
        offset = self._x_map[1]
        offset = (offset // time64.SECOND) * time64.SECOND
        return offset

    def _x_time64_to_pixel(self, time):
        pixel_offset, _, time_zero_offset, time_to_pixel_scale = self._x_map
        return pixel_offset + (time - time_zero_offset) * time_to_pixel_scale

    def _x_pixel_to_time64(self, pixel):
        pixel_offset, _, time_zero_offset, time_to_pixel_scale = self._x_map
        return time_zero_offset + (pixel - pixel_offset) * (1.0 / time_to_pixel_scale)

    def _x_time64_to_trel(self, t64):
        offset = self._x_trel_offset()
        dt = t64 - offset
        if isinstance(dt, np.ndarray):
            dt = dt.astype(np.float64)
        else:
            dt = float(dt)
        return dt / time64.SECOND

    def _x_trel_to_time64(self, trel):
        offset = self._x_trel_offset()
        s = trel * time64.SECOND
        if isinstance(s, np.ndarray):
            s = s.astype(np.int64)
            s += np.int64(offset)
        else:
            s = int(s) + int(offset)
        return s

    def _x_trel_to_pixel(self, trel):
        t64 = self._x_trel_to_time64(trel)
        return self._x_time64_to_pixel(t64)

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

    def _nan_idx(self, data):
        if data is None:
            return None
        if 'nan_idx' in data:
            return data['nan_idx']
        nan_idx = np.isnan(data['avg'])
        data['nan_idx'] = nan_idx
        data['finite_idx'] = np.logical_not(nan_idx)
        return nan_idx

    def _finite_idx(self, data):
        if data is None:
            return None
        if 'finite_idx' not in data:
            self._nan_idx(data)
        return data['finite_idx']

    def _plot_range_auto_update(self, plot):
        if plot['range_mode'] != 'auto':
            return
        y_min = []
        y_max = []
        for signal in plot['signals']:
            d = self._signals.get(signal)
            if d is None or d['data'] is None:
                continue
            d = d['data']
            finite_idx = self._finite_idx(d)

            sy_min = d['avg'] if d['min'] is None else d['min']
            sy_max = d['avg'] if d['max'] is None else d['max']
            sy_min = sy_min[finite_idx]
            sy_max = sy_max[finite_idx]
            if len(sy_min):
                y_min.append(np.min(sy_min))
                y_max.append(np.max(sy_max))
        if not len(y_min):
            y_min = 0.0
            y_max = 1.0
        else:
            y_min = min(y_min)
            y_max = max(y_max)
        r = plot['range']

        dy1 = y_max - y_min
        dy2 = r[1] - r[0]

        if y_min >= r[0] and y_max <= r[1] and dy1 / (dy2 + 1e-15) > _AUTO_RANGE_FRACT:
            return
        f = dy1 * 0.1
        plot['range'] = y_min - f/2, y_max + f

    def _plots_height(self):
        if self.state is None:
            return 0
        plots = self.state['plots']
        k = len(plots)
        h = 0
        if k > 1:
            h += _Y_INNER_SPACING * (k - 1)
        for plot in plots:
            h += plot['height']
        return h

    def _plots_height_adjust(self, h):
        h_now = self._plots_height()
        if h_now <= 0:
            return
        plots = self.state['plots']
        k = len(plots)
        if k == 0:
            return
        h_spacing = _Y_INNER_SPACING * (k - 1)
        h_min = _Y_PLOT_MIN * k + h_spacing
        if h < h_min:
            h = h_min
        h_now -= h_spacing
        h -= h_spacing
        scale = h / h_now
        h_new = 0

        # scale each plot, respecting minimum height
        for plot in plots:
            z = int(np.round(plot['height'] * scale))
            if z < _Y_PLOT_MIN:
                z = _Y_PLOT_MIN
            plot['height'] = z
            h_new += z
        dh = h - h_new
        if 0 == dh:
            pass     # no residual, great!
        elif dh > 0:
            plots[0]['height'] += dh  # add positive residual to first plot
        else:
            # distribute negative residual, respecting minimum sizes
            for plot in plots:
                r = plot['height'] - _Y_PLOT_MIN
                if r > 0:
                    adj = min(r, dh)
                    plot['height'] -= adj
                    dh -= adj
                    if dh <= 0:
                        break

    def _header_height(self):
        if not hasattr(self, 'style_manager_info'):
            return 0
        v = self.style_manager_info['sub_vars']
        axis_font = font_as_qfont(v['waveform.axis_font'])
        axis_font_metrics = QtGui.QFontMetrics(axis_font)
        plot_label_size = axis_font_metrics.boundingRect('WW')
        h = self._margin + plot_label_size.height() * 3
        return h

    def resizeEvent(self, event):
        self._repaint_request = True
        h = event.size().height()
        margin = self._header_height() + _Y_INNER_SPACING + self._margin
        h -= margin
        self._plots_height_adjust(h)
        return super().resizeEvent(event)

    def plot_paint(self, p, size):
        try:
            self._plot_paint(p, size)
        except Exception:
            self._log.exception('Exception during drawing')
        self._request_data()

    def _plot_paint(self, p, size):
        """Paint the plot.

        :param p: The QPainter instance.
        :param size: The (width, height) for the plot area.
        """
        if not hasattr(self, 'style_manager_info'):
            return
        self._repaint_request = False
        v = self.style_manager_info['sub_vars']
        widget_w, widget_h = size

        # draw the background
        background_brush = QtGui.QBrush(color_as_qcolor(v['waveform.background']))
        p.fillRect(0, 0, widget_w, widget_h, background_brush)

        # compute dimensions
        axis_font = font_as_qfont(v['waveform.axis_font'])
        text_pen = QtGui.QPen(color_as_qcolor(v['waveform.text_foreground']))
        text_brush = QtGui.QBrush(color_as_qcolor(v['waveform.text_background']))
        grid_major_pen = QtGui.QPen(color_as_qcolor(v['waveform.grid_major']))
        grid_minor_pen = QtGui.QPen(color_as_qcolor(v['waveform.grid_minor']))
        plot_border_pen = QtGui.QPen(color_as_qcolor(v['waveform.plot_border']))
        plot_separator_brush = QtGui.QBrush(color_as_qcolor(v['waveform.plot_separator']))

        plot1_trace = QPen(color_as_qcolor(v['waveform.plot1_trace']))
        plot1_trace.setWidth(self.trace_width)
        plot1_min_max_trace = QPen(color_as_qcolor(v['waveform.plot1_min_max_trace']))
        plot1_min_max_fill = QBrush(color_as_qcolor(v['waveform.plot1_min_max_fill']))
        plot1_std_fill = QBrush(color_as_qcolor(v['waveform.plot1_std_fill']))
        plot1_missing = QBrush(color_as_qcolor(v['waveform.plot1_missing']))

        axis_font_metrics = QtGui.QFontMetrics(axis_font)
        plot_label_size = axis_font_metrics.boundingRect('WW')
        y_tick_size = axis_font_metrics.boundingRect('888.888')
        y_tick_height_pixels_min = 1.5 * y_tick_size.height()
        utc_width_pixels = axis_font_metrics.boundingRect('8888-88-88W88:88:88.888888').width()
        x_tick_width_pixels_min = axis_font_metrics.boundingRect('888.888888').width()
        statistics_size = axis_font_metrics.boundingRect('WWW +888.8888 WW')

        margin = self._margin
        y_inner_spacing = _Y_INNER_SPACING
        left_margin = margin + plot_label_size.width() + margin + y_tick_size.width() + margin
        right_margin = margin + statistics_size.width() + margin
        plot_width = widget_w - left_margin - right_margin

        p.setPen(text_pen)
        p.setBrush(text_brush)
        p.setFont(axis_font)

        # compute total plot height
        top_margin = self._header_height()
        y_end = top_margin
        y_end += self._plots_height()

        # compute time and draw x-axis including UTC, seconds, grid
        y = margin + 2 * plot_label_size.height()
        x_range64 = self.x_range
        x_duration_s = (x_range64[1] - x_range64[0]) / time64.SECOND
        if x_duration_s > 0:
            x_tick_width_time_min = x_tick_width_pixels_min / (plot_width / x_duration_s)
        else:
            x_tick_width_time_min = 1e-6
        tick_spacing = _tick_spacing(x_range64[0], x_range64[1], x_tick_width_time_min)
        x_offset_pow = 10 ** np.ceil(np.log10(tick_spacing))
        x_offset_pow_t64 = time64.SECOND * x_offset_pow
        x_label_offset = int(x_offset_pow_t64 * np.floor(x_range64[0] / x_offset_pow_t64))
        x_zero_offset = x_range64[0]

        x_gain = 0.0 if x_duration_s <= 0 else plot_width / (x_duration_s * time64.SECOND)
        self._x_map = (left_margin, x_label_offset, x_zero_offset, x_gain)
        x_range_trel = [self._x_time64_to_trel(i) for i in self.x_range]

        x_grid = _ticks(x_range_trel[0], x_range_trel[1], x_tick_width_time_min)
        y_text = y + axis_font_metrics.ascent()

        x_offset = self._x_trel_offset()
        x_offset_str = time64.as_datetime(x_offset).isoformat()
        p.drawText(left_margin, margin + plot_label_size.height() + axis_font_metrics.ascent(), x_offset_str)
        p.drawText(margin, y_text, 's')
        self._draw_text(p, margin, margin + 2 * plot_label_size.height() + axis_font_metrics.ascent(), 's')
        if x_grid is None:
            pass
        else:
            for idx, x in enumerate(self._x_trel_to_pixel(x_grid['major'])):
                p.setPen(text_pen)
                p.drawText(x + 2, y_text, x_grid['labels'][idx])
                p.setPen(grid_major_pen)
                p.drawLine(x, y, x, y_end)
            # todo unit_prefix

            y = top_margin
            p.setPen(grid_minor_pen)
            for x in self._x_trel_to_pixel(x_grid['minor']):
                p.drawLine(x, y, x, y_end)
        y = top_margin

        self._y_geometry_info = [
            [margin, 'margin'],
            [top_margin - margin, 'header'],
            [_Y_INNER_SPACING, 'ignore'],
        ]

        self._x_geometry_info = [
            [margin, 'margin'],
            [left_margin - margin, 'axis'],
            [plot_width, 'plot'],
            [statistics_size.width(), 'statistics'],
            [margin, 'margin']
        ]

        # Draw each plot
        for plot_idx, plot in enumerate(self.state['plots']):
            h = plot['height']

            # draw separator
            p.setPen(self._NO_PEN)
            p.setBrush(plot_separator_brush)
            p.drawRect(0, y + 3, widget_w, y_inner_spacing - 6)
            y += y_inner_spacing
            if plot_idx != 0:
                self._y_geometry_info.append([y_inner_spacing, f'spacer.{plot_idx}'])
            self._y_geometry_info.append([h, f'plot.{plot_idx}'])

            # draw border
            p.setPen(plot_border_pen)
            p.setBrush(self._NO_BRUSH)
            # p.drawRect(left_margin, y, plot_width, h)
            p.drawLine(left_margin, y, left_margin, y + h)

            self._plot_range_auto_update(plot)
            # todo set clip bounds
            y_range = plot['range']
            y_scale = h / (y_range[1] - y_range[0])
            plot['y_map'] = (y, y_range[1], y_scale)

            # draw y-axis grid
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
            p.drawText(self._margin, y + (h + axis_font_metrics.ascent()) // 2, s)

            for signal in plot['signals']:
                d = self._signals.get(signal)
                if d is None or d['data'] is None:
                    continue
                d = d['data']
                d_x = self._x_time64_to_pixel(d['x'])
                finite_idx = self._finite_idx(d)
                change_idx = np.where(np.diff(finite_idx))[0] + 1
                segment_idx = []
                if finite_idx[0]:                       # starts with a valid segment
                    if not len(change_idx):             # best case, all data valid, one segment
                        segment_idx = [[0, len(d_x)]]
                    else:                               # NaNs, but starts with valid segment
                        segment_idx.append([0, change_idx[0]])
                        change_idx = change_idx[1:]
                while len(change_idx):
                    if len(change_idx) == 1:
                        segment_idx.append([change_idx[0], len(d_x)])
                        change_idx = change_idx[1:]
                    else:
                        segment_idx.append([change_idx[0], change_idx[1]])
                        change_idx = change_idx[2:]

                p.setPen(self._NO_PEN)
                p.setBrush(plot1_missing)
                if len(segment_idx) > 1:
                    segment_idx_last = segment_idx[0][1]
                    for idx_start, idx_stop in segment_idx[1:]:
                        x1 = d_x[segment_idx_last]
                        x2 = d_x[idx_start]
                        p.drawRect(x1, y, x2 - x1, h)
                        segment_idx_last = idx_stop

                for idx_start, idx_stop in segment_idx:
                    d_x_segment = d_x[idx_start:idx_stop]
                    d_avg = d['avg'][idx_start:idx_stop]
                    if self.show_min_max and d['min'] is not None and d['max'] is not None:
                        d_y_min = self._y_value_to_pixel(plot, d['min'][idx_start:idx_stop])
                        d_y_max = self._y_value_to_pixel(plot, d['max'][idx_start:idx_stop])
                        if 1 == self.show_min_max:
                            if 'line_min' not in d or 'line_max' not in d:
                                d['line_min'] = PointsF()
                                d['line_max'] = PointsF()
                            p.setPen(plot1_min_max_trace)
                            segs, nsegs = d['line_min'].set_line(d_x_segment, d_y_min)
                            p.drawPolyline(segs)
                            segs, nsegs = d['line_max'].set_line(d_x_segment, d_y_max)
                            p.drawPolyline(segs)
                        else:
                            if 'points_min_max' not in d:
                                d['points_min_max'] = PointsF()
                            segs, nsegs = d['points_min_max'].set_fill(d_x_segment, d_y_min, d_y_max)
                            p.setPen(self._NO_PEN)
                            p.setBrush(plot1_min_max_fill)
                            p.drawPolygon(segs)
                            if 3 == self.show_min_max:
                                d_std = d['std'][idx_start:idx_stop]
                                d_y_std_min = self._y_value_to_pixel(plot, d_avg - d_std)
                                d_y_std_max = self._y_value_to_pixel(plot, d_avg + d_std)
                                if 'points_std' not in d:
                                    d['points_std'] = PointsF()
                                segs, nsegs = d['points_std'].set_fill(d_x_segment, d_y_std_min, d_y_std_max)
                                p.setBrush(plot1_std_fill)
                                p.drawPolygon(segs)

                    d_y = self._y_value_to_pixel(plot, d_avg)
                    if 'points_avg' not in d:
                        d['points_avg'] = PointsF()
                    segs, nsegs = d['points_avg'].set_line(d_x_segment, d_y)
                    p.setPen(plot1_trace)
                    p.drawPolyline(segs)

            y += h

        self._y_geometry_info.append([margin, 'margin'])
        self._draw_markers(p, size)
        self._update_fps()
        if self.show_fps:
            p.setPen(text_pen)
            p.drawText(10, axis_font_metrics.ascent(), self._fps['str'])

    def _draw_markers(self, p, size):
        pass  # todo

    def _target_lookup_by_pos(self, pos):
        """Get the target object.

        :param pos: The (x, y) widget pixel coordinates or QtGui.QMouseEvent
        :return: target region tuple (x_name, y_name)
        """
        if isinstance(pos, QtGui.QMouseEvent):
            x, y = pos.pos().x(), pos.pos().y()
        else:
            x, y = pos
        x_name = _target_lookup_by_pos(self._x_geometry_info, x)
        y_name = _target_lookup_by_pos(self._y_geometry_info, y)
        return x_name, y_name

    def plot_mouseMoveEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        if not len(self._x_geometry_info) or not len(self._y_geometry_info):
            return
        x, y = event.pos().x(), event.pos().y()
        self._mouse_pos = (x, y)
        x_name, y_name = self._target_lookup_by_pos(event)
        # self._log.debug(f'mouse release {x_name, y_name}')
        cursor = self._CURSOR_ARROW
        if y_name is None:
            pass
        elif y_name.startswith('spacer.'):
            cursor = self._CURSOR_SIZE_VER
        elif y_name.startswith('plot.') and x_name.startswith('plot'):
            cursor = self._CURSOR_CROSS
        self.setCursor(cursor)

        if self._mouse_action is not None:
            action = self._mouse_action[0]
            if action == 'move.spacer':
                idx = self._mouse_action[1]
                dy = y - self._mouse_action[-1]
                self._mouse_action[-1] = y
                plots = self.state['plots']
                h0 = plots[idx - 1]['height']
                h1 = plots[idx]['height']
                d0, d1 = h0 + dy, h1 - dy
                if d0 < _Y_PLOT_MIN:
                    d1 = h1 + (h0 - _Y_PLOT_MIN)
                    d0 = _Y_PLOT_MIN
                if d1 < _Y_PLOT_MIN:
                    d0 = h0 + (h1 - _Y_PLOT_MIN)
                    d1 = _Y_PLOT_MIN
                plots[idx - 1]['height'] = d0
                plots[idx]['height'] = d1
                self.repaint()

    def plot_mousePressEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x, y = event.pos().x(), event.pos().y()
        x_name, y_name = self._target_lookup_by_pos(event)
        self._log.info(f'mouse press {x_name, y_name}')
        if event.button() == QtCore.Qt.LeftButton:
            if y_name.startswith('spacer'):
                idx = int(y_name.split('.')[1])
                y_start, _ = _target_lookup_by_name(self._y_geometry_info, y_name)
                self._mouse_action = ['move.spacer', idx, y, y_start, y]
            else:
                self._mouse_action = None
        if event.button() == QtCore.Qt.RightButton:
            if y_name.startswith('plot.'):
                idx = int(y_name.split('.')[1])
                if x_name.startswith('axis'):
                    self._menu_y_axis(idx, event)
                elif x_name.startswith('plot'):
                    self._menu_plot(idx, event)
                elif x_name.startswith('statistics'):
                    self._menu_statistics(idx, event)
            elif y_name == 'header':
                if x_name.startswith('plot'):
                    self._menu_header(event)

    def _render_to_pixmap(self):
        sz = self._graphics.size()
        sz = QtCore.QSize(sz.width() * 2, sz.height() * 2)
        pixmap = QtGui.QPixmap(sz)
        pixmap.setDevicePixelRatio(2)
        self._graphics.render(pixmap)
        return pixmap

    def _action_copy_image_to_clipboard(self):
        self._clipboard_image = self._render_to_pixmap().toImage()
        QtWidgets.QApplication.clipboard().setImage(self._clipboard_image)

    @QtCore.Slot(int)
    def _action_save_image_dialog_finish(self, value):
        self._log.info('finished: %d', value)
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            filenames = self._dialog.selectedFiles()
            if len(filenames) == 1:
                self._log.info('finished: accept - save')
                pixmap = self._render_to_pixmap()
                pixmap.save(filenames[0])
            else:
                self._log.info('finished: accept - but no file selected, ignore')
        else:
            self._log.info('finished: reject - abort recording')
        self._dialog.close()
        self._dialog = None

    def _action_save_image(self):
        filter_str = 'png (*.png)'
        filename = time64.filename('.png')
        path = pubsub_singleton.query('registry/paths/settings/save_path')
        path = os.path.join(path, filename)
        dialog = QtWidgets.QFileDialog(self, N_('Save image to file'), path, filter_str)
        dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dialog.finished.connect(self._action_save_image_dialog_finish)
        self._dialog = dialog
        dialog.show()

    def plot_mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x_name, y_name = self._target_lookup_by_pos(event)
        self._log.info(f'mouse release {x_name, y_name}')
        self._mouse_action = None

    def _menu_show(self, event: QtGui.QMouseEvent):
        menu = self._menu[0]
        menu.popup(event.globalPos())
        return menu

    def _menu_y_axis(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_y_axis(%s, %s)', idx, event.pos())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        style_action = settings_action_create(self, menu)
        self._menu = [menu,
                      style_action]
        return self._menu_show(event)

    def _menu_plot(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_plot(%s, %s)', idx, event.pos())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        annotations = menu.addMenu('&Annotations')
        anno_x = annotations.addMenu('&Vertical')
        anno_y = annotations.addMenu('&Horizontal')
        anno_text = annotations.addMenu('&Text')

        copy_image = menu.addAction(N_('Save image to file'))
        copy_image.triggered.connect(self._action_save_image)

        copy_image = menu.addAction(N_('Copy image to clipboard'))
        copy_image.triggered.connect(self._action_copy_image_to_clipboard)

        style_action = settings_action_create(self, menu)
        self._menu = [menu,
                      annotations, anno_x, anno_y, anno_text,
                      copy_image,
                      style_action]
        return self._menu_show(event)

    def _menu_statistics(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_statistics(%s, %s)', idx, event.pos())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        style_action = settings_action_create(self, menu)
        self._menu = [menu,
                      style_action]
        return self._menu_show(event)

    def _menu_header(self, event: QtGui.QMouseEvent):
        self._log.info('_menu_header(%s)', event.pos())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        style_action = settings_action_create(self, menu)
        self._menu = [menu,
                      style_action]
        return self._menu_show(event)

    def on_style_change(self):
        self.update()

    def _on_x_zoom(self, zoom):
        self._log.info(f'_on_x_zoom {zoom}')
        # todo

    def _on_x_pan(self, pan):
        self._log.info(f'_on_x_pan {pan}')
        # todo

    def _on_y_zoom(self, plot, zoom):
        self._log.info(f'_on_y_zoom {plot["quantity"]} {zoom}')
        # todo

    def _on_y_pan(self, plot, pan):
        self._log.info(f'_on_y_pan {plot["quantity"]} {pan}')
        # todo

    def plot_wheelEvent(self, event: QtGui.QWheelEvent):
        x_name, y_name = self._target_lookup_by_pos(self._mouse_pos)
        delta = np.array([event.angleDelta().x(), event.angleDelta().y()], dtype=np.float64)
        delta *= _WHEEL_TO_DEGREES
        self._wheel_accum_degrees += delta
        incr = np.fix(self._wheel_accum_degrees / _WHEEL_TICK_DEGREES)
        self._wheel_accum_degrees -= incr * _WHEEL_TICK_DEGREES
        x_delta, y_delta = incr
        delta = y_delta

        is_pan = QtCore.Qt.KeyboardModifier.ShiftModifier & event.modifiers()
        if x_delta and not y_delta:
            delta = x_delta
            is_pan = True
        is_y = QtCore.Qt.KeyboardModifier.ControlModifier & event.modifiers()

        if x_name == 'plot' and (y_name == 'header' or not is_y):
            if is_pan:
                self._on_x_pan(delta)
            else:
                self._on_x_zoom(delta)
        elif y_name.startswith('plot.') and (is_y or x_name == 'axis'):
            plot_idx = int(y_name.split('.')[1])
            plot = self.state['plots'][plot_idx]
            if is_pan:
                self._on_y_pan(plot, delta)
            else:
                self._on_y_zoom(plot, delta)

