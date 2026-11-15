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
from joulescope_ui.test.test_efficiency_engine import js220, js320, constant
from joulescope_ui.widgets.efficiency import EfficiencyWidget
from joulescope_ui.widgets.efficiency.efficiency_readout import value_str, efficiency_str


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
