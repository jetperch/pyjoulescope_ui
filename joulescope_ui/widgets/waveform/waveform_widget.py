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

from PySide6 import QtWidgets, QtGui, QtCore, QtOpenGLWidgets, QtOpenGL
from OpenGL import GL as gl
from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name, get_instance, time64
from joulescope_ui.shortcuts import Shortcuts
from joulescope_ui.styles import styled_widget, color_as_qcolor, color_as_string, font_as_qfont
from joulescope_ui.widget_tools import settings_action_create
from joulescope_ui.exporter import TO_JLS_SIGNAL_NAME
from .line_segments import PointsF
from .text_annotation import TextAnnotationDialog, SHAPES_DEF, Y_POSITION_MODE
from .waveform_control import WaveformControlWidget
from .interval_widget import IntervalWidget
from joulescope_ui.time_map import TimeMap
import pyjls
from collections import OrderedDict
import copy
import logging
import numpy as np
import os
import time
from PySide6.QtGui import QPen, QBrush
from joulescope_ui.units import convert_units, UNITS_SETTING, unit_prefix
from . import axis_ticks
from collections.abc import Iterable


_NAME = N_('Waveform')
_ZOOM_FACTOR = np.sqrt(2)
_WHEEL_TO_DEGREES = 1.0 / 8.0  # https://doc.qt.io/qt-6/qwheelevent.html#angleDelta
_WHEEL_TICK_DEGREES = 15.0   # Standard convention
_AUTO_RANGE_FRACT = 0.50  # autorange when current range smaller than existing range by this fractional amount.
_BINARY_RANGE = [-0.1, 1.1]
_MARGIN = 2             # from the outside edges
_Y_INNER_SPACING = 8    # vertical spacing between plots (includes line)
_Y_INNER_LINE = 4
_Y_PLOT_MIN = 16
_MARKER_RSP_OFFSET = (1 << 48)
_MARKER_RSP_STEP = 512
_JS220_AXIS_R = ['10 A', '180 mA', '18 mA', '1.8 mA', '180 µA', '18 µA', 'off', 'off', 'off']
_JS110_AXIS_R = ['10 A', '2 A', '180 mA', '18 mA', '1.8 mA', '180 µA', '18 µA', 'off', 'off']
_LOGARITHMIC_ZERO_DEFAULT = -9
_TEXT_ANNOTATION_X_POS_ALLOC = 64
_ANNOTATION_TEXT_MOD = (1 << 48)
_ANNOTATION_Y_MOD = ((1 << 16) + 2)   # must be multiple of plot colors
_MARKER_SELECT_DISTANCE_PIXELS = 5


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
        'logarithmic_zero': _LOGARITHMIC_ZERO_DEFAULT,
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


def _statistics_format(labels, values, units):
    values_txt = _si_format(values, units)
    r = []
    for label, value_txt in zip(labels, values_txt):
        v = value_txt.split(' ')
        if len(v) == 1:
            r.append((label, v[0], ''))
        else:
            r.append((label, v[0], v[1]))
    return r


def _marker_action_string_to_command(value):
    if isinstance(value, str):
        if value == 'add_single':
            value = [value, None]
        elif value == 'add_dual':
            value = [value, None, None]
        elif value == 'clear_all':
            value = [value]
        else:
            raise ValueError(f'Unsupported marker action {value}')
    return value


def _marker_id_next(markers):
    id_all = sorted([z['id'] for z in markers])
    idx = 1
    while len(id_all):
        k = id_all.pop(0)
        if idx != k:
            break
        idx += 1
    return idx


def _marker_to_rsp_id(marker_id, plot_id):
    """Generate a response id for a marker data request.

    :param marker_id: The marker id.
    :param plot_id: The plot id.
    :return: The response id unique to this combination.
    """
    return _MARKER_RSP_OFFSET + (marker_id * _MARKER_RSP_STEP) + plot_id


def _marker_from_rsp_id(rsp_id):
    """Parse a response id for a marker data request.

    :param rsp_id: The response id generated by _marker_to_rsp_id
    :return: The original (marker_id, plot_id)
    """
    if rsp_id < _MARKER_RSP_OFFSET:
        raise ValueError('invalid')
    rsp_id -= _MARKER_RSP_OFFSET
    marker_id = rsp_id // _MARKER_RSP_STEP
    plot_id = rsp_id % _MARKER_RSP_STEP
    return marker_id, plot_id


def _idx_to_segments(finite_idx):
    length = len(finite_idx)
    change_idx = np.where(np.diff(finite_idx))[0] + 1
    segment_idx = []
    if finite_idx is None or not len(finite_idx):
        return []  # empty
    if finite_idx[0]:  # starts with a valid segment
        if not len(change_idx):  # best case, all data valid, one segment
            segment_idx = [[0, length]]
        else:  # NaNs, but starts with valid segment
            segment_idx.append([0, change_idx[0]])
            change_idx = change_idx[1:]
    while len(change_idx):
        if len(change_idx) == 1:
            segment_idx.append([change_idx[0], length])
            change_idx = change_idx[1:]
        else:
            segment_idx.append([change_idx[0], change_idx[1]])
            change_idx = change_idx[2:]
    return segment_idx


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


class _PlotOpenGLWidget(QtOpenGLWidgets.QOpenGLWidget):
    """The inner plot widget that simply calls back to the Waveform widget."""

    def __init__(self, parent):
        self._log = logging.getLogger(__name__ + '.plot')
        self._parent = parent
        self._antialiasing = QtGui.QPainter.RenderHint.Antialiasing
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def initializeGL(self) -> None:
        self._log.info(f"""OpenGL information:
            Vendor: {gl.glGetString(gl.GL_VENDOR).decode("utf-8")}
            Renderer: {gl.glGetString(gl.GL_RENDERER).decode("utf-8")}
            OpenGL Version: {gl.glGetString(gl.GL_VERSION).decode("utf-8")}
            Shader Version: {gl.glGetString(gl.GL_SHADING_LANGUAGE_VERSION).decode("utf-8")}""")
        functions = QtGui.QOpenGLFunctions(self.context())
        functions.initializeOpenGLFunctions()

    def paintGL(self):
        size = self.width(), self.height()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(self._antialiasing)
        painter.beginNativePainting()
        try:
            self._parent.plot_paint(painter, size)
        finally:
            painter.endNativePainting()
        painter.end()

    def resizeEvent(self, event):
        self._parent.plot_resizeEvent(event)
        return super().resizeEvent(event)

    def mousePressEvent(self, event):
        self._parent.plot_mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._parent.plot_mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self._parent.plot_mouseMoveEvent(event)

    def wheelEvent(self, event):
        self._parent.plot_wheelEvent(event)

    def render_to_image(self) -> QtGui.QImage:
        return self.grabFramebuffer()


class _PlotWidget(QtWidgets.QWidget):
    """The inner plot widget that simply calls back to the Waveform widget."""

    def __init__(self, parent):
        self._log = logging.getLogger(__name__ + '.plot')
        self._parent = parent
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def paintEvent(self, ev):
        size = self.width(), self.height()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._parent.plot_paint(painter, size)
        painter.end()

    def resizeEvent(self, event):
        self._parent.plot_resizeEvent(event)
        return super().resizeEvent(event)

    def mousePressEvent(self, event):
        self._parent.plot_mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._parent.plot_mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self._parent.plot_mouseMoveEvent(event)

    def wheelEvent(self, event):
        self._parent.plot_wheelEvent(event)

    def render_to_image(self) -> QtGui.QImage:
        sz = self.size()
        sz = QtCore.QSize(sz.width() * 2, sz.height() * 2)
        pixmap = QtGui.QPixmap(sz)
        pixmap.setDevicePixelRatio(2)
        self.render(pixmap)
        return pixmap.toImage()


