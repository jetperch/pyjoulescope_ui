# Copyright 2022-2023 Jetperch LLC
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
The JLS v2 reader and common definitions for JLS v2 file format use.
"""


from joulescope_ui import Metadata, time64
from joulescope_ui.time_map import TimeMap
import logging
from pyjls import Reader, SignalType, data_type_as_str, DataType
import copy
import numpy as np


class ChunkMeta:
    NOTES = 0
    UI_META = 0x8001


DTYPE_MAP = {
    'f32': DataType.F32,
    'u8': DataType.U8,
    'u4': DataType.U4,
    'u1': DataType.U1,
}


TO_JLS_SIGNAL_NAME = {
    'i': 'current',
    'v': 'voltage',
    'p': 'power',
    'r': 'current_range',
    '0': 'gpi[0]',
    '1': 'gpi[1]',
    '2': 'gpi[2]',
    '3': 'gpi[3]',
    'T': 'trigger_in',
}


TO_UI_SIGNAL_NAME = {}


def _init():
    for key, value in list(TO_JLS_SIGNAL_NAME.items()):
        TO_JLS_SIGNAL_NAME[value] = value
        TO_UI_SIGNAL_NAME[value] = key
        TO_UI_SIGNAL_NAME[key] = key


_init()


class JlsV2:

    def __init__(self, path, pubsub, topic):
        self._log = logging.getLogger(__name__ + '.jls_v2')
        self._path = path
        self._jls = None
        self._signals = {}
        self.open(pubsub, topic)

    def open(self, pubsub, topic):
        if self._jls is not None:
            self.close()
        jls = Reader(self._path)
        self._jls = jls
        source_meta = {}

        def on_user_data_notes(chunk_meta_u16, data):
            if chunk_meta_u16 == ChunkMeta.NOTES and data is not None:
                pubsub.publish(f'{topic}/settings/notes', data)
                return True
            return False

        jls.user_data(on_user_data_notes)

        for source_id, source in jls.sources.items():
            pubsub.topic_add(f'{topic}/settings/sources/{source_id}/name',
                             Metadata('str', 'Source name', default=source.name))
            info = {
                'source': str(source_id),
                'vendor': source.vendor,
                'model': source.model,
                'version': source.version,
                'serial_number': source.serial_number,
                'name': f'{source.model}-{source.serial_number}',
            }
            pubsub.topic_add(f'{topic}/settings/sources/{source_id}/info',
                             Metadata('obj', 'Source metadata', default=info,
                                      flags=['hide', 'ro', 'skip_undo']))
            source_meta[source_id] = info
        for signal_id, signal in jls.signals.items():
            time_map = TimeMap()
            if signal.name not in TO_UI_SIGNAL_NAME:
                continue  # unsupported by UI, skip
            if signal.signal_type == SignalType.FSR:
                utc_first = None
                utc_last = None

                def utc_cbk(entries):
                    nonlocal utc_first, utc_last
                    if utc_first is None:
                        utc_first = entries[0, :]
                    utc_last = entries[-1, :]
                    return False

                jls.utc(signal.signal_id, 0, utc_cbk)
                g = signal.sample_rate / time64.SECOND
                if utc_first is None:
                    time_map.update(0, 0, g)
                elif utc_last[0] == utc_first[0]:
                    time_map.update(utc_first[0], utc_first[1], g)
                else:
                    d_utc = utc_last[1] - utc_first[1]
                    d_sample = utc_last[0] - utc_first[0]
                    time_map.update(utc_first[0], utc_first[1], d_sample / d_utc)

            signal_meta = copy.deepcopy(source_meta[signal.source_id])
            source_name = signal_meta['name']
            signal_subname = TO_UI_SIGNAL_NAME[signal.name]
            signal_name = f'{source_name}.{signal_subname}'

            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/name',
                             Metadata('str', 'Signal name', default=signal.name))
            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/meta',
                             Metadata('obj', 'Signal metadata', default=signal_meta,
                                      flags=['hide', 'ro', 'skip_undo']))
            sample_start, sample_end = 0, signal.length - 1
            range_meta = {
                'utc': [time_map.counter_to_time64(sample_start), time_map.counter_to_time64(sample_end)],
                'samples': {'start': sample_start, 'end': sample_end, 'length': signal.length},
                'sample_rate': signal.sample_rate,
            }
            self._log.info(f'{signal.name}: {range_meta}')
            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/range',
                             Metadata('obj', 'Signal range', default=range_meta,
                                      flags=['hide', 'ro', 'skip_undo']))
            self._signals[signal_name] = {
                'signal_id': signal.signal_id,
                'sample_rate': signal.sample_rate,
                'field': signal_subname,
                'units': signal.units,
                'data_type': data_type_as_str(signal.data_type),
                'length': signal.length,
                'time_map': time_map,
            }

    def process(self, req):
        """Handle a buffer request.

        :param req: The buffer request structure.
            See joulescope_ui.capabilities SIGNAL_BUFFER_SOURCE
        """
        if self._jls is None:
            return None
        signal_id = '.'.join(req['signal_id'].split('.')[-2:])
        signal = self._signals[signal_id]
        signal_id = signal['signal_id']
        req_end = req.get('end', 0)
        length = req.get('length', 0)
        if req['time_type'] == 'utc':
            time_map = signal['time_map']
            start = time_map.time64_to_counter(req['start'], dtype=np.int64)
            end = time_map.time64_to_counter(req_end, dtype=np.int64)
        else:
            start = req['start']
            end = req_end
        interval = end - start + 1
        response_type = 'samples'
        increment = 1
        data_type = signal['data_type']

        if not req_end:
            # self._log.info('fsr(%d, %d, %d)', signal_id, start, length)
            data = self._jls.fsr(signal_id, start, length)
        elif interval < 0:
            # self._log.warning('req with interval < 0: %r', req)
            return None
        elif not length:
            # self._log.info('fsr(%d, %d, %d)', signal_id, start, interval)
            data = self._jls.fsr(signal_id, start, interval)
        elif length and req_end and length <= (interval // 2):
            # round increment down
            increment = interval // length
            length = interval // increment
            # self._log.info('fsr_statistics(%d, %d, %d, %d)', signal_id, start, increment, length)
            data = self._jls.fsr_statistics(signal_id, start, increment, length)
            response_type = 'summary'
            data_type = 'f32'
        else:
            length = interval
            # self._log.info('fsr(%d, %d, %d)', signal_id, start, length)
            data = self._jls.fsr(signal_id, start, length)
        sample_id_end = start + increment * length - 1
        time_map = signal['time_map']

        info = {
            'version': 1,
            'field': signal['field'],
            'units': signal['units'],
            'time_range_utc': {
                'start': time_map.counter_to_time64(start),
                'end': time_map.counter_to_time64(sample_id_end),
                'length': length,
            },
            'time_range_samples': {
                'start': start,
                'end': sample_id_end,
                'length': length,
            },
            'time_map': {
                'offset_time': time_map.time_offset,
                'offset_counter': time_map.counter_offset,
                'counter_rate': signal['sample_rate'],
            },
        }
        # self._log.info(info)
        return {
            'version': 1,
            'rsp_id': req.get('rsp_id'),
            'info': info,
            'response_type': response_type,
            'data': data,
            'data_type': data_type,
        }

    def close(self):
        jls, self._jls = self._jls, None
        if jls is not None:
            jls.close()

