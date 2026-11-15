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

"""Run the efficiency engine off the Qt event thread.

See docs/plans/efficiency.md "Threading".
"""

from joulescope_ui.efficiency_engine import EfficiencyEngine
from joulescope_ui.spectrum_engine import sample_count
from joulescope_ui.stream_worker import StreamWorker


_QUEUE_SECONDS = 3.0  # about 1 second for each of up to 3 streams


class EfficiencyWorker(StreamWorker):
    """Compute efficiency windows in a worker thread.

    Each snapshot is a dict with generation, windows (the new windows since
    the previous snapshot), totals, efficiency_cumulative, rejected, curve
    (the curve bins), and t_ref.
    """

    def __init__(self, on_snapshot, frame_period=1 / 30):
        self._windows = []  # worker thread only
        super().__init__(on_snapshot, frame_period, _QUEUE_SECONDS, name='efficiency_worker')

    def push(self, instrument, signal, value):
        """Add a SIGNAL_STREAM_SOURCE message.  Never blocks.

        :param instrument: 'in' or 'out'.
        :param signal: 'p', 'i' or 'v'.
        :param value: The message, which must not be modified later.
        :return: True if queued, False if dropped due to overrun.
        """
        n = sample_count(value['data'], value.get('dtype', 'f32'))
        return self._push(n / value['sample_freq'], (instrument, signal, value))

    def engine_create(self, config):
        return EfficiencyEngine(**config)

    def engine_data(self, engine, args):
        engine.push(*args)
        windows = engine.process()
        self._windows.extend(windows)
        return bool(windows)

    def engine_update(self, engine, config):
        if engine is not None:
            engine.configure(**config)

    def engine_clear(self, engine):
        self._windows = []
        if engine is not None:
            engine.clear()

    def snapshot(self, engine, generation):
        windows, self._windows = self._windows, []
        s = {'generation': generation, 'windows': windows}
        if engine is not None:
            s.update({
                't_ref': engine.t_ref,
                'totals': dict(engine.totals),
                'efficiency_cumulative': engine.efficiency_cumulative,
                'rejected': engine.rejected,
                'curve': engine.curve.bins(),
            })
        return s
