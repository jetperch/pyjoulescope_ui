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


from joulescope_ui import Metadata
import logging
from pyjls import Reader, SignalType, data_type_as_str, DataType, TimeMap, time64
import copy


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
    '7': 'trigger_in',
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
                if not isinstance(data, str):
                    data = str(data)
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
                'sample_rate': 2_000_000
            }
            pubsub.topic_add(f'{topic}/settings/sources/{source_id}/info',
                             Metadata('obj', 'Source metadata', default=info,
                                      flags=['hide', 'ro', 'skip_undo']))
            source_meta[source_id] = info
        for signal_id, signal in jls.signals.items():
            if signal.name not in TO_UI_SIGNAL_NAME:
                continue  # unsupported by UI, skip

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
            utc_start, utc_end = jls.sample_id_to_timestamp(signal_id, [sample_start, sample_end])
            fs_in_nominal = signal_meta['sample_rate']
            try:
                fs_estimated = signal.length * time64.SECOND / (utc_end - utc_start)
            except Exception:
                fs_estimated = signal.sample_rate
            decimate_factor = fs_in_nominal // signal.sample_rate
            range_meta = {
                'utc': [utc_start, utc_end],
                'samples': {'start': sample_start, 'end': sample_end, 'length': signal.length},
                'sample_rate': signal.sample_rate,
            }
            self._log.info(f'{signal.name}: {range_meta}')
            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/range',
                             Metadata('obj', 'Signal range', default=range_meta,
                                      flags=['hide', 'ro', 'skip_undo']))

            self._signals[signal_name] = {
                'signal_id': signal.signal_id,
                'field': signal_subname,
                'units': signal.units,
                'data_type': data_type_as_str(signal.data_type),
                'length': signal.length,
                'tmap': TimeMap(jls, signal_id),
                'sample_rate': {
                    'in_nominal': fs_in_nominal,
                    'in_estimated': fs_estimated * decimate_factor,
                    'decimate_factor': decimate_factor,
                    'nominal': signal.sample_rate,
                    'estimated': fs_estimated,
                }
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
        req_start = req['start']
        req_end = req.get('end', 0)
        length = req.get('length', 0)
        if req['time_type'] == 'utc':
            tmap = signal['tmap']
            start = tmap.timestamp_to_sample_id(req_start)
            if req_end:
                end = tmap.timestamp_to_sample_id(req_end)
            else:
                end = 0
        else:
            start = req_start
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
        tmap = signal['tmap']
        t0, t1 = tmap.sample_id_to_timestamp([start, sample_id_end])
        dx = sample_id_end - start
        if dx == 0:
            dt = tmap.sample_id_to_timestamp(start + 1) - t0
            dx = 1
        else:
            dt = t1 - t0
        counter_rate = dx * time64.SECOND / dt

        info = {
            'version': 1,
            'field': signal['field'],
            'units': signal['units'],
            'time_range_utc': {
                'start': t0,
                'end': t1,
                'length': length,
            },
            'time_range_samples': {
                'start': start,
                'end': sample_id_end,
                'length': length,
            },
            'time_map': {
                'offset_counter': start,
                'offset_time': t0,
                'counter_rate': counter_rate,
            },
            'tmap': tmap,
            'sample_rate': copy.deepcopy(signal['sample_rate']),
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

