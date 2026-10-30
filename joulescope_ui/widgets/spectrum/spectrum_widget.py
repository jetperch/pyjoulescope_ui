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

"""Live spectrum analyzer widget: FFT traces and waterfall history.

See docs/plans/spectrum.md.
"""

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import register, N_, get_topic_name
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.widget_tools import CallableAction, settings_action_create, context_menu_show, \
    CONTROL_LOCATION_SETTING, control_location_apply
from joulescope_ui.source_selector import SourceSelector
from joulescope_ui.units import three_sig_figs
from joulescope_ui.spectrum_engine import WINDOWS, WINDOW_NAMES, DB_FLOOR, DECIMATE_ROLLOFF, \
    to_db, find_peaks, column_map
from joulescope_ui.widgets.waveform import axis_ticks
from .spectrum_control import SpectrumControlWidget
from .spectrum_plot import FftPlot, WaterfallPlot, WaterfallHistory, COLORMAPS, color_table, \
    colormap_rgb, f_str
from .spectrum_worker import SpectrumWorker
import logging
import numpy as np


_FFT_LENGTH_MAX_LOG2 = 20
_DECIMATE_MAX_LOG2 = 10
_MIN_VIEW_BINS = 4
_DB_RANGE_MAX = 200.0
_PEAK_SEPARATION_PIXELS = 8

_STYLE_DEFAULTS = {
    'spectrum.background': '#101010ff',
    'spectrum.text_foreground': '#C0C0C0ff',
    'spectrum.text_background': '#101010C0',
    'spectrum.grid_major': '#ffffff40',
    'spectrum.grid_minor': '#80808018',
    'spectrum.plot_border': '#ffffff80',
    'spectrum.hover': '#ffffffa0',
    'spectrum.trace_live': '#ffff00ff',
    'spectrum.trace_average': '#00ffffff',
    'spectrum.trace_max': '#ff4040c0',
    'spectrum.trace_min': '#40ff40c0',
    'spectrum.marker': '#ff8c00ff',
    'spectrum.peak': '#ff00ffff',
    'spectrum.status_warning': '#ff8c00ff',
    'spectrum.axis_font': '10pt "Lato"',
}

_TRACES = ['live', 'average', 'max', 'min']

# Settings that change the engine configuration, which resets the traces.
_ENGINE_SETTINGS = ['decimate', 'fft_length', 'fft_window', 'overlap', 'scaling', 'dc_remove',
                    'average_mode', 'average_count', 'waterfall_duration', 'waterfall_rows',
                    'waterfall_detector', 'waterfall_memory']


def _pow2_options(k0, k1, fmt):
    return [[1 << k, fmt(1 << k)] for k in range(k0, k1 + 1)]


