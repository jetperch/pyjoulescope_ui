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

"""Test joulescope_ui.widgets.efficiency."""

import json
import os
import threading
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtCore, QtWidgets
from joulescope_ui import pubsub_singleton, Metadata, CAPABILITIES, get_topic_name
from joulescope_ui.test.test_efficiency_engine import js220, js320, constant, steps
from joulescope_ui.widgets.efficiency.efficiency_export import history_csv, curve_csv
import csv
import io
import tempfile
from joulescope_ui.widgets.efficiency import EfficiencyWidget
from joulescope_ui.widgets.efficiency.efficiency_readout import value_str, efficiency_str
from joulescope_ui.widgets.efficiency.efficiency_plot import finite_runs, reduce_to_columns
import numpy as np


def _app():
    app = QtWidgets.QApplication.instance()
    return app if app is not None else QtWidgets.QApplication([])


def _process_events(predicate, timeout=3.0):
    app = _app()
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        if predicate():
            return True
        time.sleep(0.005)
    return False


def _fake_source_cls(model):
    settings = {
        'name': {'dtype': 'str', 'brief': 'name', 'default': model},
        'info': {'dtype': 'obj', 'brief': 'info', 'default': {'model': model}},
        'statistics_frequency': {'dtype': 'float', 'brief': 'f', 'default': 2.0},
    }
    events = {}
    for signal, name in [('i', 'current'), ('v', 'voltage'), ('p', 'power')]:
        settings[f'signals/{signal}/name'] = {'dtype': 'str', 'brief': 'n', 'default': name}
        settings[f'signals/{signal}/enable'] = {'dtype': 'bool', 'brief': 'e', 'default': True}
        events[f'signals/{signal}/!data'] = Metadata('obj', 'data')

    class FakeSource:
        CAPABILITIES = []
        SETTINGS = settings
        EVENTS = events

        def __init__(self):
            self.CAPABILITIES = [CAPABILITIES.SOURCE, CAPABILITIES.SIGNAL_STREAM_SOURCE]

    # pubsub keys class metadata by class name
    FakeSource.__name__ = FakeSource.__qualname__ = f'FakeSource{model}'
    return FakeSource


class TestFormat(unittest.TestCase):

    def test_value_str(self):
        self.assertEqual('365.2 mW', value_str(0.36521, 'W'))
        self.assertEqual('31.52 mW', value_str(0.031521, 'W'))
        self.assertEqual('1.235 W', value_str(1.2346, 'W'))
        self.assertEqual('-12.30 µA', value_str(-12.3e-6, 'A'))
        self.assertEqual('---', value_str(None, 'W'))
        self.assertEqual('---', value_str(float('nan'), 'W'))

    def test_efficiency_str(self):
        self.assertEqual('91.37 %', efficiency_str(0.91372))
        self.assertEqual('--- %', efficiency_str(None))


class TestPlotHelpers(unittest.TestCase):

    def test_finite_runs(self):
        self.assertEqual([], finite_runs(np.zeros(0)))
        self.assertEqual([(0, 3)], finite_runs(np.array([1.0, 2.0, 3.0])))
        y = np.array([np.nan, 1.0, 2.0, np.nan, np.nan, 3.0, np.nan, 4.0, 5.0])
        self.assertEqual([(1, 3), (5, 6), (7, 9)], [(int(a), int(b)) for a, b in finite_runs(y)])

    def test_reduce_few_points_unchanged(self):
        x, y = np.arange(10.0), np.arange(10.0)
        xr, yr = reduce_to_columns(x, y, 0.0, 10.0, 100)
        self.assertIs(x, xr)
        self.assertIs(y, yr)

    def test_reduce_min_max_and_gaps(self):
        x = np.arange(1000) / 100.0        # 0 to 9.99
        y = np.sin(x * 7)
        y[500:520] = np.nan                # a gap in columns 5
        xr, yr = reduce_to_columns(x, y, 0.0, 10.0, 10)
        self.assertEqual(20, len(xr))
        np.testing.assert_allclose(np.repeat(np.arange(10) + 0.5, 2), xr)
        for col in range(10):
            seg = y[col * 100:(col + 1) * 100]
            if col == 5:
                self.assertTrue(np.all(np.isnan(yr[10:12])))
            else:
                self.assertAlmostEqual(np.min(seg), yr[2 * col])
                self.assertAlmostEqual(np.max(seg), yr[2 * col + 1])


