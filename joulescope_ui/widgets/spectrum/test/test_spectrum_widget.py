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

"""
Test joulescope_ui.widgets.spectrum.spectrum_widget and spectrum_plot
"""

import os
import threading
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6 import QtCore, QtWidgets
from joulescope_ui import pubsub_singleton, Metadata, CAPABILITIES, get_topic_name
from joulescope_ui.spectrum_engine import SpectrumEngine
from joulescope_ui.widgets.spectrum.spectrum_widget import SpectrumWidget
from joulescope_ui.widgets.spectrum.spectrum_plot import WaterfallHistory, WaterfallImage, \
    colormap_rgb, value_to_index, color_table
from joulescope_ui.spectrum_engine import column_map
from PySide6 import QtGui


FS = 100_000.0


def _app():
    app = QtWidgets.QApplication.instance()
    return app if app is not None else QtWidgets.QApplication([])


def _tone(f, rms, n, sample_id=0):
    t = (sample_id + np.arange(n)) / FS
    return (np.sqrt(2) * rms * np.sin(2 * np.pi * f * t)).astype(np.float32)


def _process_events(predicate, timeout=3.0):
    app = _app()
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if predicate():
            return True
        time.sleep(0.005)
    return False


class TestPlotHelpers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()

    def test_colormap_endpoints(self):
        for name in ['inferno', 'viridis', 'grayscale']:
            rgb = colormap_rgb(name, 255)
            self.assertEqual((255, 3), rgb.shape)
            lum = rgb.astype(float) @ [0.2126, 0.7152, 0.0722]
            self.assertLess(lum[0], 0.15 * 255, name)
            self.assertGreater(lum[-1], 0.75 * 255, name)
            self.assertGreater(np.mean(np.diff(lum) >= -1), 0.98, name)

    def test_color_table(self):
        table = color_table('inferno', QtGui.QColor(1, 2, 3))
        self.assertEqual(256, len(table))
        self.assertEqual(QtGui.QColor(1, 2, 3).rgba(), table[0])

    def test_value_to_index(self):
        idx = value_to_index(np.array([-200, -100, -50, 0, 10, np.nan]), -100, 0)
        np.testing.assert_equal([1, 1, 128, 255, 255, 0], idx)

    def test_history(self):
        h = WaterfallHistory()
        h.reset(3, 4)
        self.assertIsNone(h.newest_sample_id)
        rows = [{'sample_id': k, 'gap': k == 3, 'db': np.full(4, k, dtype=np.float32)} for k in range(1, 4)]
        h.append(rows)
        data, ids = h.newest()
        # row 3 had a gap, so an empty row precedes it
        np.testing.assert_equal([3, 3, 2], ids)
        np.testing.assert_equal([3, np.nan, 2], data[:, 0])
        self.assertEqual(3, h.count)
        h.append([{'sample_id': 9, 'gap': False, 'db': np.zeros(5, dtype=np.float32)}])  # wrong size
        self.assertEqual(3, h.newest_sample_id)

    def test_image_incremental_matches_rebuild(self):
        h = WaterfallHistory()
        h.reset(10, 64)
        f = np.arange(64, dtype=float)
        cmap = column_map(f, np.linspace(0, 64, 17))
        table = color_table('grayscale', QtGui.QColor(0, 0, 0))
        img = WaterfallImage()
        rng = np.random.default_rng(1)
        for k in range(14):
            h.append([{'sample_id': k, 'gap': False, 'db': rng.uniform(-100, 0, 64).astype(np.float32)}])
            img.update(h, cmap, 16, -100.0, 0.0, table, 'k')
        incremental = img._array.copy()
        img2 = WaterfallImage()
        img2.update(h, cmap, 16, -100.0, 0.0, table, 'k')
        np.testing.assert_equal(img2._array, incremental)
        self.assertEqual(16, img.image.width())
        self.assertEqual(10, img.image.height())


