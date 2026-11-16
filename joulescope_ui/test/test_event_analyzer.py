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

"""Test joulescope_ui.event_analyzer (Tools → Event Analyzer)."""

import hashlib
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from joulescope_ui import pubsub_singleton
from joulescope_ui import event_analyzer as ea
from joulescope_event_analyzer.synthetic import Capture, radio, sensor
from joulescope_event_analyzer.report import common as report_common


def _write_capture(path):
    cap = Capture(duration=1.0, fs=200_000, sleep=4e-6, noise=1e-6, seed=1)
    cap.add_periodic(radio(), period=0.375, phase=0.10, scale_spread=0.01)
    cap.add_periodic(sensor(), period=0.25, phase=0.03, scale_spread=0.01)
    return cap.write_jls(path)


class _PubSub:
    """Minimal pubsub for the dialog: records publishes, answers queries."""

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.published = []

    def query(self, topic, default=None):
        return self.values.get(topic, default)

    def publish(self, topic, value):
        self.published.append((topic, value))
        self.values[topic] = value


class TestHelpers(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_parse_value(self):
        self.assertIsNone(ea.parse_value(''))
        self.assertIsNone(ea.parse_value('  auto '))
        self.assertEqual(4e-6, ea.parse_value('4e-6'))
        self.assertAlmostEqual(4e-6, ea.parse_value('4 µA'))
        self.assertAlmostEqual(4e-6, ea.parse_value('4uA'))
        self.assertAlmostEqual(200e-6, ea.parse_value('200 µs'))
        self.assertEqual(220.0, ea.parse_value('220'))
        for bad in ['abc', 'nan', 'inf']:
            with self.assertRaises(ValueError):
                ea.parse_value(bad)
        with self.assertRaises(ValueError):
            ea.parse_value('', allow_none=False)

    def test_format_round_trip(self):
        for value, units in [(4.123e-6, 'A'), (2e-4, 's'), (0.3, ''), (220, ''), (1.5, 'A')]:
            self.assertAlmostEqual(value, ea.parse_value(ea.format_value(value, units)), delta=abs(value) * 1e-9)
        self.assertEqual('', ea.format_value(None, 'A'))

    def test_default_jls(self):
        jls = os.path.join(self.tmp, 'a.jls')
        open(jls, 'wb').close()
        txt = os.path.join(self.tmp, 'a.txt')
        open(txt, 'wb').close()
        missing = os.path.join(self.tmp, 'missing.jls')
        self.assertEqual(jls, ea.default_jls([missing, txt, jls]))
        self.assertEqual('', ea.default_jls([]))
        self.assertEqual('', ea.default_jls(None))

    def test_default_output_dir(self):
        path = os.path.join(self.tmp, 'cap.jls')
        self.assertEqual(os.path.join(self.tmp, 'cap_events'), ea.default_output_dir(path))
        self.assertEqual('', ea.default_output_dir(''))

    def test_options_to_config(self):
        cfg = ea.options_to_config({'sleep_current': 4e-6, 'start_threshold': None, 'merge_gap': 1e-3,
                                    'match_tolerance': 0.2, 'battery_capacity_mAh': 220})
        self.assertEqual(4e-6, cfg.sleep.level)
        self.assertIsNone(cfg.detect.start_threshold)
        self.assertEqual(1e-3, cfg.detect.merge_gap)
        self.assertEqual(0.2, cfg.match.tolerance)
        self.assertEqual(220, cfg.report.battery_capacity_mAh)
        self.assertEqual(ea.PLOTLY_PATH, cfg.report.plotly)
        default = ea.options_to_config({})
        self.assertEqual(200e-6, default.detect.merge_gap)

    def test_bundled_plotly_matches_analyzer(self):
        with open(ea.PLOTLY_PATH, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(report_common.PLOTLY_SHA256, digest)

    def test_settings_registered(self):
        for name in ea.SETTINGS:
            pubsub_singleton.query(f'registry/event_analyzer/settings/{name}')

    def test_settings_skip_undo(self):
        topic = 'registry/event_analyzer/settings/merge_gap'
        undos = len(pubsub_singleton.undos)
        pubsub_singleton.publish(topic, 1e-3)
        pubsub_singleton.process()
        self.assertEqual(1e-3, pubsub_singleton.query(topic))
        self.assertEqual(undos, len(pubsub_singleton.undos))
        pubsub_singleton.publish(topic, None)
        pubsub_singleton.process()


class TestRun(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.jls = _write_capture(os.path.join(cls._tmp.name, 'cap.jls'))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_run_analysis(self):
        out = os.path.join(self._tmp.name, 'run')
        fractions = []
        files = ea.run_analysis(self.jls, out, {'battery_capacity_mAh': 220},
                                progress=lambda f, m: fractions.append(f))
        self.assertEqual({'csv', 'html', 'summary'}, set(files))
        self.assertTrue(all(os.path.isfile(p) for p in files.values()))
        with open(files['html'], encoding='utf-8') as f:
            page = f.read()
        self.assertIn('plotly.js v2.35.2', page)          # bundled copy embedded
        self.assertNotIn('<script src="https://cdn', page)
        self.assertTrue(fractions)
        self.assertTrue(ea.report_exists(self.jls, out))

    def test_run_analysis_cancel(self):
        out = os.path.join(self._tmp.name, 'cancel')
        event = threading.Event()
        event.set()
        with self.assertRaises(ea.Cancelled):
            ea.run_analysis(self.jls, out, {}, cancel_event=event)
        self.assertFalse(os.path.exists(out))


class TestDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls._tmp = tempfile.TemporaryDirectory()
        cls.jls = _write_capture(os.path.join(cls._tmp.name, 'cap.jls'))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.pubsub = _PubSub({
            'registry/paths/settings/mru_files': [self.jls],
            'registry/event_analyzer/settings/merge_gap': 1e-3,
        })
        self.dialog = ea.EventAnalyzerDialog(None, pubsub=self.pubsub)
        self.warnings = []
        p = mock.patch.object(QtWidgets.QMessageBox, 'warning',
                              side_effect=lambda parent, title, msg: self.warnings.append(msg))
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.dialog.deleteLater()
        self._app.processEvents()

    def _edit(self, name):
        return self.dialog.findChild(QtWidgets.QLineEdit, name)

    def _wait(self, predicate, timeout=30.0):
        t_end = time.time() + timeout
        while not predicate():
            self.assertLess(time.time(), t_end, 'timeout')
            self._app.processEvents()
            time.sleep(0.01)

    def test_defaults_from_settings(self):
        self.assertEqual(self.jls, self._edit('path').text())
        self.assertEqual(ea.default_output_dir(self.jls), self._edit('output').placeholderText())
        self.assertEqual('1 ms', self._edit('merge_gap').text())
        self.assertEqual('', self._edit('sleep_current').text())
        self.assertAlmostEqual(1e-3, self.dialog.options()['merge_gap'])

    def test_invalid_option(self):
        self._edit('match_tolerance').setText('abc')
        with self.assertRaises(ValueError):
            self.dialog.options()
        self._edit('match_tolerance').setText('-1')
        with self.assertRaises(ValueError):
            self.dialog.options()
        self.dialog._on_run()
        self.assertEqual(1, len(self.warnings))
        self.assertIsNone(self.dialog._worker)

    def test_missing_file(self):
        self._edit('path').setText(os.path.join(self._tmp.name, 'missing.jls'))
        self.dialog._on_run()
        self.assertEqual(1, len(self.warnings))
        self.assertIsNone(self.dialog._worker)

    def test_run_opens_report_and_saves_settings(self):
        out = os.path.join(self._tmp.name, 'dialog_out')
        self._edit('output').setText(out)
        self._edit('battery_capacity_mAh').setText('220')
        self.dialog._on_run()
        self.assertIsNotNone(self.dialog._worker)
        self._wait(lambda: self.dialog.files is not None)
        self.assertEqual(os.path.join(out, 'cap_events.html'), self.dialog.files['html'])
        urls = [v for t, v in self.pubsub.published if t == 'registry/ui/actions/!url_open']
        self.assertEqual(1, len(urls))
        self.assertTrue(urls[0].startswith('file:') and urls[0].endswith('cap_events.html'))
        self.assertEqual(220, self.pubsub.values['registry/event_analyzer/settings/battery_capacity_mAh'])
        self.assertEqual([], self.warnings)

        # running again into the same directory asks before replacing
        dialog2 = ea.EventAnalyzerDialog(None, pubsub=self.pubsub)
        dialog2.findChild(QtWidgets.QLineEdit, 'output').setText(out)
        with mock.patch.object(dialog2, 'confirm_overwrite', return_value=False) as confirm:
            dialog2._on_run()
        confirm.assert_called_once()
        self.assertIsNone(dialog2._worker)
        dialog2.deleteLater()

    def test_cancel(self):
        self._edit('output').setText(os.path.join(self._tmp.name, 'dialog_cancel'))
        started = threading.Event()
        release = threading.Event()

        def slow_progress(fraction, msg):   # hold the worker until the test cancels
            started.set()
            release.wait(10)

        real_run = ea.run_analysis
        with mock.patch.object(ea, 'run_analysis',
                               side_effect=lambda *a, **k: real_run(*a[:3], progress=slow_progress,
                                                                    cancel_event=k['cancel_event'])):
            self.dialog._on_run()
            self.assertTrue(started.wait(10))
            self.dialog._on_cancel()
            release.set()
            self._wait(lambda: self.dialog._worker is None)
        self.assertEqual('Cancelled', self.dialog.findChild(QtWidgets.QLabel, 'status').text())
        self.assertIsNone(self.dialog.files)
        self.assertEqual([], self.warnings)
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, 'dialog_cancel')))


if __name__ == '__main__':
    unittest.main()
