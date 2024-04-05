# Copyright 2023-2024 Jetperch LLC
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

from pyjls import Writer, Reader, SignalType, AnnotationType
from joulescope_ui import N_, pubsub_singleton, register, CAPABILITIES, time64, Metadata, get_topic_name
from joulescope_ui.jls_v2 import ChunkMeta, DTYPE_MAP
from .signal_record_config_widget import SignalRecordConfigDialog
from .disk_full_dialog import DiskFullDialog
import copy
import json
import logging
import numpy as np
import time


_UTC_INTERVAL = 10 * time64.MINUTE
_DISK_MONITOR_BASE = 'registry/DiskMonitor:0'
_DISK_MONITOR_ADD = f'{_DISK_MONITOR_BASE}/actions/!add'
_DISK_MONITOR_REMOVE = f'{_DISK_MONITOR_BASE}/actions/!remove'
_DISK_MONITOR_FULL = f'{_DISK_MONITOR_BASE}/events/full'


@register
class SignalRecord:
    CAPABILITIES = []
    _instances = []
    _log = logging.getLogger(f'{__name__}.cls')
    EVENTS = {
        '!stop': Metadata('bool', 'Recording stopped', flags=['ro', 'skip_undo']),
    }

    def __init__(self, config):
        self._utc_stop = None
        self._utc_range = None
        parent = pubsub_singleton.query('registry/app/instance')
        self._log = logging.getLogger(f'{__name__}.obj')
        self.CAPABILITIES = [CAPABILITIES.SIGNAL_STREAM_SINK]
        path = config['path']
        self._log.info('JLS record to %s', path)
        self._path = path
        try:
            self._jls = Writer(path)
            self._jls.flags = Writer.FLAG_DROP_ON_OVERFLOW
        except Exception as ex:
            pubsub_singleton.publish('registry/ui/actions/!error_msg',
                                     N_('Could not open file for write')
                                     + f'\n{ex}\n{path}')
            raise
        self._log.info('Writer started')
        self._source_idx = 1
        self._signal_idx = 1
        self._sources = {}
        self._signals = {}
        self._status = {
            'time_last': time.time(),
            'dropped': 0,
        }

        notes = config.get('notes')
        if notes is not None:
            self._jls.user_data(ChunkMeta.NOTES, notes)
        pubsub_singleton.register(self, parent=parent)

        for source in config['sources'].values():
            for signal in source.values():
                if signal['enabled'] and signal['selected']:
                    self.pubsub.subscribe(signal['data_topic'], self._on_data, ['pub'])

        self.pubsub.publish(_DISK_MONITOR_ADD, self._path)
        self.pubsub.subscribe(_DISK_MONITOR_FULL, self._on_disk_full, ['pub'])
        self.pubsub.publish('registry/paths/actions/!mru_save', path)

    def _on_data(self, topic, value):
        if self._jls is None:
            return
        if topic not in self._signals:
            source = topic.split('/')[1]
            if source not in self._sources:
                self._source_add(source, value['source'])
            self._signal_add(source, topic, value)
        signal = self._signals[topic]
        sample_id = value['sample_id']
        utc_now = value['utc']
        utc = [sample_id, utc_now]
        if signal['utc_entry_prev'] is None or (utc_now - signal['utc_entry_prev'][1]) >= _UTC_INTERVAL:
            self._log.info('utc %s: %s, %s', signal['name'], sample_id, utc_now)
            self._jls.utc(signal['id'], sample_id, utc_now)
            signal['utc_entry_prev'] = utc
        signal['utc_data_prev'] = utc
        x = value['data']
        if len(x):
            x = np.ascontiguousarray(x)
            try:
                self._jls.fsr(signal['id'], sample_id, x)
            except Exception:
                self._status['dropped'] += len(x)
                t_now = time.time()
                if t_now >= (1.0 + self._status['time_last']):
                    dropped, self._status['dropped'] = self._status['dropped'], 0
                    self.pubsub.publish('registry/ui/actions/!status_msg', f'JLS write dropped {dropped} samples')
                    self._status['time_last'] = t_now
        if self._utc_stop is not None:
            u = min([signal['utc_data_prev'][1] for signal in self._signals.values()])
            if u >= self._utc_stop:
                self.on_action_stop()

    def _source_add(self, unique_id, info):
        info = copy.deepcopy(info)
        model = info.get('model', '')
        serial_number = info.get('serial_number', '')
        name = f'{model}-{serial_number}'
        version = info.get('version')
        if isinstance(version, dict):
            version = json.dumps(version)
        self._jls.source_def(
            source_id=self._source_idx,
            name=name,
            vendor=info['vendor'],
            model=model,
            version=version,
            serial_number=serial_number,
        )
        info['id'] = self._source_idx
        info['name'] = name
        self._sources[unique_id] = info
        self._source_idx += 1

    def _signal_add(self, source, topic, value):
        source_info = self._sources[source]
        source_id = source_info['id']
        self._jls.signal_def(
            signal_id=self._signal_idx,
            source_id=source_id,
            signal_type=SignalType.FSR,
            data_type=DTYPE_MAP[value['dtype']],
            sample_rate=value['sample_freq'],
            name=value['field'].replace(' ', '_'),
            units=value['units'],
        )
        self._signals[topic] = {
            'id': self._signal_idx,
            'name': value['field'],
            'utc_entry_prev': None,    # the previous UTC entry
            'utc_data_prev': None,   # the previous UTC info from streaming sample data
        }
        self._signal_idx += 1

    def _on_disk_full(self, pubsub, topic, value):
        if self._path in value:
            self._log.info('disk full: stop JLS recording %s', self._path)
            self.pubsub.publish('registry/SignalRecord/actions/!stop', None)
            self.pubsub.publish('registry/app/settings/signal_stream_record', False)
            DiskFullDialog(pubsub, value)

    def stop_pend(self, utc_stop, utc_range):
        self._utc_stop = utc_stop
        self._utc_range = utc_range

    def on_action_stop(self):
        self._log.info('stop')
        jls, self._jls = self._jls, None
        if jls is None:
            return
        for signal in self._signals.values():
            if signal['utc_data_prev'] is not None and signal['utc_data_prev'] != signal['utc_entry_prev']:
                self._log.info('utc %s: %s', signal['name'], signal['utc_data_prev'])
                jls.utc(signal['id'], *signal['utc_data_prev'])
        jls.close()
        if self in SignalRecord._instances:
            SignalRecord._instances.remove(self)
        self.pubsub.unregister(self, delete=True)
        self.pubsub.publish(_DISK_MONITOR_REMOVE, self._path)
        self._annotation_create()

    def _annotation_create(self):
        if self._utc_range is None:
            return
        path = self._path.replace('.jls', '.anno.jls')
        self._log.info('_annotation_create start')
        z0, z1 = self._utc_range
        sample_rate = 1_000_000

        t_start = []
        t_stop = []
        with Reader(self._path) as r:
            for signal in r.signals.values():
                if signal.signal_type != 0:
                    continue
                t_start.append(r.sample_id_to_timestamp(signal.signal_id, 0))
                t_stop.append(r.sample_id_to_timestamp(signal.signal_id, signal.length - 1))
        x0 = max(t_start)
        x1 = min(t_stop)

        def x_map(x_i64):
            return int(round((x_i64 - x0) * (sample_rate / time64.SECOND)))

        with Writer(path) as w:
            w.source_def(source_id=1, name='annotations', vendor='-', model='-', version='-', serial_number='-')
            signal_id = 1
            w.signal_def(signal_id=signal_id, source_id=1, sample_rate=sample_rate, name='current', units='A')
            w.utc(signal_id, x_map(x0), x0)
            w.utc(signal_id, x_map(x1), x1)
            w.annotation(signal_id, x_map(z0), None, AnnotationType.VMARKER, 0, '1a')
            w.annotation(signal_id, x_map(z1), None, AnnotationType.VMARKER, 0, '1b')
        self._log.info('_annotation_create done')

    @staticmethod
    def on_cls_action_start(pubsub, topic, value):
        SignalRecord._log.info('on_cls_action_start')
        obj = SignalRecord(value)
        SignalRecord._instances.append(obj)

    @staticmethod
    def on_cls_action_toggled(pubsub, topic, value):
        if bool(value):
            SignalRecord._log.info('start_request')
            SignalRecordConfigDialog()
        else:
            SignalRecord._log.info('stop')
            while len(SignalRecord._instances):
                obj = SignalRecord._instances.pop()
                obj.on_action_stop()
            pubsub.publish(f'{get_topic_name(SignalRecord)}/events/!stop', True)