class TestSpectrumWidgetUnregistered(unittest.TestCase):
    """Display logic without pubsub."""

    @classmethod
    def setUpClass(cls):
        _app()

    def setUp(self):
        self.w = SpectrumWidget()
        self.w.resize(800, 600)
        self.w.show()

    def tearDown(self):
        self.w._worker.stop()
        self.w.close()
        self.w.deleteLater()

    def _snapshot(self, x, **cfg):
        config = {'fft_length': 1024, 'row_period': 0.01}
        config.update(cfg)
        self.w.setting_publish('fft_window', config.get('window', 'hann'))
        e = SpectrumEngine(config)
        e.process(0, FS, x)
        self.w._units = 'A'
        self.w._row_period = 0.01
        self.w.waterfall.reset(50, e.bins)
        self.w._on_snapshot({
            'generation': self.w._generation, 'overruns': 0, 'rows': e.rows_pop(),
            'fs': e.fs, 'fs_in': FS, 'n': e.n, 'decimate': e.decimate, 'rbw': e.rbw,
            'count': e.count, 'gaps': 0, 'live': e.live, 'average': e.average,
            'max': e.max, 'min': e.min})
        return e

    def test_defaults_in_controls(self):
        self.assertEqual(4096, self.w._control._combos['fft_length'].currentData())
        self.assertEqual('hann', self.w._control._combos['fft_window'].currentData())

    def test_peaks_and_render(self):
        x = _tone(10_000.0, 0.1, 50_000) + _tone(31_000.0, 0.01, 50_000)
        self.w.setting_publish('peak_threshold', -100.0)  # ignore float32 rounding noise
        self._snapshot(x, window='flattop')
        peaks = self.w.displayed_peaks()
        self.assertEqual(2, len(peaks))
        self.assertAlmostEqual(10_000.0, peaks[0][0], delta=FS / 1024)
        self.assertAlmostEqual(-20.0, peaks[0][1], delta=0.1)
        self.assertAlmostEqual(-40.0, peaks[1][1], delta=0.1)
        self.assertIn('RBW', self.w.status)
        self.w.setting_publish('markers', [10_000.0, 31_000.0])
        lines = self.w.marker_lines()
        self.assertEqual(3, len(lines))
        self.assertTrue(lines[2].startswith('Δ 21 kHz'))
        image = self.w.grab()
        self.assertFalse(image.isNull())

    def test_viewport_zoom_pan_reset(self):
        self._snapshot(_tone(10_000.0, 0.1, 20_000))
        full = self.w.viewport()
        self.assertEqual((0.0, FS / 2), full)
        self.w.viewport_zoom(10_000.0, 0.5)
        f0, f1 = self.w.viewport()
        self.assertAlmostEqual(5_000.0, f0)
        self.assertAlmostEqual(30_000.0, f1)
        self.assertEqual([f0, f1], self.w.f_range)
        self.w.viewport_pan((f0, f1), 100, 1000)  # drag right: view moves to lower f
        self.assertAlmostEqual(5_000.0 - 2_500.0, self.w.viewport()[0])
        self.w.viewport_pan((f0, f1), 10_000, 1000)  # clamped at 0 Hz
        self.assertAlmostEqual(0.0, self.w.viewport()[0])
        self.w.viewport_reset()
        self.assertEqual(full, self.w.viewport())

    def test_peaks_limited_to_viewport(self):
        x = _tone(10_000.0, 0.1, 50_000) + _tone(31_000.0, 0.01, 50_000)
        self.w.setting_publish('peak_threshold', -100.0)
        self._snapshot(x)
        self.w.setting_publish('f_range', [20_000.0, 40_000.0])
        self.assertEqual(1, len(self.w.peaks))
        self.assertAlmostEqual(31_000.0, self.w.peaks[0][0], delta=FS / 1024)

    def test_log_axis_mapping(self):
        self._snapshot(_tone(10_000.0, 0.1, 20_000))
        self.w.setting_publish('x_log', True)
        f0, f1 = self.w.viewport()
        self.assertAlmostEqual(FS / 1024, f0)
        rect = QtCore.QRectF(10, 0, 500, 100)
        for f in [200.0, 1000.0, 33_333.0]:
            self.assertAlmostEqual(f, self.w.x_to_f(self.w.f_to_x(f, rect), rect), delta=1e-6 * f)
        self.assertAlmostEqual(10 + 250, self.w.f_to_x(np.sqrt(f0 * f1), rect))
        self.assertFalse(self.w.grab().isNull())

    def test_y_autoscale_and_zoom(self):
        self._snapshot(_tone(10_000.0, 0.1, 20_000))
        y0, y1 = self.w.y_view()
        self.assertEqual(0, y1 % 10)
        self.assertGreater(y1, -20)
        self.assertLess(y1 - 20, 10)
        self.w.y_zoom(-50.0, 0.5)
        self.assertFalse(self.w.y_autoscale)
        self.assertAlmostEqual((y1 - y0) / 2, self.w.y_view()[1] - self.w.y_view()[0])
        self.w.viewport_reset()
        self.assertTrue(self.w.y_autoscale)

    def test_linear_units(self):
        self._snapshot(_tone(10_000.0, 0.1, 20_000), window='flattop')
        self.w.setting_publish('y_units', 'linear')
        self.assertEqual(0.0, self.w.y_view()[0])
        self.assertAlmostEqual(0.1, np.max(self.w.trace('average')), delta=0.002)
        self.assertEqual('A', self.w.y_label())
        self.w.setting_publish('scaling', 'psd')
        self.assertEqual('A/√Hz', self.w._units_str())
        self.assertFalse(self.w.grab().isNull())

    def test_traces_hidden(self):
        self._snapshot(_tone(10_000.0, 0.1, 20_000))
        self.assertIsNotNone(self.w.trace('live'))
        self.assertIsNone(self.w.trace('max'))
        self.w.setting_publish('show_max', True)
        self.assertIsNotNone(self.w.trace('max'))
        self.w.setting_publish('show_live', False)
        self.assertIsNone(self.w.trace('live'))

    def test_stale_generation_ignored(self):
        self._snapshot(_tone(10_000.0, 0.1, 20_000))
        peaks = self.w.displayed_peaks()
        self.w._on_snapshot({'generation': self.w._generation + 100, 'rows': []})
        self.assertEqual(peaks, self.w.displayed_peaks())
        self.assertIsInstance(peaks[0][0], float)

    def test_decimate_rolloff_hidden(self):
        self._snapshot(_tone(5_000.0, 0.1, 50_000), decimate=4)
        f0, f1 = self.w.viewport()
        self.assertAlmostEqual(FS / 2 / 4 * 0.9, f1)
        self.assertIn('RBW', self.w.status)

    def test_span_labels(self):
        self.w.resize(1600, 600)  # room for every control at its size hint
        _process_events(lambda: False, 0.1)
        combo = self.w._control._combos['decimate']
        width = combo.width()
        self.w._fs_in = 1_000_000
        self.w._span_labels_update()
        self.assertEqual('500 kHz', combo.itemText(0))
        self.assertEqual('31.25 kHz', combo.itemText(4))
        _process_events(lambda: combo.width() > width, 1.0)
        self.assertGreater(combo.width(), width)

    def test_waterfall_hover(self):
        self._snapshot(_tone(10_000.0, 0.1, 20_000))
        lines = self.w.waterfall_hover_lines(10_000.0, 0.0)
        self.assertIn('dB', lines[0])