class TestExport(unittest.TestCase):

    def test_history_csv(self):
        t0 = 260_000_000 * 2 ** 30
        t = np.array([t0, t0 + 2 ** 29], dtype=np.int64)
        f = io.StringIO(newline='')
        history_csv(f, t, {'efficiency': np.array([0.9, np.nan]), 'p_in': np.array([1.0, np.nan])},
                    {'input': 'JS220'})
        lines = f.getvalue().splitlines()
        self.assertEqual('# Joulescope efficiency time series', lines[0])
        self.assertEqual('# input: JS220', lines[1])
        rows = list(csv.reader(lines[2:]))
        self.assertEqual(['utc', 't (s)', 'efficiency', 'p_in (W)'], rows[0])
        self.assertEqual(['0.000000', '0.9', '1.0'], rows[1][1:])
        self.assertTrue(rows[1][0].startswith('2026-'))
        self.assertEqual(['0.500000', '', ''], rows[2][1:])  # invalid window: empty fields

    def test_curve_csv(self):
        f = io.StringIO(newline='')
        bins = [{'x': 0.01, 'x_min': 0.0094, 'x_max': 0.0106, 'efficiency': 0.9, 'efficiency_min': 0.89,
                 'efficiency_max': 0.91, 'count': 7, 'duration': 3.5, 'e_in': 0.1, 'e_out': 0.09}]
        curve_csv(f, bins, 'i_out', 'A', {})
        rows = list(csv.reader(f.getvalue().splitlines()[1:]))
        self.assertEqual('i_out (A)', rows[0][0])
        self.assertEqual(10, len(rows[0]))
        self.assertEqual(['0.01', '0.0094', '0.0106', '0.9', '0.89', '0.91', '7', '3.5', '0.1', '0.09'], rows[1])


