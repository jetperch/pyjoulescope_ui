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

"""Measure converter efficiency with an input and an output instrument.

See docs/plans/efficiency.md.
"""

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import register, N_, get_topic_name, CAPABILITIES, time64
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.widget_tools import CallableAction, settings_action_create, context_menu_show, \
    CONTROL_LOCATION_SETTING, control_location_apply
from joulescope_ui.source_selector import SourceSelector
from joulescope_ui.widgets import plot_base
from joulescope_ui.efficiency_engine import WindowHistory
from .efficiency_control import EfficiencyControlWidget
from .efficiency_export import history_csv, curve_csv
from .efficiency_plot import TimePlot, CurvePlot
from .efficiency_readout import EfficiencyReadout
from .efficiency_worker import EfficiencyWorker
import logging
import numpy as np
import os
import time


INSTRUMENTS = ('in', 'out')
_INSTRUMENT_NAMES = {'in': N_('Input'), 'out': N_('Output')}
_SETTING = {'in': 'input_source', 'out': 'output_source'}
_CONTROL = {'in': 'input', 'out': 'output'}
_SIGNAL_NAMES = {'p': N_('power'), 'i': N_('current'), 'v': N_('voltage')}
_STATISTICS_FREQUENCY_DEFAULT = 2.0
_MISSING_TIMEOUT = 2.0      # seconds without data while the other instrument streams
_SWAP_THRESHOLD = 1.05      # efficiency that suggests swapped instruments
_SWAP_COUNT = 3             # consecutive windows above _SWAP_THRESHOLD
_SOURCE_LIST_TOPIC = f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_STREAM_SOURCE}/list'
_SOURCE_DEFAULT_TOPIC = 'registry/app/settings/defaults/signal_stream_source'


SETTINGS = {
    'input_source': {
        'dtype': 'str',
        'brief': N_('The input instrument.'),
        'default': None,
        'flags': ['hide'],
    },
    'output_source': {
        'dtype': 'str',
        'brief': N_('The output instrument.'),
        'default': None,
        'flags': ['hide'],
    },
    'hold': {
        'dtype': 'bool',
        'brief': N_('Hold the display.'),
        'default': False,
        'flags': ['hide', 'tmp', 'skip_undo'],
    },
    'show_vi': {
        'dtype': 'bool',
        'brief': N_('Show voltage and current'),
        'detail': N_("""Show the input and output voltage and current
            in the readout."""),
        'default': False,
    },
    'time_plot_enable': {
        'dtype': 'bool',
        'brief': N_('Show efficiency vs time'),
        'default': True,
    },
    'time_plot_duration': {
        'dtype': 'float',
        'brief': N_('Efficiency vs time duration'),
        'detail': N_("""The duration of the efficiency vs time history.
            Use the mouse wheel to zoom in to recent history."""),
        'default': 600.0,
        'options': [[10.0, '10 s'], [30.0, '30 s'], [60.0, '1 min'], [120.0, '2 min'],
                    [300.0, '5 min'], [600.0, '10 min'], [1800.0, '30 min'], [3600.0, '1 h']],
    },
    'curve_enable': {
        'dtype': 'bool',
        'brief': N_('Show the efficiency curve'),
        'default': True,
    },
    'curve_x': {
        'dtype': 'str',
        'brief': N_('Efficiency curve x-axis'),
        'default': 'current',
        'options': [['current', N_('Output current')], ['power', N_('Output power')]],
    },
    'curve_x_scale': {
        'dtype': 'str',
        'brief': N_('Efficiency curve x-axis scale'),
        'default': 'log',
        'options': [['log', N_('Logarithmic')], ['linear', N_('Linear')]],
    },
    'curve_bins_per_decade': {
        'dtype': 'int',
        'brief': N_('Efficiency curve bins per decade'),
        'detail': N_("""The efficiency curve groups steady windows into
            logarithmically spaced load bins.  More bins give finer load
            resolution but need more data."""),
        'default': 20,
        'options': [[5, '5'], [10, '10'], [20, '20'], [50, '50']],
    },
    'curve_window': {
        'dtype': 'float',
        'brief': N_('Efficiency curve window'),
        'detail': N_("""The duration of each efficiency curve measurement.
            Statistics uses the statistics window.  A shorter window
            captures load points from fast load sweeps, but includes
            more energy storage error from the converter capacitance."""),
        'default': 0.0,
        'options': [[0.0, N_('Statistics')], [0.01, '10 ms'], [0.02, '20 ms'], [0.05, '50 ms'],
                    [0.1, '100 ms'], [0.2, '200 ms'], [0.5, '500 ms'], [1.0, '1 s']],
    },
    'steady_threshold': {
        'dtype': 'float',
        'brief': N_('Steady load threshold'),
        'detail': N_("""The efficiency curve only includes windows where the
            input and output power vary by less than this fraction of their
            mean within the window."""),
        'default': 0.05,
        'options': [[0.01, '1%'], [0.02, '2%'], [0.05, '5%'], [0.1, '10%'], [0.2, '20%']],
    },
    'curve_min_count': {
        'dtype': 'int',
        'brief': N_('Efficiency curve minimum windows'),
        'detail': N_('Draw bins with fewer windows faded and leave them off the line.'),
        'default': 5,
        'options': [[1, '1'], [2, '2'], [5, '5'], [10, '10'], [20, '20']],
    },
    'curve_whiskers': {
        'dtype': 'bool',
        'brief': N_('Show the efficiency curve min and max'),
        'default': True,
    },
    'curve_hold': {
        'dtype': 'bool',
        'brief': N_('Hold the efficiency curve'),
        'default': False,
        'flags': ['hide', 'tmp', 'skip_undo'],
    },
    'splitter': {
        'dtype': 'obj',
        'brief': N_('The pane sizes.'),
        'default': None,
        'flags': ['hide'],
    },
    'control_location': dict(CONTROL_LOCATION_SETTING),
}