class _FakeSource:
    """A signal stream source with an 'i' and a 'v' signal."""
    CAPABILITIES = []
    SETTINGS = {
        'name': {'dtype': 'str', 'brief': 'name', 'default': 'Fake'},
        'signals/i/name': {'dtype': 'str', 'brief': 'n', 'default': 'current'},
        'signals/i/enable': {'dtype': 'bool', 'brief': 'e', 'default': True},
        'signals/v/name': {'dtype': 'str', 'brief': 'n', 'default': 'voltage'},
        'signals/v/enable': {'dtype': 'bool', 'brief': 'e', 'default': False},
    }
    EVENTS = {
        'signals/i/!data': Metadata('obj', 'data'),
        'signals/v/!data': Metadata('obj', 'data'),
    }

    def __init__(self):
        self.CAPABILITIES = [CAPABILITIES.SOURCE, CAPABILITIES.SIGNAL_STREAM_SOURCE]


class TestSpectrumWidgetPubSub(unittest.TestCase):
    """End-to-end with pubsub: source selection, signals, data, and lifecycle."""

    @classmethod
    def setUpClass(cls):
        _app()

    def setUp(self):
        self.p = pubsub_singleton
        topic = 'registry/app/settings/defaults/signal_stream_source'
        if topic not in self.p:
            self.p.topic_add(topic, Metadata('str', 'default', default=None))
        self.threads = threading.active_count()
        self.source = _FakeSource()
        self.p.register(self.source, 'FakeSource-001')
        self.p.publish('registry/app/settings/defaults/signal_stream_source', 'FakeSource-001')
        self.w = SpectrumWidget()
        self.w.resize(800, 600)
        self.p.register(self.w)
        self.sample_id = 0

    def tearDown(self):
        self.p.unregister(self.w, delete=True)
        self.w.close()
        self.w.deleteLater()
        self.p.unregister(self.source, delete=True)
        _process_events(lambda: False, 0.05)

    def _push(self, signal='i', n=10_000, f=5_000.0, rms=0.01):
        self.p.publish(f'{get_topic_name(self.source)}/events/signals/{signal}/!data', {
            'sample_id': self.sample_id, 'sample_freq': FS, 'data': _tone(f, rms, n, self.sample_id),
            'dtype': 'f32', 'units': 'A', 'field': 'current'})
        self.sample_id += n

    def test_data_flow(self):
        self.assertEqual(threading.active_count(), self.threads + 1)
        self.assertEqual([('i', 'current')], self.w._signals)
        for _ in range(5):
            self._push()
        self.assertTrue(_process_events(lambda: len(self.w.peaks) > 0))
        self.assertAlmostEqual(5_000.0, self.w.peaks[0][0], delta=FS / 4096)
        self.assertEqual('A', self.w._units)

    def test_signal_enable_like_waveform(self):
        self.p.publish(f'{self.w.topic}/settings/signal', 'v')
        self.assertIsNone(self.w._data_topic)  # v disabled: no data, selection kept
        self.assertEqual('v', self.w.signal)
        self.assertEqual(False, self.p.query(f'{get_topic_name(self.source)}/settings/signals/v/enable'))
        self.p.publish(f'{get_topic_name(self.source)}/settings/signals/v/enable', True)
        self.assertIsNotNone(self.w._data_topic)
        self._push('v', f=2_000.0)
        self._push('v', f=2_000.0)
        self.assertTrue(_process_events(lambda: len(self.w.peaks) > 0))
        self.assertAlmostEqual(2_000.0, self.w.peaks[0][0], delta=FS / 4096)

    def test_setting_reconfigures(self):
        self.p.publish(f'{self.w.topic}/settings/fft_length', 1024)
        _process_events(lambda: not self.w._configure_pending)
        for _ in range(3):
            self._push()
        self.assertTrue(_process_events(lambda: self.w._snapshot.get('n') == 1024))
        self.assertEqual(1024, self.w._control._combos['fft_length'].currentData())

    def test_hold(self):
        self.p.publish(f'{self.w.topic}/settings/hold', True)
        for _ in range(3):
            self._push()
        _process_events(lambda: False, 0.2)
        self.assertEqual({}, self.w._snapshot)
        self.assertIn('Hold', self.w.status)

    def test_clear_action(self):
        for _ in range(3):
            self._push()
        self.assertTrue(_process_events(lambda: len(self.w.peaks) > 0))
        self.p.publish(f'{self.w.topic}/actions/!clear', None)
        self.assertEqual([], self.w.peaks)
        self.assertEqual(0, self.w.waterfall.count)

    def test_open_close_repeated(self):
        topic = f'{get_topic_name(self.source)}/events/signals/i/!data'
        for _ in range(5):
            self.p.unregister(self.w, delete=True)
            self.assertEqual(self.threads, threading.active_count())
            self.assertIsNone(self.w._data_topic)
            self.p.register(self.w)
            self.assertEqual(self.threads + 1, threading.active_count())
        self.assertEqual(topic, self.w._data_topic)
        self._push()
        self._push()
        self.assertTrue(_process_events(lambda: len(self.w.peaks) > 0))

    def test_unregister_stops_worker(self):
        self.p.unregister(self.w, delete=True)
        self.assertEqual(self.threads, threading.active_count())
        self._push()  # no subscriber, no error
        self.p.register(self.w)  # tearDown unregisters again


if __name__ == '__main__':
    unittest.main()
