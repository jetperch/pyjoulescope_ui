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
from joulescope_ui import CAPABILITIES, Metadata, time64, register, get_topic_name, get_instance
from joulescope_ui.jls_v2 import TO_UI_SIGNAL_NAME
from joulescope_ui.time_map import TimeMap
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


class _Dedup:
    """A deduplicating FIFO dict.

    A normal dict with popitem would work, but popitem
    operates in LIFO order.  This implementation ensures
    FIFO order by using a separate list to keep key order.

    See https://docs.python.org/3/library/stdtypes.html?highlight=popitem#dict.popitem
    """

    def __init__(self):
        self._dict = {}
        self._order = []

    def __len__(self):
        return len(self._order)

    def insert(self, key, value):
        if key not in self._dict:
            self._order.append(key)
        self._dict[key] = value

    def pop(self):
        key = self._order.pop(0)
        return self._dict.pop(key)


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
                g = time64.SECOND / signal.sample_rate
                if utc_first is None:
                    time_map.update(0, 0, 1.0 / g)
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
                             Metadata('obj', 'Signal metadata', default=signal_meta))
            sample_start, sample_end = 0, signal.length - 1
            range_meta = {
                'utc': [time_map.counter_to_time64(sample_start), time_map.counter_to_time64(sample_end)],
                'samples': {'start': sample_start, 'end': sample_end, 'length': signal.length},
                'sample_rate': signal.sample_rate,
            }
            self._log.info(f'{signal.name}: {range_meta}')
            pubsub.topic_add(f'{topic}/settings/signals/{signal_name}/range',
                             Metadata('obj', 'Signal range', default=range_meta))
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
        signal = self._signals[req['signal_id']]
        signal_id = signal['signal_id']
        if req['time_type'] == 'utc':
            time_map = signal['time_map']
            start = time_map.time64_to_counter(req['start'], dtype=np.int64)
            end = time_map.time64_to_counter(req['end'], dtype=np.int64)
        else:
            start = req['start']
            end = req['end']
        interval = end - start + 1
        length = req['length']
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
        elif length and end and length <= (interval // 2):
            # round increment down
            increment = interval // length
            length = interval // increment
            self._log.info('fsr_statistics(%d, %d, %d, %d)', signal_id, start, increment, length)
            data = self._jls.fsr_statistics(signal_id, start, increment, length)
            response_type = 'summary'
            data_type = 'f32'
        else:
            length = interval
            self._log.info('fsr(%d, %d, %d)', signal_id, start, length)
            data = self._jls.fsr(signal_id, start, length)
        sample_id_end = start + increment * (length - 1)
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


@register
class JlsSource:
    CAPABILITIES = []
    SETTINGS = {}

    def __init__(self, path=None):
        self._queue = queue.Queue()

        if path is not None:
            name = os.path.basename(os.path.splitext(path)[0])
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                raise ValueError(f'File not found: {path}')
        else:
            name = 'JlsSource'

        self.SETTINGS = {
            'name': {
                'dtype': 'str',
                'brief': 'The name for this JLS stream buffer source',
                'default': name,
            },
            'path': {
                'dtype': 'str',
                'brief': 'The file path.',
                'default': path,
            }
        }
        self._jls = None
        self.pubsub = None
        self.CAPABILITIES = [CAPABILITIES.SOURCE, CAPABILITIES.SIGNAL_BUFFER_SOURCE]
        self._thread = None

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        pubsub = self.pubsub
        path = pubsub.query(f'{topic}/settings/path')
        _log.info(f'jls_source register {topic}')
        pubsub.topic_remove(f'{topic}/settings/sources')
        pubsub.topic_remove(f'{topic}/settings/signals')
        pubsub.topic_add(f'{topic}/settings/sources', Metadata('node', 'Sources'))
        pubsub.topic_add(f'{topic}/settings/signals', Metadata('node', 'Signals'))
        jls_version = _jls_version_detect(path)
        if jls_version == 2:
            _log.info('jls_source v2')
            self._jls = JlsV2(path, pubsub, topic)
        elif jls_version == 1:
            _log.info('jls_source v1')
            raise NotImplementedError('jls v1 support not yet added')
        else:
            raise ValueError(f'Unsupported JLS version {jls_version}')

        self._thread = threading.Thread(target=self.run)
        self._thread.start()

    def on_pubsub_unregister(self):
        self._close()

    def run(self):
        do_quit = False
        requests = _Dedup()
        while not do_quit:
            timeout = 0.0 if len(requests) else 2.0
            try:
                cmd, value = self._queue.get(timeout=timeout)
            except queue.Empty:
                if len(requests):
                    value = requests.pop()
                    try:
                        rsp = self._jls.process(value)
                    except Exception:
                        _log.exception('During jls process')
                    self.pubsub.publish(value['rsp_topic'], rsp)
                continue
            if cmd == 'request':
                key = (value['rsp_topic'], value['rsp_id'])
                requests.insert(key, value)
            elif cmd == 'close':
                do_quit = True
            else:
                _log.warning('unsupported command %s', cmd)

    def close(self):
        _log.info('close %s', self.path)
        jls, self._jls, thread, self._thread = self._jls, None, self._thread, None
        if thread is not None:
            self._queue.put(['close', None])
            thread.join()
        if jls is not None:
            jls.close()
        _log.info('close done %s', self.path)

    def on_action_close(self):
        self.close()
        self.pubsub.unregister(self, delete=True)

    def on_action_request(self, value):
        self._queue.put(['request', value])

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
        for instance_unique_id in list(instances):
            instance = get_instance(instance_unique_id, default=None)
            if instance is not None:
                instance.close()
