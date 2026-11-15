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
from joulescope_ui import register, N_, get_topic_name, CAPABILITIES
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.widget_tools import CallableAction, settings_action_create, context_menu_show, \
    CONTROL_LOCATION_SETTING, control_location_apply
from joulescope_ui.source_selector import SourceSelector
from joulescope_ui.widgets import plot_base
from .efficiency_control import EfficiencyControlWidget
from .efficiency_readout import EfficiencyReadout
from .efficiency_worker import EfficiencyWorker
import logging
import math
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
        self._readout = EfficiencyReadout(self, self)
        self._layout.addWidget(self._readout)
        self._layout.addStretch(1)
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
        return {
            'in': ['p'] + extra,
            'out': ['p', 'i'] + [s for s in extra if s != 'i'],
        }

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

    def _reset(self):
        """Restart processing, such as for new instruments."""
        self._generation = self._worker.configure({'period': self.period})
        self._rx_time = {'in': None, 'out': None}
        self._results_clear()

    def _results_clear(self):
        self._window = None
        self._window_valid = None
        self._snapshot = {}
        self._swap_count = 0
        self._readout.update()

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
        self._status_update()

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
        return s

    def on_style_change(self):
        self._style_cache = None
        self._readout.updateGeometry()
        self._readout.update()

    # ---- menus ----

    def _toggle_factory(self, key):
        def fn(checked=False):
            self.setting_publish(key, not bool(getattr(self, key)))
        return fn

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            event.accept()
            menu = QtWidgets.QMenu(self)
            CallableAction(menu, N_('Swap input and output'), self.on_action_swap)
            CallableAction(menu, N_('Show voltage and current'), self._toggle_factory('show_vi'),
                           checkable=True, checked=bool(self.show_vi))
            CallableAction(menu, N_('Clear'), self.on_action_clear)
            settings_action_create(self, menu)
            context_menu_show(menu, event)
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
        overruns = self._worker.overruns
        if overruns:
            parts.append(N_('overruns {0}').format(overruns))
            warning = True
        self.status = ' | '.join(parts)
        self.status_warning = warning
        self._control.status_set(self.status, warning)
        self._control.enable.setVisible(bool(self._disabled) and all(self._sources.values()))
