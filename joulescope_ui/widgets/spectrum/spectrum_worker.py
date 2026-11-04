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

"""Run the spectrum engine off the Qt event thread.

Data and commands share one queue, so the engine needs no locks.
See docs/plans/completed/spectrum.md "Threading and data flow".
"""

from joulescope_ui.spectrum_engine import SpectrumEngine, sample_count, unpack
import logging
import queue
import threading
import time


_QUEUE_SECONDS = 1.0  # maximum queued input duration before dropping data


class SpectrumWorker:
    """Compute spectra in a worker thread.

    :param on_snapshot: The callable(snapshot) called from the worker
        thread at most once per frame_period.  Use a queued Qt signal to
        get back to the Qt thread.  The snapshot arrays are never modified
        after the call.
    :param frame_period: The minimum time between snapshots, in seconds.
    """

    def __init__(self, on_snapshot, frame_period=1 / 30):
        self._log = logging.getLogger(__name__)
        self._on_snapshot = on_snapshot
        self.frame_period = frame_period
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._queued_samples = 0
        self._generation = 0
        self._thread = None
        self.overruns = 0

    @property
    def is_running(self):
        return self._thread is not None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name='spectrum_worker', daemon=True)
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

        :param config: The SpectrumEngine configuration dict.
        :return: The configuration generation included in each snapshot.
        """
        self._generation += 1
        self._queue.put(('config', self._generation, dict(config)))
        return self._generation

    def clear(self):
        """Clear the traces and waterfall."""
        self._queue.put(('clear',))

    def push(self, sample_id, fs, data, dtype='f32'):
        """Add sample data.  Never blocks.

        :param sample_id: The sample id for data[0].
        :param fs: The sample rate in Hz.
        :param data: The sample data, which must not be modified later.
        :param dtype: The data type, see :func:`spectrum_engine.unpack`.
        :return: True if queued, False if dropped due to overrun.
        """
        n = sample_count(data, dtype)
        with self._lock:
            if self._queued_samples and self._queued_samples + n > fs * _QUEUE_SECONDS:
                self.overruns += 1
                return False
            self._queued_samples += n
        self._queue.put(('data', sample_id, fs, data, dtype, n))
        return True

    def _run(self):
        self._log.info('start')
        engine = None
        generation = 0
        dirty = False
        rows = []
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
                    _, sample_id, fs, data, dtype, n = item
                    with self._lock:
                        self._queued_samples -= n
                    if engine is not None:
                        try:
                            if engine.process(sample_id, fs, unpack(data, dtype)):
                                dirty = True
                        except Exception:
                            self._log.exception('engine process failed')
                elif cmd == 'config':
                    _, generation, config = item
                    rows = []
                    try:
                        engine = SpectrumEngine(config)
                    except Exception:
                        self._log.exception('invalid config %s', config)
                        engine = None
                    dirty = True
                elif cmd == 'clear':
                    rows = []
                    if engine is not None:
                        engine.clear()
                    dirty = True
            if engine is not None:
                rows.extend(engine.rows_pop())
            now = time.monotonic()
            if dirty and now >= t_next:
                snapshot = self._snapshot(engine, generation, rows)
                rows = []
                dirty = False
                t_next = now + self.frame_period
                try:
                    self._on_snapshot(snapshot)
                except Exception:
                    self._log.exception('on_snapshot failed')
        self._log.info('stop')

    def _snapshot(self, engine, generation, rows):
        s = {
            'generation': generation,
            'rows': rows,
        }
        if engine is None or engine.fs is None:
            return s
        s.update({
            'fs': engine.fs,
            'n': engine.n,
            'decimate': engine.decimate,
            'rbw': engine.rbw,
            'count': engine.count,
            'live': engine.live,
            'average': engine.average,
            'max': None if engine.max is None else engine.max.copy(),
            'min': None if engine.min is None else engine.min.copy(),
        })
        return s
