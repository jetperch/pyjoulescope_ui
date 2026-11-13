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

"""Test the WaveformWidget trigger display placement."""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6 import QtWidgets

from joulescope_ui import time64
from joulescope_ui.widgets.waveform.waveform_widget import WaveformWidget, _TRIGGER_RSP_ID


_T0 = time64.YEAR * 55
_MS = time64.MILLISECOND
_FS = 1_000_000.0


class _TMap:
    """Map sample ids to time64 at _FS, starting at _T0."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sample_id_to_timestamp(self, k):
        return _T0 + (np.asarray(k, dtype=np.int64) * time64.SECOND) // int(_FS)


class TestWaveformTrigger(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        w = WaveformWidget(None)
        w.source_filter = 'JsdrvStreamBuffer:001'
        w._is_streaming = lambda: True
        w.trigger_mode = 'auto'
        w.trigger_source = 'i'
        w.trigger_edge = 'rising'
        w.trigger_level = 0.0
        w.trigger_hysteresis = 0.0
        w.trigger_position = 50.0
        w.trigger_holdoff = 0.0
        w.x_extent = [_T0, _T0 + 1000 * _MS]
        w.x_range = [_T0 + 990 * _MS, _T0 + 1000 * _MS]  # 10 ms view
        self.widget = w

    def tearDown(self):
        self.widget.close()

    def _history(self, times_ms):
        self.widget._trigger_scanner.history.extend([_T0 + t * _MS for t in times_ms])

    def test_auto_free_runs_without_trigger(self):
        w = self.widget
        self.assertEqual([_T0 + 990 * _MS, _T0 + 1000 * _MS], w._compute_x_range())
        self.assertEqual('auto', w._trigger_status)
        self.assertEqual(_T0 + 995 * _MS, w._trigger_epoch)  # 0 at the trigger position

    def test_auto_locks_to_newest_complete_trigger(self):
        w = self.widget
        self._history([980, 990, 997])  # 997 lacks 5 ms of post-trigger data
        self.assertEqual([_T0 + 985 * _MS, _T0 + 995 * _MS], w._compute_x_range())
        self.assertEqual('trig', w._trigger_status)
        self.assertEqual(_T0 + 990 * _MS, w._trigger_epoch)

    def test_position(self):
        w = self.widget
        w.trigger_position = 10.0
        self._history([980, 990])
        self.assertEqual([_T0 + 989 * _MS, _T0 + 999 * _MS], w._compute_x_range())

    def test_auto_free_runs_when_trigger_stale(self):
        w = self.widget
        self._history([500])  # far older than the auto timeout
        self.assertEqual([_T0 + 990 * _MS, _T0 + 1000 * _MS], w._compute_x_range())
        self.assertEqual('auto', w._trigger_status)

    def test_normal_holds_last_trigger(self):
        w = self.widget
        w.trigger_mode = 'normal'
        self._history([500])
        self.assertEqual([_T0 + 495 * _MS, _T0 + 505 * _MS], w._compute_x_range())
        self.assertEqual('ready', w._trigger_status)

    def test_normal_without_trigger_holds_view(self):
        w = self.widget
        w.trigger_mode = 'normal'
        w.x_range = [_T0 + 100 * _MS, _T0 + 110 * _MS]
        self.assertEqual([_T0 + 100 * _MS, _T0 + 110 * _MS], w._compute_x_range())
        self.assertEqual('ready', w._trigger_status)

    def test_single_captures_then_holds(self):
        w = self.widget
        w.trigger_mode = 'single'
        self._history([990])
        self.assertEqual([_T0 + 985 * _MS, _T0 + 995 * _MS], w._compute_x_range())
        self.assertEqual('stop', w._trigger_status)
        # a newer trigger does not replace the captured trigger
        self._history([994])
        w.x_extent = [_T0, _T0 + 1100 * _MS]
        self.assertEqual([_T0 + 985 * _MS, _T0 + 995 * _MS], w._compute_x_range())
        # arm captures the next trigger
        w.on_action_trigger(None, 'arm')
        self.assertEqual('ready', w._trigger_status)
        self.assertEqual(0, len(w._trigger_scanner.history))

    def test_view_duration_follows_zoom(self):
        w = self.widget
        self._history([990])
        w.x_range = [_T0 + 989 * _MS, _T0 + 991 * _MS]  # zoomed to 2 ms
        self.assertEqual([_T0 + 989 * _MS, _T0 + 991 * _MS], w._compute_x_range())

    def test_inactive_when_not_streaming(self):
        w = self.widget
        w._is_streaming = lambda: False
        self.assertFalse(w._trigger_active())
        w._is_streaming = lambda: True
        w.trigger_mode = 'off'
        self.assertFalse(w._trigger_active())

    def _response(self, start, samples):
        return {
            'rsp_id': _TRIGGER_RSP_ID,
            'response_type': 'samples',
            'data_type': 'f32',
            'data': np.asarray(samples, dtype=np.float32),
            'info': {
                'time_range_samples': {'start': start, 'end': start + len(samples) - 1, 'length': len(samples)},
                'time_map': {'counter_rate': _FS},
                'tmap': _TMap(),
            },
        }

    def test_response_to_trigger_times(self):
        w = self.widget
        s = w._trigger_scanner
        s.detector.configure('rising', 0.5)
        s.request(0, 2000, 1000, now=0.0)  # requests 1000..2000
        x = np.zeros(1001, dtype=np.float32)
        x[201:] = 1.0  # rising between samples 1200 and 1201
        w.on_callback_response(None, self._response(1000, x))
        t_expect = _T0 + 1200 * time64.SECOND // int(_FS) + int(np.rint(0.5 * time64.SECOND / _FS))
        self.assertEqual(t_expect, s.history.latest())
        self.assertEqual(2001, s.sample_next)

    def test_stale_response_ignored(self):
        w = self.widget
        s = w._trigger_scanner
        s.detector.configure('rising', 0.5)
        x = np.array([0, 1], dtype=np.float32)
        w.on_callback_response(None, self._response(1000, x))  # nothing requested
        self.assertEqual(0, len(s.history))

    def test_drag_publishes_once_at_end(self):
        w = self.widget
        w.unique_id = 'WaveformWidget:test'
        w._mouse_action = ['move.trigger.level']
        w._mouse_action_previous = ['trigger', None]
        w._trigger_drag = {'level': 0.25, 'position': 20.0}
        self.assertEqual(0.25, w._trigger_level())
        self.assertAlmostEqual(0.20, w._trigger_position())
        self.assertEqual(0.0, w.trigger_level)  # not yet applied
        w._mouse_action_end()
        self.assertEqual(0.25, w.trigger_level)
        self.assertEqual(20.0, w.trigger_position)
        self.assertEqual({}, w._trigger_drag)

    def test_digital_level(self):
        w = self.widget
        w.trigger_source = '0'
        w.trigger_level = 3.0
        self.assertEqual(0.5, w._trigger_level())

    def test_x_pan_moves_position(self):
        w = self.widget
        w.on_action_x_pan(1)
        self.assertEqual(25.0, w.trigger_position)
        w.on_action_x_pan(-4)
        self.assertEqual(100.0, w.trigger_position)


if __name__ == '__main__':
    unittest.main()
