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

"""Test the StreamWorker base class."""

import queue
import threading
import unittest
from joulescope_ui.stream_worker import StreamWorker


class _Engine:
    def __init__(self, config):
        if config.get('fail'):
            raise ValueError('bad config')
        self.config = config
        self.total = 0
        self.clears = 0


class _Worker(StreamWorker):
    """Sum pushed values, with an optional gate to hold the worker thread."""

    def __init__(self, on_snapshot, **kwargs):
        self.gate = threading.Event()
        self.gate.set()
        self.threads = set()
        super().__init__(on_snapshot, **kwargs)

    def push(self, value, duration=0.1):
        return self._push(duration, (value,))

    def engine_create(self, config):
        return _Engine(config)

    def engine_data(self, engine, args):
        self.threads.add(threading.get_ident())
        self.gate.wait(2.0)
        if args[0] is None:
            raise RuntimeError('bad data')
        engine.total += args[0]
        return True

    def engine_clear(self, engine):
        if engine is not None:
            engine.total = 0
            engine.clears += 1

    def snapshot(self, engine, generation):
        if engine is None:
            return {'generation': generation, 'total': None}
        return {'generation': generation, 'total': engine.total, 'clears': engine.clears}


class TestStreamWorker(unittest.TestCase):

    def setUp(self):
        self.snapshots = queue.Queue()
        self.w = _Worker(self.snapshots.put, frame_period=0.001)
        self.w.start()

    def tearDown(self):
        self.w.gate.set()
        self.w.stop()
        self.assertFalse(self.w.is_running)

    def _wait(self, predicate, timeout=2.0):
        while True:
            s = self.snapshots.get(timeout=timeout)
            if predicate(s):
                return s

    def test_config_data_clear(self):
        g = self.w.configure({'a': 1})
        self.assertTrue(self.w.push(2))
        self.assertTrue(self.w.push(3))
        s = self._wait(lambda s: s.get('total') == 5)
        self.assertEqual(g, s['generation'])
        self.assertNotIn(threading.get_ident(), self.w.threads)
        self.w.clear()
        self._wait(lambda s: s.get('total') == 0 and s['clears'] == 2)
        g2 = self.w.configure({'a': 2})
        self.assertEqual(g + 1, g2)
        self._wait(lambda s: s['generation'] == g2 and s['total'] == 0)

    def test_data_before_config_ignored(self):
        self.w.push(7)
        g = self.w.configure({})
        self.w.push(1)
        self._wait(lambda s: s['generation'] == g and s['total'] == 1)

    def test_errors_do_not_stop_worker(self):
        g = self.w.configure({'fail': True})
        self._wait(lambda s: s['generation'] == g and s['total'] is None)
        self.w.push(1)  # no engine
        g = self.w.configure({})
        self.w.push(None)  # engine raises
        self.w.push(4)
        self._wait(lambda s: s['generation'] == g and s['total'] == 4)

    def test_overrun(self):
        self.w.configure({})
        self.w.gate.clear()  # hold the worker inside engine_data
        self.assertTrue(self.w.push(1, duration=0.6))
        self.assertTrue(self.w.push(1, duration=0.3))
        self.assertTrue(self.w.push(1, duration=0.1))
        self.assertFalse(self.w.push(1, duration=0.1))
        self.assertEqual(1, self.w.overruns)
        self.w.gate.set()
        self._wait(lambda s: s.get('total') == 3)
        self.assertTrue(self.w.push(1, duration=0.9))
        self._wait(lambda s: s.get('total') == 4)

    def test_first_push_always_queued(self):
        self.w.configure({})
        self.assertTrue(self.w.push(1, duration=5.0))  # larger than queue_seconds
        self._wait(lambda s: s.get('total') == 1)

    def test_stop_restart(self):
        self.w.stop()
        self.assertFalse(self.w.is_running)
        self.w.start()
        g = self.w.configure({})
        self.w.push(1)
        self._wait(lambda s: s['generation'] == g and s['total'] == 1)


if __name__ == '__main__':
    unittest.main()