SETTINGS = {
    'signal_stream_source': {
        'dtype': 'str',
        'brief': N_('The signal data stream source.'),
        'default': None,
        'flags': ['hide'],
    },
    'signal': {
        'dtype': 'str',
        'brief': N_('The signal to analyze.'),
        'default': 'i',
        'flags': ['hide'],
    },
    'hold': {
        'dtype': 'bool',
        'brief': N_('Hold the display.'),
        'default': False,
        'flags': ['hide', 'tmp', 'skip_undo'],
    },
    'decimate': {
        'dtype': 'int',
        'brief': N_('Span'),
        'detail': N_("""Reduce the analyzed frequency span by decimating
            the signal before the FFT.  The span is the sample rate / 2 /
            this factor.  Narrower spans give finer resolution bandwidth
            for the same FFT length."""),
        'default': 1,
        'options': _pow2_options(0, _DECIMATE_MAX_LOG2, lambda d: '÷1' if d == 1 else f'÷{d}'),
    },
    'fft_length': {
        'dtype': 'int',
        'brief': N_('FFT length'),
        'detail': N_("""The number of samples for each FFT.  The FFT
            produces fft_length / 2 + 1 frequency bins, and the resolution
            bandwidth is approximately the window ENBW x sample rate /
            fft_length."""),
        'default': 4096,
        'options': _pow2_options(6, _FFT_LENGTH_MAX_LOG2, lambda n: f'N={n}'),
    },
    'fft_window': {
        'dtype': 'str',
        'brief': N_('Window'),
        'default': 'hann',
        'options': [[k, WINDOW_NAMES[k]] for k in WINDOWS.keys()],
    },
    'overlap': {
        'dtype': 'float',
        'brief': N_('Overlap'),
        'detail': N_('The overlap between successive FFTs.'),
        'default': 0.5,
        'options': [[0.0, '0%'], [0.25, '25%'], [0.5, '50%'], [0.75, '75%'], [0.9, '90%']],
    },
    'dc_remove': {
        'dtype': 'bool',
        'brief': N_('Remove DC'),
        'detail': N_("""Subtract the mean of each FFT segment.  Joulescope
            signals often have a large DC component whose window leakage
            hides the low-frequency content."""),
        'default': True,
    },
    'scaling': {
        'dtype': 'str',
        'brief': N_('Scaling'),
        'detail': N_("""Amplitude shows the RMS amplitude in each bin, which
            reads the true amplitude of a tone.  PSD shows the power
            spectral density, which is independent of the resolution
            bandwidth and best for noise."""),
        'default': 'amplitude',
        'options': [['amplitude', N_('Amplitude')], ['psd', N_('PSD')]],
    },
    'y_units': {
        'dtype': 'str',
        'brief': N_('Y-axis units'),
        'default': 'dB',
        'options': [['dB', N_('dB')], ['linear', N_('linear')]],
    },
    'average_mode': {
        'dtype': 'str',
        'brief': N_('Average mode'),
        'detail': N_("""Exponential averages the most recent average count
            spectra.  Cumulative averages all spectra since the last clear.
            Averaging is computed on power, never on dB values."""),
        'default': 'exponential',
        'options': [['off', N_('Avg off')], ['exponential', N_('Avg exp')],
                    ['cumulative', N_('Avg cumul')]],
    },
    'average_count': {
        'dtype': 'int',
        'brief': N_('Average count'),
        'default': 16,
        'options': _pow2_options(1, 10, str),
    },
    'show_live': {
        'dtype': 'bool',
        'brief': N_('Show the live trace.'),
        'default': True,
    },
    'show_average': {
        'dtype': 'bool',
        'brief': N_('Show the average trace.'),
        'default': True,
    },
    'show_max': {
        'dtype': 'bool',
        'brief': N_('Show the max hold trace.'),
        'default': False,
    },
    'show_min': {
        'dtype': 'bool',
        'brief': N_('Show the min hold trace.'),
        'default': False,
    },
    'x_log': {
        'dtype': 'bool',
        'brief': N_('Logarithmic frequency axis'),
        'default': False,
    },
    'f_range': {
        'dtype': 'obj',
        'brief': N_('The frequency viewport [f_min, f_max] in Hz.'),
        'default': None,
        'flags': ['hide', 'skip_undo'],
    },
    'y_autoscale': {
        'dtype': 'bool',
        'brief': N_('Automatically scale the y-axis.'),
        'default': True,
    },
    'y_range': {
        'dtype': 'obj',
        'brief': N_('The manual y-axis range.'),
        'default': None,
        'flags': ['hide', 'skip_undo'],
    },
    'show_fft': {
        'dtype': 'bool',
        'brief': N_('Show the FFT spectrum.'),
        'default': True,
    },
    'show_waterfall': {
        'dtype': 'bool',
        'brief': N_('Show the waterfall history.'),
        'default': True,
    },
    'splitter': {
        'dtype': 'obj',
        'brief': N_('The FFT and waterfall pane sizes.'),
        'default': None,
        'flags': ['hide', 'skip_undo'],
    },
    'waterfall_duration': {
        'dtype': 'float',
        'brief': N_('Waterfall duration'),
        'default': 10.0,
        'options': [[float(v), f'{v} s'] for v in [1, 2, 5, 10, 20, 30, 60, 120, 300, 600]],
    },
    'waterfall_rows': {
        'dtype': 'int',
        'brief': N_('Waterfall rows'),
        'detail': N_("""The number of waterfall rows over the duration.  Each
            row combines all FFTs over its duration using the waterfall
            detector."""),
        'default': 200,
        'options': [[v, str(v)] for v in [50, 100, 200, 500, 1000]],
    },
    'waterfall_detector': {
        'dtype': 'str',
        'brief': N_('Waterfall detector'),
        'detail': N_("""How each row combines its FFTs.  Max keeps short
            bursts visible."""),
        'default': 'average',
        'options': [['average', N_('average')], ['max', N_('max')]],
    },
    'waterfall_memory': {
        'dtype': 'int',
        'brief': N_('Waterfall memory (MB)'),
        'detail': N_("""The maximum waterfall history memory.  Long FFTs
            with many rows may reduce the waterfall duration."""),
        'default': 64,
        'options': [[v, f'{v} MB'] for v in [16, 64, 256, 1024]],
    },
    'colormap': {
        'dtype': 'str',
        'brief': N_('Waterfall colormap'),
        'default': 'inferno',
        'options': COLORMAPS,
    },
    'intensity_follows_y': {
        'dtype': 'bool',
        'brief': N_('Waterfall intensity follows the FFT y-axis'),
        'detail': N_("""When set, the waterfall color range matches the FFT
            dB y-axis range.  When cleared, use intensity min and max."""),
        'default': True,
    },
    'intensity_min': {
        'dtype': 'float',
        'brief': N_('Waterfall intensity min (dB)'),
        'default': -140.0,
    },
    'intensity_max': {
        'dtype': 'float',
        'brief': N_('Waterfall intensity max (dB)'),
        'default': -20.0,
    },
    'peak_count': {
        'dtype': 'int',
        'brief': N_('Number of peaks to display'),
        'default': 5,
        'options': [[v, str(v)] for v in range(11)],
    },
    'peak_threshold': {
        'dtype': 'float',
        'brief': N_('Peak threshold (dB)'),
        'detail': N_('Only display peaks at or above this value.'),
        'default': -200.0,
    },
    'peak_excursion': {
        'dtype': 'float',
        'brief': N_('Peak excursion (dB)'),
        'detail': N_("""A peak must rise at least this far above the lowest
            value on each side, which ignores noise on tone skirts."""),
        'default': 10.0,
    },
    'markers': {
        'dtype': 'obj',
        'brief': N_('The marker frequencies in Hz.'),
        'default': [],
        'flags': ['hide'],
    },
    'trace_width': {
        'dtype': 'int',
        'brief': N_('Trace width'),
        'default': 1,
        'options': [[1, '1'], [2, '2'], [3, '3']],
    },
    'frame_rate': {
        'dtype': 'int',
        'brief': N_('Maximum update rate (Hz)'),
        'default': 30,
        'options': [[v, str(v)] for v in [5, 10, 20, 30, 60]],
    },
    'control_location': CONTROL_LOCATION_SETTING,
}


