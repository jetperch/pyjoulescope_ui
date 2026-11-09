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
Test SignalRecord JLS writes: errors, sample rate and sample_id jumps.
"""

import logging
import time
import unittest
from unittest.mock import Mock, patch
import numpy as np
from joulescope_ui.widgets.signal_record.signal_record import SignalRecord


_TOPIC = 'registry/JsdrvStreamBuffer:001/events/signals/JS220-000001.i/!data'
_STOP_EVENT = 'registry/SignalRecord/events/!stop'


class _Writer:
    """A pyjls Writer stand-in whose fsr and close can fail."""

    def __init__(self, fsr_error=None, close_error=None):
        self.fsr_error = fsr_error
        self.close_error = close_error
        self.fsr_calls = 0
        self.fsr_sample_ids = []
        self.utc_entries = []
        self.closed = 0

    def utc(self, *args):
        self.utc_entries.append(args)

    def fsr(self, signal_id, sample_id, data):
        self.fsr_calls += 1
        self.fsr_sample_ids.append(sample_id)
        if self.fsr_error is not None:
            raise self.fsr_error

    def close(self):
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


def _recorder(jls):
    # Bypass __init__: it registers with the application pubsub singleton.
    r = object.__new__(SignalRecord)
    r._log = logging.getLogger(__name__)
    r._path = 'out.jls'
    r._write_error = None
    r._jls = jls
    r._utc_stop = None
    r._utc_range = None
    r._sources = {}
    r._signals = {_TOPIC: {
        'id': 1, 'name': 'current', 'utc_entry_prev': None, 'utc_data_prev': None,
        'sample_freq': 100, 'sample_id_next': None, 'offset': 0,
        'offset_changed': False, 'rate_mismatch': 0,
    }}
    r._status = {'time_last': time.time(), 'dropped': 0}
    r.pubsub = Mock()
    return r


def _value(sample_id, sample_freq=100, utc=0):
    return {'sample_id': sample_id, 'sample_freq': sample_freq, 'utc': utc,
            'data': np.zeros(100, dtype=np.float32)}


def _published(r, topic):
    return [c.args[1] for c in r.pubsub.publish.call_args_list if c.args[0] == topic]


class TestSignalRecord(unittest.TestCase):

    def test_overflow_drop_continues(self):
        jls = _Writer(fsr_error=RuntimeError('fsr BUSY[11]: The resource is busy'))
        r = _recorder(jls)
        r._on_data(_TOPIC, _value(0))
        r._on_data(_TOPIC, _value(100))
        self.assertEqual(2, jls.fsr_calls)
        self.assertEqual(200, r._status['dropped'])
        self.assertEqual([], _published(r, 'registry/ui/actions/!error_msg'))

    def test_write_error_stops_recording(self):
        ex = RuntimeError('fsr IO[4]: Input/output error')
        jls = _Writer(fsr_error=ex, close_error=ex)
        r = _recorder(jls)
        r._on_data(_TOPIC, _value(0))
        r._on_data(_TOPIC, _value(100))
        self.assertEqual(1, jls.fsr_calls)  # no writes after the error
        self.assertEqual(1, len(_published(r, 'registry/ui/actions/!error_msg')))
        self.assertEqual([False], _published(r, 'registry/app/settings/signal_stream_record'))
        r.on_action_stop()
        self.assertEqual(1, jls.closed)
        self.assertEqual(1, len(_published(r, 'registry/ui/actions/!error_msg')))  # not repeated
        r.pubsub.unregister.assert_called_once()

    def test_close_error_reported_and_cleanup_completes(self):
        jls = _Writer(close_error=RuntimeError('close IO[4]: Input/output error'))
        r = _recorder(jls)
        r._on_data(_TOPIC, _value(0))
        r.on_action_stop()
        self.assertEqual(1, jls.closed)
        self.assertEqual(1, len(_published(r, 'registry/ui/actions/!error_msg')))
        r.pubsub.unregister.assert_called_once()
        self.assertIn('out.jls', _published(r, 'registry/DiskMonitor:0/actions/!remove'))

    def test_last_stop_publishes_stop_event(self):
        # The record status indicator hides on events/!stop, even when the
        # recording stops through its own action instead of the toggle.
        a, b = _recorder(_Writer()), _recorder(_Writer())
        with patch.object(SignalRecord, '_instances', [a, b]):
            a.on_action_stop()
            self.assertEqual([], _published(a, _STOP_EVENT))   # b still records
            b.on_action_stop()
            self.assertEqual([True], _published(b, _STOP_EVENT))

    def test_contiguous_and_small_gap_pass_through(self):
        jls = _Writer()
        r = _recorder(jls)
        r._on_data(_TOPIC, _value(1000))
        r._on_data(_TOPIC, _value(1100))
        r._on_data(_TOPIC, _value(1500))   # 4 second gap: JLS fills with NaN
        r._on_data(_TOPIC, _value(1550))   # overlap: JLS trims
        self.assertEqual([1000, 1100, 1500, 1550], jls.fsr_sample_ids)
        self.assertEqual(1, len(jls.utc_entries))

    def test_sample_rate_mismatch_dropped(self):
        # A reconnecting device briefly streamed at 1 MHz into a 100 Hz recording.
        jls = _Writer()
        r = _recorder(jls)
        r._on_data(_TOPIC, _value(1000))
        r._on_data(_TOPIC, _value(10_000_000, sample_freq=1_000_000))
        r._on_data(_TOPIC, _value(1100))
        self.assertEqual([1000, 1100], jls.fsr_sample_ids)
        self.assertEqual(100, r._signals[_TOPIC]['rate_mismatch'])

    def test_large_forward_jump_not_filled(self):
        jls = _Writer()
        r = _recorder(jls)
        t = 1 << 30
        r._on_data(_TOPIC, _value(1000, utc=t))
        r._on_data(_TOPIC, _value(1100, utc=t + 1))
        r._on_data(_TOPIC, _value(1_000_000_000, utc=t + 2))
        r._on_data(_TOPIC, _value(1_000_000_100, utc=t + 3))
        self.assertEqual([1000, 1100, 1200, 1300], jls.fsr_sample_ids)
        # first entry, pin before the jump, entry at the new offset
        self.assertEqual([(1, 1000, t), (1, 1100, t + 1), (1, 1200, t + 2)], jls.utc_entries)
        self.assertEqual(1, len(_published(r, 'registry/ui/actions/!status_msg')))

    def test_sample_counter_reset_continues(self):
        jls = _Writer()
        r = _recorder(jls)
        r._on_data(_TOPIC, _value(500_000))
        r._on_data(_TOPIC, _value(500_100))
        r._on_data(_TOPIC, _value(0))   # device counter reset
        r._on_data(_TOPIC, _value(100))
        self.assertEqual([500_000, 500_100, 500_200, 500_300], jls.fsr_sample_ids)


if __name__ == '__main__':
    unittest.main()
