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
Test the jsdrv Device driver open retries.
"""

import types
import unittest
from unittest import mock
from joulescope_ui.devices.jsdrv import device
from joulescope_ui.devices.jsdrv.device import Device

_PATH = 'u/js320/000001'


class _Opener(Device):
    """A Device whose driver open fails a given number of times."""

    def __init__(self, failures):
        self.calls = []
        self._failures = failures
        driver = types.SimpleNamespace(open=self._open, close=self._close)
        super().__init__(types.SimpleNamespace(driver=driver), _PATH)

    def _open(self, path, mode=None, timeout=None):
        self.calls.append(('open', path, mode, timeout))
        if self._failures:
            self._failures -= 1
            raise TimeoutError('open timed out')

    def _close(self, path, timeout=None):
        self.calls.append(('close', path))


@mock.patch.object(device.time, 'sleep')
class TestDriverOpen(unittest.TestCase):

    def test_first_open_succeeds(self, sleep):
        d = _Opener(failures=0)
        self.assertEqual(0, d._driver_open())
        # The driver default timeout, not a shorter one.
        self.assertEqual([('open', _PATH, 'restore', None)], d.calls)
        sleep.assert_not_called()

    def test_retry_after_failed_open(self, sleep):
        d = _Opener(failures=2)
        self.assertEqual(0, d._driver_open())
        self.assertEqual(['open', 'close', 'open', 'close', 'open'], [c[0] for c in d.calls])
        self.assertEqual(2, sleep.call_count)

    def test_all_attempts_fail(self, sleep):
        d = _Opener(failures=device._OPEN_ATTEMPTS)
        self.assertEqual(1, d._driver_open())
        opens = [c for c in d.calls if c[0] == 'open']
        self.assertEqual(device._OPEN_ATTEMPTS, len(opens))
        self.assertEqual(device._OPEN_ATTEMPTS - 1, sleep.call_count)

    def test_quit_stops_retries(self, sleep):
        d = _Opener(failures=device._OPEN_ATTEMPTS)
        d._quit = True
        self.assertEqual(1, d._driver_open())
        self.assertEqual(['open', 'close'], [c[0] for c in d.calls])
        sleep.assert_not_called()
