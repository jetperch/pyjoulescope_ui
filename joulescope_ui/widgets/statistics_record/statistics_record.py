# Copyright 2023 Jetperch LLC
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

from pyjls import Writer, SignalType, DataType
from joulescope_ui import pubsub_singleton, register, CAPABILITIES
from .statistics_record_config_widget import StatisticsRecordConfigDialog
import copy
import logging
import numpy as np


class ChunkMeta:
    NOTES = 0
    UI_META = 0x801


_DTYPE_MAP = {
    'f32': DataType.F32,
    'u8': DataType.U8,
    'u1': DataType.U1,
}


@register
class StatisticsRecord:
    CAPABILITIES = []
    _instances = []
    _log = logging.getLogger(f'{__name__}.cls')

    def __init__(self, topic, filename):
        parent = pubsub_singleton.query('registry/app/instance')
        self._topic = topic
        self._log = logging.getLogger(f'{__name__}.obj')
        self.CAPABILITIES = [CAPABILITIES.STATISTIC_STREAM_SINK]
        self._log.info('JLS record %s to %s', topic, filename)
        self._on_data_fn = self._on_data
        self._file = open(filename, 'wt')
        self._offsets = None

        pubsub_singleton.publish('registry/paths/actions/!mru_save', filename)
        pubsub_singleton.register(self, parent=parent)
        pubsub_singleton.subscribe(self._topic, self._on_data_fn, ['pub'])

    def _on_data(self, topic, value):
        if self._file is None:
            return
        dt = value['time']['delta']['value']
        freq = 1.0 / dt
        freq_log10 = int(np.ceil(max(0, np.log10(freq))))
        time_format = f'%.{freq_log10}f'
        hdr = '#time,current,voltage,power,charge,energy\n'
        t = value['time']['range']['value'][1]
        i = value['signals']['current']['avg']['value']
        v = value['signals']['voltage']['avg']['value']
        p = value['signals']['power']['avg']['value']
        c = value['accumulators']['charge']['value']
        e = value['accumulators']['energy']['value']

        if self._offsets is None:
            self._offsets = {
                'time': t,
                'charge': c,
                'energy': e,
            }
            self._file.write(hdr)
        t -= self._offsets['time']
        c -= self._offsets['charge']
        e -= self._offsets['energy']
        line = (time_format + ',%g,%g,%g,%g,%g\n') % (t, i, v, p, c, e)
        self._file.write(line)

    def on_action_stop(self, value):
        self._log.info('stop')
        pubsub_singleton.unsubscribe(self._topic, self._on_data_fn, ['pub'])
        f, self._file = self._file, None
        f.close()
        if self in StatisticsRecord._instances:
            StatisticsRecord._instances.remove(self)
        pubsub_singleton.unregister(self)

    @staticmethod
    def on_cls_action_start_request(pubsub, topic, value):
        StatisticsRecord._log.info('on_cls_action_start_request')
        StatisticsRecordConfigDialog()

    @staticmethod
    def on_cls_action_start(pubsub, topic, value):
        StatisticsRecord._log.info('on_cls_action_start')
        for topic, filename in value:
            obj = StatisticsRecord(topic, filename)
            StatisticsRecord._instances.append(obj)

    @staticmethod
    def on_cls_action_stop(pubsub, topic, value):
        StatisticsRecord._log.info('on_cls_action_stop')
        while len(StatisticsRecord._instances):
            obj = StatisticsRecord._instances.pop()
            obj.on_action_stop(value)
