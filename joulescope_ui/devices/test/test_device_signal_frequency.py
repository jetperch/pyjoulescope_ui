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
Test the jsdrv Device signal sample rate open and change sequences.
"""

import types
import unittest
from joulescope_ui.devices.jsdrv.device import Device

_STREAM = 'registry/app/settings/signal_stream_enable'


class _Recorder(Device):
    """A Device whose thread runs commands immediately, recording all calls."""

    topic = 'registry/JS220-000001'

    def __init__(self, streaming, saved=None):
        self.calls = []
        values = {_STREAM: streaming, f'{self.topic}/settings/signal_frequency': saved}
        driver = types.SimpleNamespace(
            publish=lambda topic, value, timeout=None: self.calls.append(('driver', topic, value)))
        super().__init__(types.SimpleNamespace(driver=driver), 'u/js220/000001')
        self.pubsub = types.SimpleNamespace(
            query=lambda topic, **kwargs: values.get(topic, kwargs.get('default')),
            publish=lambda topic, value: self.calls.append(('pubsub', topic, value)))

    def _send_to_thread(self, cmd, args=None):
        assert cmd == 'signal_frequency'
        self._signal_frequency_apply(*args)


class TestSignalFrequency(unittest.TestCase):

    def test_first_value_only_sets_rate(self):
        d = _Recorder(streaming=True)
        d._signal_frequency_request(1_000_000)
        self.assertEqual([('driver', 'u/js220/000001/h/fs', 1_000_000)], d.calls)

    def test_change_while_streaming_restarts(self):
        d = _Recorder(streaming=True)
        d._signal_frequency_request(1_000_000)
        d.calls.clear()
        d._signal_frequency_request(10_000)
        self.assertEqual([('pubsub', _STREAM, False),
                          ('driver', 'u/js220/000001/h/fs', 10_000),
                          ('pubsub', _STREAM, True)], d.calls)

    def test_change_while_stopped_stays_stopped(self):
        d = _Recorder(streaming=False)
        d._signal_frequency_request(1_000_000)
        d.calls.clear()
        d._signal_frequency_request(10_000)
        self.assertEqual([('driver', 'u/js220/000001/h/fs', 10_000)], d.calls)

    def test_same_value_does_nothing(self):
        d = _Recorder(streaming=True)
        d._signal_frequency_request(10_000)
        d.calls.clear()
        d._signal_frequency_request(10_000)
        self.assertEqual([], d.calls)

    def test_open_applies_saved_rate(self):
        # Before open reports done, so a reconnect never streams at full rate.
        d = _Recorder(streaming=True, saved=100)
        d._signal_frequency_open()
        self.assertEqual([('driver', 'u/js220/000001/h/fs', 100)], d.calls)
        d.calls.clear()
        d._signal_frequency_request(100)  # retained setting from the settings subscribe
        self.assertEqual([], d.calls)

    def test_open_without_saved_rate(self):
        d = _Recorder(streaming=True)
        d._signal_frequency_open()
        self.assertEqual([], d.calls)
        d._signal_frequency_request(1_000)
        self.assertEqual([('driver', 'u/js220/000001/h/fs', 1_000)], d.calls)

    def test_change_after_open_restarts(self):
        d = _Recorder(streaming=True, saved=100)
        d._signal_frequency_open()
        d.calls.clear()
        d._signal_frequency_request(1_000)
        self.assertEqual([('pubsub', _STREAM, False),
                          ('driver', 'u/js220/000001/h/fs', 1_000),
                          ('pubsub', _STREAM, True)], d.calls)


if __name__ == '__main__':
    unittest.main()
