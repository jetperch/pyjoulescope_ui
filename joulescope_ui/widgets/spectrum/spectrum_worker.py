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

See docs/plans/completed/spectrum.md "Threading and data flow".
"""

from joulescope_ui.spectrum_engine import SpectrumEngine, sample_count, unpack
from joulescope_ui.stream_worker import StreamWorker


_QUEUE_SECONDS = 1.0  # maximum queued input duration before dropping data


class SpectrumWorker(StreamWorker):
    """Compute spectra in a worker thread.

    :param on_snapshot: The callable(snapshot) called from the worker
        thread at most once per frame_period.  Use a queued Qt signal to
        get back to the Qt thread.  The snapshot arrays are never modified
        after the call.
    :param frame_period: The minimum time between snapshots, in seconds.
    """

    def __init__(self, on_snapshot, frame_period=1 / 30):
        self._rows = []  # worker thread only
        super().__init__(on_snapshot, frame_period, _QUEUE_SECONDS, name='spectrum_worker')

    def push(self, sample_id, fs, data, dtype='f32'):
        """Add sample data.  Never blocks.

        :param sample_id: The sample id for data[0].
        :param fs: The sample rate in Hz.
        :param data: The sample data, which must not be modified later.
        :param dtype: The data type, see :func:`spectrum_engine.unpack`.
        :return: True if queued, False if dropped due to overrun.
        """
        return self._push(sample_count(data, dtype) / fs, (sample_id, fs, data, dtype))

    def engine_create(self, config):
        return SpectrumEngine(config)

    def engine_data(self, engine, args):
        sample_id, fs, data, dtype = args
        return engine.process(sample_id, fs, unpack(data, dtype))

    def engine_clear(self, engine):
        self._rows = []
        if engine is not None:
            engine.clear()

    def engine_poll(self, engine):
        if engine is not None:
            self._rows.extend(engine.rows_pop())

    def snapshot(self, engine, generation):
        rows, self._rows = self._rows, []
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
