# Copyright 2019-2024 Jetperch LLC
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

from PySide6 import QtWidgets, QtGui, QtCore, QtOpenGLWidgets
from OpenGL import GL as gl
from joulescope_ui import CAPABILITIES, register, N_, get_topic_name, get_instance, time64
from joulescope_ui.shortcuts import Shortcuts
from joulescope_ui.styles import styled_widget, color_as_qcolor, color_as_string, font_as_qfont
from joulescope_ui.widget_tools import CallableAction, CallableSlotAdapter, settings_action_create, context_menu_show
from joulescope_ui.exporter import TO_JLS_SIGNAL_NAME
from .quantities import X_QUANTITY_OPTIONS, PRECISION_OPTIONS, quantities_format
from .quantities import si_format as quantities_si_format
from .line_segments import PointsF
from .text_annotation import TextAnnotationDialog, SHAPES_DEF, Y_POSITION_MODE
from .waveform_control import WaveformControlWidget
from .waveform_source_widget import WaveformSourceWidget
from .interval_widget import IntervalWidget
from .y_range_widget import YRangeWidget
from joulescope_ui.time_map import TimeMap
from joulescope_ui.intel_graphics_dialog import intel_graphics_dialog
import pyjls
from collections import OrderedDict
import copy
import logging
import numpy as np
import os
import time
from PySide6.QtGui import QPen, QBrush
from joulescope_ui.units import convert_units, UNITS_SETTING, unit_prefix, prefix_to_scale
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
_JS220_AXIS_R = {0: '10 A', 1: '180 mA', 2: '18 mA', 3: '1.8 mA', 4: '180 µA', 5: '18 µA',
                 6: 'off', 7: 'off', 8: 'off'}
_JS110_AXIS_R = {0: '10 A', 1: '2 A', 2: '180 mA', 3: ' 18 mA', 4: '1.8 mA', 5: '180 µA', 6: '18 µA',
                 7: 'off', 8: 'off'}
_LOGARITHMIC_ZERO_DEFAULT = -9
_TEXT_ANNOTATION_X_POS_ALLOC = 64
_ANNOTATION_TEXT_MOD = (1 << 48)
_ANNOTATION_Y_MOD = ((1 << 16) + 2)   # must be multiple of plot colors
_MARKER_SELECT_DISTANCE_PIXELS = 5
_EXPORT_WHILE_STREAMING_START_OFFSET = time64.SECOND  # not sure of any better way...
_X_MARKER_ZOOM_LEVELS = [100, 90, 75, 50, 33, 25, 10]
_DOT_RADIUS = 3


def _analog_plot(quantity, show, units, name, integral=None, range_bounds=None):
    return {
        'quantity': quantity,
        'name': name,
        'units': units,
        'enabled': bool(show),
        'signals': [],  # list of (buffer_unique_id, signal_id)
        'height': 200,
        'range_mode': 'auto',
        'range': [-0.1, 1.1],
        'range_bounds': range_bounds,
        'scale': 'linear',
        'logarithmic_zero': _LOGARITHMIC_ZERO_DEFAULT,
        'integral': integral,
        'prefix_preferred': 'auto',
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
        'prefix_preferred': 'auto',
    }


_STATE_DEFAULT = {
    'plots': [
        _analog_plot('i', True, 'A', N_('Current'), 'C', range_bounds=[-50, 50]),
        _analog_plot('v', True, 'V', N_('Voltage'), range_bounds=[-250, 250]),
        _analog_plot('p', False, 'W', N_('Power'), 'J', range_bounds=[-1000, 1000]),
        {
                'quantity': 'r',
                'name': N_('Current range'),
                'units': None,
                'enabled': False,
                'signals': [],  # list of (buffer_unique_id, signal_id)
                'height': 100,
                'range_mode': 'manual',
                'range': [-0.5, 7.25],
                'range_bounds': [-0.5, 8.25],
                'scale': 'linear',
        },
        _digital_plot('0', N_('General purpose input 0')),
        _digital_plot('1', N_('General purpose input 1')),
        _digital_plot('2', N_('General purpose input 2')),
        _digital_plot('3', N_('General purpose input 3')),
        _digital_plot('T', N_('Trigger input')),
    ],
}


_QUANTITIES = [[p['quantity'], p['name']] for p in _STATE_DEFAULT['plots']]
_QUANTITIES_TO_NAME = dict([[p['quantity'], p['name']] for p in _STATE_DEFAULT['plots']])
_NAME_TO_QUANTITIES = dict([[p['name'], p['quantity']] for p in _STATE_DEFAULT['plots']])


def _si_format(value, units, prefix_preferred=None, precision=None):
    value_strs, units = quantities_si_format([value], units, prefix_preferred, precision)
    return value_strs[0] + ' ' + units


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


def _gl_get_string(string_id):
    try:
        return gl.glGetString(string_id).decode("utf-8")
    except Exception:
        return '__unknown__'


class _PlotOpenGLWidget(QtOpenGLWidgets.QOpenGLWidget):
    """The inner plot widget that simply calls back to the Waveform widget."""

    def __init__(self, parent):
        self._log = logging.getLogger(__name__ + '.plot')
        self._antialiasing = QtGui.QPainter.RenderHint.Antialiasing
        self._render_cbk = None
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def initializeGL(self) -> None:
        functions = QtGui.QOpenGLFunctions(self.context())
        functions.initializeOpenGLFunctions()
        vendor = _gl_get_string(gl.GL_VENDOR)
        self._log.info(f"""OpenGL information:
            Vendor: {vendor}
            Renderer: {_gl_get_string(gl.GL_RENDERER)}
            OpenGL Version: {_gl_get_string(gl.GL_VERSION)}
            Shader Version: {_gl_get_string(gl.GL_SHADING_LANGUAGE_VERSION)}""")
        if 'Intel' in vendor:
            intel_graphics_dialog(self)

    def paintGL(self):
        size = self.width(), self.height()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(self._antialiasing)
        painter.beginNativePainting()
        try:
            self.parent().plot_paint(painter, size)
        finally:
            painter.endNativePainting()
        painter.end()
        render_cbk, self._render_cbk = self._render_cbk, None
        if callable(render_cbk):
            render_cbk(self.render_to_image())

    def resizeEvent(self, event):
        self.parent().plot_resizeEvent(event)
        return super().resizeEvent(event)

    def mousePressEvent(self, event):
        self.parent().plot_mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.parent().plot_mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self.parent().plot_mouseMoveEvent(event)

    def wheelEvent(self, event):
        self.parent().plot_wheelEvent(event)

    def render_callback(self, fn):
        self._render_cbk = fn

    def render_to_image(self) -> QtGui.QImage:
        return self.grabFramebuffer()


class _PlotWidget(QtWidgets.QWidget):
    """The inner plot widget that simply calls back to the Waveform widget."""

    def __init__(self, parent):
        self._log = logging.getLogger(__name__ + '.plot')
        self._render_cbk = None
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def paintEvent(self, ev):
        size = self.width(), self.height()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.parent().plot_paint(painter, size)
        painter.end()
        render_cbk, self._render_cbk = self._render_cbk, None
        if callable(render_cbk):
            render_cbk(self.render_to_image())

    def resizeEvent(self, event):
        self.parent().plot_resizeEvent(event)
        return super().resizeEvent(event)

    def mousePressEvent(self, event):
        self.parent().plot_mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.parent().plot_mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        self.parent().plot_mouseMoveEvent(event)

    def wheelEvent(self, event):
        self.parent().plot_wheelEvent(event)

    def render_callback(self, fn):
        self._render_cbk = fn

    def render_to_image(self) -> QtGui.QImage:
        sz = self.size()
        sz = QtCore.QSize(sz.width() * 2, sz.height() * 2)
        pixmap = QtGui.QPixmap(sz)
        pixmap.setDevicePixelRatio(2)
        self.render(pixmap)
        return pixmap.toImage()


