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
Test SignalRecord JLS write error handling.
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
        self.closed = 0

    def utc(self, *args):
        pass

    def fsr(self, *args):
        self.fsr_calls += 1
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
    r._signals = {_TOPIC: {'id': 1, 'name': 'current', 'utc_entry_prev': None, 'utc_data_prev': None}}
    r._status = {'time_last': time.time(), 'dropped': 0}
    r.pubsub = Mock()
    return r


def _value(sample_id):
    return {'sample_id': sample_id, 'utc': 0, 'data': np.zeros(100, dtype=np.float32)}


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


if __name__ == '__main__':
    unittest.main()