@register
@styled_widget(N_('Efficiency'))
class EfficiencyWidget(QtWidgets.QWidget):
    """Display converter efficiency from an input and an output instrument."""

    CAPABILITIES = ['widget@']
    SETTINGS = SETTINGS
    _snapshot_signal = QtCore.Signal(object)

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        self.pubsub = None
        self._style_cache = None
        self._generation = 0
        self._sources = {'in': None, 'out': None}   # resolved sources being processed
        self._data_topics = {}                      # (instrument, signal) -> topic
        self._enable_topics = []
        self._disabled = []                         # (instrument, signal) not enabled
        self._rate_topic = None
        self.period = 1.0 / _STATISTICS_FREQUENCY_DEFAULT
        self._paused = False                        # global signal_stream_enable is off
        self._rx_time = {'in': None, 'out': None}   # monotonic time of the latest data
        self._window = None                         # latest window
        self._window_valid = None                   # latest valid window
        self._snapshot = {}
        self._curve_bins = []
        self._swap_count = 0
        self.status = ''
        self.status_warning = False
        super().__init__(parent)
        for key, value in SETTINGS.items():
            setattr(self, key, value['default'])  # not registered: sets the attribute only
        self.setObjectName('efficiency_widget')
        self._callbacks = {(instrument, signal): self._data_factory(instrument, signal)
                           for instrument in INSTRUMENTS for signal in 'piv'}
        self._selectors = {}
        for instrument in INSTRUMENTS:
            selector = SourceSelector(self, 'signal_stream')
            selector.sources_changed.connect(self._on_sources_changed)
            selector.source_changed.connect(self._combos_update)  # selection, such as from undo
            selector.resolved_changed.connect(self._on_resolved_changed)
            self._selectors[instrument] = selector

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.history = WindowHistory()
        self._history_resize()
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self._splitter.setChildrenCollapsible(False)
        self._readout = EfficiencyReadout(self, self._splitter)
        self._time_plot = TimePlot(self, self._splitter)
        self._curve_plot = CurvePlot(self, self._splitter)
        self._splitter.addWidget(self._readout)
        self._splitter.addWidget(self._time_plot)
        self._splitter.addWidget(self._curve_plot)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 1)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        self._layout.addWidget(self._splitter, 1)
        self._control = EfficiencyControlWidget(self)
        self._layout.addWidget(self._control)
        self._control.value_set('hold', self.hold)

        self._worker = EfficiencyWorker(self._snapshot_signal.emit)
        self._snapshot_signal.connect(self._on_snapshot)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._status_update)

    # ---- pubsub lifecycle ----

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        for instrument in INSTRUMENTS:
            self._selectors[instrument].on_pubsub_register(
                self.pubsub, f'{topic}/settings/{_SETTING[instrument]}')
        self._worker.start()
        self._reset()
        self.pubsub.subscribe('registry/app/settings/signal_stream_enable',
                              self._on_signal_stream_enable, ['pub', 'retain'])
        self._sources_assign()
        self._connect()
        self._timer.start(500)

    def on_pubsub_unregister(self):
        self._timer.stop()
        self._worker.stop()
        self._disconnect()
        self._sources = {'in': None, 'out': None}

    def setting_publish(self, name, value):
        """Publish one of this widget's settings."""
        if self.pubsub is not None:
            self.pubsub.publish(f'{get_topic_name(self)}/settings/{name}', value)
        else:  # not registered, such as in unit tests
            setattr(self, name, value)
            getattr(self, f'on_setting_{name}', lambda v: None)(value)

    def _on_signal_stream_enable(self, value):
        # Devices keep streaming while paused; only the buffers hold.  Match them.
        self._paused = not bool(value)
        self._status_update()

    # ---- sources ----

    def source_set(self, name, value):
        """Set the 'input' or 'output' source."""
        instrument = 'in' if name == 'input' else 'out'
        self._selectors[instrument].source_set(value)

    def _source_name(self, source):
        if self.pubsub is None or source is None:
            return str(source)
        return self.pubsub.query(f'{get_topic_name(source)}/settings/name', default=source)

    def _source_model(self, source):
        info = self.pubsub.query(f'{get_topic_name(source)}/settings/info', default=None) or {}
        return str(info.get('model', '')).upper() if isinstance(info, dict) else ''

    @QtCore.Slot(object)
    def _on_sources_changed(self, sources):
        if self.pubsub is None:
            return
        self._sources_assign()
        self._combos_update()

    @QtCore.Slot(object)
    def _combos_update(self, value=None):
        if self.pubsub is None:
            return
        for instrument in INSTRUMENTS:
            selector = self._selectors[instrument]
            items = [(s, self._source_name(s)) for s in selector.sources if s != 'default']
            self._control.items_set(_CONTROL[instrument], items, selector.value)

    def _sources_assign(self):
        """Pick the input and output instruments when not yet selected.

        The input defaults to the app default device and the output to the
        first other device.  'default' is never kept, since it would give
        both the same device.
        """
        if self.pubsub is None:
            return
        s_in, s_out = self._selectors['in'], self._selectors['out']
        available = list(self.pubsub.query(_SOURCE_LIST_TOPIC, default=None) or [])
        if s_in.value in (None, 'default') and available:
            default = self.pubsub.query(_SOURCE_DEFAULT_TOPIC, default=None)
            s_in.source_set(default if default in available else available[0])
        if s_out.value in (None, 'default'):
            others = [s for s in available if s != s_in.value]
            if others:
                s_out.source_set(others[0])

    @QtCore.Slot(object)
    def _on_resolved_changed(self, value):
        if self.pubsub is not None:
            self._connect()

    def on_action_swap(self):
        """Swap the input and output instruments."""
        v_in, v_out = self._selectors['in'].value, self._selectors['out'].value
        self._selectors['in'].source_set(v_out)
        self._selectors['out'].source_set(v_in)

    def _signals_needed(self):
        extra = ['v', 'i'] if self.show_vi else []
        out = ['p'] + extra
        if self.curve_x == 'current' and 'i' not in out:
            out.append('i')
        return {'in': ['p'] + extra, 'out': out}

    def _disconnect(self):
        for key, topic in self._data_topics.items():
            self.pubsub.unsubscribe(topic, self._callbacks[key])
        self._data_topics = {}
        for t in self._enable_topics:
            self.pubsub.unsubscribe(t, self._on_signal_enable)
        self._enable_topics = []
        if self._rate_topic is not None:
            self.pubsub.unsubscribe(self._rate_topic, self._on_statistics_frequency)
            self._rate_topic = None

    def _connect(self):
        """Subscribe to the selected instruments, and reset on change."""
        if self.pubsub is None:
            return
        self._disconnect()
        sources = {instrument: self._selectors[instrument].resolved() for instrument in INSTRUMENTS}
        valid = all(sources.values()) and sources['in'] != sources['out']
        if sources != self._sources:
            self._sources = dict(sources)
            self._reset()
        self._disabled = []
        if valid:
            for instrument, signals in self._signals_needed().items():
                topic = get_topic_name(sources[instrument])
                for signal in signals:
                    enable_topic = f'{topic}/settings/signals/{signal}/enable'
                    try:
                        enabled = self.pubsub.query(enable_topic)
                    except KeyError:
                        self._disabled.append((instrument, signal))
                        continue
                    self.pubsub.subscribe(enable_topic, self._on_signal_enable, ['pub'])
                    self._enable_topics.append(enable_topic)
                    if not enabled:
                        self._disabled.append((instrument, signal))
                        continue
                    data_topic = f'{topic}/events/signals/{signal}/!data'
                    try:
                        self.pubsub.subscribe(data_topic, self._callbacks[(instrument, signal)], ['pub'])
                        self._data_topics[(instrument, signal)] = data_topic
                    except KeyError:
                        self._disabled.append((instrument, signal))
            signals = sorted(f'{instrument}.{signal}' for instrument, signal in self._data_topics)
            self._worker.update({'signals': signals})
            rate_topic = f'{get_topic_name(sources["in"])}/settings/statistics_frequency'
            try:
                self.pubsub.subscribe(rate_topic, self._on_statistics_frequency, ['pub', 'retain'])
                self._rate_topic = rate_topic
            except KeyError:
                self._on_statistics_frequency(_STATISTICS_FREQUENCY_DEFAULT)
        self._status_update()

    def _on_signal_enable(self, value):
        self._connect()

    def on_action_enable_signals(self):
        """Enable the instrument signals that this widget needs."""
        for instrument, signal in list(self._disabled):
            topic = get_topic_name(self._sources[instrument])
            self.pubsub.publish(f'{topic}/settings/signals/{signal}/enable', True)

    def _on_statistics_frequency(self, value):
        try:
            period = 1.0 / float(value)
        except (TypeError, ValueError, ZeroDivisionError):
            period = 1.0 / _STATISTICS_FREQUENCY_DEFAULT
        if period != self.period:
            self.period = period
            self._worker.update({'period': period})
            self._history_resize()
        self._status_update()

    # ---- data ----

    def _data_factory(self, instrument, signal):
        def fn(value):
            self._rx_time[instrument] = time.monotonic()
            if self.hold or self._paused:
                return
            if not self._worker.push(instrument, signal, value):
                self._status_update()
        return fn

    def _engine_curve_config(self):
        return {
            'curve_x': self.curve_x,
            'bins_per_decade': int(self.curve_bins_per_decade),
            'curve_period': float(self.curve_window) or None,
            'steady_threshold': float(self.steady_threshold),
        }

    def _reset(self):
        """Restart processing, such as for new instruments."""
        self._generation = self._worker.configure({'period': self.period, **self._engine_curve_config()})
        self._rx_time = {'in': None, 'out': None}
        self._results_clear()

    def _results_clear(self):
        self._window = None
        self._window_valid = None
        self._snapshot = {}
        self._swap_count = 0
        self._curve_bins = []
        self.history.clear()
        self._readout.update()
        self._time_plot.clear()
        self._curve_plot.clear()

    def _history_resize(self):
        self.history.reset(int(np.ceil(float(self.time_plot_duration) / self.period)) + 4)

    def on_action_clear(self):
        """Clear the cumulative efficiency and the history."""
        self._worker.clear()
        self._results_clear()
        self._status_update()

    @QtCore.Slot(object)
    def _on_snapshot(self, s):
        if s['generation'] != self._generation:
            return
        self._snapshot = s
        self.history.append(s['windows'])
        if not self.curve_hold and 'curve' in s and s['curve'] != self._curve_bins:
            self._curve_bins = s['curve']
            self._curve_plot.update()
        for w in s['windows']:
            self._window = w
            if w['valid']:
                self._window_valid = w
                eta = w.get('efficiency')
                if eta is not None and eta > _SWAP_THRESHOLD:
                    self._swap_count += 1
                else:
                    self._swap_count = 0
        self._readout.update()
        if s['windows']:
            self._time_plot.update()
        self._status_update()

    def curve_bins(self):
        """The displayed efficiency curve bins, see :meth:`Curve.bins`."""
        return self._curve_bins

    def readout(self):
        """The readout state.

        :return: dict with window (the latest valid window, or None),
            valid (True when the latest window is valid),
            efficiency_cumulative, and show_vi.
        """
        return {
            'window': self._window_valid,
            'valid': self._window is not None and bool(self._window['valid']),
            'efficiency_cumulative': self._snapshot.get('efficiency_cumulative'),
            'show_vi': bool(self.show_vi),
        }

    @staticmethod
    def _json_window(w):
        if w is None:
            return None
        return {k: (float(v) if isinstance(v, float) else v) for k, v in w.items()}

    def efficiency_info(self):
        """The efficiency state, for automation.

        :return: dict with status, input and output sources, period (s),
            window (the latest valid window), efficiency_cumulative,
            totals, rejected, overruns, and disabled signals.
        """
        return {
            'status': self.status,
            'input': self._sources['in'],
            'output': self._sources['out'],
            'period': self.period,
            'window': self._json_window(self._window_valid),
            'efficiency_cumulative': self._snapshot.get('efficiency_cumulative'),
            'totals': dict(self._snapshot.get('totals', {})),
            'rejected': int(self._snapshot.get('rejected', 0)),
            'overruns': int(self._worker.overruns),
            'disabled': [f'{instrument}.{signal}' for instrument, signal in self._disabled],
            'history': len(self.history),
            'curve': [self._json_window(b) for b in self._curve_bins],
        }

    # ---- style ----

    def plot_style(self):
        if self._style_cache is None:
            self._style_cache = self._style_build()
        return self._style_cache

    def _style_build(self):
        v = plot_base.style_vars(self)
        s = plot_base.style_build(v, 'efficiency')
        for name in ['title', 'main', 'stats']:
            font = font_as_qfont(v[f'efficiency.{name}_font'])
            s[f'{name}_font'] = font
            s[f'{name}_metrics'] = QtGui.QFontMetrics(font)
            s[f'{name}_color'] = color_as_qcolor(v[f'efficiency.{name}_color'])
        s['invalid_color'] = color_as_qcolor(v['efficiency.invalid_color'])
        s['trace_pen'] = QtGui.QPen(color_as_qcolor(v['efficiency.trace']))
        curve = color_as_qcolor(v['efficiency.curve'])
        faded = QtGui.QColor(curve)
        faded.setAlphaF(curve.alphaF() * 0.3)
        s['curve_pen'] = QtGui.QPen(curve)
        s['curve_brush'] = QtGui.QBrush(curve)
        s['curve_faded_pen'] = QtGui.QPen(faded)
        s['curve_faded_brush'] = QtGui.QBrush(faded)
        return s

    def on_style_change(self):
        self._style_cache = None
        self._readout.updateGeometry()
        self._readout.update()
        self._time_plot.update()
        self._curve_plot.update()

    # ---- export ----

    def _export_meta(self):
        return {
            N_('input'): self._source_name(self._sources['in']),
            N_('output'): self._source_name(self._sources['out']),
            N_('window'): f'{self.period:g} s',
        }

    def export_history(self, path):
        """Export the efficiency vs time history as CSV."""
        t, columns = self.history.columns()
        with open(path, 'wt', newline='', encoding='utf-8') as f:
            history_csv(f, t, columns, self._export_meta())

    def export_curve(self, path):
        """Export the efficiency curve as CSV."""
        meta = self._export_meta()
        meta[N_('curve window')] = f'{float(self.curve_window) or self.period:g} s'
        meta[N_('steady threshold')] = f'{float(self.steady_threshold):g}'
        x_name, units = ('i_out', 'A') if self.curve_x == 'current' else ('p_out', 'W')
        with open(path, 'wt', newline='', encoding='utf-8') as f:
            curve_csv(f, self._curve_bins, x_name, units, meta)

    def _export_request(self, kind):
        path = self.pubsub.query('registry/paths/settings/path', default='') if self.pubsub else ''
        filename = time64.filename(f'_efficiency_{kind}.csv')
        dialog = QtWidgets.QFileDialog(self, N_('Select save location'), os.path.join(path, filename),
                                       'CSV (*.csv)')
        dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dialog.setDefaultSuffix('csv')
        self._dialog = dialog

        def on_finished(result):
            self._dialog = None
            files = dialog.selectedFiles()
            if result != QtWidgets.QDialog.DialogCode.Accepted or len(files) != 1:
                return
            try:
                (self.export_history if kind == 'history' else self.export_curve)(files[0])
                self.pubsub.publish('registry/paths/actions/!mru_save', files[0])
            except Exception as ex:
                self._log.exception('efficiency export failed')
                self.pubsub.publish('registry/ui/actions/!error_msg', N_('Export failed') + f'\n{ex}')

        dialog.finished.connect(on_finished)
        dialog.open()

    # ---- menus ----

    def _toggle_factory(self, key):
        def fn(checked=False):
            self.setting_publish(key, not bool(getattr(self, key)))
        return fn

    def context_menu(self, event):
        """Show the context menu."""
        menu = QtWidgets.QMenu(self)
        CallableAction(menu, N_('Swap input and output'), self.on_action_swap)
        view = menu.addMenu(N_('View'))
        for key in ['show_vi', 'time_plot_enable', 'curve_enable', 'curve_whiskers']:
            CallableAction(view, SETTINGS[key]['brief'], self._toggle_factory(key),
                           checkable=True, checked=bool(getattr(self, key)))
        for key in ['time_plot_duration', 'curve_x', 'curve_x_scale']:
            submenu = menu.addMenu(SETTINGS[key]['brief'])
            for value, label in SETTINGS[key]['options']:
                CallableAction(submenu, label, self._value_factory(key, value),
                               checkable=True, checked=getattr(self, key) == value)
        CallableAction(menu, SETTINGS['curve_hold']['brief'], self._toggle_factory('curve_hold'),
                       checkable=True, checked=bool(self.curve_hold))
        export = menu.addMenu(N_('Export'))
        CallableAction(export, N_('Efficiency vs time (CSV)'), lambda: self._export_request('history'))
        CallableAction(export, N_('Efficiency curve (CSV)'), lambda: self._export_request('curve'))
        CallableAction(menu, N_('Clear'), self.on_action_clear)
        settings_action_create(self, menu)
        context_menu_show(menu, event)

    def _value_factory(self, key, value):
        def fn(checked=False):
            self.setting_publish(key, value)
        return fn

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            event.accept()
            self.context_menu(event)
        else:
            super().mousePressEvent(event)

    # ---- settings ----

    def on_setting_hold(self, value):
        self._control.value_set('hold', bool(value))
        self._status_update()

    def on_setting_show_vi(self, value):
        self._readout.updateGeometry()
        self._readout.update()
        if self.pubsub is not None:
            self._connect()

    def on_setting_time_plot_enable(self, value):
        self._time_plot.setVisible(bool(value))

    def on_setting_time_plot_duration(self, value):
        self._history_resize()
        self._time_plot.update()

    def on_setting_curve_enable(self, value):
        self._curve_plot.setVisible(bool(value))

    def _curve_config_update(self, value=None):
        self._worker.update(self._engine_curve_config())
        self._curve_bins = []
        self._curve_plot.clear()

    on_setting_curve_bins_per_decade = _curve_config_update
    on_setting_curve_window = _curve_config_update
    on_setting_steady_threshold = _curve_config_update

    def on_setting_curve_x(self, value):
        self._curve_config_update()
        if self.pubsub is not None:
            self._connect()  # output current subscription

    def _curve_repaint(self, value=None):
        self._curve_plot.clear()

    on_setting_curve_x_scale = _curve_repaint
    on_setting_curve_whiskers = _curve_repaint
    on_setting_curve_min_count = _curve_repaint

    def on_setting_curve_hold(self, value):
        if not value and 'curve' in self._snapshot:
            self._curve_bins = self._snapshot['curve']
        self._curve_plot.update()
        self._status_update()

    def on_setting_splitter(self, value):
        if value and len(value) == self._splitter.count():
            self._splitter.setSizes([int(v) for v in value])

    def _on_splitter_moved(self, pos, index):
        self.setting_publish('splitter', self._splitter.sizes())

    def on_setting_control_location(self, value):
        control_location_apply(self._layout, self._control, value)

    # ---- status ----

    def _status_update(self):
        parts, warning = [], False
        names = {i: self._source_name(self._sources[i]) for i in INSTRUMENTS}
        if not all(self._sources.values()):
            parts.append(N_('Select the input and output instruments'))
            warning = True
        elif self._sources['in'] == self._sources['out']:
            parts.append(N_('Select different input and output instruments'))
            warning = True
        else:
            if self._disabled:
                missing = [f'{_INSTRUMENT_NAMES[i]} {_SIGNAL_NAMES[s]}' for i, s in self._disabled]
                parts.append(N_('Disabled: {0}').format(', '.join(missing)))
                warning = True
            if self.hold:
                parts.append(N_('Hold'))
            elif self.curve_hold:
                parts.append(N_('Curve hold'))
            elif self._paused:
                parts.append(N_('Paused'))
            now = time.monotonic()
            for instrument in INSTRUMENTS:
                other = 'out' if instrument == 'in' else 'in'
                t, t_other = self._rx_time[instrument], self._rx_time[other]
                if t_other is not None and now - t_other < _MISSING_TIMEOUT and \
                        (t is None or now - t > _MISSING_TIMEOUT):
                    parts.append(N_('No data from {0}').format(names[instrument]))
                    warning = True
            if self.pubsub is not None and self._source_model(self._sources['in']) == 'JS110':
                parts.append(N_('JS110 input includes its burden voltage'))
                warning = True
            if self._swap_count >= _SWAP_COUNT:
                parts.append(N_('Efficiency above 100%: swap input and output?'))
                warning = True
        parts.append(f'{1.0 / self.period:g} Hz')
        totals = self._snapshot.get('totals')
        if totals:
            parts.append(N_('{0} windows').format(totals['windows']))
            if totals['invalid']:
                parts.append(N_('{0} invalid').format(totals['invalid']))
            if self._snapshot.get('rejected'):
                parts.append(N_('{0} unsteady').format(self._snapshot['rejected']))
        overruns = self._worker.overruns
        if overruns:
            parts.append(N_('overruns {0}').format(overruns))
            warning = True
        self.status = ' | '.join(parts)
        self.status_warning = warning
        self._control.status_set(self.status, warning)
        self._control.enable.setVisible(bool(self._disabled) and all(self._sources.values()))