@register
@styled_widget(N_('Spectrum'))
class SpectrumWidget(QtWidgets.QWidget):
    """Display the live frequency spectrum and waterfall of a signal."""

    CAPABILITIES = ['widget@']
    SETTINGS = SETTINGS
    _snapshot_signal = QtCore.Signal(object)

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        self.pubsub = None
        self._style_cache = None
        self._generation = 0
        self._fs_in = None          # input sample rate
        self._units = ''
        self._snapshot = {}
        self._f = None              # bin frequencies
        self._display = {}          # trace name -> display values
        self._db = {}               # trace name -> dB values
        self._y_auto = None         # autoscale y range, display units
        self._db_auto = None        # autoscale range in dB, for intensity
        self._cmap_cache = None
        self._hover = None          # (plot, QPointF)
        self._signals = []          # available (signal_id, name)
        self._enable_topics = []
        self._data_topic = None
        self._color_table = None
        self._colorbar = None
        self._configure_pending = False
        self.peaks = []
        self.marker_freqs = []      # displayed markers, which may be mid-drag
        self._f_view = None         # displayed viewport, which may be mid-pan
        self._row_period = 0.0
        self.waterfall = WaterfallHistory()
        self.y_prefix = ''
        super().__init__(parent)
        for key, value in SETTINGS.items():
            setattr(self, key, value['default'])  # not registered: sets the attribute only
        self.setObjectName('spectrum_widget')
        self.source_selector = SourceSelector(self, 'signal_stream')
        self.source_selector.sources_changed.connect(self._on_sources_changed)
        self.source_selector.resolved_changed.connect(self._on_resolved_changed)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self._splitter.setChildrenCollapsible(False)
        self._fft = FftPlot(self, self._splitter)
        self._waterfall = WaterfallPlot(self, self._splitter)
        self._splitter.addWidget(self._fft)
        self._splitter.addWidget(self._waterfall)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        self._layout.addWidget(self._splitter)
        self._control = SpectrumControlWidget(self, SETTINGS)
        self._layout.addWidget(self._control)
        for name in ['hold', 'signal'] + _ENGINE_SETTINGS:
            self._control.value_set(name, getattr(self, name))
        self.status = ''
        self.status_warning = False

        self._worker = SpectrumWorker(self._snapshot_signal.emit)
        self._snapshot_signal.connect(self._on_snapshot)

    # ---- pubsub lifecycle ----

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        self.source_selector.on_pubsub_register(self.pubsub, f'{topic}/settings/signal_stream_source')
        self._worker.start()
        self._configure()
        self._signals_update()

    def on_pubsub_unregister(self):
        self._worker.stop()
        self._data_disconnect()
        self._enable_unsubscribe()

    def setting_publish(self, name, value):
        """Publish one of this widget's settings."""
        if self.pubsub is not None:
            self.pubsub.publish(f'{get_topic_name(self)}/settings/{name}', value)
        else:  # not registered, such as in unit tests
            setattr(self, name, value)
            getattr(self, f'on_setting_{name}', lambda v: None)(value)

    # ---- source and signal ----

    @QtCore.Slot(object)
    def _on_sources_changed(self, sources):
        items = []
        for source in sources:
            name = source
            if self.pubsub is not None and source != 'default':
                name = self.pubsub.query(f'{get_topic_name(source)}/settings/name', default=source)
            items.append((source, name))
        self._control.items_set('source', items, self.source_selector.value)

    @QtCore.Slot(object)
    def _on_resolved_changed(self, value):
        self._signals_update()

    def _enable_unsubscribe(self):
        for t in self._enable_topics:
            self.pubsub.unsubscribe(t, self._on_signal_enable)
        self._enable_topics = []

    def _signals_update(self):
        if self.pubsub is None:
            return
        self._enable_unsubscribe()
        source = self.source_selector.resolved()
        signals = []
        if source is not None:
            topic = get_topic_name(source)
            for signal_id in self.pubsub.enumerate(f'{topic}/settings/signals'):
                if signal_id == 'S':
                    continue
                enable_topic = f'{topic}/settings/signals/{signal_id}/enable'
                try:
                    enabled = self.pubsub.query(enable_topic)
                except KeyError:
                    continue
                self.pubsub.subscribe(enable_topic, self._on_signal_enable, ['pub'])
                self._enable_topics.append(enable_topic)
                if enabled:
                    name = self.pubsub.query(f'{topic}/settings/signals/{signal_id}/name', default=signal_id)
                    signals.append((signal_id, name))
        self._signals = signals
        items = list(signals)
        if self.signal not in [s for s, _ in signals]:
            items.append((self.signal, self.signal))
        self._control.items_set('signal', items, self.signal)
        self._data_connect()

    def _on_signal_enable(self, value):
        self._signals_update()

    def _data_disconnect(self):
        if self._data_topic is not None:
            self.pubsub.unsubscribe(self._data_topic, self._on_data)
            self._data_topic = None

    def _data_connect(self):
        source = self.source_selector.resolved()
        topic = None
        if source is not None and self.signal in [s for s, _ in self._signals]:
            topic = f'{get_topic_name(source)}/events/signals/{self.signal}/!data'
        if topic == self._data_topic:
            return
        self._data_disconnect()
        self.on_action_clear()
        if topic is not None:
            try:
                self.pubsub.subscribe(topic, self._on_data, ['pub'])
                self._data_topic = topic
            except KeyError:
                self._log.warning('signal data topic not found: %s', topic)
        self._status_update()

    def _on_data(self, value):
        if self.hold:
            return
        fs = value['sample_freq']
        if fs != self._fs_in:
            self._fs_in = fs
            self._configure()
            self._span_labels_update()
        self._units = value.get('units', '') or ''
        if not self._worker.push(value['sample_id'], fs, value['data'], value.get('dtype', 'f32')):
            self._status_update()

    # ---- engine configuration ----

    def _engine_config(self):
        n = int(self.fft_length)
        decimate = int(self.decimate)
        overlap = float(self.overlap)
        row_period = float(self.waterfall_duration) / int(self.waterfall_rows)
        if self._fs_in:
            hop = max(1, n - int(round(overlap * n)))
            row_period = max(row_period, hop * decimate / self._fs_in)
        return {
            'fft_length': n,
            'window': self.fft_window,
            'overlap': overlap,
            'scaling': self.scaling,
            'dc_remove': bool(self.dc_remove),
            'decimate': decimate,
            'average_mode': self.average_mode,
            'average_count': int(self.average_count),
            'row_period': row_period,
            'detector': self.waterfall_detector,
        }

    def _configure(self):
        self._configure_pending = False
        cfg = self._engine_config()
        self._row_period = cfg['row_period']
        bins = cfg['fft_length'] // 2 + 1
        rows = max(1, int(round(float(self.waterfall_duration) / self._row_period)))
        rows_mem = max(8, int(self.waterfall_memory) * 1024 * 1024 // (bins * 4))
        self.waterfall.reset(min(rows, rows_mem), bins)
        self._generation = self._worker.configure(cfg)
        self._worker.frame_period = 1.0 / max(1, int(self.frame_rate))
        self._traces_clear()

    def _configure_request(self):
        # coalesce multiple setting changes, such as during registration
        if not self._configure_pending:
            self._configure_pending = True
            QtCore.QTimer.singleShot(0, self._configure_deferred)

    def _configure_deferred(self):
        if self._configure_pending and self.pubsub is not None:
            self._configure()

    def _traces_clear(self):
        self._snapshot = {}
        self._display = {}
        self._db = {}
        self.peaks = []
        self._y_auto = None
        self._db_auto = None
        self._repaint()

    def on_action_clear(self):
        """Clear the traces and waterfall history."""
        self._worker.clear()
        self.waterfall.reset(self.waterfall.capacity, self.waterfall.bins)
        self._traces_clear()

    def _engine_setting(self, name, value):
        self._control.value_set(name, value)
        if self.pubsub is not None:
            self._configure_request()

    def on_setting_decimate(self, value):
        self._engine_setting('decimate', value)

    def on_setting_fft_length(self, value):
        self._engine_setting('fft_length', value)

    def on_setting_fft_window(self, value):
        self._engine_setting('fft_window', value)

    def on_setting_overlap(self, value):
        self._engine_setting('overlap', value)

    def on_setting_scaling(self, value):
        self._engine_setting('scaling', value)

    def on_setting_dc_remove(self, value):
        self._engine_setting('dc_remove', value)

    def on_setting_average_mode(self, value):
        self._engine_setting('average_mode', value)

    def on_setting_average_count(self, value):
        self._engine_setting('average_count', value)

    def on_setting_waterfall_duration(self, value):
        self._engine_setting('waterfall_duration', value)

    def on_setting_waterfall_rows(self, value):
        self._engine_setting('waterfall_rows', value)

    def on_setting_waterfall_detector(self, value):
        self._engine_setting('waterfall_detector', value)

    def on_setting_waterfall_memory(self, value):
        self._engine_setting('waterfall_memory', value)

    # ---- snapshots ----

    @QtCore.Slot(object)
    def _on_snapshot(self, s):
        if s['generation'] != self._generation:
            return
        if 'n' not in s:
            self._traces_clear()
            self._status_update()
            return
        fs, n = s['fs'], s['n']
        if self._snapshot.get('fs') != fs or self._snapshot.get('n') != n:
            self._f = np.arange(n // 2 + 1) * (fs / n)
            self._cmap_cache = None
        self._snapshot = s
        self.waterfall.append(s['rows'])
        self._derived_update()
        self._status_update()
        self._repaint()

    def _derived_update(self):
        s = self._snapshot
        self._db = {}
        self._display = {}
        for name in _TRACES:
            p = s.get(name)
            if p is None or not getattr(self, f'show_{name}'):
                continue
            db = to_db(p)
            self._db[name] = db
            self._display[name] = db if self.y_units == 'dB' else np.sqrt(p)
        self._autoscale_update()
        self._peaks_update()

    def _view_slice(self):
        f0, f1 = self.viewport()
        i0 = int(np.searchsorted(self._f, f0, 'left'))
        i1 = int(np.searchsorted(self._f, f1, 'right'))
        return slice(i0, max(i1, i0 + 1))

    def _autoscale_update(self):
        if not self._db or self._f is None:
            return
        view = self._view_slice()
        his, los = [], []
        for name, db in self._db.items():
            v = db[view]
            v = v[v > DB_FLOOR + 1]
            if len(v):
                his.append(np.max(v))
                los.append(np.percentile(v, 2))
        if not his:
            return
        hi, lo = max(his), min(los)
        lo = max(lo, hi - _DB_RANGE_MAX)
        self._db_auto = self._hysteresis(self._db_auto, lo, hi, 10.0)
        if self.y_units == 'dB':
            self._y_auto = self._db_auto
        else:
            v_hi = 10 ** (hi / 20)
            y = self._y_auto
            if y is None or v_hi > y[1] or v_hi < 0.4 * y[1]:
                self._y_auto = [0.0, v_hi * 1.25]

    @staticmethod
    def _hysteresis(current, lo, hi, step):
        target_hi = np.ceil((hi + 0.5 * step) / step) * step
        target_lo = np.floor((lo - 0.5 * step) / step) * step
        if current is None:
            return [target_lo, target_hi]
        y0, y1 = current
        if hi > y1 or hi < y1 - 3 * step:
            y1 = target_hi
        if lo < y0 or lo > y0 + 4 * step:
            y0 = target_lo
        if y1 - y0 < 2 * step:
            y0 = y1 - 2 * step
        return [y0, y1]

    def _peak_trace(self):
        for name in ['average', 'live', 'max']:
            if name in self._db:
                return self._db[name]
        return None

    def _peaks_update(self):
        self.peaks = []
        y = self._peak_trace()
        count = int(self.peak_count)
        if y is None or count <= 0:
            return
        view = self._view_slice()
        bins = view.stop - view.start
        width = max(1, self._fft.width())
        separation = max(1, int(_PEAK_SEPARATION_PIXELS * bins / width))
        f = self._f[view]
        y = y[view]
        if len(f) < 3:
            return
        peaks = find_peaks(y, count, float(self.peak_threshold), separation, x=f,
                           excursion=float(self.peak_excursion),
                           y_interpolate=self.fft_window != 'flattop')
        self.peaks = [(fp, yp) for fp, yp, _ in peaks]

    def displayed_peaks(self):
        """The displayed peaks as [[frequency Hz, dB], ...], for automation."""
        return [[float(f), float(db)] for f, db in self.peaks]

    # ---- shared plot state ----

    def _repaint(self):
        self._fft.update()
        self._waterfall.update()

    def plot_style(self):
        if self._style_cache is None:
            self._style_cache = self._style_build()
        return self._style_cache

    def _style_build(self):
        v = dict(_STYLE_DEFAULTS)
        style_obj = getattr(self, 'style_obj', None)
        if style_obj is not None:
            v.update({k: x for k, x in style_obj['vars'].items() if k.startswith('spectrum.')})
        font = font_as_qfont(v['spectrum.axis_font'])
        fm = QtGui.QFontMetrics(font)

        def pen(name):
            return QtGui.QPen(color_as_qcolor(v[name]))

        s = {
            'background': color_as_qcolor(v['spectrum.background']),
            'background_brush': QtGui.QBrush(color_as_qcolor(v['spectrum.background'])),
            'text_pen': pen('spectrum.text_foreground'),
            'text_bg_brush': QtGui.QBrush(color_as_qcolor(v['spectrum.text_background'])),
            'grid_major_pen': pen('spectrum.grid_major'),
            'grid_minor_pen': pen('spectrum.grid_minor'),
            'border_pen': pen('spectrum.plot_border'),
            'hover_pen': pen('spectrum.hover'),
            'marker_pen': pen('spectrum.marker'),
            'peak_pen': pen('spectrum.peak'),
            'peak_brush': QtGui.QBrush(color_as_qcolor(v['spectrum.peak'])),
            'warning_pen': pen('spectrum.status_warning'),
            'font': font,
            'font_metrics': fm,
            'font_height': fm.height(),
            'font_ascent': fm.ascent(),
            'y_label_width': fm.horizontalAdvance('-888.88'),
            'right_width': 6 + 12 + 3 + fm.horizontalAdvance('-888') + 4,
        }
        for name in _TRACES:
            p = pen(f'spectrum.trace_{name}')
            p.setWidth(int(self.trace_width))
            s[f'trace_{name}_pen'] = p
        return s

    def on_style_change(self):
        self._style_cache = None
        self._color_table = None
        self._colorbar = None
        self._repaint()

    def margins(self):
        style = self.plot_style()
        return style['y_label_width'] + 8, style['right_width']

    def viewport(self):
        """The effective frequency viewport (f_min, f_max) in Hz."""
        if self._f is None or len(self._f) < 2:
            return (1.0, 2.0) if self.x_log else (0.0, 1.0)
        df = self._f[1]
        full = self._full_range()
        r = self._f_view
        if not r:
            return full
        f0 = min(max(float(r[0]), full[0]), full[1])
        f1 = min(max(float(r[1]), full[0]), full[1])
        span_min = _MIN_VIEW_BINS * df
        if f1 - f0 < span_min:
            return full
        return f0, f1

    def _full_range(self):
        """The full frequency range, excluding the decimator roll-off band."""
        f1 = float(self._f[-1])
        if self._snapshot.get('decimate', 1) > 1:
            f1 *= DECIMATE_ROLLOFF
        return (self._f[1] if self.x_log else 0.0), f1

    def _u(self, f):
        if self.x_log:
            return np.log10(np.maximum(f, 1e-300))
        return f

    def _u_inv(self, u):
        return 10 ** u if self.x_log else u

    def f_to_x(self, f, rect):
        f0, f1 = self.viewport()
        u0, u1 = self._u(f0), self._u(f1)
        if f is None or u1 <= u0 or (self.x_log and np.any(np.asarray(f) <= 0)):
            return None
        return rect.left() + (self._u(f) - u0) * (rect.width() / (u1 - u0))

    def x_to_f(self, x, rect):
        f0, f1 = self.viewport()
        u0, u1 = self._u(f0), self._u(f1)
        return float(self._u_inv(u0 + (x - rect.left()) * (u1 - u0) / max(1.0, rect.width())))

    def column_map(self, width):
        """The bin to pixel column map for the viewport, or None."""
        if self._f is None or width <= 0:
            return None
        key = self.column_map_key(width)
        if self._cmap_cache is None or self._cmap_cache[0] != key:
            f0, f1 = self.viewport()
            u0, u1 = self._u(f0), self._u(f1)
            edges = self._u_inv(np.linspace(u0, u1, width + 1))
            self._cmap_cache = (key, column_map(self._f, edges))
        return self._cmap_cache[1]

    def column_map_key(self, width=None):
        if width is None and self._cmap_cache is not None:
            return self._cmap_cache[0]
        return (width, self.viewport(), bool(self.x_log), len(self._f) if self._f is not None else 0,
                None if self._f is None or len(self._f) < 2 else self._f[1])

    def x_ticks(self, width):
        f0, f1 = self.viewport()
        if self.x_log:
            return axis_ticks.log_ticks(f0, f1)
        return axis_ticks.ticks(f0, f1, major_max=max(2, int(width / 90)))

    def y_view(self):
        """The displayed y-axis range in display units."""
        r = self.y_range
        if not self.y_autoscale and r is not None and len(r) == 2 and np.isfinite(r).all() and r[1] > r[0]:
            return float(r[0]), float(r[1])
        if self._y_auto is not None:
            return tuple(self._y_auto)
        return (-160.0, 0.0) if self.y_units == 'dB' else (0.0, 1.0)

    def y_to_pixel(self, v, rect):
        y0, y1 = self.y_view()
        k = rect.height() / (y1 - y0)
        return rect.bottom() - (np.asarray(v, dtype=np.float64) - y0) * k

    def y_from_pixel(self, y, rect):
        y0, y1 = self.y_view()
        return y0 + (rect.bottom() - y) * (y1 - y0) / max(1.0, rect.height())

    def db_to_display(self, db):
        return db if self.y_units == 'dB' else 10 ** (db / 20)

    def intensity_range(self):
        if self.intensity_follows_y:
            if self.y_units == 'dB':
                r = self.y_view()
            else:
                r = self._db_auto or (-160.0, 0.0)
        else:
            r = (float(self.intensity_min), float(self.intensity_max))
        lo, hi = float(r[0]), float(r[1])
        if hi <= lo:
            hi = lo + 1.0
        return lo, hi

    def color_table(self):
        if self._color_table is None:
            self._color_table = color_table(self.colormap, self.plot_style()['background'])
        return self._color_table

    def colorbar_image(self):
        if self._colorbar is None:
            rgb = colormap_rgb(self.colormap, 256)[::-1]
            argb = np.empty((256, 1), dtype=np.uint32)
            argb[:, 0] = (0xff << 24) | (rgb[:, 0].astype(np.uint32) << 16) \
                | (rgb[:, 1].astype(np.uint32) << 8) | rgb[:, 2]
            image = QtGui.QImage(argb.data, 1, 256, 4, QtGui.QImage.Format.Format_ARGB32)
            self._colorbar = image.copy()
        return self._colorbar

    def waterfall_time(self):
        """The waterfall history duration in seconds."""
        return self.waterfall.capacity * self._row_period

    def trace(self, name):
        return self._display.get(name)

    def _units_str(self):
        u = self._units
        if self.scaling == 'psd':
            return f'{u}²/Hz' if self.y_units == 'dB' else f'{u}/√Hz'
        return u

    def y_label(self):
        u = self._units_str()
        if self.y_units == 'dB':
            return f'dB re 1 {u}' if u else 'dB'
        return f'{self.y_prefix}{u}'

    def _value_str(self, db):
        if self.y_units == 'dB':
            return f'{db:.1f} dB'
        return three_sig_figs(10 ** (db / 20), self._units_str())

    def _trace_values_at(self, f):
        if self._f is None or len(self._f) < 2:
            return []
        idx = int(np.clip(np.round(f / self._f[1]), 0, len(self._f) - 1))
        return [(name, self._db[name][idx]) for name in _TRACES if name in self._db]

    def hover_lines(self, f):
        values = ', '.join(f'{name} {self._value_str(db)}' for name, db in self._trace_values_at(f))
        return [f'{f_str(f)}  {values}']

    def marker_lines(self):
        lines = []
        values = []
        for idx, f in enumerate(self.marker_freqs):
            v = self._trace_values_at(f)
            values.append(v[0][1] if v else None)
            s = ', '.join(f'{name} {self._value_str(db)}' for name, db in v)
            lines.append(f'M{idx + 1} {f_str(f)}  {s}')
        if len(self.marker_freqs) == 2 and None not in values:
            df = self.marker_freqs[1] - self.marker_freqs[0]
            sign = '-' if df < 0 else ''
            lines.append(f'Δ {sign}{f_str(abs(df))}  {values[1] - values[0]:+.1f} dB')
        return lines

    def peak_lines(self):
        return [f'{idx + 1}  {f_str(f)}  {self._value_str(db)}' for idx, (f, db) in enumerate(self.peaks)]

    def waterfall_hover_lines(self, f, fraction):
        duration = self.waterfall_time()
        t = fraction * duration
        lines = [f'{f_str(f)}  -{three_sig_figs(t, "s")}']
        row = int(fraction * self.waterfall.capacity)
        if self._f is not None and len(self._f) > 1 and 0 <= row < self.waterfall.count:
            data, _ = self.waterfall.newest(row + 1)
            idx = int(np.clip(np.round(f / self._f[1]), 0, len(self._f) - 1))
            db = data[row, idx]
            if np.isfinite(db):
                lines[0] += f'  {db:.1f} dB'
        return lines

    def hover(self, plot):
        if self._hover is not None and self._hover[0] is plot:
            return self._hover[1]
        return None

    def hover_set(self, plot, pos):
        prev = self._hover
        self._hover = None if pos is None else (plot, pos)
        if prev is not None and prev[0] is not plot:
            prev[0].update()
        plot.update()

    # ---- viewport and y-axis interaction ----

    def viewport_zoom(self, f_center, factor):
        if self._f is None:
            return
        f0, f1 = self.viewport()
        u0, u1, uc = self._u(f0), self._u(f1), self._u(f_center)
        r = [float(self._u_inv(uc + (u0 - uc) * factor)), float(self._u_inv(uc + (u1 - uc) * factor))]
        self._viewport_set(r, publish=True)

    def viewport_pan(self, start, dx, width):
        f0, f1 = start
        u0, u1 = self._u(f0), self._u(f1)
        du = -dx * (u1 - u0) / max(1.0, width)
        full0, full1 = self._full_range()
        du = min(max(du, self._u(full0) - u0), self._u(full1) - u1)
        self._viewport_set([float(self._u_inv(u0 + du)), float(self._u_inv(u1 + du))], publish=False)

    def _viewport_set(self, r, publish):
        if self._f is None:
            return
        full0, full1 = self._full_range()
        f0, f1 = max(r[0], full0), min(r[1], full1)
        if f1 - f0 < _MIN_VIEW_BINS * self._f[1]:
            return
        if f0 <= full0 and f1 >= full1:
            r = None
        else:
            r = [f0, f1]
        self._f_view = r
        self._cmap_cache = None
        self._derived_update()
        self._repaint()
        if publish:
            self.viewport_publish()

    def viewport_publish(self):
        self.setting_publish('f_range', self._f_view)

    def viewport_reset(self):
        self.setting_publish('f_range', None)
        self.setting_publish('y_autoscale', True)

    def y_zoom(self, center, factor):
        y0, y1 = self.y_view()
        r = [center + (y0 - center) * factor, center + (y1 - center) * factor]
        self.setting_publish('y_range', r)
        self.setting_publish('y_autoscale', False)

    # ---- markers ----

    def marker_move(self, index, f, publish):
        if f is not None and 0 <= index < len(self.marker_freqs):
            self.marker_freqs[index] = f
            self._repaint()
        if publish:
            self.setting_publish('markers', list(self.marker_freqs))

    def context_menu(self, plot, event, f, marker_index):
        menu = QtWidgets.QMenu(self)
        CallableAction(menu, N_('Add marker'), lambda: self.setting_publish('markers', self.marker_freqs + [f]))
        if self.peaks:
            peak = min(self.peaks, key=lambda p: abs(p[0] - f))[0]
            CallableAction(menu, N_('Add marker at peak'),
                           lambda: self.setting_publish('markers', self.marker_freqs + [peak]))
        if marker_index is not None:
            def remove():
                m = list(self.marker_freqs)
                m.pop(marker_index)
                self.setting_publish('markers', m)
            CallableAction(menu, N_('Remove marker'), remove)
        if self.marker_freqs:
            CallableAction(menu, N_('Clear markers'), lambda: self.setting_publish('markers', []))
        menu.addSeparator()
        traces = menu.addMenu(N_('Traces'))
        for name, label in [('live', N_('Live')), ('average', N_('Average')),
                            ('max', N_('Max hold')), ('min', N_('Min hold'))]:
            key = f'show_{name}'
            CallableAction(traces, label, self._toggle_factory(key),
                           checkable=True, checked=bool(getattr(self, key)))
        view = menu.addMenu(N_('View'))
        for key, label in [('x_log', N_('Logarithmic frequency')),
                           ('y_autoscale', N_('Autoscale y-axis')),
                           ('show_fft', N_('Show FFT')),
                           ('show_waterfall', N_('Show waterfall'))]:
            CallableAction(view, label, self._toggle_factory(key),
                           checkable=True, checked=bool(getattr(self, key)))
        units = menu.addMenu(N_('Y-axis units'))
        for value, label in SETTINGS['y_units']['options']:
            CallableAction(units, label, self._value_factory('y_units', value),
                           checkable=True, checked=self.y_units == value)
        self.source_selector.submenu_factory(menu)
        signal_menu = menu.addMenu(N_('Signal'))
        for signal_id, name in self._signals:
            CallableAction(signal_menu, name, self._value_factory('signal', signal_id),
                           checkable=True, checked=self.signal == signal_id)
        CallableAction(menu, N_('Clear'), lambda: self.on_action_clear())
        settings_action_create(self, menu)
        context_menu_show(menu, event)

    def _toggle_factory(self, key):
        def fn(checked=False):
            self.setting_publish(key, not bool(getattr(self, key)))
        return fn

    def _value_factory(self, key, value):
        def fn(checked=False):
            self.setting_publish(key, value)
        return fn

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            event.accept()
            menu = QtWidgets.QMenu(self)
            self.source_selector.submenu_factory(menu)
            settings_action_create(self, menu)
            context_menu_show(menu, event)
        else:
            super().mousePressEvent(event)

    # ---- settings ----

    def on_setting_signal(self, value):
        self._control.value_set('signal', value)
        if self.pubsub is not None:
            self._signals_update()

    def on_setting_hold(self, value):
        self._control.value_set('hold', bool(value))
        self._status_update()

    def on_setting_y_units(self, value):
        self._y_auto = None
        self._derived_update()
        self._repaint()

    def _display_update(self, value=None):
        self._derived_update()
        self._repaint()

    on_setting_show_live = _display_update
    on_setting_show_average = _display_update
    on_setting_show_max = _display_update
    on_setting_show_min = _display_update
    on_setting_peak_count = _display_update
    on_setting_peak_threshold = _display_update
    on_setting_peak_excursion = _display_update
    on_setting_intensity_follows_y = _display_update
    on_setting_intensity_min = _display_update
    on_setting_intensity_max = _display_update

    def on_setting_x_log(self, value):
        self._cmap_cache = None
        self._display_update()

    def on_setting_f_range(self, value):
        if value is not None and (len(value) != 2 or not np.isfinite(value).all()):
            value = None
        self._f_view = value
        self._cmap_cache = None
        self._display_update()

    def on_setting_y_autoscale(self, value):
        self._repaint()

    def on_setting_y_range(self, value):
        self._repaint()

    def on_setting_markers(self, value):
        self.marker_freqs = [float(f) for f in (value or [])]
        self._repaint()

    def on_setting_show_fft(self, value):
        self._fft.setVisible(bool(value))

    def on_setting_show_waterfall(self, value):
        self._waterfall.setVisible(bool(value))

    def on_setting_splitter(self, value):
        if value and len(value) == 2:
            self._splitter.setSizes([int(v) for v in value])

    def _on_splitter_moved(self, pos, index):
        self.setting_publish('splitter', self._splitter.sizes())

    def on_setting_colormap(self, value):
        self._color_table = None
        self._colorbar = None
        self._repaint()

    def on_setting_trace_width(self, value):
        self._style_cache = None
        self._repaint()

    def on_setting_frame_rate(self, value):
        self._worker.frame_period = 1.0 / max(1, int(value))

    def on_setting_control_location(self, value):
        control_location_apply(self._layout, self._control, value)

    # ---- status ----

    def _span_labels_update(self):
        if not self._fs_in:
            return
        labels = {}
        for value, _ in SETTINGS['decimate']['options']:
            labels[value] = f_str(self._fs_in / 2 / value)
        self._control.labels_set('decimate', labels)

    def _status_update(self):
        s = self._snapshot
        parts = []
        if self._data_topic is None:
            parts.append(N_('No signal'))
        elif self.hold:
            parts.append(N_('Hold'))
        if 'fs' in s:
            parts.append(f'RBW {f_str(s["rbw"])}')
            parts.append(f'{s["n"] // 2 + 1} bins')
            if s['gaps']:
                parts.append(N_('gaps {0}').format(s['gaps']))
            if self.average_mode != 'off':
                k = s['count'] if self.average_mode == 'cumulative' else min(s['count'], int(self.average_count))
                parts.append(f'avg {k}')
            t = self.waterfall_time()
            if t < 0.99 * float(self.waterfall_duration):
                parts.append(N_('waterfall {0}').format(three_sig_figs(t, 's')))
        overruns = self._worker.overruns
        if overruns:
            parts.append(N_('overruns {0}').format(overruns))
        self.status = ' | '.join(parts)
        self.status_warning = bool(overruns)
        self._fft.update()
