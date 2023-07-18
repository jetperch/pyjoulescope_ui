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

from pyjls import Writer, SignalType
from joulescope_ui import pubsub_singleton, register, CAPABILITIES, time64
from joulescope_ui.jls_v2 import ChunkMeta, DTYPE_MAP
from .signal_record_config_widget import SignalRecordConfigDialog
import copy
import json
import logging
import numpy as np


_UTC_INTERVAL = 10 * time64.MINUTE


@register
class SignalRecord:
    CAPABILITIES = []
    _singleton = None  # not strictly singleton, but target of class actions.
    _instances = []
    _log = logging.getLogger(f'{__name__}.cls')

    def __init__(self, config):
        parent = pubsub_singleton.query('registry/app/instance')
        self._log = logging.getLogger(f'{__name__}.obj')
        self.CAPABILITIES = [CAPABILITIES.SIGNAL_STREAM_SINK]
        path = config['path']
        self._log.info('JLS record to %s', path)
        self._log.info('JLS record signals: %s', config['signals'])
        self._jls = Writer(path)
        self._log.info('Writer started')
        self._on_data_fn = self._on_data
        self._source_idx = 1
        self._signal_idx = 1
        self._sources = {}
        self._signals = {}
        self._subscribe_entries = []  # (topic, fn, flags)

        notes = config.get('notes')
        if notes is not None:
            self._jls.user_data(ChunkMeta.NOTES, notes)
        pubsub_singleton.publish('registry/paths/actions/!mru_save', path)
        pubsub_singleton.register(self, parent=parent)

        for signal in config['signals']:
            self._subscribe(signal, self._on_data_fn, ['pub'])

    def _subscribe(self, topic, fn, flags):
        pubsub_singleton.subscribe(topic, fn, flags)
        self._subscribe_entries.append((topic, fn, flags))

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
            self._jls.fsr_f32(signal['id'], sample_id, x)

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

    def on_action_stop(self, value):
        self._log.info('stop')
        jls, self._jls = self._jls, None
        if jls is None:
            return
        for topic, fn, flags in self._subscribe_entries:
            pubsub_singleton.unsubscribe(topic, fn, flags)
        self._subscribe_entries.clear()
        for signal in self._signals.values():
            if signal['utc_data_prev'] is not None and signal['utc_data_prev'] != signal['utc_entry_prev']:
                self._log.info('utc %s: %s', signal['name'], signal['utc_data_prev'])
                jls.utc(signal['id'], *signal['utc_data_prev'])
        jls.close()
        if self == SignalRecord._singleton:
            SignalRecord._singleton = None
        if self in SignalRecord._instances:
            SignalRecord._instances.remove(self)
        pubsub_singleton.unregister(self)

    @staticmethod
    def on_cls_action_start_request(pubsub, topic, value):
        SignalRecord._log.info('on_cls_action_start_request')
        SignalRecordConfigDialog()

    @staticmethod
    def on_cls_action_start(pubsub, topic, value):
        SignalRecord._log.info('on_cls_action_start')
        obj = SignalRecord(value)
        if SignalRecord._singleton is None:
            SignalRecord._singleton = obj
        SignalRecord._instances.append(obj)

    @staticmethod
    def on_cls_action_stop(pubsub, topic, value):
        if SignalRecord._singleton is not None:
            SignalRecord._log.info('on_cls_action_stop')
            SignalRecord._singleton.on_action_stop(value)