class PaintState:
    IDLE = 0
    READY = 1
    PROCESSING = 2
    WAIT = 3


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
        'close_actions': {
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
        'paint_delay': {  # prevent system starvation through repaint
            'dtype': 'int',
            'brief': N_('The minimum interval between repaint in milliseconds.'),
            'default': 4,
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
        'show_frequency': {
            'dtype': 'bool',
            'brief': N_('Show frequency for dual markers and statistics.'),
            'default': False,
        },
        'quantities': {
            'dtype': 'unique_strings',
            'brief': N_('The quantities to display by default.'),
            'default': [option[0] for option in X_QUANTITY_OPTIONS],
            'options': X_QUANTITY_OPTIONS,
        },
        'precision': {
            'dtype': 'int',
            'brief': N_('The precision to display in digits.'),
            'default': 6,
            'options': PRECISION_OPTIONS,
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
        'summary_quantity': {
            'dtype': 'str',
            'brief': N_('The signal quantity to show in the summary.'),
            'options': _QUANTITIES,
            'default': 'i',
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
        'subsources': {  # list of [f'{source}.{device}']
            'dtype': 'obj',  # automatically updated on add / remove
            'brief': N_('The available subsources.'),
            'default': [],
            'flags': ['hide', 'ro', 'skip_undo', 'tmp'],
        },
        'trace_subsources': {  # list of f'{source}.{device}' or 'default' with 4 entries
            'dtype': 'obj',  # updated by user
            'brief': N_('The selected subsources for each trace.'),
            'default': ['default', None, None, None],
            'flags': ['hide'],
        },
        'trace_priority': {
            'dtype': 'obj',  # updated by user
            'brief': N_('The trace priority: highest int value on top, None is off.'),
            'default': [0, None, None, None],
            'flags': ['hide'],
        },
    }

    def __init__(self, parent=None, **kwargs):
        """Create a new instance.

        :param parent: The QtWidget parent.
        :param source_filter: The source filter string.
        :param close_actions: List of [topic, value] actions to perform on close.
            This feature can be used to close associated sources.
        """
        self._log = logging.getLogger(__name__)
        self._kwargs = kwargs
        self._style_cache = None
        self._summary_data = None
        self._default_source = None

        super().__init__(parent)

        # manage repainting
        self.__repaint_request = False
        self._paint_state = PaintState.IDLE
        self._paint_timer = QtCore.QTimer(self)
        self._paint_timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._paint_timer.setSingleShot(True)
        self._paint_timer.timeout.connect(self._on_paint_timer)

        # Cache Qt default instances to prevent memory leak in Pyside6 6.4.2
        self._NO_PEN = QtGui.QPen(QtGui.Qt.NoPen)  # prevent memory leak
        self._NO_BRUSH = QtGui.QBrush(QtGui.Qt.NoBrush)  # prevent memory leak
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_VER = QtGui.QCursor(QtGui.Qt.SizeVerCursor)
        self._CURSOR_SIZE_HOR = QtGui.QCursor(QtGui.Qt.SizeHorCursor)
        self._CURSOR_CROSS = QtGui.QCursor(QtGui.Qt.CrossCursor)

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
        self._trace_widget = WaveformSourceWidget(self)
        self._layout.addWidget(self._trace_widget)
        self._control = WaveformControlWidget(self)
        self._layout.addWidget(self._control)

        self._x_geometry_info = {}
        self._y_geometry_info = {}
        self._mouse_action = None
        self._clipboard_image = None
        self._signals = {}      # keys of '{source}.{device}.{quantity}' like JsdrvStreamBuffer:001.JS220-001122.i
        self._signals_by_rsp_id = {}
        self._signals_rsp_id_next = 2  # reserve 1 for summary
        self._signals_data = {}
        self._points = PointsF()
        self._marker_data = {}  # rsp_id -> data,

        self._fps = {
            'start': time.time(),
            'thread_durations': [],
            'time_durations': [],
            'times': [],
            'str': [],
        }

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

    @property
    def _sources(self):
        values = {}
        for signal_id in self._signals.keys():
            values[signal_id.split('.')[0]] = True
        return list(values.keys())

    def _subsources_update(self):
        values = {}
        for signal_id in self._signals.keys():
            source, device, quantity = signal_id.split('.')
            subsource = f'{source}.{device}'
            values[subsource] = True
        subsources = sorted(values.keys())
        self.pubsub.publish(f'{self.topic}/settings/subsources', subsources)

    def _traces(self, quantity=None):
        """Get the active traces.

        :param quantity: The optional plot quantity.  When specified,
            ensure that signal_id exists.
        :return: ordered list of [trace_idx, subsource]
            The first entry has the highest priority.
            Trace_idx starts from 0.
        """
        data = []
        subsources = self.trace_subsources
        for idx, priority in enumerate(self.trace_priority):
            if priority is None:
                continue
            subsource = subsources[idx]
            if subsource == 'default':
                if self.source_filter.startswith('JsdrvStreamBuffer:001'):
                    subsource = self._default_source
                elif len(self.subsources):
                    subsource = self.subsources[0]
                else:
                    subsource = None
            if subsource is None:
                continue
            if quantity is not None:
                signal_id = f'{subsource}.{quantity}'
                if signal_id not in self._signals:
                    continue
            data.append([priority, idx, subsource])
        return [[idx, subsource] for _, idx, subsource in sorted(data, reverse=True)]

    def _on_source_list(self, sources):
        if not len(sources):
            self._log.warning('No default source available')
            return
        source_filter = self.pubsub.query(f'{self.topic}/settings/source_filter')
        src_prev = self._sources

        for source in sorted(sources):
            if source_filter and not source.startswith(source_filter):
                continue
            if source in src_prev:
                continue
            topic = get_topic_name(source)
            try:
                self.pubsub.query(f'{topic}/events/signals/!add')
                self.pubsub.subscribe(f'{topic}/events/signals/!add', self._on_signal_add, ['pub'])
                self.pubsub.subscribe(f'{topic}/events/signals/!remove', self._on_signal_remove, ['pub'])
            except KeyError:
                pass
            signals = self.pubsub.enumerate(f'{topic}/settings/signals')
            for signal in sorted(signals):
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
        device, quantity = value.split('.')
        topic = get_topic_name(source)
        signal_id = f'{source}.{device}.{quantity}'
        self.pubsub.subscribe(f'{topic}/settings/signals/{value}/range',
                              self._on_signal_range, ['pub', 'retain'])
        self._repaint_request = True

    def _on_signal_remove(self, topic, value):
        self._log.info(f'_on_signal_remove({topic}, {value})')
        source = topic.split('/')[1]
        device, quantity = value.split('.')
        signal_id = f'{source}.{device}.{quantity}'
        if signal_id in self._signals:
            del self._signals[signal_id]
        self._repaint_request = True
        self._subsources_update()

    def is_signal_active(self, signal_id):  # in form '{source}.{device}.{quantity}'
        if signal_id not in self._signals:
            return False
        for _, subsource in self._traces():
            if signal_id.startswith(subsource):
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

    def _is_streaming(self):
        if not self.pubsub.query(f'registry/app/settings/signal_stream_enable'):
            return False
        source_filter = self.pubsub.query(f'{self.topic}/settings/source_filter')
        if source_filter is not None and 'JlsSource' in source_filter:
            return False
        return True

    def on_pubsub_register(self):
        self._trace_widget.on_pubsub_register(self.pubsub)
        source_filter = self._source_filter_set()
        is_device = source_filter in [None, '', 'JsdrvStreamBuffer:001']
        if self.state is None:
            self.state = copy.deepcopy(_STATE_DEFAULT)
            if not is_device:
                self.name = self._kwargs.get('name', _NAME)
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
        if 'close_actions' in self._kwargs:
            self.pubsub.publish(f'{self.topic}/settings/close_actions',
                                self._kwargs['close_actions'])
        for plot_index, plot in enumerate(self.state['plots']):
            plot['index'] = plot_index
            plot['y_region'] = f'plot.{plot_index}'
            plot.setdefault('logarithmic_zero', _LOGARITHMIC_ZERO_DEFAULT)
            plot.setdefault('prefix_preferred', 'auto')
            if 'label' not in plot:
                plot['label'] = '' if ('integral' in plot) else plot['quantity']
        self.pubsub.subscribe('registry_manager/capabilities/signal_buffer.source/list',
                              self._on_source_list, ['pub', 'retain'])
        topic = get_topic_name(self)
        self._control.on_pubsub_register(self.pubsub, topic, source_filter)
        self._shortcuts_add()
        self.pubsub.subscribe('registry/app/settings/units', self._update_on_publish, ['pub'])
        self.pubsub.subscribe('registry/app/settings/defaults/signal_buffer_source',
                              self._on_default_signal_buffer_source, ['pub', 'retain'])

        self._repaint_request = True
        self._paint_state = PaintState.READY
        self._paint_timer.start(1)

    def _update_on_publish(self):
        self._repaint_request = True

    def _on_default_signal_buffer_source(self, value):
        self._default_source = value
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

    def on_pubsub_unregister(self):
        self._shortcuts.clear()
        self._paint_timer.stop()
        self._paint_state = PaintState.IDLE

    def on_pubsub_delete(self):
        for topic, value in self.pubsub.query(f'{self.topic}/settings/close_actions', default=[]):
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
        device, quantity = topic_parts[-2].split('.')
        signal_id = f'{source}.{device}.{quantity}'
        if value == [0, 0]:  # no data
            self._log.info('_on_signal_range(%s, %s) remove', topic, value)
            self._signals.pop(signal_id, None)
            self._repaint_request = True
            self._subsources_update()
            return
        d = self._signals.get(signal_id)
        if d is None:
            self._log.info('_on_signal_range(%s, %s) add', topic, value)
            d = {
                'id': signal_id,
                'rsp_id': self._signals_rsp_id_next,
                'range': None,
            }
            self._signals[signal_id] = d
            self._signals_by_rsp_id[self._signals_rsp_id_next] = d
            self._signals_rsp_id_next += 1
            self._subsources_update()
        if value != d['range']:
            d['range'] = value
            d['changed'] = time.time()
            self._repaint_request = True
        return None

    @property
    def _repaint_request(self):
        return self.__repaint_request

    @_repaint_request.setter
    def _repaint_request(self, value):
        self.__repaint_request |= value
        if self.__repaint_request and self._paint_state == PaintState.READY:
            self._graphics.update()

    @QtCore.Slot()
    def _on_paint_timer(self):
        if self._paint_state != PaintState.WAIT:
            self._log.warning('Unexpected paint state: %s', self._paint_state)
        self._paint_state = PaintState.READY
        if self.__repaint_request:
            self._graphics.update()

    def _extents(self):
        x_min = []
        x_max = []
        for signal_id, signal in self._signals.items():
            if self.is_signal_active(signal_id):
                x_range = signal['range']
                if x_range is None or x_range[0] is None or x_range[1] is None:
                    continue
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
        _, e1 = self._extents()
        self.x_range = self._compute_x_range()
        # x0, x1 = self.x_range
        # xc = (x0 >> 1) + (x1 >> 1)
        # self._log.info(f'request x_range({x0}, {x1}) {xc} {time64.as_datetime(xc)}')
        changed = False

        # Get the signal for the summary waveform
        traces = self._traces(self.summary_quantity)
        if len(traces):
            signal_id = f'{traces[0][1]}.{self.summary_quantity}'
            summary_signal = self._signals.get(signal_id, None)
            if summary_signal is not None and summary_signal.get('changed', False):
                summary_length = self._summary_geometry()[2]  # width in pixels
                self._request_signal(summary_signal, self._extents(), rsp_id=1, length=summary_length)

        for signal_id, signal in self._signals.items():
            if not self.is_signal_active(signal_id):
                continue
            if force or signal.get('changed', None):
                signal['changed'] = None
                self._request_signal(signal, self.x_range)
                changed = True
        if self.state is not None:
            for m in self.annotations['x'].values():
                if m.get('mode', 'absolute') == 'relative':
                    for k in range(1, 2 if m['dtype'] == 'single' else 3):
                        m_pos = e1 + m[f'rel{k}']
                        if m[f'pos{k}'] != m_pos:
                            m['changed'] = True
                        m[f'pos_next{k}'] = m_pos

                if m.get('changed', True) or changed:
                    m['changed'] = False
                    self._request_marker_data(m)

    def _request_marker_data(self, marker):
        if marker['dtype'] != 'dual':
            return
        marker_id = marker['id']
        traces = self._traces()  # list of [idx, subsource]
        if not traces:
            return
        for plot in self.state['plots']:
            if not plot['enabled']:
                continue
            quantity = plot['quantity']
            signal_id = f'{traces[0][1]}.{quantity}'
            if signal_id not in self._signals:
                continue
            rsp_id = _marker_to_rsp_id(marker_id, plot['index'])
            if marker.get('mode', 'absolute') == 'relative':
                x0, x1 = marker['pos_next1'], marker['pos_next2']
            else:
                x0, x1 = marker['pos1'], marker['pos2']
            if x0 > x1:
                x0, x1 = x1, x0
            self._request_signal(signal_id, (x0, x1), rsp_id=rsp_id, length=1)

    def _request_signal(self, signal, x_range, rsp_id=None, length=None):
        if isinstance(signal, str):
            signal = self._signals[signal]
        source, subsignal_id = signal['id'].split('.', 1)
        topic_req = f'registry/{source}/actions/!request'
        topic_rsp = f'{get_topic_name(self)}/callbacks/!response'
        if length is None:
            x_info = self._x_geometry_info.get('plot')
            if x_info is None:
                return
            length = x_info[0]
        if length > 0:
            req = {
                'signal_id': subsignal_id,
                'time_type': 'utc',
                'rsp_topic': topic_rsp,
                'rsp_id': signal['rsp_id'] if rsp_id is None else rsp_id,
                'start': x_range[0],
                'end': x_range[1],
                'length': length,
            }
            self.pubsub.publish(topic_req, req, defer=True)

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
            if data_type in ['f32', 'f64', 'u8', 'u16', 'u32', 'u64', 'i8', 'i16', 'i32', 'i64']:
                pass
            elif data_type == 'u1':
                y = np.unpackbits(y, bitorder='little')[:len(x)]
            elif data_type in ['u4', 'i4']:
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
            if signal['id'] not in self._signals_data:
                self._signals_data[signal['id']] = {}
            self._signals_data[signal['id']]['data'] = data

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
        if 'y_map' not in plot:
            return 0
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
        statistics_value_size = 0
        statistics_unit_size = axis_font_metrics.boundingRect('mWh').width()

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

            'plot_trace_pen': [
                QPen(color_as_qcolor(trace1, alpha=trace_alpha)),
                QPen(color_as_qcolor(trace2, alpha=trace_alpha)),
                QPen(color_as_qcolor(trace3, alpha=trace_alpha)),
                QPen(color_as_qcolor(trace4, alpha=trace_alpha)),
            ],
            'plot_trace_brush': [
                QBrush(color_as_qcolor(trace1, alpha=trace_alpha)),
                QBrush(color_as_qcolor(trace2, alpha=trace_alpha)),
                QBrush(color_as_qcolor(trace3, alpha=trace_alpha)),
                QBrush(color_as_qcolor(trace4, alpha=trace_alpha)),
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
            'y_tick_size': y_tick_size,
            'y_tick_height_pixels_min': 1.5 * y_tick_size.height(),
            'utc_width_pixels': axis_font_metrics.boundingRect('8888-88-88W88:88:88.888888').width(),
            'x_tick_width_pixels_min': axis_font_metrics.boundingRect('888.888888').width(),

            'statistics_name_size': statistics_name_size,
            'statistics_value_size': statistics_value_size,
            'statistics_unit_size': statistics_unit_size,
            'statistics_size': 0,
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
        self._invalidate_geometry()
        return self._style_cache

    def on_setting_trace_width(self, value):
        if self._style_cache is not None:
            for trace in self._style_cache['plot_trace_pen']:
                trace.setWidth(value)
            self._repaint_request = True

    def _plot_range_auto_update(self, plot):
        if plot['range_mode'] != 'auto':
            return
        y_min = []
        y_max = []
        for _, subsource in self._traces():
            signal_id = f'{subsource}.{plot["quantity"]}'
            d = self._signals.get(signal_id)
            if d is None:
                continue
            sig_d = self._signals_data.get(signal_id)
            if sig_d is None:
                continue
            d = sig_d['data']
            finite_idx = self._finite_idx(d)

            if 0 == self.show_min_max:
                sy_min = d['avg']
                sy_max = d['avg']
            else:
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
        dy1 = y_max - y_min
        dy2 = abs(r[1] - r[0])
        if dy1 <= 1e-9:
            if plot['quantity'] == 'r':
                f = 0.25
            else:
                f = y_min * 1e-6 + 1e-9  # Bound to work with 32-bit floating point
        elif y_min >= r[0] and y_max <= r[1] and dy1 / (dy2 + 1e-15) > _AUTO_RANGE_FRACT:
            return
        else:
            f = (dy1 * 0.1) / 2
        plot['range'] = y_min - f, y_max + f

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
        if self._paint_state != PaintState.READY:
            return
        self._paint_state = PaintState.PROCESSING
        t_time_start = time.time_ns()
        try:
            self._plot_paint(p, size)
        except Exception:
            self._log.exception('Exception during drawing')

        self._request_data()

        t_time_end = time.time_ns()
        t_duration_ms = np.ceil(1e-6 * (t_time_end - t_time_start) + 0.5)
        self._paint_state = PaintState.WAIT
        wait = max(self.paint_delay, int(self.fps - t_duration_ms))
        self._paint_timer.start(wait)

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
        axis_font_metrics = s['axis_font_metrics']
        plot_labels = [plot.get('label', '') for plot in self.state['plots']] + ['WW']
        left_width = max([axis_font_metrics.boundingRect(label).width() for label in plot_labels])
        left_width += margin + s['y_tick_size'].width() + margin
        if self.show_statistics:
            right_width = s['statistics_size']
        else:
            right_width = 0
        plot_width = widget_w - left_width - right_width - 2 * margin
        y_inner_spacing = _Y_INNER_SPACING

        y_geometry = [
            [margin, 'margin.top'],
            [50, 'summary'],
            [y_inner_spacing, 'spacer.ignore.summary'],
            [3 * axis_font_metrics.height() + 3 * margin, 'x_axis'],
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

    def _invalidate_geometry(self):
        if self._style_cache is None:
            return
        s = self._style
        axis_font_metrics = s['axis_font_metrics']
        s['statistics_value_size'] = axis_font_metrics.boundingRect('+x.' + ('8' * self.precision)).width()
        s['statistics_size'] = (_MARGIN * 2 + s['statistics_name_size'] +
                                s['statistics_value_size'] + s['statistics_unit_size'])

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

        resize = not len(self._y_geometry_info)
        self._compute_geometry(size)
        if resize:
            self._plots_height_adjust()
        self._draw_background(p, size)
        self._draw_summary(p)
        if not self._draw_x_axis(p):
            return  # plot is not valid
        self.__repaint_request = False
        self._annotations_remove_expired()
        self._draw_update_markers()
        self._draw_markers_background(p)

        # Draw each plot
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
        overscan = 0.05
        if y_min >= y_max:
            y_margin = 1e-3
            y_top = y_max + y_margin
            y_gain = h / (2 * y_margin)
        else:
            y_p2p = y_max - y_min
            y_ovr = (1 + 2 * overscan) * y_p2p
            y_top = y_max + y_p2p * overscan
            y_gain = h / y_ovr

        quantity = self.summary_quantity
        traces = self._traces(quantity)
        if len(traces):
            trace_idx, subsource = traces[0]
            pen = s['plot_trace_pen'][trace_idx]
            brush = s[f'plot_min_max_fill_brush'][trace_idx]
        else:
            pen = s['summary_trace']
            brush = s['summary_min_max_fill']

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
                p.setBrush(brush)
                p.drawPolygon(segs)
            d_y = y_value_to_pixel(d_avg)
            segs = self._points.set_line(d_x_segment, d_y)
            p.setPen(pen)
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

        label_h = s['axis_font_metrics'].height()
        label_a = s['axis_font_metrics'].ascent()
        y = x_axis_y0 + 3 * label_h + 3 * self._margin
        # y0_text = y - 3 * label_h - 2 * self._margin + label_a
        y1_text = y - 2 * label_h - self._margin + label_a
        y2_text = y - 1 * label_h + label_a

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

        if self.show_statistics:
            x_stats = self._x_geometry_info['statistics'][1]
            dt_str = _si_format(x_duration_s, 's', precision=self.precision)
            p.drawText(x_stats + _MARGIN, y2_text, f'Δt={dt_str[1:]}')
            if x_duration_s > 0 and self.show_frequency:
                f_str = _si_format(1.0 / x_duration_s, 'Hz', precision=self.precision)
                p.drawText(x_stats + _MARGIN, y1_text, f'F={f_str[1:]}')

        if x_grid is None:
            pass
        else:
            p.drawText(left_x0, y1_text, x_grid['offset_str'])
            p.drawText(left_x0, y2_text, x_grid['units'])
            for idx, x in enumerate(self._x_map.trel_to_counter(x_grid['major'])):
                p.setPen(s['text_pen'])
                x_str = x_grid['labels'][idx]
                x_start = x + _MARGIN
                x_end = x_start + font_metrics.boundingRect(x_str).width() + _MARGIN
                if x_end <= plot_x1:
                    p.drawText(x_start, y2_text, x_str)
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
        quantity = plot['quantity']
        traces = self._traces(quantity)
        if not len(traces):
            return
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
        p.setFont(s['axis_font'])
        major_max = h / s['y_tick_height_pixels_min']
        if plot['scale'] == 'logarithmic':
            y_grid = axis_ticks.ticks(y_range[0], y_range[1], 1.0, major_max=major_max,
                                      logarithmic_zero=plot['logarithmic_zero'])
        else:
            v_spacing_min = 1 if quantity == 'r' else None
            y_grid = axis_ticks.ticks(y_range[0], y_range[1], v_spacing_min, major_max=major_max,
                                      prefix_preferred=plot['prefix_preferred'])
        axis_font_metrics = s['axis_font_metrics']
        if y_grid is not None:
            if quantity == 'r':
                subsource = traces[0][1]
                if 'JS220' in subsource:
                    y_grid['labels'] = [_JS220_AXIS_R.get(int(s_label), '') for s_label in y_grid['labels']]
                elif 'JS110' in subsource:
                    y_grid['labels'] = [_JS110_AXIS_R.get(int(s_label), '') for s_label in y_grid['labels']]
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
        plot_name = plot.get('label', '')
        plot_units = plot.get('units')
        if plot_units is not None and y_grid is not None:
            plot_units = f"{y_grid['unit_prefix']}{plot_units}"
        if not plot_units:
            p.drawText(left, y0 + (h + axis_font_metrics.ascent()) // 2, plot_name)
        elif not plot_name:
            p.drawText(left, y0 + (h + axis_font_metrics.ascent()) // 2, plot_units)
        else:
            y_center = y0 + h // 2
            p.drawText(left, y_center - axis_font_metrics.ascent(), plot_name)
            p.drawText(left, y_center + axis_font_metrics.height(), plot_units)

        p.setClipRect(x0, y0, w, h)
        for trace_idx, subsource in traces[-1::-1]:
            signal_id = f'{subsource}.{quantity}'
            d = self._signals.get(signal_id)
            if d is None:
                continue
            sig_d = self._signals_data.get(signal_id)
            if sig_d is None:
                continue
            d = sig_d['data']
            d_x = self._x_map.time64_to_counter(d['x'])
            if len(d_x) == w:
                d_x, d_x2 = np.rint(d_x), d_x
                if np.any(np.abs(d_x - d_x2) > 0.5):
                    self._log.warning('x does not conform to pixels')
                    d_x = d_x2
            x_space = (d_x[-1] - d_x[0]) / (1 + len(d_x))

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
                p.setPen(s['plot_trace_pen'][trace_idx])
                p.drawPolyline(segs)
                p.setPen(self._NO_PEN)
                p.setBrush(s['plot_trace_brush'][trace_idx])
                if x_space > (3 * _DOT_RADIUS):
                    for x, y in zip(d_x_segment, d_y):
                        p.drawEllipse(QtCore.QPointF(x, y), _DOT_RADIUS, _DOT_RADIUS)
                p.setBrush(self._NO_BRUSH)

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
            t = _si_format(m['pos1'], plot['units'], precision=self.precision)

            if m['dtype'] == 'dual':
                dy = _si_format(m['pos2'] - m['pos1'], plot['units'], precision=self.precision)
                self._draw_text(p, x0 + _MARGIN, p1 + _MARGIN, t + '  Δ=' + dy)
                p.setPen(pen)
                p2 = np.rint(self._y_value_to_pixel(plot, m['pos2']))
                p.drawLine(x0, p2, x1, p2)
                p.setPen(s['text_pen'])
                t = _si_format(m['pos2'], plot['units'], precision=self.precision)
                self._draw_text(p, x0 + _MARGIN, p2 + _MARGIN, t + '  Δ=' + dy)
            else:
                self._draw_text(p, x0 + _MARGIN, p1 + _MARGIN, t)

        p.setClipping(False)

    def _draw_update_markers(self):
        for m in self.annotations['x'].values():
            if m.get('mode', 'absolute') == 'relative':
                m['pos1'] = m.get('pos_next1', m['pos1'])
                if m['dtype'] == 'dual':
                    m['pos2'] = m.get('pos_next2', m['pos2'])

    def _marker_color_index(self, m):
        return (m['id'] % 6) + 1

    def _draw_markers_background(self, p):
        s = self._style
        _, y0, _ = self._y_geometry_info['x_axis']
        _, y1, _ = self._y_geometry_info['margin.bottom']
        xw, x0, x1 = self._x_geometry_info['plot']
        font_metrics = s['axis_font_metrics']
        yh = font_metrics.height()
        ya = y0 + 2 * self._margin + yh

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
            yf = ya + yh if self.show_frequency else ya
            p.drawRect(p1, yf, pd, y1 - yf)
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
                self._log.info(f"marker remove: x_range={self.x_range} marker={self.annotations['x'][m_id]}")
                del self.annotations['x'][m_id]
        for plot_index, entry in enumerate(self.annotations['text']):
            _, outside = self._text_annotations_filter(x_range, plot_index)
            for a_id in outside:
                self._text_annotation_remove(a_id)

    def _draw_markers(self, p, size):
        s = self._style
        _, y0, _ = self._y_geometry_info['x_axis']
        _, y1, _ = self._y_geometry_info['margin.bottom']
        xw, x0, x1 = self._x_geometry_info['plot']
        font_metrics = s['axis_font_metrics']
        f_h = font_metrics.height()
        f_a = font_metrics.ascent()
        margin, margin2 = _MARGIN, _MARGIN * 2
        ya = y0 + margin2 + f_h

        for idx, m in enumerate(self.annotations['x'].values()):
            color_index = self._marker_color_index(m)
            pos1 = m['pos1']
            w = f_h // 2
            he = f_h // 3
            pen = s[f'marker{color_index}_pen']
            fg = s[f'marker{color_index}_fg']
            bg = s[f'marker{color_index}_bg']
            p.setPen(self._NO_PEN)
            p.setBrush(fg)
            p1 = np.rint(self._x_map.time64_to_counter(pos1))
            yl = y0 + f_h + he
            if m.get('flag') is None:
                m['flag'] = PointsF()
            if m['dtype'] == 'single':
                pl = p1 - w
                pr = p1 + w
                segs = self._points.set_line([pl, pl, p1, pr, pr], [y0, y0 + f_h, yl, y0 + f_h, y0])
                p.setClipRect(x0, y0, xw, y1 - y0)
                p.drawPolygon(segs)
                p.setPen(pen)
                p.drawLine(p1, y0 + f_h + he, p1, y1)
                self._draw_single_marker_text(p, m, pos1)
            else:
                p2 = np.rint(self._x_map.time64_to_counter(m['pos2']))
                if p2 < p1:
                    p1, p2 = p2, p1
                dt = abs((m['pos1'] - m['pos2']) / time64.SECOND)
                dt_str = _si_format(dt, 's', precision=self.precision)[1:]
                dt_w = font_metrics.boundingRect(dt_str).width()
                f_str, f_w = '', 0
                fill_h = f_h + margin2
                if self.show_frequency:
                    if dt > 0:
                        f_str = _si_format(1.0 / dt, 'Hz', precision=self.precision)[1:]
                        f_w = font_metrics.boundingRect(f_str).width()
                    fill_h += f_h
                    ya += f_h
                w = max(dt_w, f_w)
                p.setClipRect(x0, y0, xw, y1 - y0)
                p.setPen(pen)
                p.drawLine(p1, ya, p1, y1)
                p.drawLine(p2, ya, p2, y1)
                dt_x = (p1 + p2 - w) // 2
                q1, q2 = dt_x - margin, dt_x + w + margin
                q1, q2 = min(p1, q1), max(p2, q2)
                p.setPen(s['text_pen'])
                p.fillRect(q1, y0, q2 - q1, fill_h, p.brush())
                p.drawText(dt_x, y0 + margin + f_a, dt_str)
                if self.show_frequency and dt > 0:
                    f_x = (p1 + p2 - f_w) // 2
                    p.drawText(f_x, y0 + margin + f_a + f_h, f_str)
                txp = ['left', 'right'] if m['pos1'] < m['pos2'] else ['right', 'left']
                self._draw_dual_marker_text(p, m, 'text_pos1', txp[0])
                self._draw_dual_marker_text(p, m, 'text_pos2', txp[1])
        p.setClipping(False)

    def on_setting_precision(self):
        self._invalidate_geometry()

    def _draw_statistics_text(self, p: QtGui.QPainter, pos, values, text_pos=None, text_pos_auto_default=None):
        """Draw statistics text.

        :param p: The QPainter.
        :param pos: The (x, y) position for the text corner in pixels.
        :param values: The iterable of (name, value, units).
        :param text_pos: The text position which is one of [auto, right, left, off].
            None (default) is equivalent to auto.
        """
        if not len(values):
            return
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
        xl = x0 - _MARGIN - r_w
        xr = x0 + _MARGIN + r_w

        if text_pos == 'auto':
            if text_pos_auto_default is None:
                text_pos_auto_default = 'right'
            z0, z1 = np.rint(self._x_map.time64_to_counter(self.x_range))
            if xl < z0:
                text_pos = 'right'
            elif xr > z1:
                text_pos = 'left'
            else:
                text_pos = text_pos_auto_default

        if text_pos == 'left':
            x1 = xl
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
        traces = self._traces()
        if not len(traces):
            return
        text_pos = m.get('text_pos1', 'auto')
        if text_pos == 'off':
            return
        p0 = np.rint(self._x_map.time64_to_counter(x))
        xp = self._x_map.counter_to_time64(p0)
        xw, x0, _ = self._x_geometry_info['plot']
        for plot in self.state['plots']:
            if not plot['enabled']:
                continue
            quantity = plot['quantity']
            signal_id = f'{traces[0][1]}.{quantity}'
            d_sig = self._signals_data.get(signal_id)
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

            units, prefix_preferred = plot['units'], plot['prefix_preferred']
            if d['std'] is not None:
                v_std, v_min, v_max = d['std'][idx], d['min'][idx], d['max'][idx]
                v_rms = np.sqrt(v_avg * v_avg + v_std * v_std)
                values = {
                    'avg': (v_avg, units),
                    'std': (v_std, units),
                    'rms': (v_rms, units),
                    'min': (v_min, units),
                    'max': (v_max, units),
                    'p2p': (v_max - v_min, units),
                }
            else:
                values = {
                    'avg': (v_avg, units),
                }

            quantities = m.get('quantities', self.quantities)
            precision = self.precision
            text = quantities_format(quantities, values, prefix_preferred=prefix_preferred, precision=precision)
            self._draw_statistics_text(p, (p0, y0), text, text_pos)
        p.setClipping(False)

    def _draw_dual_marker_text(self, p, m, text_pos_key, text_pos_auto_default):
        text_pos_default = 'off' if text_pos_key == 'text_pos1' else 'auto'
        text_pos = m.get(text_pos_key, text_pos_default)
        if text_pos == 'off':
            return
        marker_id = m['id']
        xw, x0, _ = self._x_geometry_info['plot']
        for plot in self.state['plots']:
            if not plot['enabled']:
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
            units, prefix_preferred = plot['units'], plot['prefix_preferred']
            if data['std'] is None:
                values = {'avg': (v_avg, units)}
            else:
                v_std = float(data['std'][0])
                v_min = float(data['min'][0])
                v_max = float(data['max'][0])
                values = {
                    'avg': (v_avg, units),
                    'std': (v_std, units),
                    'rms': (np.sqrt(v_avg * v_avg + v_std * v_std), units),
                    'min': (v_min, units),
                    'max': (v_max, units),
                    'p2p': (v_max - v_min, units),
                }
                integral_units = plot.get('integral')
                if integral_units is not None:
                    integral_v, integral_units = convert_units(v_avg * dt, integral_units, self.units)
                    values['integral'] = (integral_v, integral_units)

            quantities = m.get('quantities', self.quantities)
            precision = self.precision
            text = quantities_format(quantities, values, prefix_preferred=prefix_preferred, precision=precision)
            pos_field = text_pos_key.split('_')[-1]
            p0 = np.rint(self._x_map.time64_to_counter(m[pos_field]))
            self._draw_statistics_text(p, (p0, y0), text, text_pos, text_pos_auto_default=text_pos_auto_default)
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
        traces = self._traces()
        if not len(traces):
            return None, None
        try:
            if isinstance(plot, str):
                plot_idx = int(plot.split('.')[1])
                plot = self.state['plots'][plot_idx]
            quantity = plot['quantity']
            signal_id = f'{traces[0][1]}.{quantity}'
            data = self._signals_data.get(signal_id)
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
        x_rel = data['x'][index]
        x_pixels = self._x_map.time64_to_counter(x_rel)
        y = data['avg'][index]
        if not np.isfinite(y):
            return
        y_pixels = int(np.rint(self._y_value_to_pixel(plot, y)))

        s = self._style
        p.setPen(self._NO_PEN)
        p.setBrush(s['waveform.hover'])
        p.drawEllipse(QtCore.QPointF(x_pixels, y_pixels), _DOT_RADIUS, _DOT_RADIUS)

        p.setFont(s['axis_font'])
        x_txt = _si_format(x_rel, 's', precision=self.precision)
        y_txt = _si_format(y, plot['units'], precision=self.precision)
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
        x_pixels += _DOT_RADIUS
        if x_pixels + w > x1:
            # show on left side
            x_pixels -= 2 * _DOT_RADIUS + w
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

        units, prefix_preferred = plot['units'], plot['prefix_preferred']
        values = {
            'avg': (y_avg, units),
            'std': (y_std, units),
            'rms': (y_rms, units),
            'min': (y_min, units),
            'max': (y_max, units),
            'p2p': (y_max - y_min, units),
        }
        dt = (z1 - z0) / time64.SECOND
        integral_units = plot.get('integral')
        if integral_units is not None:
            integral_v, integral_units = convert_units(y_avg * dt, integral_units, self.units)
            values['integral'] = (integral_v, integral_units)

        quantities = self.quantities
        precision = self.precision
        text = quantities_format(quantities, values, prefix_preferred=prefix_preferred, precision=precision)
        p.setClipRect(x0, y0, xd, yd)
        self._draw_statistics_text(p, (x0, y0), text)
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
            x, y = pos.position().x(), pos.position().y()
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

    def _find_x_marker_banner(self, x):
        for m in reversed(self.annotations['x'].values()):
            if m['dtype'] != 'dual':
                continue
            x0, x1 = self._x_map.time64_to_counter(m['pos1']), self._x_map.time64_to_counter(m['pos2'])
            if x0 > x1:
                x0, x1 = x1, x0
            if x0 <= x <= x1:
                return f'x_marker.{m["id"]}.pos1'
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
        x, y = event.position().x(), event.position().y()
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
                e1 = self._extents()[1]
                xr = self.x_range
                xt = max(xr[0], min(xt, xr[1]))  # bound to range
                item, x_offset, move_both = self._mouse_action[1:4]
                m, m_field = self._item_parse_x_marker(item)
                m['changed'] = True
                xd = xt - x_offset - m[m_field]
                m[m_field] += xd
                is_relative = m.get('mode', 'absolute') == 'relative'
                if m['dtype'] == 'dual' and move_both:
                    m_field2 = 'pos1' if m_field == 'pos2' else 'pos2'
                    m[m_field2] += xd
                    if m[m_field2] < xr[0]:
                        dx = xr[0] - m[m_field2]
                    elif m[m_field2] > xr[1]:
                        dx = xr[1] - m[m_field2]
                    else:
                        dx = 0
                    m[m_field] += dx
                    m[m_field2] += dx
                    if is_relative:
                        m['rel' + m_field2[-1]] = m[m_field2] - e1
                if is_relative:
                    m['rel' + m_field[-1]] = m[m_field] - e1
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
        self._repaint_request = True

    def _x_marker_move_start(self, item, x, move_both):
        xt = self._x_map.counter_to_time64(x)
        m, pos = self._item_parse_x_marker(item, activate=True)
        x0 = m[pos]
        x_offset = xt - x0
        self._mouse_action = ['move.x_marker', item, x_offset, move_both]

    def plot_mousePressEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x, y = event.position().x(), event.position().y()
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
                    self._x_marker_move_start(item, x, is_ctrl)
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
            elif y_name == 'x_axis' and x_name == 'plot':
                y0 = self._y_geometry_info['x_axis'][1]
                y1 = y0 + self._style['axis_font_metrics'].ascent() + _MARGIN * 2
                if y0 <= y <= y1:
                    item = self._find_x_marker_banner(x)
                    if item:
                        self._x_marker_move_start(item, x, True)
                        return
                if self.pin_left or self.pin_right:
                    pass  # pinned to extents, cannot pan
                else:
                    self._log.info('x_pan start')
                    self._mouse_action = ['x_pan', x]
            elif not is_ctrl and y_name.startswith('plot.') and x_name == 'plot':
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

    def _render_to_image(self, cbk) -> QtGui.QImage:
        return self._graphics.render_callback(cbk)
        self._repaint_request = True

    def _action_copy_image_to_clipboard(self, checked=False):
        def on_image(img: QtGui.QImage):
            self._clipboard_image = img
            QtWidgets.QApplication.clipboard().setImage(self._clipboard_image)
        self._render_to_image(on_image)

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
                def on_image(img: QtGui.QImage):
                    if not img.save(filename):
                        self._log.warning('Could not save image: %s', filename)
                self._render_to_image(on_image)
            else:
                self._log.info('finished: accept - but no file selected, ignore')
        else:
            self._log.info('finished: reject - abort recording')
        self._dialog.close()
        self._dialog = None

    def _action_save_image(self, checked=False):
        filter_str = 'png (*.png)'
        filename = time64.filename('.png')
        path = self.pubsub.query('registry/paths/settings/path')
        path = os.path.join(path, filename)
        dialog = QtWidgets.QFileDialog(self, N_('Save image to file'), path, filter_str)
        dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dialog.finished.connect(self._action_save_image_dialog_finish)
        self._dialog = dialog
        dialog.show()

    def plot_mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x, y = event.position().x(), event.position().y()
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

    def _on_menu_x_marker(self, action):
        pos = self._x_map.counter_to_time64(self._mouse_pos[0])
        topic = get_topic_name(self)
        self.pubsub.publish(f'{topic}/actions/!x_markers', [action, pos, None])

    @QtCore.Slot()
    def _on_menu_x_marker_add_single(self):
        self._on_menu_x_marker('add_single')

    @QtCore.Slot()
    def _on_menu_x_marker_add_dual(self):
        self._on_menu_x_marker('add_dual')

    @QtCore.Slot()
    def _on_menu_x_marker_clear_all(self):
        self._on_menu_x_marker('clear_all')

    def _menu_add_x_annotations(self, menu: QtWidgets.QMenu):
        menu.addAction(N_('Single marker'), self._on_menu_x_marker_add_single)
        menu.addAction(N_('Dual markers'), self._on_menu_x_marker_add_dual)

        mode = menu.addMenu(N_('Mode'))
        mode_group = QtGui.QActionGroup(mode)
        mode_group.setExclusive(True)
        mode_absolute = QtGui.QAction(N_('Absolute'), mode_group, checkable=True)
        mode_absolute.setChecked(self.x_axis_annotation_mode == 'absolute')  # todo
        mode.addAction(mode_absolute)
        mode_absolute.triggered.connect(self._on_menu_x_mode_absolute)

        mode_relative = QtGui.QAction(N_('Relative'), mode_group, checkable=True)
        mode_relative.setChecked(self.x_axis_annotation_mode == 'relative')
        mode.addAction(mode_relative)
        mode_relative.triggered.connect(self._on_menu_x_mode_relative)

        menu.addAction(N_('Clear all'), self._on_menu_x_marker_clear_all)

    def _on_menu_x_mode_absolute(self):
        self.x_axis_annotation_mode = 'absolute'

    def _on_menu_x_mode_relative(self):
        self.x_axis_annotation_mode = 'relative'

    def _menu_x_axis(self, event: QtGui.QMouseEvent):
        self._log.info('_menu_x_axis(%s)', event.position())
        menu = QtWidgets.QMenu('Waveform x-axis context menu', self)
        annotations = menu.addMenu(N_('Annotations'))
        self._menu_add_x_annotations(annotations)
        settings_action_create(self, menu)
        context_menu_show(menu, event)

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

    @QtCore.Slot()
    def _on_menu_y_marker_add_single(self):
        self._on_menu_y_marker('add_single')

    @QtCore.Slot()
    def _on_menu_y_marker_add_dual(self):
        self._on_menu_y_marker('add_dual')

    @QtCore.Slot()
    def _on_menu_y_marker_clear_all(self):
        self._on_menu_y_marker('clear_all')

    def _menu_add_y_annotations(self, menu: QtWidgets.QMenu):
        menu.addAction(N_('Single marker'), self._on_menu_y_marker_add_single)
        menu.addAction(N_('Dual markers'), self._on_menu_y_marker_add_dual)
        menu.addAction(N_('Clear all'), self._on_menu_y_marker_clear_all)

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

    def _on_menu_y_prefix_preferred(self, idx, value):
        plot = self.state['plots'][idx]
        if value != plot['prefix_preferred']:
            plot['prefix_preferred'] = value
            self._repaint_request = True

    def _on_menu_y_range_mode(self, idx, value):
        plot = self.state['plots'][idx]
        plot['range_mode'] = value
        self._repaint_request = True

    def _on_menu_y_range_exact(self, idx, y_range, range_mode_manual=None):
        if range_mode_manual is not None:
            range_mode_manual.setChecked(True)
        plot = self.state['plots'][idx]
        plot['range_mode'] = 'manual'
        plot['range'] = y_range
        self._repaint_request = True

    def _on_plot_label_set(self, idx, txt):
        plot = self.state['plots'][idx]
        plot['label'] = txt
        self._repaint_request = True

    def _menu_y_axis(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_y_axis(%s, %s)', idx, event.position())
        menu = QtWidgets.QMenu('Waveform y-axis context menu', self)
        plot = self.state['plots'][idx]
        annotations = menu.addMenu(N_('Annotations'))
        self._menu_add_y_annotations(annotations)
        if plot['range_mode'] != 'fixed':
            range_mode = menu.addMenu(N_('Range'))
            range_group = QtGui.QActionGroup(range_mode)
            range_group.setExclusive(True)

            CallableAction(range_group, N_('Auto'),
                           lambda: self._on_menu_y_range_mode(idx, 'auto'),
                           checkable=True, checked=(plot['range_mode'] == 'auto'))
            range_mode_manual = CallableAction(range_group, N_('Manual'),
                                               lambda: self._on_menu_y_range_mode(idx, 'manual'),
                                               checkable=True, checked=(plot['range_mode'] == 'manual'))
            range_mode_exact_menu = range_mode.addMenu(N_('Exact'))
            range_widget = YRangeWidget(range_mode_exact_menu, plot['range'], plot['units'],
                                        fn=lambda y_range: self._on_menu_y_range_exact(idx, y_range, range_mode_manual))
            range_action = QtWidgets.QWidgetAction(range_mode_exact_menu)
            range_action.setDefaultWidget(range_widget)
            range_mode_exact_menu.addAction(range_action)

        if plot['quantity'] in ['i', 'p']:
            scale = plot['scale']
            scale_mode = menu.addMenu(N_('Scale'))
            scale_group = QtGui.QActionGroup(scale_mode)
            scale_group.setExclusive(True)
            scale_mode_auto = CallableAction(scale_group, N_('Linear'),
                                             lambda: self._on_menu_y_scale_mode(idx, 'linear'),
                                             checkable=True)
            scale_mode_auto.setChecked(scale == 'linear')
            scale_mode.addAction(scale_mode_auto)
            scale_mode_manual = CallableAction(scale_group, N_('Logarithmic'),
                                               lambda: self._on_menu_y_scale_mode(idx, 'logarithmic'),
                                               checkable=True)
            scale_mode_manual.setChecked(scale == 'logarithmic')
            scale_mode.addAction(scale_mode_manual)

            if scale == 'logarithmic':
                z = plot['logarithmic_zero']
                logarithmic_zero = menu.addMenu(N_('Logarithmic zero'))
                logarithmic_group = QtGui.QActionGroup(logarithmic_zero)
                logarithmic_group.setExclusive(True)

                def logarithm_action_gen(value):
                    CallableAction(logarithmic_group, f'{value:d}',
                                   lambda: self._on_menu_y_logarithmic_zero(idx, value),
                                   checkable=True, checked=(value==z))

                for log_power in range(1, -10, -1):
                    logarithm_action_gen(log_power)

        if plot['quantity'] in ['i', 'v', 'p'] and plot['scale'] != 'logarithmic':
            prefix_preferred = plot['prefix_preferred']
            prefix_menu = menu.addMenu(N_('Preferred prefix'))
            prefix_group = QtGui.QActionGroup(prefix_menu)
            prefix_group.setExclusive(True)

            def prefix_action_gen(value):
                CallableAction(prefix_group, value,
                               lambda: self._on_menu_y_prefix_preferred(idx, value),
                               checkable=True, checked=(value == prefix_preferred))

            for prefix in ['auto', '', 'm', 'µ', 'n']:
                prefix_action_gen(prefix)

        name_menu = menu.addMenu(N_('Name'))
        name_edit = QtWidgets.QLineEdit(plot.get('label', ''))
        name_slot = CallableSlotAdapter(name_edit, lambda: self._on_plot_label_set(idx, name_edit.text()))
        name_edit.textChanged.connect(name_slot.slot)
        name_action = QtWidgets.QWidgetAction(name_menu)
        name_action.setDefaultWidget(name_edit)
        name_menu.addAction(name_action)

        settings_action_create(self, menu)
        return context_menu_show(menu, event)

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

    def _on_menu_annotations_save(self, checked=False):
        for source in self._sources:
            if source.startswith('JlsSource'):
                path = self.pubsub.query(f'{get_topic_name(source)}/settings/path')
                path_base, path_ext = os.path.splitext(path)
                anno_path = f'{path_base}.anno{path_ext}'
                self.on_callback_annotation_save({'path': anno_path})

    def _on_menu_annotations_clear_all(self, checked=False):
        self._on_menu_x_marker('clear_all')
        self._on_menu_y_marker('clear_all')
        self._on_menu_text_annotation('clear_all')

    def _menu_add_text_annotations(self, menu: QtWidgets.QMenu):
        CallableAction(menu, N_('Add'), lambda: self._on_menu_text_annotation('add'))
        CallableAction(menu, N_('Hide all text'), lambda: self._on_menu_text_annotation('text_hide_all'))
        CallableAction(menu, N_('Show all text'), lambda: self._on_menu_text_annotation('text_show_all'))
        CallableAction(menu, N_('Clear all'), lambda: self._on_menu_text_annotation('clear_all'))

    def _menu_plot(self, idx, event: QtGui.QMouseEvent):
        self._log.info('_menu_plot(%s, %s)', idx, event.position())
        plot = self.state['plots'][idx]
        menu = QtWidgets.QMenu('Waveform context menu', self)
        annotations = menu.addMenu(N_('Annotations'))
        anno_x = annotations.addMenu(N_('Vertical'))
        self._menu_add_x_annotations(anno_x)

        anno_y = annotations.addMenu(N_('Horizontal'))
        self._menu_add_y_annotations(anno_y)
        anno_text = annotations.addMenu(N_('Text'))
        self._menu_add_text_annotations(anno_text)
        for source in self._sources:
            if source.startswith('JlsSource'):
                annotations.addAction(N_('Save'), self._on_menu_annotations_save)
                break
        annotations.addAction(N_('Clear all'), self._on_menu_annotations_clear_all)

        if plot['range_mode'] == 'manual':
            CallableAction(menu, N_('Y-axis auto range'),
                           lambda: self._on_menu_y_range_mode(idx, 'auto'))

        menu.addAction(N_('Save image to file'), self._action_save_image)
        menu.addAction(N_('Copy image to clipboard'), self._action_copy_image_to_clipboard)
        CallableAction(menu, N_('Export visible data'), lambda: self._on_x_export('range'))
        CallableAction(menu, N_('Export all data'), lambda: self._on_x_export('extents'))
        settings_action_create(self, menu)
        return context_menu_show(menu, event)

    def _menu_dt(self, event: QtGui.QMouseEvent):
        self._log.info('_menu_dt(%s)', event.position())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        x0, x1 = self.x_range
        interval = abs(x1 - x0) / time64.SECOND
        interval_widget = IntervalWidget(self, interval)
        interval_widget.value.connect(self._on_dt_interval)
        interval_action = QtWidgets.QWidgetAction(menu)
        interval_action.setDefaultWidget(interval_widget)
        menu.addAction(interval_action)
        return context_menu_show(menu, event)

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
        self._log.info('_menu_statistics(%s, %s)', idx, event.position())
        menu = QtWidgets.QMenu('Waveform context menu', self)
        settings_action_create(self, menu)
        return context_menu_show(menu, event)

    def _on_x_marker_statistics_show(self, marker, text_pos_key, pos):
        marker[text_pos_key] = pos
        self._repaint_request = True

    def _signals_get(self):
        signals = []
        for _, subsource in self._traces():
            for plot in self.state['plots']:
                if plot['enabled']:
                    quantity = plot['quantity']
                    signal_id = f'{subsource}.{quantity}'
                    if signal_id in self._signals:
                        signals.append(signal_id)
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

    def _on_x_export_range_resolve(self, src):
        if isinstance(src, int):  # marker_id
            m = self._annotation_lookup(src)
            x0, x1 = m['pos1'], m['pos2']
            if x0 > x1:
                x0, x1 = x1, x0
            return x0, x1
        elif isinstance(src, str):
            e0, e1 = self._extents()
            if src == 'range':
                x0, x1 = self.x_range
            elif src == 'extents':
                x0, x1 = e0, e1
            else:
                raise ValueError(f'unsupported x_export source {src}')
            if self._is_streaming():
                self._log.info('export on streaming: enforce start buffer')
                x0 = min(max(x0, e0 + _EXPORT_WHILE_STREAMING_START_OFFSET), e1)
            return x0, x1
        else:
            raise ValueError(f'unsupported x_export source {src}')

    def _on_x_export(self, src):
        x_range = self._on_x_export_range_resolve(src)
        if self._is_streaming():
            # defer final range computation using a callable
            x_range = lambda: self._on_x_export_range_resolve(src)

        signals = self._signals_get()
        # Use CAPABILITIES.RANGE_TOOL_CLASS value format.
        self.pubsub.publish('registry/exporter/actions/!run', {
            'x_range': x_range,
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
        value = {
            'x_range': (x0, x1),
            'origin': self.unique_id,
            'signals': self._signals_get(),
        }
        y_name = self._find_item(self._mouse_pos)[-1]
        if y_name.startswith('plot.'):
            plot_idx = int(y_name.split('.')[1])
            quantity = self.state['plots'][plot_idx]['quantity']
            value['quantity'] = quantity
            traces = self._traces(quantity)
            if len(traces):
                value['signal_default'] = f'{traces[0][1]}.{quantity}'

        self.pubsub.publish(f'registry/{unique_id}/actions/!run', value)

    def _construct_analysis_menu_action(self, menu, unique_id, idx):
        cls = get_instance(unique_id)
        CallableAction(menu, cls.NAME, lambda: self._on_range_tool(unique_id, idx))

    def _on_x_marker_zoom(self, marker_idx, zoom_level):
        m = self._annotation_lookup(marker_idx)
        z0, z1 = m['pos1'], m['pos2']
        zc = (z1 + z0) / 2
        zd = abs(z1 - z0) / (2 * float(zoom_level))
        z0, z1 = int(zc - zd), int(zc + zd)
        self.pubsub.publish(f'{self.topic}/actions/!x_zoom_to', [z0, z1])

    def _construct_x_marker_zoom_menu_action(self, menu, idx, zoom_level):
        CallableAction(menu, f'{zoom_level}%', lambda: self._on_x_marker_zoom(idx, zoom_level / 100.0))

    def _on_x_interval(self, m, pos_text, interval):
        other_pos = 'pos2' if pos_text == 'pos1' else 'pos1'
        if m.get('mode', 'absolute') == 'relative':
            pos_text = 'rel' + pos_text[-1]
            other_pos = 'rel' + other_pos[-1]
        m[other_pos] = m[pos_text] + int(interval * time64.SECOND)
        m['changed'] = True
        self._repaint_request = True

    def _on_x_marker_quantities_changed(self, m, x):
        m['quantities'] = x
        self._repaint_request = True

    def _menu_x_marker_single(self, item, event: QtGui.QMouseEvent):
        m, pos_text = self._item_parse_x_marker(item)
        is_dual = m.get('dtype') == 'dual'
        pos = m.get(f'text_{pos_text}', 'auto')

        menu = QtWidgets.QMenu('Waveform x_marker context menu', self)

        if is_dual:
            CallableAction(menu, N_('Export'), lambda: self._on_x_export(m['id']))
            analysis_menu = menu.addMenu(N_('Analysis'))
            range_tools = self.pubsub.query('registry_manager/capabilities/range_tool.class/list')
            for unique_id in range_tools:
                if unique_id == 'exporter':
                    continue  # special, has own menu item
                self._construct_analysis_menu_action(analysis_menu, unique_id, m['id'])

            other_pos = 'pos2' if pos_text == 'pos1' else 'pos1'
            interval_menu = menu.addMenu(N_('Interval'))
            interval = (m[other_pos] - m[pos_text]) / time64.SECOND
            interval_widget = IntervalWidget(self, interval)
            adapter = CallableSlotAdapter(interval_widget, lambda x: self._on_x_interval(m, pos_text, x))
            interval_widget.value.connect(adapter.slot)
            interval_action = QtWidgets.QWidgetAction(interval_menu)
            interval_action.setDefaultWidget(interval_widget)
            interval_menu.addAction(interval_action)

            zoom_menu = menu.addMenu(N_('Zoom'))
            for zoom_level in _X_MARKER_ZOOM_LEVELS:
                self._construct_x_marker_zoom_menu_action(zoom_menu, m['id'], zoom_level)

        show_stats_menu = menu.addMenu(N_('Show statistics'))
        show_stats_group = QtGui.QActionGroup(show_stats_menu)
        CallableAction(show_stats_group, N_('Auto'),
                       lambda: self._on_x_marker_statistics_show(m, f'text_{pos_text}', 'auto'),
                       checkable=True, checked=(pos == 'auto'))
        CallableAction(show_stats_group, N_('Left'),
                       lambda: self._on_x_marker_statistics_show(m, f'text_{pos_text}', 'left'),
                       checkable=True, checked=(pos == 'left'))
        CallableAction(show_stats_group, N_('Right'),
                       lambda: self._on_x_marker_statistics_show(m, f'text_{pos_text}', 'right'),
                       checkable=True, checked=(pos == 'right'))
        CallableAction(show_stats_group, N_('Off'),
                       lambda: self._on_x_marker_statistics_show(m, f'text_{pos_text}', 'off'),
                       checkable=True, checked=(pos == 'off'))
        CallableAction(menu, N_('Remove'),
                       lambda: self.pubsub.publish(f'{get_topic_name(self)}/actions/!x_markers', ['remove', m['id']]))
        return context_menu_show(menu, event)

    def _menu_text_annotation_context(self, item, event):
        a = self._item_parse_text_annotation(item)
        menu = QtWidgets.QMenu('Waveform text annotation context menu', self)
        CallableAction(menu, N_('Edit'), lambda: self._on_text_annotation_edit(a['id']))
        CallableAction(menu, N_('Show text'), lambda value: self._on_text_annotation_show(a['id'], value),
                       checkable=True, checked=a['text_show'])

        y_mode = menu.addMenu(N_('Y mode'))
        y_mode_group = QtGui.QActionGroup(y_mode)

        def y_mode_item(value, name):
            CallableAction(y_mode_group, name,
                           lambda: self._on_text_annotation_y_mode(a['id'], value),
                           checkable=True, checked=(a['y_mode'] == value))
        [y_mode_item(*args) for args in Y_POSITION_MODE]

        shape = menu.addMenu(N_('Shape'))
        shape_group = QtGui.QActionGroup(shape)

        def shape_item(index, name):
            CallableAction(shape_group, name,
                           lambda: self._on_text_annotation_shape(a['id'], index),
                           checkable=True, checked=(a['shape'] == index))
        [shape_item(index, value[1]) for index, value in enumerate(SHAPES_DEF)]
        CallableAction(menu, N_('Remove'), lambda: self._on_text_annotation_remove(a['id']))
        return context_menu_show(menu, event)

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
        CallableAction(menu, N_('Remove'),
                       lambda: self.pubsub.publish(f'{get_topic_name(self)}/actions/!y_markers',
                                                   ['remove', m['plot_index'], m['id']]))
        return context_menu_show(menu, event)

    def _menu_summary_quantity(self, menu, quantity, name):
        def action():
            self.summary_quantity = quantity
        return CallableAction(menu, name, action)

    def _menu_summary(self, event: QtGui.QMouseEvent):
        self._log.info('_menu_summary(%s)', event.position())
        menu = QtWidgets.QMenu('Waveform summary context menu', self)
        signal_menu = QtWidgets.QMenu('Signal', menu)
        menu.addMenu(signal_menu)
        selected = self.summary_quantity
        for plot in self.state['plots']:
            quantity = plot['quantity']
            traces = self._traces(plot['quantity'])
            if len(traces) == 0:
                continue
            a = self._menu_summary_quantity(signal_menu, quantity=quantity, name=plot['name'])
            a.setChecked(quantity == selected)
        settings_action_create(self, menu)
        return context_menu_show(menu, event)

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
        self._log.info('x_marker_add %s', marker['id'])
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
        x0, x1 = self.x_range
        if pos1 is None:
            xc = (x1 + x0) // 2
            pos1 = self._x_marker_position(xc)
        marker = {
            'id': self._annotation_next_id('x'),
            'dtype': 'single',
            'mode': self.x_axis_annotation_mode,
            'pos1': pos1,
            'changed': True,
            'text_pos1': 'auto',
            'text_pos2': 'off',
        }
        if self.x_axis_annotation_mode == 'relative':
            marker['mode'] = 'relative'
            marker['rel1'] = pos1 - self._extents()[1]
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
            'text_pos2': 'auto',
        }
        if self.x_axis_annotation_mode == 'relative':
            e1 = self._extents()[1]
            marker['mode'] = 'relative'
            marker['rel1'] = pos1 - e1
            marker['rel2'] = pos2 - e1

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
                            if m['pos1'] <= x0 and m['pos2'] >= x1:
                                continue
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
        elif isinstance(center, float):
            raise ValueError(f'center is not int: {type(center)} {center}')
        center = int(center)
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

    def on_action_x_zoom_to(self, value):
        """Perform a zoom action to an exact region

        :param value: [x0, x1].
            * x0: The starting time.
            * x1: The ending time.
        """
        undo_x_range = list(self.x_range)
        z0, z1 = value
        e0, e1 = self._extents()
        if z0 < e0:
            z1 += e0 - z0
            z0 = e0
        if z1 > e1:
            z0 -= z1 - e1
            z1 = e1
            z0 = max(z0, e0)
        if z0 > e0:
            self.pin_left = False
        if z1 < e1:
            self.pin_right = False
        self.x_range = [z0, z1]
        self._plot_data_invalidate()
        return [f'{get_topic_name(self)}/actions/!x_range', undo_x_range]

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
        plot['range'] = [center - d_y * f, center + d_y * (1 - f)]
        b = plot.get('range_bounds', None)
        if b is not None:
            if plot['range'][0] < b[0]:
                plot['range'][1] = min(plot['range'][1] + (b[0] - plot['range'][0]), b[1])
                plot['range'][0] = b[0]
            elif plot['range'][1] > b[1]:
                plot['range'][0] = max(plot['range'][0] - (plot['range'][1] - b[1]), b[0])
                plot['range'][1] = b[1]
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
                t = (self.x_range[0] + self.x_range[1]) // 2
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
        quantity = plot['quantity']
        for _, subsource  in self._traces(quantity):
            signal_id = f'{subsource}.{quantity}'
            self._signals[signal_id]['changed'] = True
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

    def on_setting_summary_quantity(self):
        self._plot_data_invalidate()

    def on_setting_trace_subsources(self):
        self._plot_data_invalidate()

    def on_setting_trace_priority(self):
        self._plot_data_invalidate()