class TestEfficiencyWidget(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()

    def setUp(self):
        self.p = pubsub_singleton
        for topic, meta in [
                ('registry/app/settings/defaults/signal_stream_source', Metadata('str', 'default', default=None)),
                ('registry/app/settings/signal_stream_enable', Metadata('bool', 'stream', default=True))]:
            if topic not in self.p:
                self.p.topic_add(topic, meta)
        self.p.publish('registry/app/settings/signal_stream_enable', True)
        self.threads = threading.active_count()
        self.sources = {}
        self._source_add('JS220-0001', 'JS220')
        self._source_add('JS320-0002', 'JS320')
        self.p.publish('registry/app/settings/defaults/signal_stream_source', 'JS220-0001')
        self.w = EfficiencyWidget()
        self.w.resize(700, 300)
        self.p.register(self.w)
        self.streams = None

    def _source_add(self, unique_id, model):
        source = _fake_source_cls(model)()
        self.p.register(source, unique_id)
        self.sources[unique_id] = source

    def tearDown(self):
        self.p.unregister(self.w, delete=True)
        self.w.close()
        self.w.deleteLater()
        for source in self.sources.values():
            self.p.unregister(source, delete=True)
        _process_events(lambda: False, 0.05)

    def _streams_create(self, p_in=1.0, p_out=0.9, i_out=0.3, source_in='JS220-0001', source_out='JS320-0002'):
        self.streams = [
            (source_in, 'p', js220(constant(p_in))),
            (source_out, 'p', js320(constant(p_out))),
            (source_out, 'i', js320(constant(i_out))),
        ]

    def _feed(self, duration, step=0.05):
        if self.streams is None:
            self._streams_create()
        t = max(s.t_next for _, _, s in self.streams)
        t_end = t + duration
        while t < t_end:
            t += step
            for source, signal, s in self.streams:
                topic = f'{get_topic_name(source)}/events/signals/{signal}/!data'
                for msg in s.until(t):
                    self.p.publish(topic, msg)
            _app().processEvents()

    def test_auto_assign(self):
        info = self.w.efficiency_info()
        self.assertEqual('JS220-0001', info['input'])
        self.assertEqual('JS320-0002', info['output'])
        self.assertEqual('JS220-0001', self.p.query(f'{self.w.topic}/settings/input_source'))
        self.assertEqual('JS320-0002', self.p.query(f'{self.w.topic}/settings/output_source'))
        self.assertEqual(threading.active_count(), self.threads + 1)
        self.assertEqual({('in', 'p'), ('out', 'p'), ('out', 'i')}, set(self.w._data_topics))

    def test_data_flow(self):
        self._feed(2.0)
        self.assertTrue(_process_events(lambda: self.w.efficiency_info()['totals'].get('windows', 0) >= 3))
        info = self.w.efficiency_info()
        json.dumps(info)
        w = info['window']
        self.assertAlmostEqual(0.9, w['efficiency'], delta=1e-6)
        self.assertAlmostEqual(1.0, w['p_in'], delta=1e-6)
        self.assertAlmostEqual(0.1, w['p_loss'], delta=1e-6)
        self.assertAlmostEqual(0.3, w['i_out'], delta=1e-6)
        self.assertAlmostEqual(0.5, w['t1'] - w['t0'], delta=1e-9)
        self.assertAlmostEqual(0.9, info['efficiency_cumulative'], delta=1e-6)
        self.assertEqual(0, info['overruns'])
        self.assertIn('2 Hz', info['status'])
        self.assertFalse(self.w.status_warning, info['status'])
        self.w._readout.grab()  # paints without error

    def test_statistics_frequency(self):
        self.p.publish(f'{get_topic_name("JS220-0001")}/settings/statistics_frequency', 10.0)
        self.assertAlmostEqual(0.1, self.w.period)
        self._feed(1.0)
        self.assertTrue(_process_events(lambda: self.w.efficiency_info()['window'] is not None))
        w = self.w.efficiency_info()['window']
        self.assertAlmostEqual(0.1, w['t1'] - w['t0'], delta=1e-9)
        # the output instrument rate does not matter
        self.p.publish(f'{get_topic_name("JS320-0002")}/settings/statistics_frequency', 1.0)
        self.assertAlmostEqual(0.1, self.w.period)

    def test_disabled_signal(self):
        enable_topic = f'{get_topic_name("JS320-0002")}/settings/signals/i/enable'
        self.p.publish(enable_topic, False)
        self.assertEqual(['out.i'], self.w.efficiency_info()['disabled'])
        self.assertIn('Disabled', self.w.status)
        self.assertTrue(self.w.status_warning)
        self.assertFalse(self.w._control.enable.isHidden())
        self.assertNotIn(('out', 'i'), self.w._data_topics)
        self.w.on_action_enable_signals()
        self.assertTrue(self.p.query(enable_topic))
        self.assertEqual([], self.w.efficiency_info()['disabled'])
        self.assertTrue(self.w._control.enable.isHidden())
        self.assertIn(('out', 'i'), self.w._data_topics)

    def test_show_vi_subscribes(self):
        self.p.publish(f'{self.w.topic}/settings/show_vi', True)
        self.assertEqual({('in', 'p'), ('in', 'v'), ('in', 'i'), ('out', 'p'), ('out', 'i'), ('out', 'v')},
                         set(self.w._data_topics))
        self.w._readout.grab()

    def test_swap(self):
        self.w.on_action_swap()
        info = self.w.efficiency_info()
        self.assertEqual('JS320-0002', info['input'])
        self.assertEqual('JS220-0001', info['output'])
        # data still flows from the physical instruments: efficiency > 100%
        self._streams_create(p_in=0.9, p_out=1.0, i_out=0.3, source_in='JS320-0002', source_out='JS220-0001')
        self._feed(2.5)
        self.assertTrue(_process_events(lambda: 'swap' in self.w.status))
        self.assertTrue(self.w.status_warning)

    def test_combos_follow_settings(self):
        combo = self.w._control._combos['output']
        self.assertEqual('JS320-0002', combo.currentData())
        self.p.publish(f'{self.w.topic}/settings/output_source', 'JS220-0001')
        self.assertEqual('JS220-0001', combo.currentData())
        self.w.on_action_swap()
        self.assertEqual('JS220-0001', self.w._control._combos['input'].currentData())
        self.assertEqual('JS220-0001', combo.currentData())

    def test_same_device(self):
        self.w.source_set('output', 'JS220-0001')
        self.assertEqual({}, self.w._data_topics)
        self.assertIn('different', self.w.status)
        self.assertTrue(self.w.status_warning)

    def test_missing_instrument(self):
        self._streams_create()
        self.streams = self.streams[:1]  # input only
        self._feed(0.5)
        self.w._rx_time['out'] = None
        self.w._status_update()
        self.assertIn('No data from JS320', self.w.status)

    def test_js110_input_warning(self):
        self._source_add('JS110-0003', 'JS110')
        self.w.source_set('input', 'JS110-0003')
        self.assertIn('JS110', self.w.status)
        self.w.source_set('input', 'JS220-0001')
        self.w.source_set('output', 'JS110-0003')  # correct as the output
        self.assertNotIn('JS110', self.w.status)

    def test_hold(self):
        self.p.publish(f'{self.w.topic}/settings/hold', True)
        self._feed(1.5)
        _process_events(lambda: False, 0.2)
        self.assertIsNone(self.w.efficiency_info()['window'])
        self.assertIn('Hold', self.w.status)

    def test_global_pause(self):
        topic = 'registry/app/settings/signal_stream_enable'
        self.p.publish(topic, False)
        try:
            self._feed(1.5)
            _process_events(lambda: False, 0.2)
            self.assertIsNone(self.w.efficiency_info()['window'])
            self.assertIn('Paused', self.w.status)
        finally:
            self.p.publish(topic, True)

    def test_clear(self):
        self._feed(1.5)
        self.assertTrue(_process_events(lambda: self.w.efficiency_info()['window'] is not None))
        self.w.on_action_clear()
        info = self.w.efficiency_info()
        self.assertIsNone(info['window'])
        self.assertIsNone(info['efficiency_cumulative'])
        self._feed(1.5)
        self.assertTrue(_process_events(lambda: self.w.efficiency_info()['window'] is not None))

    def test_narrow_readout(self):
        r = self.w._readout
        self.w.show()
        _process_events(lambda: False, 0.05)
        wide = r.height()
        self.assertEqual(r.sizeHint().height(), wide)
        narrow_width = r.minimumSizeHint().width()
        self.assertLess(narrow_width, r.sizeHint().width())
        self.assertGreater(r.heightForWidth(narrow_width), wide)
        r.resize(narrow_width, r.heightForWidth(narrow_width))
        r.grab()

    def test_time_plot(self):
        self.w.show()
        self._feed(3.0)
        self.assertTrue(_process_events(lambda: self.w.efficiency_info()['history'] >= 5))
        plot = self.w._time_plot
        x, y = plot.data()
        self.assertTrue(np.all(np.diff(x) > 0))
        self.assertEqual(0.0, x[-1])
        np.testing.assert_allclose(90.0, y, atol=1e-4)
        y0, y1 = plot.y_view(y)
        self.assertLess(y0, 90.0)
        self.assertGreater(y1, 90.0)
        self.assertLess(y1 - y0, 1.0)  # zoomed to the data, not 0 to 100%
        self.assertGreater(len(plot.grab().toImage().bits()), 0)
        # hover snaps to the nearest window
        plot._span = 5.0  # windows well apart in pixels
        x, y = plot.data()
        rect = plot.plot_rect()
        plot._hover = QtCore.QPointF(rect.right() - 1, rect.center().y())
        hover_x, lines = plot._hover_at(rect, x, y, lambda v: rect.left() + (np.asarray(v) + plot.span())
                                        * rect.width() / plot.span())
        self.assertAlmostEqual(rect.right(), hover_x)
        self.assertEqual(['0.000 s', '90.00 %'], lines)
        plot.grab()

    def test_time_plot_settings(self):
        self.assertEqual(600.0 / 0.5 + 4, self.w.history.capacity)
        self.p.publish(f'{self.w.topic}/settings/time_plot_duration', 60.0)
        self.assertEqual(60.0 / 0.5 + 4, self.w.history.capacity)
        self.p.publish(f'{get_topic_name("JS220-0001")}/settings/statistics_frequency', 10.0)
        self.assertEqual(60.0 / 0.1 + 4, self.w.history.capacity)
        self.p.publish(f'{self.w.topic}/settings/time_plot_enable', False)
        self.assertTrue(self.w._time_plot.isHidden())
        self.p.publish(f'{self.w.topic}/settings/time_plot_enable', True)
        self.assertFalse(self.w._time_plot.isHidden())

    def test_time_plot_zoom(self):
        plot = self.w._time_plot
        self.assertEqual(600.0, plot.span())
        plot._span = 30.0
        self.assertEqual(30.0, plot.span())
        self.p.publish(f'{self.w.topic}/settings/time_plot_duration', 10.0)
        self.assertEqual(10.0, plot.span())  # never wider than the history

    def test_time_plot_gap(self):
        self.w.show()
        self._feed(2.0)
        out = self.streams[1][2]
        out.skip()  # lose one output chunk
        self._feed(2.0)
        self.assertTrue(_process_events(lambda: len(finite_runs(self.w._time_plot.data()[1])) >= 2))
        _, y = self.w._time_plot.data()
        self.assertTrue(np.any(np.isnan(y)))
        self.assertEqual(1, self.w.efficiency_info()['totals']['invalid'])
        self.w._time_plot.grab()

    def test_clear_clears_history(self):
        self._feed(2.0)
        self.assertTrue(_process_events(lambda: self.w.efficiency_info()['history'] > 0))
        self.w.on_action_clear()
        self.assertEqual(0, self.w.efficiency_info()['history'])

    def _staircase(self, currents, eta, step=1.5, duration=None):
        p_out = [3.3 * i for i in currents]
        p_in = [p / e for p, e in zip(p_out, eta)]
        args = (step, 0.05)
        self.streams = [
            ('JS220-0001', 'p', js220(steps(p_in, *args))),
            ('JS320-0002', 'p', js320(steps(p_out, *args))),
            ('JS320-0002', 'i', js320(steps(currents, *args))),
        ]
        self._feed(step * len(currents) - 0.1 if duration is None else duration)

    def test_curve(self):
        currents, eta = [0.001, 0.01, 0.1], [0.7, 0.85, 0.9]
        self._staircase(currents, eta)
        self.assertTrue(_process_events(lambda: len(self.w.curve_bins()) == 3))
        bins = self.w.efficiency_info()['curve']
        for b, i, e in zip(bins, currents, eta):
            self.assertAlmostEqual(i, b['x'], delta=i * 1e-6)
            self.assertAlmostEqual(e, b['efficiency'], delta=1e-6)
            self.assertLessEqual(b['x_min'], i)
            self.assertGreater(b['x_max'], i)
        json.dumps(self.w.efficiency_info())
        self.assertIn('unsteady', self.w.status)  # windows spanning the steps
        plot = self.w._curve_plot
        self.w.show()
        plot.grab()
        self.p.publish(f'{self.w.topic}/settings/curve_x_scale', 'linear')
        plot.grab()
        self.assertIn('windows', plot.hover_lines(self.w.curve_bins()[0])[2])

    def test_curve_power_axis(self):
        self.p.publish(f'{self.w.topic}/settings/curve_x', 'power')
        self.assertNotIn(('out', 'i'), self.w._data_topics)  # not needed without show_vi
        self._staircase([0.01, 0.1], [0.8, 0.9])
        self.assertTrue(_process_events(lambda: len(self.w.curve_bins()) == 2))
        self.assertAlmostEqual(0.033, self.w.curve_bins()[0]['x'], delta=1e-6)
        self.p.publish(f'{self.w.topic}/settings/curve_x', 'current')
        self.assertIn(('out', 'i'), self.w._data_topics)
        self.assertEqual([], self.w.curve_bins())  # cleared: different x quantity

    def test_curve_hold_and_settings(self):
        self._staircase([0.01, 0.1, 0.001], [0.8, 0.9, 0.6], duration=2.9)
        self.assertTrue(_process_events(lambda: len(self.w.curve_bins()) == 2))
        self.p.publish(f'{self.w.topic}/settings/curve_hold', True)
        held = list(self.w.curve_bins())
        self._feed(1.4)
        _process_events(lambda: False, 0.3)
        self.assertEqual(held, self.w.curve_bins())
        self.assertIn('Curve hold', self.w.status)
        self.p.publish(f'{self.w.topic}/settings/curve_hold', False)
        self.assertTrue(_process_events(lambda: len(self.w.curve_bins()) == 3))
        self.p.publish(f'{self.w.topic}/settings/curve_bins_per_decade', 10)
        self.assertEqual([], self.w.curve_bins())

    def test_curve_empty_paint(self):
        self.w.show()
        self.assertEqual([], self.w.curve_bins())
        self.w._curve_plot.grab()

    def test_export(self):
        self._staircase([0.01, 0.1], [0.8, 0.9])
        self.assertTrue(_process_events(lambda: len(self.w.curve_bins()) == 2))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'history.csv')
            self.w.export_history(path)
            with open(path, newline='') as f:
                lines = f.read().splitlines()
            self.assertIn('# input: JS220', lines)
            self.assertIn('# output: JS320', lines)
            rows = list(csv.reader([x for x in lines if not x.startswith('#')]))
            self.assertEqual(self.w.efficiency_info()['history'] + 1, len(rows))
            path = os.path.join(d, 'curve.csv')
            self.w.export_curve(path)
            with open(path, newline='') as f:
                rows = list(csv.reader([x for x in f.read().splitlines() if not x.startswith('#')]))
            self.assertEqual('i_out (A)', rows[0][0])
            self.assertEqual(3, len(rows))
            self.assertAlmostEqual(0.8, float(rows[1][3]), delta=1e-6)

    def test_open_close_repeated(self):
        topics = dict(self.w._data_topics)
        for _ in range(5):
            self.p.unregister(self.w, delete=True)
            self.assertEqual(self.threads, threading.active_count())
            self.assertEqual({}, self.w._data_topics)
            self.p.register(self.w)
            self.assertEqual(self.threads + 1, threading.active_count())
        self.assertEqual(topics, self.w._data_topics)
        self._feed(1.5)
        self.assertTrue(_process_events(lambda: self.w.efficiency_info()['window'] is not None))


if __name__ == '__main__':
    unittest.main()
