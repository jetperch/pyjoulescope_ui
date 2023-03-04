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

from pyjls import Reader, SignalType, data_type_as_str
from joulescope_ui import CAPABILITIES, Metadata, time64, register, get_topic_name
from joulescope_ui.jls_v2 import TO_UI_SIGNAL_NAME
import copy
import logging
import os
import numpy as np
import queue
import threading


_V1_PREFIX = bytes([0xd3, 0x74, 0x61, 0x67, 0x66, 0x6d, 0x74, 0x20, 0x0d, 0x0a, 0x20, 0x0a, 0x20, 0x20, 0x1a, 0x1c])
_V2_PREFIX = bytes([0x6a, 0x6c, 0x73, 0x66, 0x6d, 0x74, 0x0d, 0x0a, 0x20, 0x0a, 0x20, 0x1a, 0x20, 0x20, 0xb2, 0x1c])
_log = logging.getLogger(__name__)


def _jls_version_detect(filename):
    """Detect the JLS version.

    :param filename: The JLS filename.
    :return: 1 or 2
    """
    if hasattr(filename, 'read') and hasattr(filename, 'seek'):
        d = filename.read(16)
        filename.seek(0)
    else:
        with open(filename, 'rb') as f:
            d = f.read(16)
    if d == _V2_PREFIX:
        return 2
    elif d == _V1_PREFIX:
        return 1
    else:
        raise RuntimeError('unsupported file prefix')


