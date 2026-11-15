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

"""Run a Qt-free signal stream engine in a worker thread.

Data and commands share one queue, so the engine needs no locks and sees
configuration changes in order with the data.  See
docs/plans/completed/spectrum.md, "Threading and data flow".
"""

import logging
import queue
import threading
import time


class StreamWorker:
    """Base class for an engine running in a worker thread.

    Subclasses implement the engine hooks, which run only on the worker
    thread: :meth:`engine_create`, :meth:`engine_data`,
    :meth:`engine_update`, :meth:`engine_clear`, :meth:`engine_poll`, and
    :meth:`snapshot`.

    :param on_snapshot: The callable(snapshot) called from the worker
        thread at most once per frame_period.  Use a queued Qt signal to
        get back to the Qt thread.  Snapshots must not be modified after
        the call.
    :param frame_period: The minimum time between snapshots, in seconds.
    :param queue_seconds: The maximum queued input duration, in seconds of
        sample data, before :meth:`push` drops data.
    :param name: The thread name.
    """

    def __init__(self, on_snapshot, frame_period=1 / 30, queue_seconds=1.0, name='stream_worker'):
        self._log = logging.getLogger(type(self).__module__)
        self._on_snapshot = on_snapshot
        self.frame_period = frame_period
        self.queue_seconds = queue_seconds
        self._name = name
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._queued_seconds = 0.0
        self._generation = 0
        self._thread = None
        self.overruns = 0

    @property
    def is_running(self):
        return self._thread is not None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
            self._thread.start()

    def stop(self, timeout=2.0):
        thread, self._thread = self._thread, None
        if thread is not None:
            self._queue.put(('quit',))
            thread.join(timeout)
            if thread.is_alive():
                self._log.warning('worker thread did not stop')

    def configure(self, config):
        """Apply a new engine configuration, which resets all state.

        :param config: The engine configuration dict.
        :return: The configuration generation included in each snapshot.
        """
        self._generation += 1
        self._queue.put(('config', self._generation, dict(config)))
        return self._generation

    def update(self, config):
        """Update the engine configuration in place, keeping its state.

        :param config: The partial engine configuration dict, passed to
            :meth:`engine_update`.
        """
        self._queue.put(('update', dict(config)))

    def clear(self):
        """Clear the engine results."""
        self._queue.put(('clear',))

    def _push(self, duration, args):
        """Queue data.  Never blocks.

        :param duration: The data duration in seconds, for backpressure.
        :param args: The tuple passed to :meth:`engine_data`, which must
            not be modified later.
        :return: True if queued, False if dropped due to overrun.
        """
        with self._lock:
            if self._queued_seconds and self._queued_seconds + duration > self.queue_seconds:
                self.overruns += 1
                return False
            self._queued_seconds += duration
        self._queue.put(('data', duration, args))
        return True

    # ---- engine hooks, called only from the worker thread ----

    def engine_create(self, config):
        """Create a new engine for config."""
        raise NotImplementedError()

    def engine_data(self, engine, args):
        """Process the data args from :meth:`_push`.

        :return: True if the snapshot changed.
        """
        raise NotImplementedError()

    def engine_update(self, engine, config):
        """Update the engine configuration in place, engine may be None."""
        pass

    def engine_clear(self, engine):
        """Clear the engine results, engine may be None."""
        pass

    def engine_poll(self, engine):
        """Called after each queue item or timeout, engine may be None."""
        pass

    def snapshot(self, engine, generation):
        """Get the snapshot, engine may be None."""
        raise NotImplementedError()

    def _run(self):
        self._log.info('start')
        engine = None
        generation = 0
        dirty = False
        t_next = time.monotonic()
        while True:
            timeout = max(0.0, t_next - time.monotonic()) if dirty else None
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                item = None
            if item is not None:
                cmd = item[0]
                if cmd == 'quit':
                    break
                elif cmd == 'data':
                    _, duration, args = item
                    with self._lock:
                        self._queued_seconds = max(0.0, self._queued_seconds - duration)
                    if engine is not None:
                        try:
                            if self.engine_data(engine, args):
                                dirty = True
                        except Exception:
                            self._log.exception('engine data failed')
                elif cmd == 'config':
                    _, generation, config = item
                    try:
                        engine = self.engine_create(config)
                    except Exception:
                        self._log.exception('invalid config %s', config)
                        engine = None
                    self.engine_clear(engine)
                    dirty = True
                elif cmd == 'update':
                    try:
                        self.engine_update(engine, item[1])
                    except Exception:
                        self._log.exception('invalid update %s', item[1])
                    dirty = True
                elif cmd == 'clear':
                    self.engine_clear(engine)
                    dirty = True
            self.engine_poll(engine)
            now = time.monotonic()
            if dirty and now >= t_next:
                snapshot = self.snapshot(engine, generation)
                dirty = False
                t_next = now + self.frame_period
                try:
                    self._on_snapshot(snapshot)
                except Exception:
                    self._log.exception('on_snapshot failed')
        self._log.info('stop')
