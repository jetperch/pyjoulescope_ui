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
The JLS v1 reader.
"""
import copy
import os
import logging
from joulescope_ui import Metadata, time64
from joulescope_ui.time_map import TimeMap
import numpy as np
import functools


# Only use joulescope package for the JLS v1 support
# Cannot use backend '1' since we use pyjoulescope_driver directly
# Cannot use backend '0' since macOS depends on libusb dynlibs that we do not package.
os.environ['JOULESCOPE_BACKEND'] = 'none'

from joulescope.data_recorder import DataReader


SIGNALS_V1 = {
    'i': {
        'index': 0,
        'name': 'current',
        'samples_name': 'current',
        'units': 'A',
    },
    'v': {
        'index': 1,
        'name': 'voltage',
        'samples_name': 'voltage',
        'units': 'V',
    },
    'p': {
        'index': 2,
        'name': 'power',
        'samples_name': 'power',
        'units': 'W',
    },
    'r': {
        'index': 3,
        'name': 'current_range',
        'samples_name': 'current_range',
        'units': '',
    },
    '0': {
        'index': 4,
        'name': 'gpi[0]',
        'samples_name': 'current_lsb',
        'units': '',
    },
    '1': {
        'index': 5,
        'name': 'gpi[1]',
        'samples_name': 'voltage_lsb',
        'units': ''
    },
}


class JlsV1:

    def __init__(self, path, pubsub, topic):
        for key, value in SIGNALS_V1.items():
            value['id'] = key
        self._log = logging.getLogger(__name__ + '.jls_v1')
        self._path = path
        self._jls = None
        self._time_map = TimeMap()
        self.open(pubsub, topic)
        self._samples_get_inner = functools.lru_cache(maxsize=64)(
            lambda start, end: self._jls.samples_get(start, end, units='samples'))
        self._summary_get_inner = functools.lru_cache(maxsize=64)(
            lambda start, end, increment: self._jls.data_get(start, end, increment, units='samples'))

    def open(self, pubsub, topic):
        time_map = self._time_map
        if self._jls is not None:
            self.close()
        jls = DataReader().open(self._path)
        self._jls = jls
        source_name = os.path.splitext(os.path.basename(self._path))[0]
        sample_start, sample_end = jls.sample_id_range
        sample_end -= 1
        fs = jls.sampling_frequency
        utc = 0  # can we do better than this?
        time_map.update(0, utc, fs / time64.SECOND)
        time_range = {
            'utc': [time_map.counter_to_time64(sample_start), time_map.counter_to_time64(sample_end)],
            'samples': {'start': sample_start, 'end': sample_end - 1, 'length': sample_end},
            'sample_rate': fs,
        }

        if jls.calibration is None:
            info = {
                'vendor': 'Jetperch LLC',
                'model': '__unknown__',
                'version': '0.0.0',
                'serial_number': '000000',
                'name': source_name,
            }
        else:
            c = jls.calibration.json()
            info = {
                'vendor': c['vendor_name'],
                'model': c['product_name'],
                'version': '0.0.0',
                'serial_number': c['serial_number'],
                'name': source_name,
            }
        pubsub.topic_add(f'{topic}/settings/sources/1/name',
                         Metadata('str', 'Source name', default=source_name))
        pubsub.topic_add(f'{topic}/settings/sources/1/info',
                         Metadata('obj', 'Source metadata', default=info,
                                  flags=['hide', 'ro', 'skip_undo']))

        meta = copy.deepcopy(info)
        meta['source'] = '1'
        for signal in SIGNALS_V1.keys():
            signal_id = f'1.{signal}'
            pubsub.topic_add(f'{topic}/settings/signals/{signal_id}/name',
                             Metadata('str', 'Signal name', default=signal))
            pubsub.topic_add(f'{topic}/settings/signals/{signal_id}/meta',
                             Metadata('obj', 'Signal metadata', default=meta,
                                      flags=['hide', 'ro', 'skip_undo']))
            pubsub.topic_add(f'{topic}/settings/signals/{signal_id}/range',
                             Metadata('obj', 'Signal range', default=time_range,
                                      flags=['hide', 'ro', 'skip_undo']))

    def _samples_get(self, signal_name, start, length):
        signal = SIGNALS_V1[signal_name]
        # self._log.info('_samples_get(%s, %d, %d)', signal['id'], start, length)
        data = self._samples_get_inner(start, start + length)
        return data['signals'][signal['samples_name']]['value']

    def _summary_get(self, signal_name, start, length, interval):
        signal = SIGNALS_V1[signal_name]
        # round increment down
        increment = interval // length
        length = interval // increment
        # self._log.info('fsr_statistics(%s, %d, %d, %d)', signal['id'], start, increment, length)
        if length == 1:
            data = self._jls.statistics_get(start, start + length * increment, units='samples')
            data = data['signals'][signal['samples_name']]
            data = np.array([[
                    data['µ']['value'],
                    np.sqrt(data['σ2']['value']),
                    data['min']['value'],
                    data['max']['value'],
                ]], dtype=np.float32)
        else:
            data = self._summary_get_inner(start, start + increment * length, increment)
            data = data[:, signal['index']]
            k = data['length']
            k[k < 1] = 1.0
            increment = np.max(k)
            d_cat = (
                data['mean'].reshape((-1, 1)),
                np.sqrt(data['variance'] / k).reshape((-1, 1)),
                data['min'].reshape((-1, 1)),
                data['max'].reshape((-1, 1)))
            data = np.concatenate(d_cat, axis=1)
        return data, increment

    def process(self, req):
        """Handle a buffer request.

        :param req: The buffer request structure.
            See joulescope_ui.capabilities SIGNAL_BUFFER_SOURCE
        """
        if self._jls is None:
            return None
        req_end = req.get('end', 0)
        length = req.get('length', 0)
        if req['time_type'] == 'utc':
            time_map = self._time_map
            start = time_map.time64_to_counter(req['start'], dtype=np.int64)
            end = time_map.time64_to_counter(req['end'], dtype=np.int64)
        else:
            start = req['start']
            end = req['end']
        signal_id = req['signal_id']
        interval = end - start + 1
        response_type = 'samples'
        increment = 1
        signal_name = signal_id.split('.')[-1]
        signal = SIGNALS_V1[signal_name]

        if not req_end:
            data = self._samples_get(signal_name, start, length)
        elif interval < 0:
            self._log.warning('req with interval < 0: %r', req)
            return None
        elif not length:
            data = self._samples_get(signal_name, start, interval)
        elif length and req_end and length <= (interval // 2):
            data, increment = self._summary_get(signal_name, start, length, interval)
            length = data.shape[0]
            response_type = 'summary'
        else:
            length = interval
            data = self._samples_get(signal_name, start, length)
        sample_id_end = start + increment * length - 1
        time_map = self._time_map

        info = {
            'version': 1,
            'field': signal_name,
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
                'counter_rate': time_map.time_to_counter_scale * time64.SECOND,
            },
        }
        # self._log.info(info)
        return {
            'version': 1,
            'rsp_id': req.get('rsp_id'),
            'info': info,
            'response_type': response_type,
            'data': data,
            'data_type': 'f32',
        }

    def close(self):
        jls, self._jls = self._jls, None
        if jls is not None:
            jls.close()