class JlsV2:

    def __init__(self, path, pubsub, topic):
        self._log = logging.getLogger(__name__ + '.jls_v2')
        self._path = path
        self._pubsub = pubsub
        self._topic = topic
        self._jls = None
        self._quit = False
        self._time_map = None  # sample_offset, utc_offset_t64, gain_sample_to_utc, gain_utc_to_sample
        self._signals = {}
        self._queue = queue.Queue()
        self.open()

    def _time_samples_to_utc(self, sample):
        sample_offset, utc_offset_t64, gain_sample_to_utc, _ = self._time_map
        return int(np.rint((sample - sample_offset) * gain_sample_to_utc)) + utc_offset_t64

    def _time_utc_to_samples(self, utc):
        sample_offset, utc_offset_t64, _, gain_utc_to_sample = self._time_map
        return int(np.rint((utc - utc_offset_t64) * gain_utc_to_sample)) + sample_offset

    def open(self):
        topic = self._topic
        pubsub = self._pubsub
        jls = Reader(self._path)
        self._jls = jls
        source_meta = {}

        for source_id, source in jls.sources.items():
            pubsub.topic_add(f'{topic}/settings/sources/{source_id}/name',
                             Metadata('str', 'Source name', default=source.name))
            meta = {
                'vendor': source.vendor,
                'model': source.model,
                'version': source.version,
                'serial_number': source.serial_number,
                'name': f'{source.model}-{source.serial_number}',
            }
            pubsub.topic_add(f'{topic}/settings/sources/{source_id}/meta',
                             Metadata('obj', 'Source metadata', default=meta))
            source_meta[source_id] = meta
        for signal_id, signal in jls.signals.items():
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
                if utc_first is None:
                    g = time64.SECOND / signal.sample_rate
                    self._time_map = [0, 0, g, 1.0 / g]
                elif utc_last[0] == utc_first[0]:
                    self._time_map = [utc_first[0], utc_first[1], g, 1.0 / g]
                else:
                    d_utc = utc_last[1] - utc_first[1]
                    d_sample = utc_last[0] - utc_first[0]
                    g = d_utc / d_sample
                    self._time_map = [utc_first[0], utc_first[1], g, 1.0 / g]

            signal_meta = copy.deepcopy(source_meta[signal.source_id])
            source_name = signal_meta['name']
            signal_subname = TO_UI_SIGNAL_NAME[signal.name]
            signal_name = f'{source_name}.{signal_subname}'

            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/name',
                             Metadata('str', 'Signal name', default=signal.name))
            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/meta',
                             Metadata('obj', 'Signal metadata', default=signal_meta))
            sample_start, sample_end = 0, signal.length - 1
            range_meta = {
                'utc': [self._time_samples_to_utc(sample_start), self._time_samples_to_utc(sample_end)],
                'samples': {'start': sample_start, 'end': sample_end, 'length': signal.length},
                'sample_rate': signal.sample_rate,
            }
            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/range',
                             Metadata('obj', 'Signal range', default=range_meta))
            self._signals[signal_name] = {
                'signal_id': signal.signal_id,
                'sample_rate': signal.sample_rate,
                'field': signal_subname,
                'units': signal.units,
                'data_type': data_type_as_str(signal.data_type),
            }

    def _handle_request(self, value):
        """Handle a buffer request.

        :param value: The buffer request structure.
            See joulescope_ui.capabilities SIGNAL_BUFFER_SOURCE
        """
        signal = self._signals[value['signal_id']]
        signal_id = signal['signal_id']
        if value['time_type'] == 'utc':
            start = self._time_utc_to_samples(value['start'])
            end = self._time_utc_to_samples(value['end'])
        else:
            start = value['start']
            end = value['end']
        interval = end - start + 1
        length = value['length']
        response_type = 'samples'
        increment = 1
        data_type = signal['data_type']

        if interval < 0:
            return
        if end is None:
            self._log.info('fsr(%d, %d, %d)', signal_id, start, length)
            data = self._jls.fsr(signal_id, start, length)
        elif length is None:
            self._log.info('fsr(%d, %d, %d)', signal_id, start, interval)
            data = self._jls.fsr(signal_id, start, interval)
        elif length and end and length < (interval // 2):
            # round increment down and increase length as needed
            increment = interval // length
            length = (end - start + 1) // increment
            self._log.info('fsr_statistics(%d, %d, %d, %d)', signal_id, start, increment, length)
            data = self._jls.fsr_statistics(signal_id, start, increment, length)
            response_type = 'summary'
            data_type = 'f32'
        else:
            self._log.info('fsr(%d, %d, %d)', signal_id, start, length)
            data = self._jls.fsr(signal_id, start, length)
        sample_id_end = start + increment * (length - 1)

        info = {
            'version': 1,
            'field': signal['field'],
            'units': signal['units'],
            'time_range_utc': {
                'start': self._time_samples_to_utc(start),
                'end': self._time_samples_to_utc(end),
                'length': length,
            },
            'time_range_samples': {
                'start': start,
                'end': sample_id_end,
                'length': length,
            },
            'time_map': {
                'offset_time': self._time_map[1],
                'offset_counter': self._time_map[0],
                'counter_rate': signal['sample_rate'],
            },
        }
        self._log.info(info)
        response = {
            'version': 1,
            'rsp_id': value.get('rsp_id'),
            'info': info,
            'response_type': response_type,
            'data': data,
            'data_type': data_type,
        }
        self._pubsub.publish(value['rsp_topic'], response)

    def quit(self):
        self._quit = True

    def request(self, value):
        self._queue.put(['request', value])

    def run(self):
        while not self._quit:
            try:
                cmd, value = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if cmd == 'request':
                self._handle_request(value)

@register
class JlsSource:
    CAPABILITIES = []
    SETTINGS = {
        'name': {
            'dtype': 'str',
            'brief': 'The name for this JLS stream buffer source',
            'default': None,
        },
    }

    def __init__(self, path):
        self._path = os.path.abspath(path)
        self._jls = None
        self.pubsub = None
        if not os.path.isfile(path):
            raise ValueError(f'File not found: {self._path}')
        self.CAPABILITIES = [CAPABILITIES.SOURCE, CAPABILITIES.SIGNAL_BUFFER_SOURCE]
        self._version = _jls_version_detect(path)
        self._thread = None

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        pubsub = self.pubsub
        name = os.path.basename(os.path.splitext(self._path)[0])
        _log.info(f'jls_source register {topic}/settings/signals')
        pubsub.topic_add(f'{topic}/settings/sources', Metadata('node', 'Sources'))
        pubsub.topic_add(f'{topic}/settings/signals', Metadata('node', 'Signals'))
        pubsub.publish(f'{topic}/settings/name', name)
        if self._version == 2:
            _log.info('jls_source v2')
            self._jls = JlsV2(self._path, self.pubsub, self.topic)
        elif self.version == 1:
            _log.info('jls_source v1')
            raise NotImplementedError('jls v1 support not yet added')
        else:
            raise ValueError('Unsupported JLS version')

        self._thread = threading.Thread(target=self._jls.run)
        self._thread.start()

    def on_pubsub_unregister(self):
        self._close()

    def _close(self):
        if self._jls is not None:
            jls, self._jls, thread, self._thread = self._jls, None, self._thread, None
            jls.quit()
            if thread is not None:
                thread.join()

    def on_action_close(self):
        self.pubsub.unregister(self, delete=True)
        self._close()

    def on_action_request(self, value):
        self._jls.request(value)

    @staticmethod
    def on_cls_action_open(pubsub, topic, value):
        if isinstance(value, str):
            path = value
        else:
            raise ValueError(f'unsupported value {value}')
        _log.info('open %s', path)
        obj = JlsSource(path)
        pubsub.register(obj)

    @staticmethod
    def on_cls_action_finalize(pubsub, topic, value):
        instances = pubsub.query(f'{get_topic_name(JlsSource)}/instances')
        for instance in list(instances):
            pubsub.publish(f'{get_topic_name(instance)}/actions/!close', None)
        JlsSource.pubsub.unregister(JlsSource, delete=True)
