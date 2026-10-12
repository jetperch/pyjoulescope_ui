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
Test Exporter JLS write error handling.
"""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from joulescope_ui import exporter
from joulescope_ui.exporter import Exporter
from joulescope_ui import time64


_ERROR_TOPIC = 'registry/ui/actions/!error_msg'
_UNIQUE_ID = 'Exporter:test'


class _Writer:
    """A pyjls Writer stand-in that creates the file and can fail on close."""

    close_error = None

    def __init__(self, path):
        with open(path, 'wb') as f:
            f.write(b'partial')
        self.closed = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def user_data(self, chunk_meta, data):
        pass

    def close(self):
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


class _CloseErrorWriter(_Writer):
    close_error = RuntimeError('jls_twr_close WRITE[5]: write failed')


def _exporter(path):
    value = {
        'x_range': [time64.YEAR, time64.YEAR + time64.SECOND],
        'signals': ['JsdrvStreamBuffer:001.JS220-000001.i'],
        'kwargs': {'path': path},
    }
    e = Exporter(value)
    e.unique_id = _UNIQUE_ID
    e.pubsub = Mock()
    e._rt.pubsub = e.pubsub
    e._jls_init = Mock()  # no signals: _export writes nothing
    return e


def _published(e, topic):
    return [c.args[1] for c in e.pubsub.publish.call_args_list if c.args[0] == topic]


class TestExporter(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, 'out.jls')
        self.e = None

    def tearDown(self):
        e, self.e = self.e, None
        if e is not None:
            e.on_pubsub_unregister()
        self._dir.cleanup()

    def _run(self, writer_cls):
        self.e = _exporter(self.path)
        with patch.object(exporter, 'Writer', writer_cls), \
                patch.object(exporter, 'pubsub_singleton') as singleton:
            self.e._RangeToolBase__run_outer()
        return singleton

    def _assert_finalized(self):
        finalize = f'registry/{_UNIQUE_ID}/actions/!finalize'
        self.assertEqual([None], _published(self.e, finalize))

    def test_success(self):
        singleton = self._run(_Writer)
        self.assertEqual([], _published(self.e, _ERROR_TOPIC))
        self.assertTrue(os.path.isfile(self.path))
        singleton.publish.assert_called_once_with('registry/paths/actions/!mru_save', self.path)
        self._assert_finalized()

    def test_close_error_reports_removes_and_finalizes(self):
        singleton = self._run(_CloseErrorWriter)
        errors = _published(self.e, _ERROR_TOPIC)
        self.assertEqual(1, len(errors))
        self.assertIn('WRITE', errors[0])
        self.assertIn(self.path, errors[0])
        self.assertFalse(os.path.exists(self.path))
        singleton.publish.assert_not_called()  # no mru_save
        self._assert_finalized()

    def test_request_timeout_reports_removes_and_finalizes(self):
        self.e = _exporter(self.path)
        self.e._jls_init = Mock(side_effect=TimeoutError('request timed out'))
        with patch.object(exporter, 'Writer', _Writer), \
                patch.object(exporter, 'pubsub_singleton'):
            self.e._RangeToolBase__run_outer()
        errors = _published(self.e, _ERROR_TOPIC)
        self.assertEqual(1, len(errors))
        self.assertIn('request timed out', errors[0])
        self.assertFalse(os.path.exists(self.path))
        self._assert_finalized()

    def test_open_error_keeps_existing_file(self):
        with open(self.path, 'wb') as f:
            f.write(b'existing')
        singleton = self._run(Mock(side_effect=RuntimeError('open failed')))
        self.assertEqual(1, len(_published(self.e, _ERROR_TOPIC)))
        with open(self.path, 'rb') as f:
            self.assertEqual(b'existing', f.read())
        singleton.publish.assert_not_called()
        self._assert_finalized()

    def test_cancel_removes_file(self):
        self.e = _exporter(self.path)
        e = self.e

        def jls_init(jls):
            e.on_action_cancel()  # unregister from the worker, as a race would
            e.pubsub.unregister.assert_called_once()
            e.on_pubsub_unregister()

        e._jls_init = jls_init
        with patch.object(exporter, 'Writer', _Writer), \
                patch.object(exporter, 'pubsub_singleton') as singleton:
            e._RangeToolBase__run_outer()
        self.assertTrue(e.abort)
        self.assertFalse(os.path.exists(self.path))
        singleton.publish.assert_not_called()
        self.assertEqual([], _published(e, f'registry/{_UNIQUE_ID}/actions/!finalize'))
        self.e = None  # already unregistered