@register
@styled_widget(_NAME)
class WaveformWidget(QtWidgets.QWidget):
    CAPABILITIES = ['widget@', CAPABILITIES.SIGNAL_BUFFER_SINK]

    SETTINGS = {
        'source_filter': {
            'dtype': 'str',
            'brief': N_('The source filter string.'),
            'default': 'JsdrvStreamBuffer:001',
        },
        'on_widget_close_actions': {
            'dtype': 'obj',
            'brief': 'The list of [topic, value] to perform on widget close.',
            'default': [],
            'flags': ['hide', 'ro'],
        },
        'trace_width': {
            'dtype': 'int',
            'brief': N_('The trace width.'),
            'options': [
                [1, '1'],
                [2, '2'],
                [4, '4'],
                [6, '6'],
                [8, '8'],
                [10, '10'],
                [12, '12'],
                [15, '15'],
            ],
            'default': 1,
        },
        'fps': {
            'dtype': 'int',
            'brief': N_('The target frames per second.'),
            'options': [
                [5, N_('vsync'), 2],
                [50, N_('20 Hz')],
                [100, N_('10 Hz')],
                [200, N_('5 Hz')],
            ],
            'default': 50,
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
        'opengl': {
            'dtype': 'bool',
            'brief': N_('Use OpenGL rendering.'),
            'default': True,
        },
        'x_range': {
            'dtype': 'obj',
            'brief': 'The x-axis range.',
            'default': [0, 0],
            'flags': ['hide', 'ro', 'skip_undo'],  # publish only
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
            'flags': ['hide', 'ro'],
        },
        'annotations': {
            'dtype': 'obj',
            'brief': N_('The annotations.'),
            'default': None,
            'flags': ['hide', 'ro', 'skip_undo', 'tmp'],
        },
        'control_location': {
            'dtype': 'str',
            'brief': N_('Control location'),
            'default': 'bottom',
            'options': [
                ['off', N_('off')],
                ['top', N_('top')],
                ['bottom', N_('bottom')],
            ],
        },
        'summary_signal': {
            'dtype': 'obj',
            'brief': N_('The signal to show in the summary.'),
            'default': None,
        },
        'x_axis_annotation_mode': {
            'dtype': 'str',
            'brief': N_('X-axis annotation mode'),
            'default': 'absolute',
            'options': [
                ['absolute', N_('Absolute')],
                ['relative', N_('Relative')],
            ],
        },
        'units': UNITS_SETTING,
    }

    def __init__(self, parent=None, **kwargs):
        """Create a new instance.

        :param parent: The QtWidget parent.
        :param source_filter: The source filter string.
        :param on_widget_close_actions: List of [topic, value] actions to perform on close.
            This feature can be used to close associated sources.
        """
        self._log = logging.getLogger(__name__)
        self._kwargs = kwargs
        self._style_cache = None
        self._summary_data = None
        super().__init__(parent)

        # Cache Qt default instances to prevent memory leak in Pyside6 6.4.2
        self._NO_PEN = QtGui.QPen(QtGui.Qt.NoPen)  # prevent memory leak
        self._NO_BRUSH = QtGui.QBrush(QtGui.Qt.NoBrush)  # prevent memory leak
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_VER = QtGui.QCursor(QtGui.Qt.SizeVerCursor)
        self._CURSOR_SIZE_HOR = QtGui.QCursor(QtGui.Qt.SizeHorCursor)
        self._CURSOR_CROSS = QtGui.QCursor(QtGui.Qt.CrossCursor)

        self._subscribe_list = []
        self._menu = None
        self._dialog = None
        self._shortcuts = Shortcuts(self)
        self._x_map = TimeMap()
        self._x_summary_map = TimeMap()
        self._mouse_pos = None
        self._mouse_pos_start = None
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
        self._sources = {}
        self._signals = {}
        self._signals_by_rsp_id = {}
        self._signals_rsp_id_next = 2  # reserve 1 for summary
        self._signals_data = {}
        self._points = PointsF()
        self._marker_data = {}  # rsp_id -> data,
        self._subsource_order = []

        self._refresh_timer = QtCore.QTimer()
        self._refresh_timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)
        self._repaint_request = False
        self._fps = {
            'start': time.time(),
            'thread_durations': [],
            'time_durations': [],
            'times': [],
            'str': [],
        }

    def _subscribe(self, topic: str, update_fn: callable, flags=None):
        self._subscribe_list.append((topic, update_fn))
        return self.pubsub.subscribe(topic, update_fn, flags)

    def on_setting_opengl(self, value):
        value = bool(value)
        cls = _PlotOpenGLWidget if value else _PlotWidget
        if isinstance(self._graphics, cls):
            return
        index = self._layout.indexOf(self._graphics)
        self._layout.removeWidget(self._graphics)
        self._graphics.close()
        self._graphics.deleteLater()
        self._graphics = cls(self)
        self._layout.insertWidget(index, self._graphics)

    def on_setting_control_location(self, value):
        if value == 'off':
            self._control.setVisible(False)
            return
        self._layout.removeWidget(self._control)
        if value == 'top':
            pos = 0
        else:
            pos = -1
        self._layout.insertWidget(pos, self._control)
        self._control.setVisible(True)

    def _on_source_list(self, sources):
        if not len(sources):
            self._log.warning('No default source available')
            return
        source_filter = self.pubsub.query(f'{self.topic}/settings/source_filter')
        for source in sources:
            if not source.startswith(source_filter):
                continue
            if source in self._sources:
                continue
            self._sources[source] = True
            topic = get_topic_name(source)
            signals = self.pubsub.enumerate(f'{topic}/settings/signals')
            try:
                self.pubsub.query(f'{topic}/events/signals/!add')
                self._subscribe(f'{topic}/events/signals/!add', self._on_signal_add, ['pub'])
                self._subscribe(f'{topic}/events/signals/!remove', self._on_signal_remove, ['pub'])
            except KeyError:
                pass
            for signal in signals:
                self._on_signal_add(f'{topic}/events/signals/!add', signal)
            self.pubsub.publish(f'{topic}/actions/!annotations_request',
                                {'rsp_topic': f'{self.topic}/callbacks/!annotations'})

    def on_callback_annotations(self, value):
        if value is None:
            return
        for a in value:
            if a['annotation_type'] == 'text':
                plot = self._plot_get(a['plot_name'])
                a['plot_index'] = plot['index']
                self._text_annotation_add(a)
            elif a['annotation_type'] == 'y':
                plot = self._plot_get(a['plot_name'])
                if a['dtype'] == 'single':
                    self._y_marker_add_single(plot, a['pos1'])
                elif a['dtype'] == 'dual':
                    self._y_marker_add_dual(plot, a['pos1'], a['pos2'])
                else:
                    self._log.warning('unsupported y dtype %s', a['dtype'])
            elif a['annotation_type'] == 'x':
                if a['dtype'] == 'single':
                    self._x_marker_add_single(a['pos1'])
                elif a['dtype'] == 'dual':
                    self._x_marker_add_dual(a['pos1'], a['pos2'])
                else:
                    self._log.warning('unsupported x dtype %s', a['dtype'])
            else:
                self._log.warning('unsupported annotation_type %s', a['annotation_type'])

    def _on_signal_add(self, topic, value):
        self._log.info(f'_on_signal_add({topic}, {value})')
        source = topic.split('/')[1]
        signal = value
        topic = get_topic_name(source)
        item = (source, signal)
        self._subscribe(f'{topic}/settings/signals/{signal}/range',
                        self._on_signal_range, ['pub', 'retain'])
        source_id, quantity = signal.split('.')
        for plot in self.state['plots']:
            if plot['quantity'] == quantity:
                if item not in plot['signals']:
                    plot['signals'].append(item)
                    self._plot_data_invalidate(plot)
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
            del self._signals[item]
        self._repaint_request = True

    def is_signal_active(self, source_signal):
        if source_signal not in self._signals:
            return False
        for plot in self.state['plots']:
            if not plot['enabled']:
                continue
            elif source_signal in plot['signals']:
                return True
        return False

    def _source_filter_set(self):
        topic = f'{self.topic}/settings/source_filter'
        if 'source_filter' in self._kwargs:
            source_filter = self._kwargs['source_filter']
            self.pubsub.publish(topic, source_filter)
            return source_filter
        else:
            return self.pubsub.query(topic)

    def on_pubsub_register(self):
        source_filter = self._source_filter_set()
        is_device = source_filter in [None, '', 'JsdrvStreamBuffer:001']
        if self.state is None:
            self.state = copy.deepcopy(_STATE_DEFAULT)
            if not is_device:
                self.name = self._kwargs.get('name', _NAME)
        elif is_device:  # clear prior state
            for plot in self.state['plots']:
                plot['signals'] = []
        if self.annotations is None:
            self.annotations = {
                'next_id': 0,
                'x': OrderedDict(),
                'y': [],
                'text': [],
            }
            for _ in self.state['plots']:
                self.annotations['y'].append(OrderedDict())
                e = np.zeros((_TEXT_ANNOTATION_X_POS_ALLOC, 2), dtype=np.int64)
                e[:, 0] = np.iinfo(np.int64).max
                self.annotations['text'].append({
                    'items': {},
                    'x_lookup': e,
                    'x_lookup_length': 0,
                })
        else:  # restore OrderedDict:
            self.annotations['x'] = OrderedDict(self.annotations['x'])
            self.annotations['y'] = [OrderedDict(y) for y in self.annotations['y']]
        if self.summary_signal is not None:
            self.summary_signal = tuple(self.summary_signal)
        if 'on_widget_close_actions' in self._kwargs:
            self.pubsub.publish(f'{self.topic}/settings/on_widget_close_actions',
                                self._kwargs['on_widget_close_actions'])
        for plot_index, plot in enumerate(self.state['plots']):
            plot['index'] = plot_index
            plot['signals'] = [tuple(signal) for signal in plot['signals']]
            plot['y_region'] = f'plot.{plot_index}'
            plot.setdefault('logarithmic_zero', _LOGARITHMIC_ZERO_DEFAULT)
        self._subscribe('registry_manager/capabilities/signal_buffer.source/list',
                        self._on_source_list, ['pub', 'retain'])
        topic = get_topic_name(self)
        self._control.on_pubsub_register(self.pubsub, topic, source_filter)
        self._shortcuts_add()
        self._subscribe('registry/app/settings/units', self._update_on_publish, ['pub'])

    def _update_on_publish(self):
        self._repaint_request = True

    def _shortcuts_add(self):
        topic = get_topic_name(self)
        self._shortcuts.add(QtCore.Qt.Key_Asterisk, f'{topic}/actions/!x_zoom_all')
        # self._shortcuts.add(QtCore.Qt.Key_Delete,  # clear annotations
        # self._shortcuts.add(QtCore.Qt.Key_Backspace, # clear annotations
        self._shortcuts.add(QtCore.Qt.Key_Left, f'{topic}/actions/!x_pan', -1)
        self._shortcuts.add(QtCore.Qt.Key_Right, f'{topic}/actions/!x_pan', 1)
        self._shortcuts.add(QtCore.Qt.Key_Up, f'{topic}/actions/!x_zoom', [1, None])
        self._shortcuts.add(QtCore.Qt.Key_Down, f'{topic}/actions/!x_zoom', [-1, None])
        self._shortcuts.add(QtCore.Qt.Key_Plus, f'{topic}/actions/!x_zoom', [1, None])
        self._shortcuts.add(QtCore.Qt.Key_Minus, f'{topic}/actions/!x_zoom', [-1, None])

    def _cleanup(self):
        for topic, fn in self._subscribe_list:
            self.pubsub.unsubscribe(topic, fn)
        self._subscribe_list.clear()
        self._shortcuts.clear()
        self._refresh_timer.stop()

    def on_pubsub_unregister(self):
        self._control.on_pubsub_unregister()
        self._cleanup()

    def closeEvent(self, event):
        self._cleanup()
        return super().closeEvent(event)

    def on_widget_close(self):
        for topic, value in self.pubsub.query(f'{self.topic}/settings/on_widget_close_actions', default=[]):
            self._log.info('waveform close: %s %s', topic, value)
            self.pubsub.publish(topic, value)

    def _update_fps(self, thread_duration, time_duration):
        t = time.time()
        self._fps['times'].append(t)
        self._fps['thread_durations'].append(thread_duration)
        self._fps['time_durations'].append(time_duration)
        if t - self._fps['start'] >= 1.0:
            x = np.array(self._fps['times'])
            x = np.diff(x)
            d1 = np.array(self._fps['thread_durations'])
            d2 = np.array(self._fps['time_durations'])
            self._fps['start'] = t
            self._fps['times'].clear()
            self._fps['thread_durations'].clear()
            self._fps['time_durations'].clear()
            self._fps['str'].clear()
            if len(x):
                self._fps['str'].append(f'{1 / np.mean(x):.2f} fps')
            for name, v in [('interval', x), ('thread_duration', d1), ('time_duration', d2)]:
                if not len(v):
                    continue
                v *= 1000  # convert from seconds to milliseconds
                v_avg, v_min, v_max = np.mean(v), np.min(v), np.max(v)
                self._fps['str'].append(f'{name} avg={v_avg:.2f}, min={v_min:.2f}, max={v_max:.2f} ms')
        return None

    def _on_signal_range(self, topic, value):
        if value is None:
            return
        value = value['utc']
        topic_parts = topic.split('/')
        source = topic_parts[1]
        signal_id = topic_parts[-2]
        item = (source, signal_id)
        if value == [0, 0]:  # no data
            self._log.info('_on_signal_range(%s, %s) remove', topic, value)
            self._signals.pop(item, None)
            self._repaint_request = True
            return
        d = self._signals.get(item)
        if d is None:
            self._log.info('_on_signal_range(%s, %s) add', topic, value)
            d = {
                'item': item,
                'source': source,
                'signal_id': signal_id,
                'rsp_id': self._signals_rsp_id_next,
                'range': None,
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
            self._graphics.update()

    def _extents(self):
        x_min = []
        x_max = []
        for key, signal in self._signals.items():
            if self.is_signal_active(key):
                x_range = signal['range']
                x_min.append(x_range[0])
                x_max.append(x_range[1])
        if 0 == len(x_min):
            return [0, 0]
        # return min(x_min), max(x_max)   # todo restore when JLS v2 supports out of range requests
        return [max(x_min), min(x_max)]

    def _compute_x_range(self):
        e0, e1 = self._extents()
        if self.x_range is None or self.x_range == [0, 0]:
            return e0, e1
        x0, x1 = self.x_range
        d_e = e1 - e0
        d_x = x1 - x0
        d_z = min(d_e, d_x)
        if (x0 == 0 and x1 == 0) or d_x == 0:
            return [e0, e1]
        elif self.pin_left and self.pin_right:
            return [e0, e1]
        elif self.pin_right:
            return [e1 - d_z, e1]
        elif self.pin_left:
            return [e0, e0 + d_z]
        else:
            x0 = max(x0, e0)
            return [x0, x0 + d_z]

    def _request_data(self, force=False):
        force = bool(force)
        if not len(self._x_geometry_info):
            return
        self.x_range = self._compute_x_range()
        # x0, x1 = self.x_range
        # xc = (x0 >> 1) + (x1 >> 1)
        # self._log.info(f'request x_range({x0}, {x1}) {xc} {time64.as_datetime(xc)}')
        changed = False

        # Get the signal for the summary waveform
        if len(self._signals):
            summary_signal = self.summary_signal
            summary_signal = self._signals.get(summary_signal)
            if summary_signal is None:
                candidates = [k for k in self._signals.keys() if k[1].endswith('.i')]
                if len(candidates):
                    summary_signal = self._signals[candidates[0]]
                else:
                    summary_signal = next(iter(self._signals.values()))
            if summary_signal.get('changed', False):
                summary_length = self._summary_geometry()[2]  # width in pixels
                self._request_signal(summary_signal, self._extents(), rsp_id=1, length=summary_length)

        for key, signal in self._signals.items():
            if not self.is_signal_active(key):
                continue
            if force or signal['changed']:
                signal['changed'] = None
                self._request_signal(signal, self.x_range)
                changed = True
        if self.state is not None:
            for m in self.annotations['x'].values():
                if m.get('mode', 'absolute') == 'relative':
                    if 'rel1' in m:
                        m['pos1'] = self.x_range[1] + m['rel1']
                    if 'rel2' in m:
                        m['pos2'] = self.x_range[1] + m['rel2']
                    m['changed'] = True
                if m.get('changed', True) or changed:
                    m['changed'] = False
                    self._request_marker_data(m)

    def _request_marker_data(self, marker):
        if marker['dtype'] != 'dual':
            return
        marker_id = marker['id']
        for plot in self.state['plots']:
            if not plot['enabled']:
                continue
            signal = plot['signals']
            if not len(signal):
                continue
            signal = {
                'source': signal[0][0],
                'signal_id': signal[0][1],
            }
            rsp_id = _marker_to_rsp_id(marker_id, plot['index'])
            x0, x1 = marker['pos1'], marker['pos2']
            if x0 > x1:
                x0, x1 = x1, x0
            self._request_signal(signal, (x0, x1), rsp_id=rsp_id, length=1)

    def _request_signal(self, signal, x_range, rsp_id=None, length=None):
        topic_req = f'registry/{signal["source"]}/actions/!request'
        topic_rsp = f'{get_topic_name(self)}/callbacks/!response'
        if length is None:
            x_info = self._x_geometry_info.get('plot')
            if x_info is None:
                return
            length = x_info[0]
        req = {
            'signal_id': signal['signal_id'],
            'time_type': 'utc',
            'rsp_topic': topic_rsp,
            'rsp_id': signal['rsp_id'] if rsp_id is None else rsp_id,
            'start': x_range[0],
            'end': x_range[1],
            'length': length,
        }
        self.pubsub.publish(topic_req, req)

    def on_callback_response(self, topic, value):
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
                d[0::2] = np.bitwise_and(y, 0x0f)
                d[1::2] = np.bitwise_and(np.right_shift(y, 4), 0x0f)
                y = d[:len(x)]
            else:
                self._log.warning('Unsupported sample data type: %s', data_type)
                return
            if len(x) != len(y):
                assert(len(x) == len(y))
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
        data['time_range_utc'] = utc
        data['time_range_samples'] = value['info']['time_range_samples']

        if rsp_id >= _MARKER_RSP_OFFSET:
            marker_id, plot_id = _marker_from_rsp_id(rsp_id)
            self._marker_data[(marker_id, plot_id)] = data
        elif rsp_id == 1:
            if self._summary_data is None:
                self._summary_data = {}
            self._summary_data['data'] = data
        else:
            signal = self._signals_by_rsp_id.get(rsp_id)
            # x0, x1 = utc['start'], utc['end']
            # xc = (x0 >> 1) + (x1 >> 1)
            # self._log.info(f'rsp x_range({x0}, {x1}) {xc} {time64.as_datetime(xc)}')
            if signal is None:
                self._log.warning('Unknown signal rsp_id %s', rsp_id)
                return
            if signal['item'] not in self._signals_data:
                self._signals_data[signal['item']] = {}
            self._signals_data[signal['item']]['data'] = data

    def _y_transform_fwd(self, plot, value):
        scale = plot.get('scale', 'linear')
        if scale == 'linear':
            return value
        elif scale == 'logarithmic':
            is_iterable = isinstance(value, Iterable)
            if is_iterable and not isinstance(value, np.ndarray):
                y = np.array(value)
            else:
                y = value
            y_pow_zero = plot['logarithmic_zero']
            y_bias = 10 ** (y_pow_zero - 2)
            y_sign = np.sign(y)
            y_abs = np.abs(y)
            y = np.log10(y_abs + y_bias) - y_pow_zero
            if is_iterable:
                y[y < 0] = 0
            else:
                y = max(0, y)
            y *= y_sign
            return y
        else:
            raise ValueError(f'unsupported y-axis scale: {scale}')

    def _y_transform_rev(self, plot, value):
        scale = plot.get('scale', 'linear')
        if scale == 'linear':
            return value
        elif scale == 'logarithmic':
            is_iterable = isinstance(value, Iterable)
            if is_iterable and not isinstance(value, np.ndarray):
                y = np.array(value)
            else:
                y = value
            y_pow_zero = plot['logarithmic_zero']
            y_sign = np.sign(y)
            y_abs = np.abs(y)
            y = 10 ** (y_abs + y_pow_zero)
            y *= y_sign
            return y
        else:
            raise ValueError(f'unsupported y-axis scale: {scale}')

    def _y_value_to_pixel(self, plot, value, skip_transform=None):
        if not bool(skip_transform):
            value = self._y_transform_fwd(plot, value)
        pixel_offset, value_offset, value_to_pixel_scale = plot['y_map']
        return pixel_offset + (value_offset - value) * value_to_pixel_scale

    def _y_pixel_to_value(self, plot, pixel, skip_transform=None):
        pixel_offset, value_offset, value_to_pixel_scale = plot['y_map']
        value = (pixel_offset - pixel) * (1.0 / value_to_pixel_scale) + value_offset
        if not bool(skip_transform):
            value = self._y_transform_rev(plot, value)
        return value

    def _draw_text(self, p, x, y, txt):
        """Draws text over existing items.

        :param p: The QPainter instance.
        :param x: The x-axis location.
        :param y: The y-axis location.
        :param txt: The text to draw
        """
        margin = _MARGIN
        margin2 = _MARGIN * 2
        metrics = p.fontMetrics()
        r = metrics.boundingRect(txt)
        p.fillRect(x, y, r.width() + margin2, r.height() + margin2, p.brush())
        p.drawText(x + margin, y + margin + metrics.ascent(), txt)

    def _finite_idx(self, data):
        if data is None:
            return None
        if 'finite_idx' not in data:
            nan_idx = np.isnan(data['avg'])
            data['nan_idx'] = nan_idx
            data['finite_idx'] = np.logical_not(nan_idx)
        return data['finite_idx']

    @property
    def _style(self):
        if self._style_cache is not None:
            return self._style_cache
        if self.style_obj is None:
            self._style_cache = None
            return
        v = self.style_obj['vars']

        axis_font = font_as_qfont(v['waveform.axis_font'])
        axis_font_metrics = QtGui.QFontMetrics(axis_font)
        y_tick_size = axis_font_metrics.boundingRect('888.888')

        statistics_name_size = axis_font_metrics.boundingRect('maxx').width()
        statistics_value_size = axis_font_metrics.boundingRect('+888.888x').width()
        statistics_unit_size = axis_font_metrics.boundingRect('mW').width()
        statistics_size = _MARGIN * 2 + statistics_name_size + statistics_value_size + statistics_unit_size

        trace_alpha = int(v['waveform.trace_alpha'], 0)
        min_max_trace_alpha = int(v['waveform.min_max_trace_alpha'], 0)
        min_max_fill_alpha = int(v['waveform.min_max_fill_alpha'], 0)
        std_fill_alpha = int(v['waveform.std_fill_alpha'], 0)
        missing_alpha = int(v['waveform.missing_alpha'], 0)

        summary_trace = color_as_string(v['waveform.summary_trace'], alpha=0xff)
        trace1 = color_as_string(v['waveform.trace1'], alpha=0xff)
        trace2 = color_as_string(v['waveform.trace2'], alpha=0xff)
        trace3 = color_as_string(v['waveform.trace3'], alpha=0xff)
        trace4 = color_as_string(v['waveform.trace4'], alpha=0xff)

        self._style_cache = {
            'background_brush': QtGui.QBrush(color_as_qcolor(v['waveform.background'])),

            'text_pen': QtGui.QPen(color_as_qcolor(v['waveform.text_foreground'])),
            'text_brush': QtGui.QBrush(color_as_qcolor(v['waveform.text_background'])),
            'grid_major_pen': QtGui.QPen(color_as_qcolor(v['waveform.grid_major'])),
            'grid_minor_pen': QtGui.QPen(color_as_qcolor(v['waveform.grid_minor'])),
            'plot_border_pen': QtGui.QPen(color_as_qcolor(v['waveform.plot_border'])),
            'plot_separator_brush': QtGui.QBrush(color_as_qcolor(v['waveform.plot_separator'])),

            'waveform.hover': QBrush(color_as_qcolor(v['waveform.hover'])),

            'summary_missing': QBrush(color_as_qcolor(summary_trace, alpha=missing_alpha)),
            'summary_trace': QPen(color_as_qcolor(summary_trace, alpha=trace_alpha)),
            'summary_min_max_fill': QBrush(color_as_qcolor(summary_trace, alpha=min_max_fill_alpha)),
            'summary_view': QBrush(color_as_qcolor(v['waveform.summary_view'])),

            'plot_trace': [
                QPen(color_as_qcolor(trace1, alpha=trace_alpha)),
                QPen(color_as_qcolor(trace2, alpha=trace_alpha)),
                QPen(color_as_qcolor(trace3, alpha=trace_alpha)),
                QPen(color_as_qcolor(trace4, alpha=trace_alpha)),
            ],
            'plot_min_max_trace': [
                QPen(color_as_qcolor(trace1, alpha=min_max_trace_alpha)),
                QPen(color_as_qcolor(trace2, alpha=min_max_trace_alpha)),
                QPen(color_as_qcolor(trace3, alpha=min_max_trace_alpha)),
                QPen(color_as_qcolor(trace4, alpha=min_max_trace_alpha)),
            ],
            'plot_min_max_fill_pen': [
                QPen(color_as_qcolor(trace1, alpha=min_max_fill_alpha)),
                QPen(color_as_qcolor(trace2, alpha=min_max_fill_alpha)),
                QPen(color_as_qcolor(trace3, alpha=min_max_fill_alpha)),
                QPen(color_as_qcolor(trace4, alpha=min_max_fill_alpha)),
            ],
            'plot_min_max_fill_brush': [
                QBrush(color_as_qcolor(trace1, alpha=min_max_fill_alpha)),
                QBrush(color_as_qcolor(trace2, alpha=min_max_fill_alpha)),
                QBrush(color_as_qcolor(trace3, alpha=min_max_fill_alpha)),
                QBrush(color_as_qcolor(trace4, alpha=min_max_fill_alpha)),
            ],
            'plot_std_fill': [
                QBrush(color_as_qcolor(trace1, alpha=std_fill_alpha)),
                QBrush(color_as_qcolor(trace2, alpha=std_fill_alpha)),
                QBrush(color_as_qcolor(trace3, alpha=std_fill_alpha)),
                QBrush(color_as_qcolor(trace4, alpha=std_fill_alpha)),
            ],
            'plot_missing': [
                QBrush(color_as_qcolor(trace1, alpha=missing_alpha)),
                QBrush(color_as_qcolor(trace2, alpha=missing_alpha)),
                QBrush(color_as_qcolor(trace3, alpha=missing_alpha)),
                QBrush(color_as_qcolor(trace4, alpha=missing_alpha)),
            ],

            'axis_font': axis_font,
            'axis_font_metrics': QtGui.QFontMetrics(axis_font),
            'plot_label_size': axis_font_metrics.boundingRect('WW'),
            'y_tick_size': y_tick_size,
            'y_tick_height_pixels_min': 1.5 * y_tick_size.height(),
            'utc_width_pixels': axis_font_metrics.boundingRect('8888-88-88W88:88:88.888888').width(),
            'x_tick_width_pixels_min': axis_font_metrics.boundingRect('888.888888').width(),

            'statistics_name_size': statistics_name_size,
            'statistics_value_size': statistics_value_size,
            'statistics_unit_size': statistics_unit_size,
            'statistics_size': statistics_size,
        }

        for k in range(1, 7):
            c = v[f'waveform.marker{k}']
            self._style_cache[f'marker{k}_pen'] = QPen(color_as_qcolor(c))
            self._style_cache[f'marker{k}_fg'] = QBrush(color_as_qcolor(c))
            self._style_cache[f'marker{k}_bg'] = QBrush(color_as_qcolor(c[:-2] + '20'))

        for k in range(11):
            color_name = f'waveform.annotation_shape{k}'
            c = v[color_name]
            self._style_cache[color_name] = QBrush(color_as_qcolor(c))
        self._style_cache['waveform.annotation_text'] = QPen(color_as_qcolor(v['waveform.annotation_text']))
        annotation_font = font_as_qfont(v['waveform.annotation_font'])
        self._style_cache['waveform.annotation_font'] = annotation_font
        self._style_cache['waveform.annotation_font_metrics'] = QtGui.QFontMetrics(annotation_font)
        self.on_setting_trace_width(self.trace_width)
        return self._style_cache

    def on_setting_trace_width(self, value):
        if self._style_cache is not None:
            for trace in self._style_cache['plot_trace']:
                trace.setWidth(value)
            self._repaint_request = True

    def _subsource_order_update(self):
        sources = set()
        for (source_id, signal_id), signal in self._signals.items():
            subsource = signal_id.split('.')[0]
            sources.add(f'{source_id}/{subsource}')
        self._subsource_order = list(sources)

    def _plot_range_auto_update(self, plot):
        if plot['range_mode'] != 'auto':
            return
        y_min = []
        y_max = []
        for signal in plot['signals']:
            d = self._signals.get(signal)
            if d is None:
                continue
            sig_d = self._signals_data.get(signal)
            if sig_d is None:
                continue
            d = sig_d['data']
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
        y_min, y_max = self._y_transform_fwd(plot, [y_min, y_max])
        dy1 = max(1e-9, y_max - y_min)
        dy2 = abs(r[1] - r[0])

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
            self._log.info('_plots_height_adjust too short: %s < %s', h, h_min)
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
            right_width = margin + s['statistics_size']
        else:
            right_width = 0
        plot_width = widget_w - left_width - right_width - 2 * margin
        y_inner_spacing = _Y_INNER_SPACING

        y_geometry = [
            [margin, 'margin.top'],
            [50, 'summary'],
            [y_inner_spacing, 'spacer.ignore.summary'],
            [s['plot_label_size'].height() * 3, 'x_axis'],
            [y_inner_spacing, 'spacer.ignore.x_axis'],
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
        t_thread_start = time.thread_time_ns()
        t_time_start = time.time_ns()
        self._repaint_request = False

        resize = not len(self._y_geometry_info)
        self._compute_geometry(size)
        if resize:
            self._plots_height_adjust()
        self._draw_background(p, size)
        self._draw_summary(p)
        if not self._draw_x_axis(p):
            return  # plot is not valid
        self._annotations_remove_expired()
        self._draw_markers_background(p)

        # Draw each plot
        self._subsource_order_update()
        for plot in self.state['plots']:
            if plot['enabled']:
                self._draw_plot(p, plot)
                self._draw_plot_statistics(p, plot)
                self._draw_text_annotations(p, plot)
        self._draw_spacers(p)
        self._draw_markers(p, size)

        self._draw_hover(p)
        self._set_cursor()

        thread_duration = (time.thread_time_ns() - t_thread_start) / 1e9
        time_duration = (time.time_ns() - t_time_start) / 1e9
        self._update_fps(thread_duration, time_duration)
        self._draw_fps(p)

    def _draw_background(self, p, size):
        s = self._style
        widget_w, widget_h = size
        p.fillRect(0, 0, widget_w, widget_h, s['background_brush'])

    def _summary_geometry(self):
        _, _, x0 = self._x_geometry_info['margin.left']
        _, x1, _ = self._x_geometry_info['margin.right']
        yh, y0, _, = self._y_geometry_info['summary']
        return (x0, y0, x1 - x0, yh)

    def _draw_summary(self, p):
        s = self._style
        d_sig = self._summary_data
        if d_sig is None:
            return
        d = d_sig['data']
        length = len(d['x'])
        x0, y0, w, h = self._summary_geometry()
        x = d['x']
        xe0, xe1 = x[0], x[-1]
        dxe = xe1 - xe0
        if length <= 1 or w <= 1 or dxe <= 1e-15:
            return
        x_gain = w / dxe
        self._x_summary_map.update(x0, xe0, x_gain)

        xp = self._x_summary_map.time64_to_counter(x)
        p.setClipRect(x0, y0, w, h)
        finite_idx = np.logical_not(np.isnan(d['avg']))
        segment_idx = _idx_to_segments(finite_idx)

        p.setPen(self._NO_PEN)
        if len(segment_idx) > 1:
            segment_idx_last = segment_idx[0][1]
            for idx_start, idx_stop in segment_idx[1:]:
                z1 = xp[segment_idx_last]
                z2 = xp[idx_start]
                p.fillRect(z1, y0, max(1, z2 - z1), h, s['summary_missing'])
                segment_idx_last = idx_stop

        xp_range = np.rint(self._x_summary_map.time64_to_counter(np.array(self.x_range)))
        pr0, pr1 = int(xp_range[0]), int(xp_range[-1])
        pr0, pr1 = max(0, min(pr0, w)), max(0, min(pr1, w))
        p.fillRect(x0 + pr0, y0, max(1, pr1 - pr0), h, s['summary_view'])

        d_y_avg = d['avg'][finite_idx]
        if not len(d_y_avg):
            return
        if d['min'] is not None:
            y_min = np.min(d['min'][finite_idx])
        else:
            y_min = np.min(d_y_avg)
        if d['max'] is not None:
            y_max = np.max(d['max'][finite_idx])
        else:
            y_max = np.max(d_y_avg)
        if y_min >= y_max:
            return
        overscan = 0.05
        y_p2p = y_max - y_min
        y_ovr = (1 + 2 * overscan) * y_p2p
        y_top = y_max + y_p2p * overscan
        y_gain = h / y_ovr

        def y_value_to_pixel(y):
            return (y_top - y) * y_gain

        for idx_start, idx_stop in segment_idx:
            d_x_segment = xp[idx_start:idx_stop]
            d_avg = d['avg'][idx_start:idx_stop]
            if self.show_min_max and d['min'] is not None and d['max'] is not None:
                d_y_min = y_value_to_pixel(d['min'][idx_start:idx_stop])
                d_y_max = y_value_to_pixel(d['max'][idx_start:idx_stop])
                segs = self._points.set_fill(d_x_segment, d_y_min, d_y_max)
                p.setPen(self._NO_PEN)
                p.setBrush(s['summary_min_max_fill'])
                p.drawPolygon(segs)
            d_y = y_value_to_pixel(d_avg)
            segs = self._points.set_line(d_x_segment, d_y)
            p.setPen(s['summary_trace'])
            p.drawPolyline(segs)

        p.setClipping(False)

    def _draw_x_axis(self, p):
        s = self._style
        p.setPen(s['text_pen'])
        p.setBrush(s['text_brush'])
        p.setFont(s['axis_font'])
        font_metrics = s['axis_font_metrics']

        # compute time and draw x-axis including UTC, seconds, grid
        x_axis_height, x_axis_y0, x_axis_y1 = self._y_geometry_info['x_axis']
        left_width, left_x0, left_x1, = self._x_geometry_info['y_axis']
        plot_width, plot_x0, plot_x1, = self._x_geometry_info['plot']
        _, y_end, _, = self._y_geometry_info['margin.bottom']

        y = x_axis_y0 + 2 * s['plot_label_size'].height()
        major_count_max = plot_width / s['x_tick_width_pixels_min']
        x_range64 = self.x_range
        x_duration_s = (x_range64[1] - x_range64[0]) / time64.SECOND
        if (plot_width > 1) and (x_duration_s > 0):
            x_gain = (plot_width - 1) / (x_duration_s * time64.SECOND)
        else:
            return False
        x_grid = axis_ticks.x_ticks(x_range64[0], x_range64[1], major_count_max)
        self._x_map.update(left_x1, x_range64[0], x_gain)
        self._x_map.trel_offset = x_grid['offset']

        y_text = y + font_metrics.ascent()

        if self.show_statistics:
            x_stats = self._x_geometry_info['statistics'][1]
            dt_str = _si_format(x_duration_s, 's')
            p.drawText(x_stats + _MARGIN, y_text, f'Δt={dt_str[1:]}')

        if x_grid is None:
            pass
        else:
            p.drawText(left_x0, x_axis_y0 + s['plot_label_size'].height() + font_metrics.ascent(), x_grid['offset_str'])
            p.drawText(left_x0, y_text, x_grid['units'])
            for idx, x in enumerate(self._x_map.trel_to_counter(x_grid['major'])):
                p.setPen(s['text_pen'])
                x_str = x_grid['labels'][idx]
                x_start = x + _MARGIN
                x_end = x_start + font_metrics.boundingRect(x_str).width() + _MARGIN
                if x_end <= plot_x1:
                    p.drawText(x_start, y_text, x_str)
                p.setPen(s['grid_major_pen'])
                p.drawLine(x, y, x, y_end)

            p.setPen(s['grid_minor_pen'])
            for x in self._x_map.trel_to_counter(x_grid['minor']):
                p.drawLine(x, x_axis_y1, x, y_end)
        return True

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
        y_range = plot['range']  # in transformed coordinates
        if y_range[0] >= y_range[1]:
            y_scale = 1.0
        else:
            y_scale = h / (y_range[1] - y_range[0])
        plot['y_map'] = (y0, y_range[1], y_scale)

        # draw y-axis grid
        if plot['scale'] == 'logarithmic':
            major_interval_min = 1
            logarithmic_zero = plot['logarithmic_zero']
        else:
            major_interval_min = None
            logarithmic_zero = None
        p.setFont(s['axis_font'])
        y_tick_height_value_min = s['y_tick_height_pixels_min'] / plot['y_map'][-1]
        y_grid = axis_ticks.ticks(y_range[0], y_range[1], y_tick_height_value_min,
                        major_interval_min=major_interval_min,
                        logarithmic_zero=logarithmic_zero)
        axis_font_metrics = s['axis_font_metrics']
        if y_grid is not None:
            if plot['quantity'] == 'r':
                y_grid = axis_ticks.ticks(y_range[0], y_range[1], y_tick_height_value_min, 1)
                if len(plot['signals']):
                    if 'JS220' in plot['signals'][0][1]:
                        y_grid['labels'] = [_JS220_AXIS_R[int(s_label)] for s_label in y_grid['labels']]
                    elif 'JS110' in plot['signals'][0][1]:
                        y_grid['labels'] = [_JS110_AXIS_R[int(s_label)] for s_label in y_grid['labels']]
            for idx, t in enumerate(self._y_value_to_pixel(plot, y_grid['major'], skip_transform=True)):
                p.setPen(s['text_pen'])
                s_label = y_grid['labels'][idx]
                font_m = axis_font_metrics.boundingRect(s_label)
                f_ah = axis_font_metrics.ascent() // 2
                f_y = t + f_ah
                f_y_up = f_ah
                f_y_down = f_ah + axis_font_metrics.descent()
                if f_y - f_y_up > y0 and f_y + f_y_down < y1:
                    p.drawText(x0 - 4 - font_m.width(), f_y, s_label)
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
        elif y_grid is None:
            s_label = plot_units
        else:
            s_label = f"{y_grid['unit_prefix']}{plot_units}"
        p.drawText(left, y0 + (h + axis_font_metrics.ascent()) // 2, s_label)

        p.setClipRect(x0, y0, w, h)

        for signal in plot['signals']:
            d = self._signals.get(signal)
            if d is None:
                continue
            sig_d = self._signals_data.get(signal)
            if sig_d is None:
                continue
            subsource = f'{signal[0]}/{signal[1].split(".")[0]}'
            trace_idx = self._subsource_order.index(subsource)
            d = sig_d['data']
            d_x = self._x_map.time64_to_counter(d['x'])
            if len(d_x) == w:
                d_x, d_x2 = np.rint(d_x), d_x
                if np.any(np.abs(d_x - d_x2) > 0.5):
                    self._log.warning('x does not conform to pixels')
                    d_x = d_x2

            finite_idx = self._finite_idx(d)
            segment_idx = _idx_to_segments(finite_idx)

            p.setPen(self._NO_PEN)
            p.setBrush(s['plot_missing'][trace_idx])
            if len(segment_idx) > 1:
                segment_idx_last = segment_idx[0][1]
                for idx_start, idx_stop in segment_idx[1:]:
                    xa = d_x[segment_idx_last]
                    xb = d_x[idx_start]
                    p.drawRect(xa, y0, max(1, xb - xa), h)
                    segment_idx_last = idx_stop

            for idx_start, idx_stop in segment_idx:
                d_x_segment = d_x[idx_start:idx_stop]
                d_avg = d['avg'][idx_start:idx_stop]
                if self.show_min_max and d['min'] is not None and d['max'] is not None:
                    d_y_min = self._y_value_to_pixel(plot, d['min'][idx_start:idx_stop])
                    d_y_max = self._y_value_to_pixel(plot, d['max'][idx_start:idx_stop])
                    if 1 == self.show_min_max:
                        p.setPen(s['plot_min_max_trace'][trace_idx])
                        segs = self._points.set_line(d_x_segment, d_y_min)
                        p.drawPolyline(segs)
                        segs = self._points.set_line(d_x_segment, d_y_max)
                        p.drawPolyline(segs)
                    else:
                        segs = self._points.set_fill(d_x_segment, d_y_min, d_y_max)
                        p.setPen(s['plot_min_max_fill_pen'][trace_idx])
                        p.setBrush(s['plot_min_max_fill_brush'][trace_idx])
                        p.drawPolygon(segs)
                        if 3 == self.show_min_max:
                            d_std = d['std'][idx_start:idx_stop]
                            d_y_std_min = self._y_value_to_pixel(plot, d_avg - d_std)
                            d_y_std_max = self._y_value_to_pixel(plot, d_avg + d_std)
                            d_y_std_min = np.amin(np.vstack([d_y_std_min, d_y_min]), axis=0)
                            d_y_std_max = np.amax(np.vstack([d_y_std_max, d_y_max]), axis=0)
                            segs = self._points.set_fill(d_x_segment, d_y_std_min, d_y_std_max)
                            p.setPen(self._NO_PEN)
                            p.setBrush(s['plot_std_fill'][trace_idx])
                            p.drawPolygon(segs)

                d_y = self._y_value_to_pixel(plot, d_avg)
                segs = self._points.set_line(d_x_segment, d_y)
                p.setPen(s['plot_trace'][trace_idx])
                p.drawPolyline(segs)

        p.setBrush(s['text_brush'])
        f_a = s['axis_font_metrics'].ascent()
        for m in self.annotations['y'][plot['index']].values():
            color_index = self._marker_color_index(m)
            pen = s[f'marker{color_index}_pen']
            fg = s[f'marker{color_index}_fg']
            bg = s[f'marker{color_index}_bg']
            p1 = np.rint(self._y_value_to_pixel(plot, m['pos1']))
            p.setPen(pen)
            p.drawLine(x0, p1, x1, p1)
            p.setPen(s['text_pen'])
            t = _si_format(m['pos1'], plot['units'])

            if m['dtype'] == 'dual':
                dy = _si_format(m['pos2'] - m['pos1'], plot['units'])
                self._draw_text(p, x0 + _MARGIN, p1 + _MARGIN, t + '  Δ=' + dy)
                p.setPen(pen)
                p2 = np.rint(self._y_value_to_pixel(plot, m['pos2']))
                p.drawLine(x0, p2, x1, p2)
                p.setPen(s['text_pen'])
                t = _si_format(m['pos2'], plot['units'])
                self._draw_text(p, x0 + _MARGIN, p2 + _MARGIN, t + '  Δ=' + dy)
            else:
                self._draw_text(p, x0 + _MARGIN, p1 + _MARGIN, t)

        p.setClipping(False)

    def _marker_color_index(self, m):
        return (m['id'] % 6) + 1

    def _draw_markers_background(self, p):
        s = self._style
        h, y0, _ = self._y_geometry_info['x_axis']
        _, y1, _ = self._y_geometry_info['margin.bottom']
        xw, x0, x1 = self._x_geometry_info['plot']
        font_metrics = s['axis_font_metrics']
        ya = y0 + _MARGIN + font_metrics.ascent()

        p.setClipRect(x0, y0, xw, y1 - y0)
        for m in self.annotations['x'].values():
            if m['dtype'] != 'dual':
                continue
            x1, x2 = m['pos1'], m['pos2']
            if x2 < x1:
                x1, x2 = x2, x1
            p1 = np.rint(self._x_map.time64_to_counter(x1))
            p2 = np.rint(self._x_map.time64_to_counter(x2))
            color_index = self._marker_color_index(m)
            bg = s[f'marker{color_index}_bg']
            p.setPen(self._NO_PEN)
            p.setBrush(bg)
            pd = p2 - p1
            p.drawRect(p1, ya, pd, y1 - ya)
        p.setClipping(False)

    def _x_markers_filter(self, x_range):
        inside = []
        outside = []
        x_min, x_max = x_range
        for m_id, m in self.annotations['x'].items():
            pos1 = m['pos1']
            if not x_min <= pos1 <= x_max:
                outside.append(m_id)
                continue
            if m['dtype'] == 'dual':
                pos2 = m['pos2']
                if not x_min <= pos2 <= x_max:
                    outside.append(m_id)
                    continue
                if x_min == pos1 and x_max == pos2:
                    outside.append(m_id)
                    continue
            inside.append(m_id)
        return inside, outside

    def _text_annotations_filter(self, x_range, plot_index):
        inside = []
        outside = []
        x_min, x_max = x_range
        for a_id, a in self.annotations['text'][plot_index]['items'].items():
            if x_min <= a['x'] <= x_max:
                inside.append(a_id)
            else:
                outside.append(a_id)
        return inside, outside

    def _annotations_remove_expired(self):
        x_range = self._extents()
        _, outside = self._x_markers_filter(x_range)
        for m_id in outside:
            if self.annotations['x'][m_id].get('mode', 'absolute') == 'absolute':
                del self.annotations['x'][m_id]
        for plot_index, entry in enumerate(self.annotations['text']):
            _, outside = self._text_annotations_filter(x_range, plot_index)
            for a_id in outside:
                self._text_annotation_remove(a_id)

    def _draw_markers(self, p, size):
        s = self._style
        h, y0, _ = self._y_geometry_info['x_axis']
        _, y1, _ = self._y_geometry_info['margin.bottom']
        xw, x0, x1 = self._x_geometry_info['plot']
        font_metrics = s['axis_font_metrics']
        h = font_metrics.height()
        f_a = font_metrics.ascent()
        margin, margin2 = _MARGIN, _MARGIN * 2
        ya = y0 + margin + f_a
        x_min = self._extents()[0]

        for idx, m in enumerate(self.annotations['x'].values()):
            color_index = self._marker_color_index(m)
            pos1 = m['pos1']
            w = h // 2
            he = h // 3
            pen = s[f'marker{color_index}_pen']
            fg = s[f'marker{color_index}_fg']
            bg = s[f'marker{color_index}_bg']
            p.setPen(self._NO_PEN)
            p.setBrush(fg)
            p1 = np.rint(self._x_map.time64_to_counter(pos1))
            yl = y0 + h + he
            if m.get('flag') is None:
                m['flag'] = PointsF()
            if m['dtype'] == 'single':
                pl = p1 - w
                pr = p1 + w
                segs = self._points.set_line([pl, pl, p1, pr, pr], [y0, y0 + h, yl, y0 + h, y0])
                p.setClipRect(x0, y0, xw, y1 - y0)
                p.drawPolygon(segs)
                p.setPen(pen)
                p.drawLine(p1, y0 + h + he, p1, y1)
                self._draw_single_marker_text(p, m, pos1)
            else:
                p2 = np.rint(self._x_map.time64_to_counter(m['pos2']))
                if p2 < p1:
                    p1, p2 = p2, p1

                p.setClipRect(x0, y0, xw, y1 - y0)
                p.setPen(pen)
                p.drawLine(p1, ya, p1, y1)
                p.drawLine(p2, ya, p2, y1)
                dt = abs((m['pos1'] - m['pos2']) / time64.SECOND)
                dt_str = _si_format(dt, 's')[1:]
                dt_str_r = font_metrics.boundingRect(dt_str)
                dt_x = (p1 + p2 - dt_str_r.width()) // 2
                q1, q2 = dt_x - margin, dt_x + dt_str_r.width() + margin
                q1, q2 = min(p1, q1), max(p2, q2)
                p.setPen(s['text_pen'])
                p.fillRect(q1, y0, q2 - q1, f_a + margin2, p.brush())
                p.drawText(dt_x, y0 + margin + f_a, dt_str)
                self._draw_dual_marker_text(p, m, 'text_pos1')
                self._draw_dual_marker_text(p, m, 'text_pos2')
        p.setClipping(False)

    def _draw_statistics_text(self, p: QtGui.QPainter, pos, values, text_pos=None):
        """Draw statistics text.

        :param p: The QPainter.
        :param pos: The (x, y) position for the text corner in pixels.
        :param values: The iterable of (name, value, units).
        :param text_pos: The text position which is one of [right, left, off].
            None (default) is equivalent to right.
        """
        s = self._style
        if text_pos is None:
            text_pos = 'right'
        elif text_pos == 'off':
            return
        font_metrics = s['axis_font_metrics']
        field_width = s['statistics_name_size']
        value_width = s['statistics_value_size']
        unit_width = s['statistics_unit_size']
        f_a = font_metrics.ascent()
        f_h = font_metrics.height()
        p.setFont(s['axis_font'])
        p.setPen(s['text_pen'])
        x0, y0 = pos

        r_w = 2 * _MARGIN + field_width + value_width + unit_width
        r_h = 2 * _MARGIN + f_h * len(values)
        if text_pos == 'left':
            x1 = x0 - _MARGIN - r_w
        else:
            x1 = x0 + _MARGIN
        y1 = y0
        p.fillRect(x1, y1, r_w, r_h, s['text_brush'])
        x1 += _MARGIN
        y1 += _MARGIN + f_a
        for label, value, units in values:
            p.drawText(x1, y1, label)
            p.drawText(x1 + field_width, y1, value)
            p.drawText(x1 + field_width + value_width, y1, units)
            y1 += f_h

    def _draw_single_marker_text(self, p, m, x):
        text_pos = m.get('text_pos1', 'right')
        if text_pos == 'off':
            return
        p0 = np.rint(self._x_map.time64_to_counter(x))
        xp = self._x_map.counter_to_time64(p0)
        xw, x0, _ = self._x_geometry_info['plot']
        for plot in self.state['plots']:
            if not plot['enabled'] or not len(plot['signals']):
                continue
            signal_index = plot['signals'][0]
            d_sig = self._signals_data.get(signal_index)
            if d_sig is None:
                continue
            d = d_sig['data']
            s_x = d['x']
            idx = np.argmin(np.abs(s_x - xp))
            v_avg = d['avg'][idx]
            if not np.isfinite(v_avg):
                continue
            yh, y0, y1 = self._y_geometry_info[plot['y_region']]
            p.setClipRect(x0, y0, xw, yh)

            if d['std'] is None:
                labels = ['avg']
                values = [v_avg]
            else:
                v_std, v_min, v_max = d['std'][idx], d['min'][idx], d['max'][idx]
                v_rms = np.sqrt(v_avg * v_avg + v_std * v_std)
                labels = ['avg', 'std', 'rms', 'min', 'max', 'p2p']
                values = [v_avg, v_std, v_rms, v_min, v_max, v_max - v_min]
            values = _statistics_format(labels, values, plot['units'])
            self._draw_statistics_text(p, (p0, y0), values, text_pos)
        p.setClipping(False)

    def _draw_dual_marker_text(self, p, m, text_pos_key):
        text_pos_default = 'off' if text_pos_key == 'text_pos1' else 'right'
        text_pos = m.get(text_pos_key, text_pos_default)
        if text_pos == 'off':
            return
        marker_id = m['id']
        xw, x0, _ = self._x_geometry_info['plot']
        for plot in self.state['plots']:
            if not plot['enabled'] or not len(plot['signals']):
                continue
            plot_id = plot['index']
            key = (marker_id, plot_id)
            if key not in self._marker_data:
                return
            yh, y0, y1 = self._y_geometry_info[plot['y_region']]
            p.setClipRect(x0, y0, xw, yh)
            data = self._marker_data[key]
            utc = data['time_range_utc']
            dt = (utc['end'] - utc['start']) / time64.SECOND
            v_avg = float(data['avg'][0])
            if not np.isfinite(v_avg):
                continue
            v_std = float(data['std'][0])
            v_min = float(data['min'][0])
            v_max = float(data['max'][0])
            labels = ['avg', 'std', 'rms', 'min', 'max', 'p2p']
            v_rms = np.sqrt(v_avg * v_avg + v_std * v_std)
            values = [v_avg, v_std, v_rms, v_min, v_max, v_max - v_min]
            values = _statistics_format(labels, values, plot['units'])

            integral_units = plot.get('integral')
            if integral_units is not None:
                integral_v, integral_units = convert_units(v_avg * dt, integral_units, self.units)
                integral_values = _statistics_format(['∫'], [integral_v], integral_units)
                values.extend(integral_values)

            pos_field = text_pos_key.split('_')[-1]
            p0 = np.rint(self._x_map.time64_to_counter(m[pos_field]))
            self._draw_statistics_text(p, (p0, y0), values, text_pos)
        p.setClipping(False)

    def _draw_fps(self, p):
        s = self._style
        if self.show_fps:
            p.setFont(s['axis_font'])
            p.setPen(s['text_pen'])
            y = s['axis_font_metrics'].ascent()
            y_incr = s['axis_font_metrics'].height()
            for s in self._fps['str']:
                p.drawText(10, y, s)
                y += y_incr

    def _signal_data_get(self, plot):
        try:
            if isinstance(plot, str):
                plot_idx = int(plot.split('.')[1])
                plot = self.state['plots'][plot_idx]
            signals = plot['signals']
            # signal = self._signals[signals[0]]
            data = self._signals_data.get(signals[0])
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
        data = data['data']
        if not len(data['avg']):
            return
        x_pixels = self._mouse_pos[0]
        x = self._x_map.counter_to_time64(x_pixels)
        x_rel = self._x_map.time64_to_trel(x)
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
        p.setClipping(False)

    def _draw_plot_statistics(self, p, plot):
        if not self.show_statistics:
            return
        plot, sig_data = self._signal_data_get(plot)
        if sig_data is None:
            return
        data = sig_data['data']
        xd, x0, x1 = self._x_geometry_info['statistics']
        yd, y0, y1 = self._y_geometry_info[plot['y_region']]
        z0, z1 = self.x_range

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
        values = _statistics_format(q_names, q_value, plot['units'])

        dt = (z1 - z0) / time64.SECOND
        integral_units = plot.get('integral')
        if integral_units is not None:
            integral_v, integral_units = convert_units(y_avg * dt, integral_units, self.units)
            integral_values = _statistics_format(['∫'], [integral_v], integral_units)
            values.extend(integral_values)
        p.setClipRect(x0, y0, xd, yd)
        self._draw_statistics_text(p, (x0, y0), values)
        p.setClipping(False)

    def _annotation_next_id(self, annotation_type: str, plot_index=None):
        next_idx = 0
        prefix = annotation_type[0]
        if prefix == 'x':
            for idx in sorted(list(self.annotations['x'].keys())):
                if idx != next_idx:
                    break
                next_idx += 1
        elif prefix == 'y':
            for idx in sorted(list(self.annotations['y'][plot_index].keys())):
                idx_mod = idx % _ANNOTATION_Y_MOD
                if idx_mod != next_idx:
                    break
                next_idx += 1
            next_idx += _ANNOTATION_Y_MOD * (plot_index + 1)
        elif prefix == 't':
            next_idx = self.annotations['next_id']
            self.annotations['next_id'] = next_idx + 1
            next_idx += _ANNOTATION_TEXT_MOD * (plot_index + 1)
        else:
            raise ValueError('could not assign annotation id')
        self._log.info('_annotation_next_id(%s, %s) => %s',
                       annotation_type, plot_index, next_idx)
        return next_idx

    def _annotation_lookup(self, a_id):
        if isinstance(a_id, dict):
            return a_id  # presume that it is a valid text annotation
        elif isinstance(a_id, int):
            if a_id < _ANNOTATION_Y_MOD:
                return self.annotations['x'][a_id]
            elif a_id < _ANNOTATION_TEXT_MOD:
                plot_index = (a_id // _ANNOTATION_Y_MOD) - 1
                return self.annotations['y'][plot_index][a_id]
            else:
                plot_index = (a_id // _ANNOTATION_TEXT_MOD) - 1
                return self.annotations['text'][plot_index]['items'][a_id]
        raise RuntimeError(f'annotation {a_id} not found')

    def _text_annotation_nearest(self, plot, x, y, d_max):
        plot_entry = self.annotations['text'][plot['index']]
        items = plot_entry['items']
        x_lookup_length = plot_entry['x_lookup_length']
        x_lookup = plot_entry['x_lookup'][:x_lookup_length, :]
        x_v = self._x_map.time64_to_counter(x_lookup[:, 0])
        x_lookup_idx = np.abs(x_v - x) < d_max  # possible entries
        x_lookup = x_lookup[x_lookup_idx, :]
        x_v = x_v[x_lookup_idx]
        if not len(x_v):
            return None
        y_range = plot['range']
        y_center = (y_range[1] + y_range[0]) / 2
        y_v = np.array([(y_center if items[a_id]['y_mode'] == 'centered' else items[a_id]['y'])
                        for a_id in x_lookup[:, 1]], dtype=float)
        y_v = self._y_value_to_pixel(plot, y_v)
        d = (x_v - x) ** 2 + (y_v - y) ** 2
        idx = np.argmin(d)
        if d[idx] < (d_max ** 2):
            return items[x_lookup[idx, 1]]
        return None

    def _draw_text_annotations(self, p, plot):
        plot_entry = self.annotations['text'][plot['index']]
        items = plot_entry['items']
        x_lookup_length = plot_entry['x_lookup_length']
        x_lookup = plot_entry['x_lookup'][:x_lookup_length, :]
        if not len(x_lookup):
            return
        x0, x1 = self.x_range
        t = x_lookup[:, 0]
        view = x_lookup.compress(np.logical_and(t >= x0, t <= x1), axis=0)
        view[:, 0] = self._x_map.time64_to_counter(view[:, 0])
        if not len(view):
            return
        x_range = self._x_map.time64_to_counter([x0, x1])
        y_range = self._y_value_to_pixel(plot, np.array(plot['range'], dtype=float))
        y_center = int((y_range[0] + y_range[1]) / 2)
        p.setClipRect(x_range[0], y_range[0], x_range[1] - x_range[0], y_range[1] - y_range[0])

        s = self._style
        text_color = s['waveform.annotation_text']
        font = s['waveform.annotation_font']
        font_metrics = s['waveform.annotation_font_metrics']
        font_h = font_metrics.height()
        p.setFont(font)

        for x, a_id in view:
            a = items[a_id]
            if a['y_mode'] == 'manual':
                y = self._y_value_to_pixel(plot, a['y'])
            else:
                y = y_center
            shape = a['shape'] % 11
            p.setPen(self._NO_PEN)
            p.setBrush(s[f'waveform.annotation_shape{shape}'])
            path = SHAPES_DEF[shape][-1]
            p.translate(x, y)
            p.scale(10, 10)
            p.drawPath(path)
            p.resetTransform()
            text = a['text']
            if a['text_show'] and text:
                p.setPen(text_color)
                p.setBrush(s['text_brush'])
                self._draw_text(p, x, y + font_h, text)
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

    def _find_x_marker(self, x):
        marker_info = []  # x, marker, pos
        for m in reversed(self.annotations['x'].values()):
            marker_info.append([m['pos1'], m, 'pos1'])
            if m['dtype'] == 'dual':
                marker_info.append([m['pos2'], m, 'pos2'])
        mx = np.array([e[0] for e in marker_info], dtype=np.int64)
        mx = self._x_map.time64_to_counter(mx)
        dx = np.abs(x - mx)
        z = np.where(dx < _MARKER_SELECT_DISTANCE_PIXELS)[0]
        if len(z):
            _, marker, pos = marker_info[z[0]]
            return f'x_marker.{marker["id"]}.{pos}'
        return ''

    def _item_parse_x_marker(self, item: str, activate=None) -> (dict, str):
        parts = item.split('.')
        if len(parts) != 3 or parts[0] != 'x_marker':
            raise ValueError(f'invalid x_marker spec: {item}')
        marker_id, pos = parts[1:]
        marker_id = int(marker_id)
        marker = self._annotation_lookup(marker_id)
        if bool(activate):
            self.annotations['x'].move_to_end(marker_id)
        return marker, pos

    def _find_text_annotation(self, plot, x, y, distance):
        plot = self._plot_get(plot)
        a = self._text_annotation_nearest(plot, x, y, distance)
        if a is None:
            return ''
        return f'text_annotation.{a["id"]}'

    def _item_parse_text_annotation(self, item) -> dict:
        parts = item.split('.')
        if len(parts) != 2 or parts[0] != 'text_annotation':
            raise ValueError(f'invalid text_annotation spec: {item}')
        return self._annotation_lookup(int(parts[1]))

    def _find_y_marker(self, plot, y):
        plot = self._plot_get(plot)
        plot_index = plot['index']
        marker_info = []  # y, marker, pos
        for m in reversed(self.annotations['y'][plot_index].values()):
            marker_info.append([m['pos1'], m, 'pos1'])
            if m['dtype'] == 'dual':
                marker_info.append([m['pos2'], m, 'pos2'])
        my = np.array([e[0] for e in marker_info], dtype=float)
        my = self._y_value_to_pixel(plot, my)
        dy = np.abs(y - my)
        z = np.where(dy < _MARKER_SELECT_DISTANCE_PIXELS)[0]
        if len(z):
            _, marker, pos = marker_info[z[0]]
            return f'y_marker.{marker["id"]}.{pos}'
        return ''

    def _item_parse_y_marker(self, item: str, activate=None) -> (dict, str):
        parts = item.split('.')
        if len(parts) != 3 or parts[0] != 'y_marker':
            raise ValueError(f'invalid y_marker spec: {item}')
        marker_id, pos = parts[1:]
        marker_id = int(marker_id)
        marker = self._annotation_lookup(marker_id)
        if bool(activate):
            self.annotations['y'][marker['plot_index']].move_to_end(marker_id)
        return marker, pos

    def _find_item(self, pos=None):
        if pos is None:
            pos = self._mouse_pos
        if pos is None:
            return '', '', ''
        x_name, y_name = self._target_lookup_by_pos(pos)
        item = ''
        if y_name is None:
            pass
        elif y_name.startswith('spacer.'):
            if not y_name.startswith('spacer.ignore'):
                item = y_name
        elif y_name.startswith('plot.') and x_name.startswith('plot'):
            if x_name.startswith('plot'):
                item = self._find_text_annotation(y_name, pos[0], pos[1], 10)
            if not item:
                item = self._find_x_marker(pos[0])
            if not item and x_name.startswith('plot'):
                item = self._find_y_marker(y_name, pos[1])
        elif y_name == 'x_axis' and x_name.startswith('plot'):
            item = self._find_x_marker(pos[0])
        return item, x_name, y_name

    def _set_cursor(self, pos=None):
        if pos is None:
            pos = self._mouse_pos
        item, x_name, y_name = self._find_item(pos)
        cursor = self._CURSOR_ARROW
        if item.startswith('spacer'):
            cursor = self._CURSOR_SIZE_VER
        elif item.startswith('x_marker'):
            cursor = self._CURSOR_SIZE_HOR
        elif 'y_marker' in item:
            cursor = self._CURSOR_SIZE_VER
        self._graphics.setCursor(cursor)
        return item, x_name, y_name

    def plot_mouseMoveEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        if not len(self._x_geometry_info) or not len(self._y_geometry_info):
            return
        x, y = event.pos().x(), event.pos().y()
        self._mouse_pos = (x, y)
        self._set_cursor()
        self._repaint_request = True

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
            elif action == 'move.x_marker':
                xt = self._x_map.counter_to_time64(x)
                xr = self.x_range
                xt = max(xr[0], min(xt, xr[1]))  # bound to range
                item, move_both = self._mouse_action[1:3]
                m, m_field = self._item_parse_x_marker(item)
                m['changed'] = True
                xd = xt - m[m_field]
                m[m_field] += xd
                is_relative = m.get('mode', 'absolute') == 'relative'
                if is_relative:
                    m['rel' + m_field[-1]] = m[m_field] - xr[1]
                if m['dtype'] == 'dual':
                    if move_both:
                        m_field = 'pos1' if m_field == 'pos2' else 'pos2'
                        m[m_field] += xd
                        if is_relative:
                            m['rel' + m_field[-1]] = m[m_field] - xr[1]
                    self._request_marker_data(m)
            elif action == 'move.y_marker':
                item, move_both = self._mouse_action[1:3]
                m, m_field = self._item_parse_y_marker(item)
                plot = self._plot_get(m['plot_index'])
                yt = self._y_pixel_to_value(plot, y, skip_transform=True)
                yd = yt - self._y_transform_fwd(plot, m[m_field])
                yr = plot['range']
                yt = max(yr[0], min(yt, yr[1]))  # bound to range
                y = self._y_value_to_pixel(plot, yt, skip_transform=True)
                m[m_field] = self._y_pixel_to_value(plot, y)
                if m['dtype'] == 'dual' and move_both:
                    m_field = 'pos1' if m_field == 'pos2' else 'pos2'
                    m[m_field] = self._y_transform_rev(plot, yd + self._y_transform_fwd(plot, m[m_field]))
            elif action == 'x_pan':
                self._mouse_x_pan(x)
            elif action == 'x_pan_summary':
                self._mouse_x_pan_summary(x)
            elif action == 'y_pan':
                self._mouse_y_pan(y)
            elif action == 'move.text_annotation':
                item, is_ctrl = self._mouse_action[1:3]
                a = self._item_parse_text_annotation(item)
                plot = self._plot_get(a['plot_index'])

                # bound to x range
                xt = self._x_map.counter_to_time64(x)
                xr = self.x_range
                xt = max(xr[0], min(xt, xr[1]))  # bound to x range
                a['x'] = xt
                entry = self.annotations['text'][plot['index']]
                x_lookup = entry['x_lookup']
                x_lookup_idx = np.where(x_lookup[:, 1] == a['id'])[0][0]
                x_lookup[x_lookup_idx, 0] = xt

                # bound to y range
                if a['y_mode'] == 'manual':
                    yt = self._y_pixel_to_value(plot, y, skip_transform=True)
                    yr = plot['range']
                    yt = max(yr[0], min(yt, yr[1]))  # bound to range
                    y = self._y_value_to_pixel(plot, yt, skip_transform=True)
                    a['y'] = self._y_pixel_to_value(plot, y)

    def _x_pan(self, t0, t1):
        e0, e1 = self._extents()
        dt = int(t0 - t1)
        x0, x1 = self.x_range
        d_x = x1 - x0
        z0, z1 = x0 + dt, x1 + dt
        if self.pin_left or z0 < e0:
            z0, z1 = e0, e0 + d_x
        elif self.pin_right or z1 > e1:
            z0, z1 = e1 - d_x, e1
        self.x_range = [z0, z1]
        self._plot_data_invalidate()

    def _mouse_x_pan(self, x):
        t0 = self._x_map.counter_to_time64(self._mouse_action[1])
        t1 = self._x_map.counter_to_time64(x)
        self._mouse_action[1] = x
        self._x_pan(t0, t1)

    def _mouse_x_pan_summary(self, x):
        t1 = self._x_summary_map.counter_to_time64(self._mouse_action[1])
        t0 = self._x_summary_map.counter_to_time64(x)
        self._mouse_action[1] = x
        self._x_pan(t0, t1)

    def _mouse_y_pan(self, y1):
        idx = self._mouse_action[1]
        plot = self.state['plots'][idx]
        if plot['range_mode'] == 'fixed':
            return
        plot['range_mode'] = 'manual'
        y0 = self._mouse_action[2]
        self._mouse_action[2] = y1
        y0 = self._y_pixel_to_value(plot, y0, skip_transform=True)
        y1 = self._y_pixel_to_value(plot, y1, skip_transform=True)
        dy = y1 - y0
        r0, r1 = plot['range']
        plot['range'] = r0 - dy, r1 - dy
        self._repaint_request

    def plot_mousePressEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x, y = event.pos().x(), event.pos().y()
        item, x_name, y_name = self._find_item((x, y))
        is_ctrl = bool(QtCore.Qt.KeyboardModifier.ControlModifier & event.modifiers())
        self._log.info(f'mouse press ({x}, {y}) -> ({item}, {x_name}, {y_name}) is_ctrl={is_ctrl}')
        if self._mouse_action is None:
            self._mouse_pos_start = (x, y)
        if event.button() == QtCore.Qt.LeftButton:
            if item.startswith('spacer.'):
                idx = int(item.split('.')[1])
                _, y_start, _ = self._y_geometry_info[item]
                self._mouse_action = ['move.spacer', idx, y, y_start, y]
            elif item.startswith('x_marker.'):
                if self._mouse_action is not None:
                    self._mouse_action = None
                else:
                    self._item_parse_x_marker(item, activate=True)
                    self._mouse_action = ['move.x_marker', item, is_ctrl]
            elif item.startswith('text_annotation.'):
                if self._mouse_action is not None:
                    self._mouse_action = None
                else:
                    self._mouse_action = ['move.text_annotation', item, is_ctrl]
            elif 'y_marker' in item:
                if self._mouse_action is not None:
                    self._mouse_action = None
                else:
                    self._item_parse_y_marker(item, activate=True)
                    self._mouse_action = ['move.y_marker', item, is_ctrl]
            elif y_name == 'summary':
                if self.pin_left or self.pin_right:
                    pass  # pinned to extents, cannot pan
                else:
                    self._log.info('x_pan_summary start')
                    self._mouse_action = ['x_pan_summary', x]
            elif not is_ctrl and (y_name.startswith('plot.') or y_name == 'x_axis') and x_name == 'plot':
                if self.pin_left or self.pin_right:
                    pass  # pinned to extents, cannot pan
                else:
                    self._log.info('x_pan start')
                    self._mouse_action = ['x_pan', x]
            elif y_name.startswith('plot.') and (x_name.startswith('y_axis') or (is_ctrl and x_name == 'plot')):
                idx = int(y_name.split('.')[1])
                self._log.info('y_pan start')
                self._mouse_action = ['y_pan', idx, y]
            else:
                self._mouse_action = None
        if event.button() == QtCore.Qt.RightButton:
            if item.startswith('x_marker.'):
                self._menu_x_marker_single(item, event)
            elif item.startswith('text_annotation.'):
                self._menu_text_annotation_context(item, event)
            elif 'y_marker' in item:
                self._menu_y_marker_single(item, event)
            elif y_name.startswith('plot.'):
                idx = int(y_name.split('.')[1])
                if x_name.startswith('y_axis'):
                    self._menu_y_axis(idx, event)
                elif x_name.startswith('plot'):
                    self._menu_plot(idx, event)
                elif x_name.startswith('statistics'):
                    self._menu_statistics(idx, event)
            elif y_name == 'x_axis':
                if x_name.startswith('plot'):
                    self._menu_x_axis(event)
                elif x_name.startswith('statistics'):
                    self._menu_dt(event)
            elif y_name == 'summary':
                self._menu_summary(event)

    def _render_to_image(self) -> QtGui.QImage:
        return self._graphics.render_to_image()

    def _action_copy_image_to_clipboard(self):
        self._clipboard_image = self._render_to_image()
        QtWidgets.QApplication.clipboard().setImage(self._clipboard_image)

    @QtCore.Slot(int)
    def _action_save_image_dialog_finish(self, value):
        self._log.info('finished: %d', value)
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            filenames = self._dialog.selectedFiles()
            if len(filenames) == 1:
                filename = filenames[0]
                _, ext = os.path.splitext(filename)
                if ext in [None, '']:
                    filename += '.png'
                elif ext[1:].lower() not in ['bmp', 'jpg', 'jpeg', 'png', 'ppm', 'xbm', 'xpm']:
                    filename += '.png'
                self._log.info('finished: accept - save: %s', filename)
                img = self._render_to_image()
                if not img.save(filename):
                    self._log.warning('Could not save image: %s', filename)
            else:
                self._log.info('finished: accept - but no file selected, ignore')
        else:
            self._log.info('finished: reject - abort recording')
        self._dialog.close()
        self._dialog = None

    def _action_save_image(self):
        filter_str = 'png (*.png)'
        filename = time64.filename('.png')
        path = pubsub_singleton.query('registry/paths/settings/path')
        path = os.path.join(path, filename)
        dialog = QtWidgets.QFileDialog(self, N_('Save image to file'), path, filter_str)
        dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dialog.finished.connect(self._action_save_image_dialog_finish)
        self._dialog = dialog
        dialog.show()

    def plot_mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x, y = event.pos().x(), event.pos().y()
        item, x_name, y_name = self._find_item((x, y))
        self._log.info(f'mouse release ({x}, {y}) -> ({item}, {x_name}, {y_name})')
        if self._mouse_pos_start == (x, y):
            if item.startswith('x_marker') or 'y_marker' in item:
                pass  # keep dragging
            elif item.startswith('text_annotation.') and self._mouse_action is not None:
                a = self._item_parse_text_annotation(item)
                is_ctrl = self._mouse_action[-1]
                if is_ctrl:
                    a['text_show'] = not a['text_show']
                    self._repaint_request = True
                else:
                    dialog = TextAnnotationDialog(self, self.unique_id, a)
                    dialog.show()
                self._mouse_action = None
            else:
                self._mouse_action = None
        else:
            self._mouse_action = None

    def _menu_show(self, event: QtGui.QMouseEvent):
        menu = self._menu[0]
        menu.popup(event.globalPos())
        return menu

    def _on_menu_x_marker(self, action):
        pos = self._x_map.counter_to_time64(self._mouse_pos[0])
        topic = get_topic_name(self)
        self.pubsub.publish(f'{topic}/actions/!x_markers', [action, pos, None])

    def _menu_add_x_annotations(self, menu: QtWidgets.QMenu):
        single = QtGui.QAction(N_('Single marker'))
        menu.addAction(single)
        single.triggered.connect(lambda: self._on_menu_x_marker('add_single'))
        dual = QtGui.QAction(N_('Dual markers'))
        menu.addAction(dual)
        dual.triggered.connect(lambda: self._on_menu_x_marker('add_dual'))

        mode = menu.addMenu(N_('Mode'))
        mode_group = QtGui.QActionGroup(mode)
        mode_group.setExclusive(True)
        mode_absolute = QtGui.QAction(N_('Absolute'), mode_group, checkable=True)
        mode_absolute.setChecked(self.x_axis_annotation_mode == 'absolute')  # todo
        mode.addAction(mode_absolute)
        mode_absolute.triggered.connect(lambda: self._on_menu_x_mode('absolute'))

        mode_relative = QtGui.QAction(N_('Relative'), mode_group, checkable=True)
        mode_relative.setChecked(self.x_axis_annotation_mode == 'relative')
        mode.addAction(mode_relative)
        mode_relative.triggered.connect(lambda: self._on_menu_x_mode('relative'))

        clear_all = QtGui.QAction(N_('Clear all'))
        menu.addAction(clear_all)
        clear_all.triggered.connect(lambda: self._on_menu_x_marker('clear_all'))
        return [single, dual, [mode, mode_group, mode_absolute, mode_relative], clear_all]

    def _on_menu_x_mode(self, mode):
        self.x_axis_annotation_mode = mode

    def _menu_x_axis(self, event: QtGui.QMouseEvent):
        self._log.info('_menu_x_axis(%s)', event.pos())
        menu = QtWidgets.QMenu('Waveform x-axis context menu', self)

        annotations = menu.addMenu(N_('Annotations'))
        annotations_sub = self._menu_add_x_annotations(annotations)
        style_action = settings_action_create(self, menu)
        self._menu = [menu, annotations_sub, style_action]
        return self._menu_show(event)

    def _lookup_plot(self, pos=None):
        """Lookup the y-axis plot for the y pixel position.

        :param pos: The y-axis pixel position.  None (default) uses
            the current mouse coordinates.
        :return: The plot object.  If the current position is not in a
            plot, then return None.
        """
        if pos is None:
            pos = self._mouse_pos[1]
        y_name = _target_lookup_by_pos(self._y_geometry_info, pos)
        if not y_name.startswith('plot.'):
            return None
        parts = y_name.split('.')
        plot_index = int(parts[1])
        return self.state['plots'][plot_index]

    def _on_menu_y_marker(self, action):
        plot = self._lookup_plot()
        if plot is not None:
            pos = self._y_pixel_to_value(plot, self._mouse_pos[1])
            topic = get_topic_name(self)
            self.pubsub.publish(f'{topic}/actions/!y_markers', [action, plot, pos, None])

    def _menu_add_y_annotations(self, menu: QtWidgets.QMenu):
        single = QtGui.QAction(N_('Single marker'))
        menu.addAction(single)
        single.triggered.connect(lambda: self._on_menu_y_marker('add_single'))
        dual = QtGui.QAction(N_('Dual markers'))
        menu.addAction(dual)
        dual.triggered.connect(lambda: self._on_menu_y_marker('add_dual'))
        clear_all = QtGui.QAction(N_('Clear all'))
        menu.addAction(clear_all)
        clear_all.triggered.connect(lambda: self._on_menu_y_marker('clear_all'))
        return [single, dual, clear_all]

    def _on_menu_y_scale_mode(self, idx, value):
        plot = self.state['plots'][idx]
        if value != plot['scale']:
            plot['scale'] = value
            plot['range_mode'] = 'auto'
            self._repaint_request = True

    def _on_menu_y_logarithmic_zero(self, idx, value):
        plot = self.state['plots'][idx]
        if value != plot['logarithmic_zero']:
            plot['logarithmic_zero'] = value
            plot['scale'] = 'logarithmic'
            plot['range_mode'] = 'auto'
            self._repaint_request = True

    def _on_menu_y_range_mode(self, idx, value):
        plot = self.state['plots'][idx]
        plot['range_mode'] = value
        self._repaint_request = True

    def _menu_y_axis(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_y_axis(%s, %s)', idx, event.pos())
        menu = QtWidgets.QMenu('Waveform y-axis context menu', self)
        plot = self.state['plots'][idx]
        annotations = menu.addMenu(N_('Annotations'))
        annotations_sub = self._menu_add_y_annotations(annotations)
        if plot['range_mode'] != 'fixed':
            range_mode = menu.addMenu(N_('Range'))
            range_group = QtGui.QActionGroup(range_mode)
            range_group.setExclusive(True)
            range_mode_auto = QtGui.QAction(N_('Auto'), range_group, checkable=True)
            range_mode_auto.setChecked(plot['range_mode'] == 'auto')
            range_mode.addAction(range_mode_auto)
            range_mode_auto.triggered.connect(lambda: self._on_menu_y_range_mode(idx, 'auto'))
            range_mode_manual = QtGui.QAction(N_('Manual'), range_group, checkable=True)
            range_mode_manual.setChecked(plot['range_mode'] == 'manual')
            range_mode.addAction(range_mode_manual)
            range_mode_manual.triggered.connect(lambda: self._on_menu_y_range_mode(idx, 'manual'))
            range_menu = [range_mode, range_group, range_mode_auto, range_mode_manual]
        else:
            range_menu = []

        if plot['quantity'] in ['i', 'p']:
            scale = plot['scale']
            scale_mode = menu.addMenu(N_('Scale'))
            scale_group = QtGui.QActionGroup(scale_mode)
            scale_group.setExclusive(True)
            scale_mode_auto = QtGui.QAction(N_('Linear'), scale_group, checkable=True)
            scale_mode_auto.setChecked(scale == 'linear')
            scale_mode.addAction(scale_mode_auto)
            scale_mode_auto.triggered.connect(lambda: self._on_menu_y_scale_mode(idx, 'linear'))
            scale_mode_manual = QtGui.QAction(N_('Logarithmic'), scale_group, checkable=True)
            scale_mode_manual.setChecked(scale == 'logarithmic')
            scale_mode.addAction(scale_mode_manual)
            scale_mode_manual.triggered.connect(lambda: self._on_menu_y_scale_mode(idx, 'logarithmic'))
            scale_menu = [scale_mode, scale_group, scale_mode_auto, scale_mode_manual]

            if scale == 'logarithmic':
                z = plot['logarithmic_zero']
                logarithmic_zero = menu.addMenu(N_('Logarithmic zero'))
                logarithmic_group = QtGui.QActionGroup(logarithmic_zero)
                logarithmic_group.setExclusive(True)
                scale_menu.extend([logarithmic_zero, logarithmic_group])

                def logarithm_action_gen(value):
                    v = QtGui.QAction(f'{value:d}', logarithmic_group, checkable=True)
                    v.setChecked(value == z)
                    logarithmic_zero.addAction(v)
                    v.triggered.connect(lambda: self._on_menu_y_logarithmic_zero(idx, value))
                    scale_menu.append(v)
                    return v

                for v in range(1, -10, -1):
                    logarithm_action_gen(v)
        else:
            scale_menu = []

        style_action = settings_action_create(self, menu)
        self._menu = [menu, annotations, annotations_sub, scale_menu, range_menu, style_action]
        return self._menu_show(event)

    def _on_menu_text_annotation(self, action):
        plot = self._lookup_plot()
        if plot is None:
            return
        topic = get_topic_name(self)
        if action == 'add':
            kwargs = {
                # new, so no id
                'plot_index': plot['index'],
                'text': '',
                'text_show': True,
                'shape': 0,
                'x': self._x_map.counter_to_time64(self._mouse_pos[0]),
                'y': self._y_pixel_to_value(plot, self._mouse_pos[1]),
                'y_mode': 'manual',
            }
            dialog = TextAnnotationDialog(self, self.unique_id, kwargs)
            dialog.show()
        else:
            self.pubsub.publish(f'{topic}/actions/!text_annotation', [action, plot['index']])

    def _on_menu_annotations_save(self):
        for source in self._sources.keys():
            if source.startswith('JlsSource'):
                break
        path = self.pubsub.query(f'{get_topic_name(source)}/settings/path')
        path_base, path_ext = os.path.splitext(path)
        anno_path = f'{path_base}.anno{path_ext}'
        self.on_callback_annotation_save({'path': anno_path})

    def _on_menu_annotations_clear_all(self):
        self._on_menu_x_marker('clear_all')
        self._on_menu_y_marker('clear_all')
        self._on_menu_text_annotation('clear_all')

    def _menu_add_text_annotations(self, menu: QtWidgets.QMenu):
        add = QtGui.QAction(N_('Add'))
        menu.addAction(add)
        add.triggered.connect(lambda: self._on_menu_text_annotation('add'))
        hide = QtGui.QAction(N_('Hide all text'))
        menu.addAction(hide)
        hide.triggered.connect(lambda: self._on_menu_text_annotation('text_hide_all'))
        show = QtGui.QAction(N_('Show all text'))
        menu.addAction(show)
        show.triggered.connect(lambda: self._on_menu_text_annotation('text_show_all'))
        clear_all = QtGui.QAction(N_('Clear all'))
        menu.addAction(clear_all)
        clear_all.triggered.connect(lambda: self._on_menu_text_annotation('clear_all'))
        return [add, hide, show, clear_all]

    def _menu_plot(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_plot(%s, %s)', idx, event.pos())
        dynamic = []
        plot = self.state['plots'][idx]
        menu = QtWidgets.QMenu('Waveform context menu', self)
        annotations = menu.addMenu(N_('Annotations'))
        anno_x = annotations.addMenu(N_('Vertical'))
        anno_x_sub = self._menu_add_x_annotations(anno_x)

        anno_y = annotations.addMenu(N_('Horizontal'))
        anno_y_sub = self._menu_add_y_annotations(anno_y)
        anno_text = annotations.addMenu(N_('Text'))
        anno_text_sub = self._menu_add_text_annotations(anno_text)
        for source in self._sources.keys():
            if source.startswith('JlsSource'):
                anno_save = annotations.addAction(N_('Save'))
                anno_save.triggered.connect(self._on_menu_annotations_save)
                dynamic.append(anno_save)
                break
        anno_clear_all = annotations.addAction(N_('Clear all'))
        anno_clear_all.triggered.connect(self._on_menu_annotations_clear_all)

        if plot['range_mode'] == 'manual':
            range_mode = menu.addAction(N_('Y-axis auto range'))
            range_mode.triggered.connect(lambda: self._on_menu_y_range_mode(idx, 'auto'))
            dynamic.append(range_mode)

        copy_image = menu.addAction(N_('Save image to file'))
        copy_image.triggered.connect(self._action_save_image)

        copy_image = menu.addAction(N_('Copy image to clipboard'))
        copy_image.triggered.connect(self._action_copy_image_to_clipboard)

        export_range = menu.addAction(N_('Export visible data'))
        export_range.triggered.connect(lambda: self._on_x_export('range'))

        export_all = menu.addAction(N_('Export all data'))
        export_all.triggered.connect(lambda: self._on_x_export('extents'))

        style_action = settings_action_create(self, menu)
        self._menu = [menu,
                      dynamic,
                      annotations, anno_x, anno_x_sub, anno_y, anno_y_sub, anno_text, anno_text_sub,
                      anno_clear_all,
                      copy_image,
                      export_range, export_all,
                      style_action]
        return self._menu_show(event)

    def _menu_dt(self, event: QtGui.QMouseEvent):
        self._log.info('_menu_dt(%s)', event.pos())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        x0, x1 = self.x_range
        interval = abs(x1 - x0) / time64.SECOND
        interval_widget = IntervalWidget(self, interval)
        interval_widget.value.connect(self._on_dt_interval)
        interval_action = QtWidgets.QWidgetAction(menu)
        interval_action.setDefaultWidget(interval_widget)
        menu.addAction(interval_action)

        self._menu = [menu, interval_widget, interval_action]
        return self._menu_show(event)

    def _on_dt_interval(self, dt):
        e0, e1 = self._extents()
        er = e1 - e0
        dt = int(dt * time64.SECOND)
        dt = min(dt, er)
        if dt < er and self.pin_left and self.pin_right:
            self.pin_left = False  # unpin from left

        x0, x1 = self.x_range
        xc = (x1 + x0) // 2
        dt_half = dt // 2
        x0, x1 = xc - dt_half, xc + dt_half
        if self.pin_left or x0 < e0:
            x0, x1 = e0, e0 + dt
        elif self.pin_right or x1 > e0:
            x0, x1 = e1 - dt, e1
        self.x_range = [x0, x1]
        self._plot_data_invalidate()

        self._repaint_request = True

    def _menu_statistics(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_statistics(%s, %s)', idx, event.pos())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        style_action = settings_action_create(self, menu)
        self._menu = [menu,
                      style_action]
        return self._menu_show(event)

    def _on_x_marker_statistics_show(self, marker, text_pos_key, pos):
        marker[text_pos_key] = pos
        self._repaint_request = True

    def _signals_get(self):
        signals = []
        for plot in self.state['plots']:
            if plot['enabled']:
                signals.extend(plot['signals'])
        return signals

    def _annotations_filter(self, x_range):
        r = {}
        inside, _ = self._x_markers_filter(x_range)
        r['x'] = [self.annotations['x'][m_id] for m_id in inside]
        x_range = self._extents()
        _, outside = self._x_markers_filter(x_range)
        for m_id in outside:
            del self.annotations['x'][m_id]
        for plot_index, entry in enumerate(self.annotations['text']):
            _, outside = self._text_annotations_filter(x_range, plot_index)
            for a_id in outside:
                self._text_annotation_remove(a_id)

    def _on_x_export(self, src):
        if isinstance(src, int):  # marker_id
            m = self._annotation_lookup(src)
            x0, x1 = m['pos1'], m['pos2']
            if x0 > x1:
                x0, x1 = x1, x0
        elif isinstance(src, str):
            if src == 'range':
                x0, x1 = self.x_range
            elif src == 'extents':
                x0, x1 = self._extents()
            else:
                raise ValueError(f'unsupported x_export source {src}')
        else:
            raise ValueError(f'unsupported x_export source {src}')

        signals = self._signals_get()
        # Use CAPABILITIES.RANGE_TOOL_CLASS value format.
        pubsub_singleton.publish('registry/exporter/actions/!run', {
            'x_range': (x0, x1),
            'signals': signals,
            'range_tool': {
                'start_callbacks': [f'{get_topic_name(self)}/callbacks/!annotation_save'],
                'done_callbacks': [],
            }
        })

    def _on_range_tool(self, unique_id, marker_idx):
        m = self._annotation_lookup(marker_idx)
        x0, x1 = m['pos1'], m['pos2']
        if x0 > x1:
            x0, x1 = x1, x0
        pubsub_singleton.publish(f'registry/{unique_id}/actions/!run', {
            'x_range': (x0, x1),
            'origin': self.unique_id,
            'signals': self._signals_get(),
            #  todo 'signal_default':
        })

    def _construct_analysis_menu_action(self, analysis_menu, unique_id, idx):
        cls = get_instance(unique_id)
        action = analysis_menu.addAction(cls.NAME)
        action.triggered.connect(lambda: self._on_range_tool(unique_id, idx))
        return action

    def _on_x_interval(self, m, pos_text, interval):
        other_pos = 'pos2' if pos_text == 'pos1' else 'pos1'
        if m.get('mode', 'absolute') == 'relative':
            pos_text = 'rel' + pos_text[-1]
            other_pos = 'rel' + other_pos[-1]
        m[other_pos] = m[pos_text] + int(interval * time64.SECOND)
        m['changed'] = True
        self._request_marker_data(m)

    def _menu_x_marker_single(self, item, event: QtGui.QMouseEvent):
        m, pos_text = self._item_parse_x_marker(item)
        dynamic_items = []
        is_dual = m.get('dtype') == 'dual'
        pos = m.get(f'text_{pos_text}', 'right')

        menu = QtWidgets.QMenu('Waveform x_marker context menu', self)

        if is_dual:
            export = menu.addAction(N_('Export'))
            export.triggered.connect(lambda: self._on_x_export(m['id']))
            dynamic_items.append(export)

            analysis_menu = menu.addMenu(N_('Analysis'))
            dynamic_items.append(analysis_menu)
            range_tools = self.pubsub.query('registry_manager/capabilities/range_tool.class/list')
            for unique_id in range_tools:
                if unique_id == 'exporter':
                    continue  # special, has own menu item
                action = self._construct_analysis_menu_action(analysis_menu, unique_id, m['id'])
                dynamic_items.append(action)

            other_pos = 'pos2' if pos_text == 'pos1' else 'pos1'
            interval_menu = menu.addMenu(N_('Interval'))
            interval = (m[other_pos] - m[pos_text]) / time64.SECOND
            interval_widget = IntervalWidget(self, interval)
            interval_widget.value.connect(lambda x: self._on_x_interval(m, pos_text, x))
            interval_action = QtWidgets.QWidgetAction(interval_menu)
            interval_action.setDefaultWidget(interval_widget)
            interval_menu.addAction(interval_action)
            dynamic_items.append([interval_menu, interval_widget, interval_action])

        show_stats_menu = menu.addMenu(N_('Show statistics'))
        show_stats_group = QtGui.QActionGroup(show_stats_menu)

        left = show_stats_menu.addAction(N_('Left'))
        left.setCheckable(True)
        left.setChecked(pos == 'left')
        left.triggered.connect(lambda: self._on_x_marker_statistics_show(m, f'text_{pos_text}', 'left'))
        show_stats_group.addAction(left)

        right = show_stats_menu.addAction(N_('Right'))
        right.setCheckable(True)
        right.setChecked(pos == 'right')
        right.triggered.connect(lambda: self._on_x_marker_statistics_show(m, f'text_{pos_text}', 'right'))
        show_stats_group.addAction(right)

        off = show_stats_menu.addAction(N_('Off'))
        off.setCheckable(True)
        off.setChecked(pos == 'off')
        off.triggered.connect(lambda: self._on_x_marker_statistics_show(m, f'text_{pos_text}', 'off'))
        show_stats_group.addAction(off)

        marker_remove = menu.addAction(N_('Remove'))
        topic = get_topic_name(self)
        marker_remove.triggered.connect(lambda: self.pubsub.publish(f'{topic}/actions/!x_markers', ['remove', m['id']]))
        self._menu = [menu, dynamic_items,
                      show_stats_menu, show_stats_group, left, right, off,
                      marker_remove]
        return self._menu_show(event)

    def _menu_text_annotation_context(self, item, event):
        a = self._item_parse_text_annotation(item)
        menu = QtWidgets.QMenu('Waveform text annotation context menu', self)

        edit = menu.addAction(N_('Edit'))
        edit.triggered.connect(lambda: self._on_text_annotation_edit(a['id']))

        show = menu.addAction(N_('Show text'))
        show.setCheckable(True)
        show.setChecked(a['text_show'])
        show.toggled.connect(lambda value: self._on_text_annotation_show(a['id'], value))

        menu_items = []
        y_mode = menu.addMenu(N_('Y mode'))
        y_mode_group = QtGui.QActionGroup(y_mode)

        def y_mode_item(value, name):
            m = y_mode.addAction(name)
            m.setCheckable(True)
            m.setChecked(a['y_mode'] == value)
            m.triggered.connect(lambda: self._on_text_annotation_y_mode(a['id'], value))
            y_mode_group.addAction(m)
            return m

        menu_items.append([y_mode_item(*value) for value in Y_POSITION_MODE])

        shape = menu.addMenu(N_('Shape'))
        shape_group = QtGui.QActionGroup(shape)

        def shape_item(index, name):
            m = shape.addAction(name)
            m.setCheckable(True)
            m.setChecked(a['shape'] == index)
            m.triggered.connect(lambda: self._on_text_annotation_shape(a['id'], index))
            shape_group.addAction(m)
            return m

        menu_items.append([shape_item(index, value[1]) for index, value in enumerate(SHAPES_DEF)])

        remove = menu.addAction(N_('Remove'))
        remove.triggered.connect(lambda: self._on_text_annotation_remove(a['id']))

        self._menu = [
            menu, edit, show, y_mode, y_mode_group, shape, shape_group, remove,
        ]

        return self._menu_show(event)

    def _on_text_annotation_edit(self, a_id):
        a = self._annotation_lookup(a_id)
        TextAnnotationDialog(self, self.unique_id, a).show()

    def _on_text_annotation_show(self, a_id, value):
        a = self._annotation_lookup(a_id)
        a['text_show'] = bool(value)
        self._repaint_request = True

    def _on_text_annotation_y_mode(self, a_id, value):
        a = self._annotation_lookup(a_id)
        a['y_mode'] = value
        self._repaint_request = True

    def _on_text_annotation_shape(self, a_id, index):
        a = self._annotation_lookup(a_id)
        a['shape'] = index
        self._repaint_request = True

    def _on_text_annotation_remove(self, a_id):
        a = self._annotation_lookup(a_id)
        self._text_annotation_remove(a)

    def _menu_y_marker_single(self, item, event: QtGui.QMouseEvent):
        m, m_pos = self._item_parse_y_marker(item)
        menu = QtWidgets.QMenu('Waveform y_marker context menu', self)
        marker_remove = menu.addAction(N_('Remove'))
        topic = get_topic_name(self)
        marker_remove.triggered.connect(lambda: self.pubsub.publish(f'{topic}/actions/!y_markers',
                                                                    ['remove', m['plot_index'], m['id']]))
        self._menu = [menu,
                      marker_remove]
        return self._menu_show(event)

    def _menu_summary_signal(self, menu, signal):
        def action():
            self.summary_signal = signal

        a = menu.addAction(' '.join(signal))
        a.triggered.connect(action)
        return a

    def _menu_summary(self, event: QtGui.QMouseEvent):
        self._log.info('_menu_summary(%s)', event.pos())
        menu = QtWidgets.QMenu('Waveform summary context menu', self)
        signal_menu = QtWidgets.QMenu('Signal', menu)
        menu.addMenu(signal_menu)
        signals = []
        selected = self.summary_signal
        for item, signal in self._signals.items():
            if selected is None:
                selected = item
            a = self._menu_summary_signal(signal_menu, item)
            signals.append(a)
            a.setChecked(item == selected)
        style_action = settings_action_create(self, menu)
        self._menu = [menu, signal_menu, signals, style_action]
        return self._menu_show(event)

    def on_style_change(self):
        self._style_cache = None
        self._repaint_request = True
        self.update()

    def _x_marker_position(self, xi):
        xi_init = xi
        x0, x1 = self.x_range
        p0, p1 = self._x_map.time64_to_counter(x0), self._x_map.time64_to_counter(x1)
        pd = (p1 - p0) // 25
        pd = min(10, pd)
        xd = self._x_map.counter_to_time64(p0 + pd) - x0

        m1 = [z['pos1'] for z in self.annotations['x'].values()]
        m2 = [z['pos2'] for z in self.annotations['x'].values() if 'pos2' in z]
        m = np.array(m1 + m2, dtype=float)
        if not len(m):
            return xi
        while xi < x1:
            dm = np.min(np.abs(m - xi))
            if dm >= xd:
                return xi
            xi += xd
        return xi_init  # give up

    def _x_marker_add(self, marker):
        self._log.info('x_marker_add %s', marker)
        self.annotations['x'][marker['id']] = marker
        return marker

    def _x_marker_remove(self, marker):
        self._log.info('x_marker_remove %s', marker)
        if isinstance(marker, int):
            marker = self.annotations['x'].pop(marker)
            return marker
        elif isinstance(marker, dict):
            marker = self.annotations['x'].pop(marker['id'])
            return marker
        else:
            raise ValueError('unsupported remove')

    def _x_marker_add_single(self, pos1=None):
        if pos1 is None:
            x0, x1 = self.x_range
            xc = (x1 + x0) // 2
            pos1 = self._x_marker_position(xc)
        marker = {
            'id': self._annotation_next_id('x'),
            'dtype': 'single',
            'mode': self.x_axis_annotation_mode,
            'pos1': pos1,
            'changed': True,
            'text_pos1': 'right',
            'text_pos2': 'off',
        }
        if self.x_axis_annotation_mode == 'relative':
            marker['mode'] = 'relative'
            marker['rel1'] = pos1 - x1
        return self._x_marker_add(marker)

    def _x_marker_add_dual(self, pos1=None, pos2=None):
        x0, x1 = self.x_range
        if pos1 is not None and pos2 is None:
            xc = pos1
            pos1 = None
        else:
            xc = (x1 + x0) // 2
        xd = (x1 - x0) // 10
        if pos1 is None:
            pos1 = self._x_marker_position(xc - xd)
        if pos2 is None:
            pos2 = self._x_marker_position(xc + xd)
        marker = {
            'id': self._annotation_next_id('x'),
            'dtype': 'dual',
            'mode': self.x_axis_annotation_mode,
            'pos1': pos1,
            'pos2': pos2,
            'changed': True,
            'text_pos1': 'off',
            'text_pos2': 'right',
        }
        if self.x_axis_annotation_mode == 'relative':
            marker['mode'] = 'relative'
            marker['rel1'] = pos1 - x1
            marker['rel2'] = pos2 - x1

        return self._x_marker_add(marker)

    def on_action_x_markers(self, topic, value):
        """Perform a marker action.

        :param value: Either the action string or [action, args...].
            Action strings that do not require arguments include:
            add_single, add_dual, clear_all.  The commands are:
            * ['add_single', pos]
            * ['add_dual', center, None]
            * ['add_dual', pos1, pos2]
            * ['clear_all']
            * ['remove', marker_id, ...]
            * ['add', marker_obj, ...]  # for undo remove
        """
        self._log.info('x_markers %s', value)
        value = _marker_action_string_to_command(value)
        cmd = value[0]
        self._repaint_request = True
        if cmd == 'remove':
            m = self._x_marker_remove(value[1])
            return [topic, ['add', m]]
        elif cmd == 'add_single':
            m = self._x_marker_add_single(value[1])
            return [topic, ['remove', m['id']]]
        elif cmd == 'add_dual':
            m = self._x_marker_add_dual(value[1], value[2])
            return [topic, ['remove', m['id']]]
        elif cmd == 'add':
            for m in value[1:]:
                self._x_marker_add(m)
            return [topic, ['remove'] + value[1:]]
        elif cmd == 'clear_all':
            self.annotations['x'], rv = OrderedDict(), self.annotations['x']
            return None
        else:
            raise NotImplementedError(f'Unsupported marker action {value}')

    def _y_marker_position(self, plot, yi):
        yi = self._y_transform_fwd(plot, yi)
        yi_init = yi
        y0, y1 = plot['range']
        p0 = self._y_value_to_pixel(plot, y0, skip_transform=True)
        p1 = self._y_value_to_pixel(plot, y1, skip_transform=True)
        pd = (p1 - p0) // 25
        pd = min(10, pd)
        xd = self._y_pixel_to_value(plot, p0 + pd, skip_transform=True) - y0
        items = self.annotations['y'][plot['index']]
        m1 = [self._y_transform_fwd(plot, z['pos1']) for z in items.values()]
        m2 = [self._y_transform_fwd(plot, z['pos2']) for z in items.values() if 'pos2' in z]
        m = np.array(m1 + m2, dtype=float)
        if not len(m):
            return self._y_transform_rev(plot, yi)
        while yi < y1:
            dm = np.min(np.abs(m - yi))
            if dm >= xd:
                return self._y_transform_rev(plot, yi)
            yi += xd
        return self._y_transform_rev(plot, yi_init)  # give up

    def _y_marker_add(self, marker):
        self._log.info('y_marker_add(%s)', marker)
        self.annotations['y'][marker['plot_index']][marker['id']] = marker
        return marker

    def _y_marker_remove(self, marker):
        self._log.info('y_marker_remove(%s)', marker)
        marker = self._annotation_lookup(marker)
        del self.annotations['y'][marker['plot_index']][marker['id']]
        return marker

    def _y_marker_add_single(self, plot, pos1=None):
        if pos1 is None:
            y0, y1 = plot['range']
            yc = (y1 + y0) // 2
            pos1 = self._y_marker_position(plot, yc)
        plot_index = plot['index']
        marker = {
            'id': self._annotation_next_id('y', plot_index),
            'dtype': 'single',
            'pos1': pos1,
            'plot_index': plot_index,
        }
        return self._y_marker_add(marker)

    def _y_marker_add_dual(self, plot, pos1=None, pos2=None):
        if pos1 is not None and pos2 is not None:
            pass  # use the provided values.
        else:
            y0, y1 = plot['range']
            if pos1 is not None:
                yc = self._y_transform_fwd(plot, pos1)
                pos1 = None
            else:
                yc = (y1 + y0) / 2
            yd = (y1 - y0) / 10
            if pos1 is None:
                pos1 = self._y_marker_position(plot, self._y_transform_rev(plot, yc - yd))
            if pos2 is None:
                pos2 = self._y_marker_position(plot, self._y_transform_rev(plot, yc + yd))
        plot_index = plot['index']
        marker = {
            'id': self._annotation_next_id('y', plot_index),
            'dtype': 'dual',
            'pos1': pos1,
            'pos2': pos2,
            'plot_index': plot_index,
        }
        return self._y_marker_add(marker)

    def _plot_get(self, plot):
        """Get a plot.

        :param plot: The plot specification, which is one of:
            * The plot index integer.
            * The plot region name or plot quantity.
            * The plot instance.
        :return: The plot instance.
        :raises ValueError: On invalid plot specifications.
        :raises KeyError: If the specified plot does not exist.
        """

        if isinstance(plot, str):
            parts = plot.split('.')
            if len(parts) == 2:
                plot = int(parts[1])
            elif len(parts) == 1:
                quantities = [p['quantity'] for p in self.state['plots']]
                plot = quantities.index(parts[0])
            else:
                raise ValueError(f'Unsupported plot string: {plot}')
        if isinstance(plot, int):
            plot = self.state['plots'][plot]
        elif isinstance(plot, dict):
            pass
        else:
            raise ValueError(f'Unsupported plot identifier {plot}')
        return plot

    def on_action_y_markers(self, topic, value):
        """Perform a y-axis marker action.

        :param value: Either the action string or [action, args...].
            Action strings that do not require arguments include:
            add_single, add_dual, clear_all.  The commands are:
            * ['add_single', plot, pos]
            * ['add_dual', plot, center, None]
            * ['add_dual', plot, pos1, pos2]
            * ['clear_all', plot]
            * ['remove', plot, marker_id, ...]
            * ['add', plot, marker_obj, ...]  # for undo remove

            In all cases, plot can be the plot index or plot object.
        """
        self._log.info('y_markers %s', value)
        value = _marker_action_string_to_command(value)
        cmd = value[0]
        plot = self._plot_get(value[1])
        plot_index = plot['index']
        self._repaint_request = True
        if cmd == 'remove':
            for m in value[2:]:
                self._y_marker_remove(m)
            return [topic, ['add', plot_index] + value[2:]]
        elif cmd == 'add_single':
            m = self._y_marker_add_single(plot, value[2])
            return [topic, ['remove', plot_index, m['id']]]
        elif cmd == 'add_dual':
            m = self._y_marker_add_dual(plot, value[2], value[3])
            return [topic, ['remove', plot_index, m['id']]]
        elif cmd == 'add':
            for m in value[2:]:
                self._y_marker_add(m)
            return [topic, ['remove', plot_index] + value[2:]]
        elif cmd == 'clear_all':
            self.annotations['y'][plot_index], items = OrderedDict(), self.annotations['y'][plot_index]
            return [topic, ['add', list(items.values())]]
        else:
            raise NotImplementedError(f'Unsupported marker action {value}')

    def _text_annotation_add(self, a):
        plot_index = a['plot_index']
        if 'id' not in a:
            a['id'] = self._annotation_next_id('text', plot_index)
        entry = self.annotations['text'][plot_index]
        entry['items'][a['id']] = a
        x_lookup_length = entry['x_lookup_length']
        x_lookup = entry['x_lookup']
        if (x_lookup_length + 1) > len(x_lookup):
            np.resize(x_lookup, (len(x_lookup) * 2, 2))
            x_lookup[x_lookup_length:, 0] = np.iinfo(np.int64).max
        x_lookup[x_lookup_length, :] = a['x'], a['id']
        entry['x_lookup_length'] += 1
        self._repaint_request = True

    def _text_annotation_remove(self, a):
        a = self._annotation_lookup(a)
        entry = self.annotations['text'][a['plot_index']]
        a_id = a['id']
        x_lookup = entry['x_lookup']
        idx = np.where(x_lookup[:, 1] == a_id)[0]
        idx_len = len(idx)
        if idx_len == 0:
            self._log.warning('_text_annotation_remove but missing in x_pos list')
        elif idx_len > 1:
            self._log.warning('_text_annotation_remove but too many entries')
        else:
            x_lookup[idx[0]:-1, :] = x_lookup[(idx[0] + 1):, :]
            entry['x_lookup_length'] -= 1
        del self.annotations['text'][a['plot_index']]['items'][a_id]
        self._repaint_request = True

    def on_callback_annotation_save(self, value):
        """Export callback to save annotations.

        :param value: The value dict with keys (see _on_x_export):
            * x_range: The (x0, x1) time64 range.  Use extents if not provided.
            * signals: The list of signals to export.
            * path: The user-selected export path for the main data file.
        """
        self._log.info('on_callback_annotation_save start')
        x0, x1 = value.get('x_range', self._extents())
        path_base, path_ext = os.path.splitext(value['path'])
        path = f'{path_base}.anno{path_ext}'
        sample_rate = 1_000_000

        def x_map(x_i64):
            return int(round((x_i64 - x0) * (sample_rate / time64.SECOND)))

        with pyjls.Writer(path) as w:
            w.source_def(source_id=1, name='annotations', vendor='-', model='-',
                         version='-', serial_number='-')
            signal_id = 1
            for plot in self.state['plots']:
                z = []
                if not plot['enabled']:
                    continue
                plot_index = plot['index']
                w.signal_def(signal_id=signal_id, source_id=1, sample_rate=sample_rate,
                             name=TO_JLS_SIGNAL_NAME[plot['quantity']], units=plot['units'])
                w.utc(signal_id, x_map(x0), x0)
                w.utc(signal_id, x_map(x1), x1)

                # Add y-axis markers at start
                for m in self.annotations['y'][plot_index].values():
                    m_id = (m['id'] % _ANNOTATION_Y_MOD) + 1
                    if m['dtype'] == 'single':
                        z.append([signal_id, x0, m['pos1'], pyjls.AnnotationType.HMARKER, 0, f'{m_id}'])
                    elif m['dtype'] == 'dual':
                        z.append([signal_id, x0, m['pos1'], pyjls.AnnotationType.HMARKER, 0, f'{m_id}a'])
                        z.append([signal_id, x0, m['pos2'], pyjls.AnnotationType.HMARKER, 0, f'{m_id}b'])

                # Add x-axis markers, but only to first signal
                if signal_id == 1:
                    inside, _ = self._x_markers_filter((x0, x1))
                    for m_id in inside:
                        m = self._annotation_lookup(m_id)
                        m_id += 1  # convert to 1-indexed
                        if m['dtype'] == 'single':
                            z.append([signal_id, m['pos1'], None, pyjls.AnnotationType.VMARKER, 0, f'{m_id}'])
                        elif m['dtype'] == 'dual':
                            z.append([signal_id, m['pos1'], None, pyjls.AnnotationType.VMARKER, 0, f'{m_id}a'])
                            z.append([signal_id, m['pos2'], None, pyjls.AnnotationType.VMARKER, 0, f'{m_id}b'])

                # Add text annotations
                inside, _ = self._text_annotations_filter((x0, x1), plot_index)
                for a_id in inside:
                    a = self._annotation_lookup(a_id)
                    y = a['y'] if a['y_mode'] == 'manual' else None
                    z.append([signal_id, a['x'], y, pyjls.AnnotationType.TEXT, a['shape'], a['text']])

                for e in sorted(z, key=lambda e: e[1]):
                    signal_id, x, y, dtype, group_id, data = e
                    x = x_map(x)
                    w.annotation(signal_id, x, y, dtype, group_id, data)
                signal_id += 1
        self._log.info('on_callback_annotation_save done')

    def on_action_text_annotation(self, topic, value):
        """Perform a text annotation action.

        :param value: The list of the command action string and arguments.
            The supported commands are:
            * ['add', kwargs, ...]
            * ['update', kwargs, ...]
            * ['text_hide_all', plot]
            * ['text_show_all', plot]
            * ['clear_all', plot]
            * ['remove', kwargs, ...]

        In all cases, plot can be the plot index or plot object.
        See the top of this file for the text_annotation data structure definition.
        """
        self._log.info('text_annotation %s', value)
        action = value[0]
        self._repaint_request = True
        if action == 'add':
            for a in value[1:]:
                self._text_annotation_add(a)
            return [topic, ['remove', a]]
        elif action == 'update':
            pass  # text_annotation entry modified in place
        elif action == 'remove':
            for a in value[1:]:
                self._text_annotation_remove(a)
            return [topic, ['add', a]]
        elif action in ['text_hide_all', 'text_show_all']:
            show = (action == 'text_show_all')
            if len(value) == 1:
                plot_ids = [p['index'] for p in self.state['plots']]
            else:
                plot_ids = value[1:]
            for plot_id in plot_ids:
                entry = self.annotations['text'][plot_id]
                for item in entry['items'].values():
                    item['text_show'] = show
            return [topic, ['text_hide_all' if show else 'text_show_all'] + value[1:]]
        elif action in ['clear_all']:
            if len(value) == 1:
                plot_ids = [p['index'] for p in self.state['plots']]
            else:
                plot_ids = value[1:]
            all_items = []
            for plot_id in plot_ids:
                entry = self.annotations['text'][plot_id]
                self.annotations['text'][plot_id]['items'], items = OrderedDict(), self.annotations['text'][plot_id]['items']
                entry['x_lookup_length'] = 0
                entry['x_lookup'][:, 0] = np.iinfo(np.int64).max
                all_items.extend(items.values())
            return [topic, ['add', all_items]]
        else:
            raise ValueError(f'unsupported text_annotation action {action}')

    def on_action_x_range(self, topic, value):
        """Set the x-axis range.

        :param topic: The topic name.
        :param value: The [x_min, x_max] range.
        """
        e0, e1 = self._extents()
        x0, x1 = self.x_range
        z0, z1 = value
        if z1 < z0:
            z0, z1 = z1, z0
        z0 = min(max(z0, e0), e1)
        z1 = min(max(z1, e0), e1)
        self.x_range = [z0, z1]
        self._plot_data_invalidate()
        return [topic, [x0, x1]]

    def on_action_x_zoom(self, value):
        """Perform a zoom action.

        :param value: [steps, center, {center_pixels}].
            * steps: the number of incremental steps to zoom.
            * center: the x-axis time64 center location for the zoom.
              If center is None, use the screen center.
            * center_pixels: the optional center location in screen pixels.
              When provided, double-check that the zoom operation
              maintained the center location.
        """
        steps, center = value[:2]
        if steps == 0:
            return
        self._log.info('x_zoom %s', value)
        if self.pin_left and self.pin_right:
            if steps > 0:
                # zoom in when locked to full extents
                self.pin_left = False  # unpin from left
        e0, e1 = self._extents()
        x0, x1 = self.x_range
        d_e = e1 - e0
        d_x = x1 - x0
        if d_e <= 0:
            return
        elif d_x <= 0:
            d_x = d_e
        if center is None:
            center = (x1 + x0) // 2
        center = max(x0, min(center, x1))
        f = (center - x0) / d_x
        if steps < 0:  # zoom out
            d_x = d_x * _ZOOM_FACTOR
        else:
            d_x = d_x / _ZOOM_FACTOR
        r = max(min(d_x, d_e), time64.MICROSECOND)
        z0, z1 = center - int(r * f), center + int(r * (1 - f))
        if self.pin_left or z0 < e0:
            z0, z1 = e0, int(e0 + r)
        elif self.pin_right or z1 > e1:
            z0, z1 = int(e1 - r), e1
        elif len(value) == 3:  # double check center location
            pixel = self._x_map.time64_to_counter(center)
            if abs(pixel - value[2]) >= 1.0:
                self._log.warning('center change: %s -> %s', value[2], pixel)
        self.x_range = [z0, z1]
        self._plot_data_invalidate()
        return [f'{get_topic_name(self)}/actions/!x_range', [x0, x1]]

    def on_action_x_zoom_all(self):
        """Perform a zoom action to the full extents.
        """
        self._log.info('x_zoom_all')
        x0, x1 = self.x_range
        self._plot_data_invalidate()
        self.x_range = self._extents()
        return [f'{get_topic_name(self)}/actions/!x_range', [x0, x1]]

    def on_action_x_pan(self, pan):
        self._log.info(f'on_action_x_pan {pan}')
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
        self._plot_data_invalidate()
        self.x_range = [z0, z1]
        return [f'{get_topic_name(self)}/actions/!x_range', [x0, x1]]

    def on_action_y_zoom_all(self):
        """Restore all plots to y-axis auto ranging mode."""
        self._log.info('y_zoom_all')
        has_change = False
        for plot in self.state['plots']:
            if plot['range_mode'] == 'manual':
                plot['range_mode'] = 'auto'
                has_change = True
        self._repaint_request |= has_change

    def on_action_y_range(self, topic, value):
        """Set the y-axis range.

        :param topic: The topic name.
        :param value: The [plot_idx, y_min, y_max] range entry or list of entries.
        """
        if not len(value):
            return None
        rv = []
        if isinstance(value[0], int):
            value = [value]
        for plot_idx, z0, z1 in value:
            plot = self.state['plots'][plot_idx]
            y0, y1 = plot['range']
            plot['range'] = [z0, z1]
            rv.append([plot_idx, y0, y1])
        self._repaint_request = True
        return [topic, rv]

    def on_action_y_zoom(self, value):
        """Perform a y-axis zoom action.

        :param value: [plot_idx, steps, center, {center_pixels}].
            * plot_idx: The plot index to zoom.
            * steps: the number of incremental steps to zoom.
            * center: the y-axis center location for the zoom.
              If center is None, use the screen center.
            * center_pixels: the optional center location in screen pixels.
              When provided, double-check that the zoom operation
              maintained the center location.
        """
        plot_idx, steps, center = value[:3]
        plot = self.state['plots'][plot_idx]
        self._log.info('y_zoom(%s, %r, %r)',  plot['quantity'], steps, center)
        if plot['range_mode'] == 'fixed':
            return
        if plot['range_mode'] == 'auto':
            plot['range_mode'] = 'manual'
        center = self._y_transform_fwd(plot, center)
        y_min, y_max = plot['range']
        d_y = y_max - y_min
        f = (center - y_min) / d_y
        d_y *= _ZOOM_FACTOR ** -steps
        plot['range'] = center - d_y * f, center + d_y * (1 - f)
        self._repaint_request = True
        return [f'{get_topic_name(self)}/actions/!y_range', [plot_idx, y_min, y_max]]

    def on_action_y_pan(self, value):
        """Pan the plot's y-axis.

        :param value: [plot_idx, mode, pan].
            * plot_idx: The plot index to zoom.
            * mode: 'relative' to full-scale or 'absolute'.
            * pan: The amount to pan.
        """
        plot_idx, mode, pan = value[:3]
        plot = self.state['plots'][plot_idx]
        self._log.info(f'y_pan(%sr, %r, %r)', plot['quantity'], mode, pan)
        y0, y1 = plot['range']
        if mode == 'relative':
            a = (y1 - y0) * 0.25 * pan
        else:
            a = pan
        plot['range'] = y0 + a, y1 + a
        self._repaint_request = True
        return [f'{get_topic_name(self)}/actions/!y_range', [plot_idx, y0, y1]]

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

        if y_name == 'summary':
            if is_pan:
                self.on_action_x_pan(delta)
            else:
                t = (self.x_range[0] + self.x_range[1]) / 2
                topic = get_topic_name(self)
                self.pubsub.publish(f'{topic}/actions/!x_zoom', [delta, t])
        if x_name == 'plot' and (y_name == 'x_axis' or not is_y):
            if is_pan:
                self.on_action_x_pan(delta)
            else:
                t = self._x_map.counter_to_time64(self._mouse_pos[0])
                topic = get_topic_name(self)
                self.pubsub.publish(f'{topic}/actions/!x_zoom', [delta, t, self._mouse_pos[0]])
        elif y_name.startswith('plot.') and (is_y or x_name == 'y_axis'):
            plot_idx = int(y_name.split('.')[1])
            plot = self.state['plots'][plot_idx]
            topic = get_topic_name(self)
            if is_pan:
                self.pubsub.publish(f'{topic}/actions/!y_pan', [plot_idx, 'relative', delta])
            else:
                y_pixel = self._mouse_pos[1]
                y = self._y_pixel_to_value(plot, y_pixel)
                self.pubsub.publish(f'{topic}/actions/!y_zoom', [plot_idx, delta, y, y_pixel])

    def _plot_data_invalidate(self, plot=None):
        try:
            plots = self.state['plots']
        except (AttributeError, KeyError, TypeError):
            return
        if plot is None:
            for signal in self._signals.values():
                signal['changed'] = True
            self._repaint_request = True
            return
        if not plot['enabled']:
            return
        for signal in plot['signals']:
            if not isinstance(signal, tuple):
                return  # on_pubsub_register not called yet
            if signal in self._signals:
                self._signals[signal]['changed'] = True
                self._repaint_request = True

    def on_action_plot_show(self, topic, value):
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
                    self._plot_data_invalidate(plot)
                    self.x_range = self._compute_x_range()
                    self._repaint_request = True
                return [topic, [quantity, not show]]
        self._log.warning('plot_show could not match %s', quantity)

    def on_setting_pin_left(self):
        self._plot_data_invalidate()

    def on_setting_pin_right(self):
        self._plot_data_invalidate()

    def on_setting_show_min_max(self):
        self._repaint_request = True

    def on_setting_fps(self, value):
        self._log.info('fps: period = %s ms', value)
        self._refresh_timer.start(value)

    def on_setting_summary_signal(self):
        self._plot_data_invalidate()
