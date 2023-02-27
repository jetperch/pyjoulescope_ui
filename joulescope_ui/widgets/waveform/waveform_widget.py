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
from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name, tooltip_format, time64
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.widget_tools import settings_action_create
from .line_segments import PointsF
from .waveform_control import WaveformControlWidget
import copy
import logging
import numpy as np
import os
import time
from PySide6.QtGui import QPainter, QPen, QBrush, QColor
from joulescope_ui.units import unit_prefix, three_sig_figs


_ZOOM_FACTOR = np.sqrt(2)
_WHEEL_TO_DEGREES = 1.0 / 8.0  # https://doc.qt.io/qt-6/qwheelevent.html#angleDelta
_WHEEL_TICK_DEGREES = 15.0   # Standard convention
_AUTO_RANGE_FRACT = 0.50  # autorange when current range smaller than existing range by this fractional amount.
_BINARY_RANGE = [-0.1, 1.1]
_MARGIN = 2             # from the outside edges
_Y_INNER_SPACING = 8    # vertical spacing between plots (includes line)
_Y_INNER_LINE = 4
_Y_PLOT_MIN = 16


def _analog_plot(quantity, show, units, name, integral=None):
    return {
        'quantity': quantity,
        'name': name,
        'units': units,
        'enabled': bool(show),
        'signals': [],  # list of (buffer_unique_id, signal_id)
        'height': 200,
        'range_mode': 'auto',
        'range': [-0.1, 1.1],
        'scale': 'linear',
        'integral': integral,
    }


def _digital_plot(quantity, name):
    return {
        'quantity': quantity,
        'name': name,
        'units': None,
        'enabled': False,
        'signals': [],  # list of (buffer_unique_id, signal_id)
        'height': 100,
        'range_mode': 'fixed',
        'range': _BINARY_RANGE,
        'scale': 'linear',
    }


_STATE_DEFAULT = {
    'plots': [
        _analog_plot('i', True, 'A', N_('Current'), 'C'),
        _analog_plot('v', True, 'V', N_('Voltage')),
        _analog_plot('p', False, 'W', N_('Power'), 'J'),
        {
                'quantity': 'r',
                'name': N_('Current range'),
                'units': None,
                'enabled': False,
                'signals': [],  # list of (buffer_unique_id, signal_id)
                'height': 100,
                'range_mode': 'manual',
                'range': [-0.1, 7.1],
                'scale': 'linear',
        },
        _digital_plot('0', N_('General purpose input 0')),
        _digital_plot('1', N_('General purpose input 1')),
        _digital_plot('2', N_('General purpose input 2')),
        _digital_plot('3', N_('General purpose input 3')),
        _digital_plot('T', N_('Trigger input')),
    ],
    'x_marker1': [],  # list of [id, x_pos]
    'x_marker2': [],  # list of [id, x_pos1, x_pos2]
}


def _si_format(values, units):
    results = []
    if units is None:
        units = ''
    is_array = hasattr(values, '__len__')
    if not is_array:
        values = [values]
    if len(values):
        values = np.array(values)
        max_value = float(np.max(np.abs(values)))
        _, prefix, scale = unit_prefix(max_value)
        scale = 1.0 / scale
        if len(units) or len(prefix):
            units_suffix = f' {prefix}{units}'
        else:
            units_suffix = ''
        for v in values:
            v *= scale
            if abs(v) < 0.000005:  # minimum display resolution
                v = 0
            v_str = ('%+6f' % v)[:8]
            results.append(f'{v_str}{units_suffix}')
    return results if is_array else results[0]


class _PlotWidget(QtWidgets.QWidget):
    """The inner plot widget that simply calls back to the Waveform widget."""

    def __init__(self, parent):
        self._parent = parent
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        size = self.width(), self.height()
        painter = QtGui.QPainter(self)  # calls begin()
        self._parent.plot_paint(painter, size)
        # painter.end()  Automatically called by destructor

    def resizeEvent(self, event):
        self._parent.plot_resizeEvent(event)

    def leaveEvent(self, event):
        self._parent.plot_leaveEvent(event)
        return super().leaveEvent(event)

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
    while minor_start < v_min and k < len(sel_idx):
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


def _target_from_list(targets):
    d = {}
    v = 0
    for sz, n in targets:
        v_next = v + sz
        if n in d:
            raise RuntimeError(f'Duplicate section name {n}')
        d[n] = [sz, v, v_next]
        v = v_next
    return d


def _target_lookup_by_pos(targets, pos):
    for name, (_, _, v) in targets.items():
        if pos < v:
            break
    return name


@register
@styled_widget(N_('Waveform'))
class WaveformWidget(QtWidgets.QWidget):
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
                [0, N_('off')],
                [1, N_('lines')],
                [2, N_('fill 1')],
                [3, N_('fill 2')],
            ],
            'default': 3,
        },
        'show_fps': {
            'dtype': 'bool',
            'brief': N_('Show the frames per second.'),
            'default': False,
        },
        'show_hover': {
            'dtype': 'bool',
            'brief': N_('Show the statistics on mouse hover.'),
            'default': True,
        },
        'show_statistics': {
            'dtype': 'bool',
            'brief': N_('Show the plot statistics on the right.'),
            'default': True,
        },
        'x_range': {
            'dtype': 'obj',
            'brief': 'The x-axis range.',
            'default': [0, 0],
            'flags': ['hidden', 'ro', 'skip_undo'],  # publish only
        },
        'pin_left': {
            'dtype': 'bool',
            'brief': N_('Pin the left side (oldest) data so that it stays in view.'),
            'default': True,
        },
        'pin_right': {
            'dtype': 'bool',
            'brief': N_('Pin the right side (newest) data so that it stays in view.'),
            'default': True,
        },
        'state': {
            'dtype': 'obj',
            'brief': N_('The waveform state.'),
            'default': None,
            'flags': ['hidden', 'ro'],
        },
    }

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        self.pubsub = None
        self.state = None
        self._style_cache = None
        super().__init__(parent)

        # Cache Qt default instances to prevent memory leak in Pyside6 6.4.2
        self._NO_PEN = QtGui.QPen(QtGui.Qt.NoPen)  # prevent memory leak
        self._NO_BRUSH = QtGui.QBrush(QtGui.Qt.NoBrush)  # prevent memory leak
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_VER = QtGui.QCursor(QtGui.Qt.SizeVerCursor)
        self._CURSOR_CROSS = QtGui.QCursor(QtGui.Qt.CrossCursor)

        self._on_source_list_fn = self._on_source_list
        self._on_signal_add_fn = self._on_signal_add
        self._on_signal_remove_fn = self._on_signal_remove
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
        self._control = WaveformControlWidget(self)
        self._layout.addWidget(self._control)

        self._x_geometry_info = {}
        self._y_geometry_info = {}
        self._mouse_action = None
        self._clipboard_image = None
        self._signals = {}
        self._signals_by_rsp_id = {}
        self._signals_rsp_id_next = 2  # reserve 1 for summary

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

    def _on_source_list(self, sources):
        if not len(sources):
            self._log.warning('No default source available')
            return
        source = sources[0]
        topic = get_topic_name(source)
        signals = self.pubsub.enumerate(f'{topic}/settings/signals')
        try:
            self.pubsub.query(f'{topic}/events/signals/!add')
            self.pubsub.subscribe(f'{topic}/events/signals/!add', self._on_signal_add_fn, ['pub'])
            self.pubsub.subscribe(f'{topic}/events/signals/!remove', self._on_signal_remove_fn, ['pub'])
        except KeyError:
            pass

        for signal in signals:
            self._on_signal_add(f'{topic}/events/signals/!add', signal)

    def _on_signal_add(self, topic, value):
        self._log.info(f'_on_signal_add({topic}, {value})')
        source = topic.split('/')[1]
        signal = value
        topic = get_topic_name(source)
        item = (source, signal)
        if item in self._signals:
            self._signals[item]['enabled'] = True
        self.pubsub.subscribe(f'{topic}/settings/signals/{signal}/range',
                              self._on_signal_range_fn, ['pub', 'retain'])
        source_id, quantity = signal.split('.')
        for plot in self.state['plots']:
            if plot['quantity'] == quantity:
                if item not in plot['signals']:
                    plot['signals'].append(item)
        self._repaint_request = True

    def _on_signal_remove(self, topic, value):
        self._log.info(f'_on_signal_remove({topic}, {value})')
        source = topic.split('/')[1]
        signal = value
        item = (source, signal)
        for plot in self.state['plots']:
            if item in plot['signals']:
                plot['signals'].remove(item)
        if item in self._signals:
            self._signals[item]['enabled'] = False

    def on_pubsub_register(self):
        if self.state is None:
            self.state = copy.deepcopy(_STATE_DEFAULT)
        for plot_index, plot in enumerate(self.state['plots']):
            plot['index'] = plot_index
            plot['y_region'] = f'plot.{plot_index}'
            if 'y_marker1' not in plot:
                plot['y_marker1'] = []
            if 'y_marker2' not in plot:
                plot['y_marker2'] = []
        self.pubsub.subscribe('registry_manager/capabilities/signal_buffer.source/list',
                              self._on_source_list_fn, ['pub', 'retain'])
        topic = get_topic_name(self)
        self._control.on_pubsub_register(self.pubsub, topic)

    def closeEvent(self, event):
        self.pubsub.unsubscribe_all(self._on_source_list_fn)
        self.pubsub.unsubscribe_all(self._on_signal_range_fn)
        self._refresh_timer.stop()
        return super().closeEvent(event)

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
                'enabled': True,
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
            self._repaint_request = d['enabled']
        return None

    def _on_refresh_timer(self):
        if self._repaint_request:
            self.repaint()

    def _extents(self):
        x_min = []
        x_max = []
        for signal in self._signals.values():
            if signal['enabled']:
                x_range = signal['range']
                x_min.append(x_range[0])
                x_max.append(x_range[1])
        if 0 == len(x_min):
            return [0, 0]
        return min(x_min), max(x_max)

    def _compute_x_range(self):
        e0, e1 = self._extents()
        x0, x1 = self.x_range
        d_e = e1 - e0
        d_x = x1 - x0
        d_z = min(d_e, d_x)
        if x0 == 0 and x1 == 0:
            return e0, e1
        elif self.pin_left and self.pin_right:
            return e0, e1
        elif self.pin_right:
            return e1 - d_z, e1
        elif self.pin_left:
            return e0, e0 + d_z
        else:
            x0 = max(x0, e0)
            return x0, x0 + d_z

    def _request_data(self, force=False):
        force = bool(force)
        self.x_range = self._compute_x_range()
        for signal in self._signals.values():
            if not signal['enabled']:
                continue
            if force or signal['changed']:
                signal['changed'] = None
                self._request_signal(signal, self.x_range)

    def _request_signal(self, signal, x_range, rsp_id=None):
        topic_req = f'registry/{signal["source"]}/actions/!request'
        topic_rsp = f'{get_topic_name(self)}/callbacks/!response'
        x_info = self._x_geometry_info.get('plot')
        if x_info is None:
            return
        req = {
            'signal_id': signal['signal_id'],
            'time_type': 'utc',
            'rsp_topic': topic_rsp,
            'rsp_id': signal['rsp_id'] if rsp_id is None else rsp_id,
            'start': x_range[0],
            'end': x_range[1],
            'length': x_info[0],
        }
        self.pubsub.publish(topic_req, req)

    def on_cbk_response(self, topic, value):
        utc = value['info']['time_range_utc']
        if utc['length'] == 0:
            return
        x = np.linspace(utc['start'], utc['end'], utc['length'], dtype=np.int64)
        response_type = value['response_type']
        rsp_id = value['rsp_id']

        self._repaint_request = True
        if response_type == 'samples':
            # self._log.info(f'response samples {length}')
            y = value['data']
            data_type = value['data_type']
            if data_type == 'f32':
                pass
            elif data_type == 'u1':
                y = np.unpackbits(y, bitorder='little')[:len(x)]
            elif data_type == 'u4':
                d = np.empty(len(y) * 2, dtype=np.uint8)
                d[0::2] = np.logical_and(y, 0x0f)
                d[1::2] = np.logical_and(np.right_shift(y, 4), 0x0f)
                y = d[:len(x)]
            else:
                self._log.warning('Unsupported sample data type: %s', data_type)
                return
            data = {
                'x': x,
                'avg': y,
                'std': None,
                'min': None,
                'max': None,
            }
        elif response_type == 'summary':
            # self._log.info(f'response summary {length}')
            y = value['data']
            data = {
                'x': x,
                'avg': y[:, 0],
                'std': y[:, 1],
                'min': y[:, 2],
                'max': y[:, 3],
            }
        else:
            self._log.warning('unsupported response type: %s', response_type)
            return

        signal = self._signals_by_rsp_id.get(rsp_id)
        if signal is None:
            self._log.warning('Unknown signal rsp_id %s', rsp_id)
            return
        signal['data'] = data

    def _x_trel_offset(self):
        offset = self._x_map[1]
        offset = (offset // time64.SECOND) * time64.SECOND
        return offset

    def _x_time64_to_pixel(self, time):
        pixel_offset, _, time_zero_offset, time_to_pixel_scale = self._x_map
        return pixel_offset + (time - time_zero_offset) * time_to_pixel_scale

    def _x_pixel_to_time64(self, pixel):
        pixel_offset, _, time_zero_offset, time_to_pixel_scale = self._x_map
        return time_zero_offset + int((pixel - pixel_offset) * (1.0 / time_to_pixel_scale))

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

    @property
    def _style(self):
        if self._style_cache is not None:
            return self._style_cache
        if not hasattr(self, 'style_manager_info'):
            self._style_cache = None
        v = self.style_manager_info['sub_vars']

        axis_font = font_as_qfont(v['waveform.axis_font'])
        axis_font_metrics = QtGui.QFontMetrics(axis_font)
        y_tick_size = axis_font_metrics.boundingRect('888.888')

        self._style_cache = {
            'background_brush': QtGui.QBrush(color_as_qcolor(v['waveform.background'])),

            'text_pen': QtGui.QPen(color_as_qcolor(v['waveform.text_foreground'])),
            'text_brush': QtGui.QBrush(color_as_qcolor(v['waveform.text_background'])),
            'grid_major_pen': QtGui.QPen(color_as_qcolor(v['waveform.grid_major'])),
            'grid_minor_pen': QtGui.QPen(color_as_qcolor(v['waveform.grid_minor'])),
            'plot_border_pen': QtGui.QPen(color_as_qcolor(v['waveform.plot_border'])),
            'plot_separator_brush': QtGui.QBrush(color_as_qcolor(v['waveform.plot_separator'])),

            'waveform.hover': QBrush(color_as_qcolor(v['waveform.hover'])),

            'plot1_trace': QPen(color_as_qcolor(v['waveform.plot1_trace'])),
            'plot1_min_max_trace': QPen(color_as_qcolor(v['waveform.plot1_min_max_trace'])),
            'plot1_min_max_fill_pen': QPen(color_as_qcolor(v['waveform.plot1_min_max_fill'])),
            'plot1_min_max_fill_brush': QBrush(color_as_qcolor(v['waveform.plot1_min_max_fill'])),
            'plot1_std_fill': QBrush(color_as_qcolor(v['waveform.plot1_std_fill'])),
            'plot1_missing': QBrush(color_as_qcolor(v['waveform.plot1_missing'])),

            'axis_font': axis_font,
            'axis_font_metrics': QtGui.QFontMetrics(axis_font),
            'plot_label_size': axis_font_metrics.boundingRect('WW'),
            'y_tick_size': y_tick_size,
            'y_tick_height_pixels_min': 1.5 * y_tick_size.height(),
            'utc_width_pixels': axis_font_metrics.boundingRect('8888-88-88W88:88:88.888888').width(),
            'x_tick_width_pixels_min': axis_font_metrics.boundingRect('888.888888').width(),

            'statistics_name_size': axis_font_metrics.boundingRect('maxx').width(),
            'statistics_value_size': axis_font_metrics.boundingRect('+888.888x').width(),
            'statistics_unit_size': axis_font_metrics.boundingRect('WWW').width(),
            'statistics_size': axis_font_metrics.boundingRect('maxx+888.888xmA'),
        }
        self._style_cache['plot1_trace'].setWidth(self.trace_width)
        return self._style_cache

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

    def _plots_height_adjust(self, h=None):
        if h is None:
            h = self._graphics.height()
        if not len(self._y_geometry_info):
            return
        for name, (k, _, _) in self._y_geometry_info.items():
            if not name.startswith('plot'):
                h -= k
        plots = [p for p in self.state['plots'] if p['enabled']]
        k = len(plots)
        if k == 0:
            return
        h_now = 0
        for plot in plots:
            h_now += plot['height']
        if h_now <= 0:
            return
        h_min = _Y_PLOT_MIN * k
        if h < h_min:
            self._log.info('too short')
            h = h_min
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

    def plot_resizeEvent(self, event):
        event.accept()
        self._repaint_request = True
        self._plots_height_adjust()

    def plot_leaveEvent(self, event):
        self.setCursor(self._CURSOR_ARROW)

    def plot_paint(self, p, size):
        try:
            self._plot_paint(p, size)
        except Exception:
            self._log.exception('Exception during drawing')
        self._request_data()

    def _compute_geometry(self, size=None):
        s = self._style
        if s is None:
            self._x_geometry_info = {}
            self._y_geometry_info = {}
            return
        if size is None:
            widget_w, widget_h = self._graphics.width(), self._graphics.height()
        else:
            widget_w, widget_h = size

        margin = self._margin
        left_width = s['plot_label_size'].width() + margin + s['y_tick_size'].width() + margin
        if self.show_statistics:
            right_width = margin + s['statistics_size'].width()
        else:
            right_width = 0
        plot_width = widget_w - left_width - right_width - 2 * margin
        y_inner_spacing = _Y_INNER_SPACING

        y_geometry = [
            [margin, 'margin.top'],
            [s['plot_label_size'].height() * 3, 'x_axis'],
            [y_inner_spacing, 'spacer.ignore'],
        ]
        plot_first = True
        for plot in self.state['plots']:
            if not plot['enabled']:
                continue
            plot_idx = plot['index']
            if not plot_first:
                y_geometry.append([y_inner_spacing, f'spacer.{plot_idx}'])
            plot_first = False
            y_geometry.append([plot['height'], plot['y_region']])
        y_geometry.append([margin, 'margin.bottom'])

        x_geometry = [
            [margin, 'margin.left'],
            [left_width, 'y_axis'],
            [plot_width, 'plot'],
        ]
        if right_width:
            x_geometry.append([right_width, 'statistics'])
        x_geometry.append([margin, 'margin.right'])

        self._x_geometry_info = _target_from_list(x_geometry)
        self._y_geometry_info = _target_from_list(y_geometry)

    def _plot_paint(self, p, size):
        """Paint the plot.

        :param p: The QPainter instance.
        :param size: The (width, height) for the plot area.
        """
        s = self._style
        if s is None:
            return
        self._repaint_request = False

        resize = not len(self._y_geometry_info)
        self._compute_geometry(size)
        if resize:
            self._plots_height_adjust()
        self._draw_background(p, size)
        self._draw_x_axis(p)

        # Draw each plot
        for plot in self.state['plots']:
            if plot['enabled']:
                self._draw_plot(p, plot)
                p.setClipping(False)
                self._draw_plot_statistics(p, plot)
        self._draw_spacers(p)
        self._draw_markers(p, size)
        self._draw_fps(p)
        self._draw_hover(p)

    def _draw_background(self, p, size):
        s = self._style
        widget_w, widget_h = size
        p.fillRect(0, 0, widget_w, widget_h, s['background_brush'])

    def _draw_x_axis(self, p):
        s = self._style
        p.setPen(s['text_pen'])
        p.setBrush(s['text_brush'])
        p.setFont(s['axis_font'])

        # compute time and draw x-axis including UTC, seconds, grid
        x_axis_height, x_axis_y0, x_axis_y1 = self._y_geometry_info['x_axis']
        left_width, left_x0, left_x1, = self._x_geometry_info['y_axis']
        plot_width, plot_x0, plot_x1, = self._x_geometry_info['plot']
        _, y_end, _, = self._y_geometry_info['margin.bottom']

        y = x_axis_y0 + 2 * s['plot_label_size'].height()
        x_range64 = self.x_range
        x_duration_s = (x_range64[1] - x_range64[0]) / time64.SECOND
        if x_duration_s > 0:
            x_tick_width_time_min = s['x_tick_width_pixels_min'] / (plot_width / x_duration_s)
        else:
            x_tick_width_time_min = 1e-6
        tick_spacing = _tick_spacing(x_range64[0], x_range64[1], x_tick_width_time_min)
        x_offset_pow = 10 ** np.ceil(np.log10(tick_spacing))
        x_offset_pow_t64 = time64.SECOND * x_offset_pow
        x_label_offset = int(x_offset_pow_t64 * np.floor(x_range64[0] / x_offset_pow_t64))
        x_zero_offset = x_range64[0]

        x_gain = 0.0 if x_duration_s <= 0 else (plot_width - 1) / (x_duration_s * time64.SECOND)
        self._x_map = (left_x1, x_label_offset, x_zero_offset, x_gain)
        x_range_trel = [self._x_time64_to_trel(i) for i in self.x_range]

        x_grid = _ticks(x_range_trel[0], x_range_trel[1], x_tick_width_time_min)
        y_text = y + s['axis_font_metrics'].ascent()

        x_offset = self._x_trel_offset()
        x_offset_str = time64.as_datetime(x_offset).isoformat()
        p.drawText(plot_x0, x_axis_y0 + s['plot_label_size'].height() + s['axis_font_metrics'].ascent(), x_offset_str)
        p.drawText(left_x0, y_text, 's')
        self._draw_text(p, left_x0, x_axis_y0 + 2 * s['plot_label_size'].height() + s['axis_font_metrics'].ascent(), 's')
        if x_grid is None:
            pass
        else:
            for idx, x in enumerate(self._x_trel_to_pixel(x_grid['major'])):
                p.setPen(s['text_pen'])
                p.drawText(x + 2, y_text, x_grid['labels'][idx])
                p.setPen(s['grid_major_pen'])
                p.drawLine(x, y, x, y_end)
            # todo unit_prefix

            p.setPen(s['grid_minor_pen'])
            for x in self._x_trel_to_pixel(x_grid['minor']):
                p.drawLine(x, x_axis_y1, x, y_end)

    def _draw_spacers(self, p):
        s = self._style
        p.setPen(self._NO_PEN)
        p.setBrush(s['plot_separator_brush'])
        _, _, x0 = self._x_geometry_info['margin.left']
        _, x1, _ = self._x_geometry_info['margin.right']
        w = x1 - x0

        for name, (h, y0, y1) in self._y_geometry_info.items():
            if name.startswith('spacer'):
                p.drawRect(x0, y0 + 3, w, 2)

    def _draw_plot(self, p, plot):
        s = self._style
        h, y0, y1 = self._y_geometry_info[f'plot.{plot["index"]}']
        w, x0, x1 = self._x_geometry_info['plot']
        _, left, _, = self._x_geometry_info['y_axis']

        # draw border
        p.setPen(s['plot_border_pen'])
        p.setBrush(self._NO_BRUSH)
        # p.drawRect(left_margin, y, plot_width, h)
        p.drawLine(x0, y0, x0, y1)

        self._plot_range_auto_update(plot)
        y_range = plot['range']
        y_scale = h / (y_range[1] - y_range[0])
        plot['y_map'] = (y0, y_range[1], y_scale)

        # draw y-axis grid
        p.setFont(s['axis_font'])
        y_tick_height_value_min = s['y_tick_height_pixels_min'] / plot['y_map'][-1]
        y_grid = _ticks(y_range[0], y_range[1], y_tick_height_value_min)
        axis_font_metrics = s['axis_font_metrics']
        if y_grid is not None:
            for idx, t in enumerate(self._y_value_to_pixel(plot, y_grid['major'])):
                p.setPen(s['text_pen'])
                s_label = y_grid['labels'][idx]
                font_w = axis_font_metrics.boundingRect(s_label).width()
                p.drawText(x0 - 4 - font_w, t + axis_font_metrics.ascent() // 2, s_label)
                p.setPen(s['grid_major_pen'])
                p.drawLine(x0, t, x1, t)

            # p.setPen(grid_minor_pen)
            # for t in self._y_value_to_pixel(plot, y_grid['minor']):
            #    p.drawLine(left_margin, t, left_margin + plot_width, t)

        # draw label
        p.setPen(s['text_pen'])
        p.setFont(s['axis_font'])
        plot_units = plot.get('units')
        if plot_units is None:
            s_label = plot['quantity']
        else:
            s_label = f"{y_grid['unit_prefix']}{plot_units}"
        p.drawText(left, y0 + (h + axis_font_metrics.ascent()) // 2, s_label)

        p.setClipRect(x0, y0, w, h)

        for signal in plot['signals']:
            d = self._signals.get(signal)
            if d is None or d['data'] is None:
                continue
            d = d['data']
            d_x = self._x_time64_to_pixel(d['x'])
            if len(d_x) == w:
                d_x, d_x2 = np.rint(d_x), d_x
                if np.any(np.abs(d_x - d_x2) > 0.5):
                    self._log.warning('x does not conform to pixels')
                    d_x = d_x2
            finite_idx = self._finite_idx(d)
            change_idx = np.where(np.diff(finite_idx))[0] + 1
            segment_idx = []
            if finite_idx[0]:  # starts with a valid segment
                if not len(change_idx):  # best case, all data valid, one segment
                    segment_idx = [[0, len(d_x)]]
                else:  # NaNs, but starts with valid segment
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
            p.setBrush(s['plot1_missing'])
            if len(segment_idx) > 1:
                segment_idx_last = segment_idx[0][1]
                for idx_start, idx_stop in segment_idx[1:]:
                    x1 = d_x[segment_idx_last]
                    x2 = d_x[idx_start]
                    p.drawRect(x1, y0, x2 - x1, h)
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
                        p.setPen(s['plot1_min_max_trace'])
                        segs, nsegs = d['line_min'].set_line(d_x_segment, d_y_min)
                        p.drawPolyline(segs)
                        segs, nsegs = d['line_max'].set_line(d_x_segment, d_y_max)
                        p.drawPolyline(segs)
                    else:
                        if 'points_min_max' not in d:
                            d['points_min_max'] = PointsF()
                        segs, nsegs = d['points_min_max'].set_fill(d_x_segment, d_y_min, d_y_max)
                        p.setPen(s['plot1_min_max_fill_pen'])
                        p.setBrush(s['plot1_min_max_fill_brush'])
                        p.drawPolygon(segs)
                        if 3 == self.show_min_max:
                            d_std = d['std'][idx_start:idx_stop]
                            d_y_std_min = self._y_value_to_pixel(plot, d_avg - d_std)
                            d_y_std_max = self._y_value_to_pixel(plot, d_avg + d_std)
                            if 'points_std' not in d:
                                d['points_std'] = PointsF()
                            segs, nsegs = d['points_std'].set_fill(d_x_segment, d_y_std_min, d_y_std_max)
                            p.setPen(self._NO_PEN)
                            p.setBrush(s['plot1_std_fill'])
                            p.drawPolygon(segs)

                d_y = self._y_value_to_pixel(plot, d_avg)
                if 'points_avg' not in d:
                    d['points_avg'] = PointsF()
                segs, nsegs = d['points_avg'].set_line(d_x_segment, d_y)
                p.setPen(s['plot1_trace'])
                p.drawPolyline(segs)

    def _draw_markers(self, p, size):
        pass  # todo

    def _draw_fps(self, p):
        s = self._style
        self._update_fps()
        if self.show_fps:
            p.setFont(s['axis_font'])
            p.setPen(s['text_pen'])
            p.drawText(10, s['axis_font_metrics'].ascent(), self._fps['str'])

    def _signal_data_get(self, plot):
        try:
            if isinstance(plot, str):
                plot_idx = int(plot.split('.')[1])
                plot = self.state['plots'][plot_idx]
            signals = plot['signals']
            signal = self._signals[signals[0]]
            data = signal['data']
            return plot, data
        except (KeyError, IndexError):
            return None, None

    def _draw_hover(self, p):
        if not self.show_hover:
            return
        if self._mouse_pos is None:
            return
        x_name, y_name = self._target_lookup_by_pos(self._mouse_pos)
        if x_name != 'plot' or not y_name.startswith('plot.'):
            return
        plot, data = self._signal_data_get(y_name)
        if data is None:
            return
        x_pixels = self._mouse_pos[0]
        x = self._x_pixel_to_time64(x_pixels)
        x_rel = self._x_time64_to_trel(x)
        index = np.abs(data['x'] - x).argmin()
        y = data['avg'][index]
        if not np.isfinite(y):
            return
        y_pixels = int(np.rint(self._y_value_to_pixel(plot, y)))

        dot_radius = 2
        dot_diameter = dot_radius * 2
        s = self._style
        p.setPen(self._NO_PEN)
        p.setBrush(s['waveform.hover'])
        p.drawEllipse(x_pixels - dot_radius, y_pixels - dot_radius, dot_diameter, dot_diameter)

        p.setFont(s['axis_font'])
        x_txt = _si_format([x_rel], 's')[0]
        y_txt = _si_format([y], plot['units'])[0]
        font_metrics = s['axis_font_metrics']
        margin = 2
        f_h = font_metrics.height()
        f_a = font_metrics.ascent()
        h = 2 * margin + f_h * 2
        w = 2 * margin + max(font_metrics.boundingRect(x_txt).width(), font_metrics.boundingRect(y_txt).width())
        y_pixels -= h // 2

        _, x0, x1 = self._x_geometry_info[x_name]
        _, y0, y1 = self._y_geometry_info[y_name]
        p.setClipRect(x0, y0, x1 - x0, y1 - y0)
        x_pixels += dot_radius
        if x_pixels + w > x1:
            # show on left side
            x_pixels -= dot_diameter + w
        if y_pixels < y0:
            y_pixels = y0
        elif y_pixels + h > y1:
            y_pixels = y1 - h

        p.setPen(s['text_pen'])
        p.setBrush(s['text_brush'])
        p.fillRect(x_pixels, y_pixels, w, h, p.brush())
        p.drawText(x_pixels + margin, y_pixels + margin + f_a, y_txt)
        p.drawText(x_pixels + margin, y_pixels + margin + f_h + f_a, x_txt)

    def _draw_plot_statistics(self, p, plot):
        if not self.show_statistics:
            return
        plot, data = self._signal_data_get(plot)
        if data is None:
            return
        xd, x0, x1 = self._x_geometry_info['statistics']
        yd, y0, y1 = self._y_geometry_info[plot['y_region']]
        s = self._style
        z0, z1 = self.x_range
        font = s['axis_font']
        font_metrics = s['axis_font_metrics']
        f_h = font_metrics.height()
        f_a = font_metrics.ascent()
        p.setFont(font)
        p.setPen(s['text_pen'])
        p.setBrush(self._NO_BRUSH)

        x_data = data['x']
        y_data = data['avg']
        idx_sel = np.logical_and(np.logical_and(x_data >= z0, x_data <= z1), np.isfinite(y_data))
        y_data = y_data[idx_sel]
        if not len(y_data):
            return
        y_avg = np.mean(y_data)
        if data['std'] is None:
            y_std = np.std(y_data)
        else:
            y_std = data['std'][idx_sel]
            y_d = y_data - y_avg
            y_std = y_std * y_std + y_d * y_d
            y_std = np.sqrt(np.sum(y_std) / len(y_std))
        if data['min'] is None:
            y_min = np.min(y_data)
        else:
            y_min = np.min(data['min'][idx_sel])
        if data['max'] is None:
            y_max = np.max(y_data)
        else:
            y_max = np.max(data['max'][idx_sel])
        y_rms = np.sqrt(y_avg * y_avg + y_std * y_std)
        q_names = ['avg', 'std', 'rms', 'min', 'max', 'p2p']
        q_value = [y_avg, y_std, y_rms, y_min, y_max, y_max - y_min]
        q_str = _si_format(q_value, plot['units'])

        dt = (z1 - z0) / time64.SECOND
        integral_units = plot.get('integral')
        if integral_units is not None:
            q_names.append('∫')
            q_str.append(_si_format(y_avg * dt, integral_units))
        q_names.append('Δt')
        q_str.append(_si_format(dt, 's'))
        y = y0 + f_a
        p.setClipRect(x0, y0, xd, yd)
        x2 = x0 + s['statistics_name_size']
        for name, value in zip(q_names, q_str):
            p.drawText(x0, y, name)
            p.drawText(x2, y, value)
            y += f_h
        p.setClipping(False)

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
        elif y_name.startswith('spacer.') and y_name not in ['spacer.ignore']:
            cursor = self._CURSOR_SIZE_VER
        elif y_name.startswith('plot.') and x_name.startswith('plot'):
            cursor = self._CURSOR_CROSS
            self._repaint_request = True
        self.setCursor(cursor)

        if self._mouse_action is not None:
            action = self._mouse_action[0]
            if action == 'move.spacer':
                plot_idx = self._mouse_action[1]
                dy = y - self._mouse_action[-1]
                self._mouse_action[-1] = y
                plots = [p for p in self.state['plots'] if p['enabled']]
                for idx, plot in enumerate(plots):
                    if plot['index'] == plot_idx:
                        break
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
            if action == 'x_pan':
                self._mouse_x_pan(x)

    def _mouse_x_pan(self, x):
        t0 = self._x_pixel_to_time64(self._mouse_action[1])
        t1 = self._x_pixel_to_time64(x)
        self._mouse_action[1] = x
        e0, e1 = self._extents()
        dt = t0 - t1
        x0, x1 = self.x_range
        d_x = x1 - x0
        z0, z1 = x0 + dt, x1 + dt
        if self.pin_left or z0 < e0:
            z0, z1 = e0, e0 + d_x
        elif self.pin_right or z1 > e1:
            z0, z1 = e1 - d_x, e1
        self.x_range = z0, z1
        self._request_data(True)

    def plot_mousePressEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x, y = event.pos().x(), event.pos().y()
        x_name, y_name = self._target_lookup_by_pos(event)
        self._log.info(f'mouse press {x_name, y_name}')
        if event.button() == QtCore.Qt.LeftButton:
            if y_name.startswith('spacer') and y_name not in ['spacer.ignore']:
                idx = int(y_name.split('.')[1])
                _, y_start, _ = self._y_geometry_info[y_name]
                self._mouse_action = ['move.spacer', idx, y, y_start, y]
            elif y_name.startswith('plot') and x_name == 'plot':
                if self.pin_left or self.pin_right:
                    pass  # pinned to extents, cannot pan
                else:
                    self._mouse_action = ['x_pan', x]
            else:
                self._mouse_action = None
        if event.button() == QtCore.Qt.RightButton:
            if y_name.startswith('plot.'):
                idx = int(y_name.split('.')[1])
                if x_name.startswith('y_axis'):
                    self._menu_y_axis(idx, event)
                elif x_name.startswith('plot'):
                    self._menu_plot(idx, event)
                elif x_name.startswith('statistics'):
                    self._menu_statistics(idx, event)
            elif y_name == 'x_axis':
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
        self._style_cache = None
        self.update()

    def on_action_markers(self, value):
        """Perform a marker action.

        :param value: Either the action string or details for markers.
            Action strings include: add_single, add_dual, clear_all
        """
        self._log.info('markers %s', value)
        if isinstance(value, str):
            if value == 'add_single':
                pass
            elif value == 'add_dual':
                pass
            elif value == 'clear_all':
                pass
            else:
                raise ValueError(f'Unsupported marker action {value}')
        else:
            raise NotImplementedError(f'Unsupported marker action {value}')

    def on_action_x_zoom(self, value):
        """Perform a zoom action.

        :param value: [steps, center].  Steps is the number of incremental
            steps to zoom.  Center is the x-axis time center point for the zoom.
            If Center is None, use the screen center.
        """
        steps, center = value
        if steps == 0:
            return
        self._log.info('x_zoom %s', value)
        if self.pin_left and self.pin_right:
            return  # already locked to full extents
        e0, e1 = self._extents()
        x0, x1 = self.x_range
        d_e = e1 - e0
        d_x = x1 - x0
        if center is None:
            center = (x1 + x0) // 2
        center = max(x0, min(center, x1))
        f = (center - x0) / d_x
        if steps < 0:  # zoom out
            d_x = d_x * _ZOOM_FACTOR
        else:
            d_x = d_x / _ZOOM_FACTOR
        r = min(d_x, d_e)
        z0, z1 = center - int(r * f), center + int(r * (1 - f))
        if self.pin_left or z0 < e0:
            z0, z1 = e0, e0 + r
        elif self.pin_right or z1 > e1:
            z0, z1 = e1 - r, e1
        self._repaint_request = True
        self.x_range = z0, z1
        self._request_data(True)

    def on_action_x_zoom_all(self):
        """Perform a zoom action to the full extents.
        """
        self._log.info('x_zoom_all')
        self._repaint_request = True
        self.x_range = self._extents()
        self._request_data(True)

    def _on_x_pan(self, pan):
        self._log.info(f'_on_x_pan {pan}')
        if self.pin_left or self.pin_right:
            return  # locked to extents
        e0, e1 = self._extents()
        x0, x1 = self.x_range
        d_x = x1 - x0
        p = int(d_x * 0.25 * pan)
        z0, z1 = x0 + p, x1 + p
        if z0 < e0:
            z0, z1 = e0, e0 + d_x
        elif self.pin_right or z1 > e1:
            z0, z1 = e1 - d_x, e1
        self._repaint_request = True
        self.x_range = z0, z1
        self._request_data(True)

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

        if x_name == 'plot' and (y_name == 'x_axis' or not is_y):
            if is_pan:
                self._on_x_pan(delta)
            else:
                t = self._x_pixel_to_time64(self._mouse_pos[0])
                topic = get_topic_name(self)
                self.pubsub.publish(f'{topic}/actions/!x_zoom', [delta, t])
        elif y_name.startswith('plot.') and (is_y or x_name == 'y_axis'):
            plot_idx = int(y_name.split('.')[1])
            plot = self.state['plots'][plot_idx]
            if is_pan:
                self._on_y_pan(plot, delta)
            else:
                self._on_y_zoom(plot, delta)

    def on_action_plot_show(self, value):
        """Show/hide plots.

        :param value: [quantity, show].  Quantity is the one character
            identifier for the plot.  show is True to show, false to hide.
        """
        self._log.info('plot_show %s', value)
        quantity, show = value
        show = bool(show)
        for plot in self.state['plots']:
            if plot['quantity'] == quantity:
                if show != plot['enabled']:
                    plot['enabled'] = show
                    self._compute_geometry()
                    self._plots_height_adjust()
                    self._request_data(True)
                return
        self._log.warning('plot_show could not match %s', quantity)
