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

from joulescope_ui import CAPABILITIES, N_, Metadata, get_topic_name, get_unique_id, get_instance
from pyjoulescope_driver import time64
from .device import Device
import copy
import logging
import time


_MEM_CLEANUP_PERIOD_S = 1.0   # process memory cleanup with this period (seconds)
_MEM_EXPIRE_INTERVAL_S = 2.0  # expire entries older than this duration (seconds)


_CAPABILITIES_OBJECT = [
    CAPABILITIES.SOURCE,
    CAPABILITIES.SIGNAL_BUFFER_SOURCE,
]


_EVENTS = {
    'sources/!add': Metadata('str', 'Source added'),
    'sources/!remove': Metadata('str', 'Source removed'),
    'signals/!add': Metadata('str', 'Signal added'),
    'signals/!remove': Metadata('str', 'Signal removed'),
}


_SETTINGS = {
    'name': {
        'dtype': 'str',
        'brief': N_('Name'),
        'default': N_('Joulescope stream buffer'),
    },
    'size': {
        'dtype': 'int',
        'brief': N_('Buffer memory size in bytes'),
        'default': int(0.5 * 1024 ** 3),
    },
    'duration': {
        'dtype': 'float',
        'brief': N_('Buffer memory duration in seconds'),
        'default': 0.0,
        'flags': ['ro', 'tmp', 'skip_undo'],
    },
    'sources': {
        'dtype': 'node',
        'brief': 'Hold source settings',
        'default': None,
        'flags': ['hide', 'skip_undo'],
    },
    'signals': {
        'dtype': 'node',
        'brief': 'Hold signal settings',
        'default': None,
        'flags': ['hide', 'skip_undo'],
    },
    'clear_on_play': {
        'dtype': 'bool',
        'brief': 'Clear on play',
        'detail': """\
            When signal sample streaming is paused, the stream buffer pauses
            sample accumulation.  This setting controls what happens on play
            when streaming resumes.
            
            When unset, the buffer continues to accumulate samples into the
            existing buffer data.  This mode treats the pause duration as
            missing samples.
            
            When set, the buffer is cleared and all prior data is purged.
            The buffer functions as if sample streaming started for the
            first time.""",
        'default': True,
    }

}

_SETTINGS_PER_SOURCE = {
    'name': Metadata({
        'dtype': 'str',
        'brief': N_('Name'),
        'default': N_('Source name'),
    }),
    'info': Metadata({
        'dtype': 'obj',
        'brief': N_('Source information'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],
    }),
}

_SETTINGS_PER_SIGNAL = {
    'name': Metadata({
        'dtype': 'str',
        'brief': N_('Name'),
        'default': N_('Signal name'),
    }),
    'meta': Metadata({
        'dtype': 'obj',
        'brief': N_('Signal metadata'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],
    }),
    'range': Metadata({
        'dtype': 'obj',
        'brief': N_('Signal time range'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],
    }),
}


def defer_until_registered(f):
    def wrapper(self, value):
        if self._initialize_cache is not None:
            self._initialize_cache.append((f, value))
        else:
            f(self, value)
    return wrapper


class JsdrvStreamBuffer:
    """Joulescope stream buffer.

    The Joulescope driver provides up to 254 stream buffer instances,
    each of which are represented by an instance of this class.
    """
    CAPABILITIES = []
    EVENTS = {}

    def __init__(self, wrapper, stream_buffer_id):
        self.pubsub = None
        self.CAPABILITIES = _CAPABILITIES_OBJECT
        self.EVENTS = _EVENTS
        self.SETTINGS = _SETTINGS
        self._wrapper = wrapper  #: JsdrvWrapper
        self._initialize_cache = []
        self._id = f'{int(stream_buffer_id):03d}'
        self._rsp_topic = f'm/mem/{self._id}/!rsp'
        self._log = logging.getLogger(f'{__name__}.{self._id}')
        self._driver_subscriptions = []
        self._sources: dict[str, str] = {}  # device unique_id -> device_path
        self._signals: dict[str, [int, object, float]] = {}     # signal id ui_str -> [buffer_id, meta, duration]
        self._signals_reverse: dict[int, str] = {}  # signal id buffer_id -> ui_str
        self._device_signal_id_next = 1
        self._device_subscriptions = {}
        self._pubsub_device_subscriptions = {}  # device_id: [(topic, fn), ...]

        self._signals_free = list(range(1, 256))
        self._req_fwd = {}  # (pubsub_rsp_topic, pubsub_rsp_id): device_rsp_id
        self._req_bwd = {}  # device_rsp_id: (pubsub_rsp_topic, pubsub_rsp_id)
        self._req_time = {}  # device_rsp_id: time_last_used
        self._collect_time = time.time()

    def __str__(self):
        return f'JsdrvStreamBuffer({self._id})'

    def _on_device_ids(self, value):
        self._log.info('_on_device_ids %s', value)
        existing = set(self._sources.keys())
        for unique_id in value:
            if unique_id not in self._sources:
                self._on_device_add(unique_id)
            try:
                existing.remove(unique_id)
            except KeyError:
                pass
        for device in existing:
            self._on_device_remove(device)

    def _on_device_add(self, device):
        unique_id = get_unique_id(device)
        device = get_instance(unique_id)
        if '-UPDATER' in device.unique_id:
            return
        self._log.info('device_add %s', unique_id)
        self._sources[unique_id] = device.device_path
        topic = get_topic_name(self.unique_id)
        source_topic = f'{topic}/settings/sources/{unique_id}'
        for name, meta in _SETTINGS_PER_SOURCE.items():
            self.pubsub.topic_add(f'{source_topic}/{name}', meta, exists_ok=True)
        self.pubsub.publish(f'{source_topic}/name', device.name)
        self.pubsub.publish(f'{source_topic}/info', device.info)
        self._ui_device_subscribe(device, 'settings/state',
                                  self._on_device_state, ['pub', 'retain'])

    def _on_device_state(self, topic, value):
        unique_id = topic.split('/')[1]
        if '-UPDATER' in unique_id:
            return
        if value == 2:  # open
            self._on_device_open(unique_id)
        else:
            self._on_device_close(unique_id)  # may have duplicate close

    def _on_device_open(self, device):
        device_id = get_unique_id(device)
        self._log.info('device_open %s', device_id)
        device_topic = get_topic_name(device_id)
        for signal in self.pubsub.enumerate(f'{device_topic}/settings/signals'):
            self._ui_device_subscribe(device_id, f'settings/signals/{signal}/enable',
                                      self._on_signal_enable, ['pub', 'retain'])
        topic = get_topic_name(self.unique_id)
        self.pubsub.publish(f'{topic}/events/sources/!add', device_id)

    def _on_device_close(self, device):
        device_id = get_unique_id(device)
        if len(self._pubsub_device_subscriptions.get(device_id, [])) <= 1:
            return
        self._log.info('device_close %s', device_id)
        topic = get_topic_name(self.unique_id)
        self.pubsub.publish(f'{topic}/events/sources/!remove', device_id)
        signals = list(self._signals.keys())
        for signal_id in signals:
            if signal_id.split('.')[0] == device_id:
                self.on_action_remove(signal_id)
        subs = self._pubsub_device_subscriptions[device_id]
        subs, self._pubsub_device_subscriptions[device_id] = subs[1:], subs[:1]
        for topic, fn in subs:
            self.pubsub.unsubscribe(topic, fn)

    def _on_device_remove(self, device):
        unique_id = get_unique_id(device)
        device_path = self._sources.pop(unique_id)
        if '-UPDATER' in unique_id:
            return
        self._log.info('device_remove %s', unique_id)
        topic = get_topic_name(self.unique_id)
        source_topic = f'{topic}/settings/{unique_id}'
        for topic, fn in self._pubsub_device_subscriptions.pop(unique_id, []):
            self.pubsub.unsubscribe(topic, fn)
        for name, meta in _SETTINGS_PER_SOURCE.items():
            self.pubsub.topic_remove(f'{source_topic}/{name}')
        for topic in list(self._device_subscriptions.keys()):
            if topic.startswith(device_path):
                fn = self._device_subscriptions.pop(topic)
                self._wrapper.driver.unsubscribe(topic, fn)

    def _device_subscribe(self, topic, flags, fn):
        self._device_subscriptions[topic] = fn
        self._wrapper.driver.subscribe(topic, flags, fn)

    def _driver_publish(self, topic, value, timeout=None):
        if self._wrapper.driver is not None:
            self._wrapper.driver.publish(topic, value, timeout)

    def _ui_subscribe(self, topic, fn, flags=None):
        self.pubsub.subscribe(topic, fn, flags)

    def _ui_device_subscribe(self, device, topic, fn, flags=None):
        unique_id = get_unique_id(device)
        if unique_id not in self._pubsub_device_subscriptions:
            self._pubsub_device_subscriptions[unique_id] = []
        base_topic = get_topic_name(unique_id)
        topic = f'{base_topic}/{topic}'
        self.pubsub.subscribe(topic, fn, flags)
        self._pubsub_device_subscriptions[unique_id].append((topic, fn))

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        for t in self.pubsub.enumerate(f'{topic}/settings/sources', absolute=True):
            self.pubsub.topic_remove(t)
        for t in self.pubsub.enumerate(f'{topic}/settings/signals', absolute=True):
            self.pubsub.topic_remove(t)
        self._driver_publish('m/@/!add', int(self._id))
        self._device_subscribe(self._rsp_topic, 'pub', self._on_buf_response)
        for fn, value in self._initialize_cache:
            fn(self, value)
        self._initialize_cache = None
        self._ui_subscribe('registry/jsdrv/settings/device_ids', self._on_device_ids, ['pub', 'retain'])
        self._ui_subscribe('registry/app/settings/signal_stream_enable', self._on_signal_steam_enable, ['pub', 'retain'])

    def _on_signal_steam_enable(self, value):
        if value and self.clear_on_play:
            self.on_action_clear()
        self.on_setting_hold(not bool(value))

    def on_pubsub_unregister(self):
        self._log.info('unregister')
        for topic, fn in self._device_subscriptions:
            self._wrapper.driver.unsubscribe(topic, fn)
        self._device_subscriptions.clear()
        self._driver_publish('m/@/!remove', int(self._id))
        self.pubsub.topic_remove(f'{get_topic_name(self)}/settings/signals')

    def _on_device_signal_info(self, topic, value):
        # device_signal_info m/001/s/001/info {'version': 1, 'field_id': 1, 'index': 0, 'element_type': 4, 'element_size_bits': 32, 'topic': b'u/js220/000415/s/i/!data', 'size_in_utc': 8725724278, 'size_in_samples': 8126464, 'time_range_utc': {'start': 911549982937, 'end': 914237683277, 'length': 2503116}, 'time_range_samples': {'start': 848947077, 'end': 851450193, 'length': 2503116}, 'sample_rate': 1000000.0}
        buf_id = int(topic.split('/')[-2])
        signal_id = self._signals_reverse.get(buf_id)
        duration = value['size_in_utc'] / time64.SECOND
        t = get_topic_name(self)
        if signal_id in self._signals:
            self._signals[signal_id][-1] = duration
            duration = min([x[-1] for x in self._signals.values()])
            self.pubsub.publish(f'{t}/settings/duration', duration)
        if signal_id is not None:
            utc = value['time_range_utc']
            r = {
                'utc': [utc['start'], utc['end']],
                'samples': value['time_range_samples'],
                'sample_rate': value['time_map']['counter_rate'],
            }
            self.pubsub.publish(f'{t}/settings/signals/{signal_id}/range', r)

    def _on_signal_enable(self, topic, value):
        p = topic.split('/')
        device_unique_id = p[1]
        signal = p[4]
        signal_id = f'{device_unique_id}.{signal}'
        value = bool(value)
        if value:
            self.on_action_add(signal_id)
        elif signal_id in self._signals.keys():
            self.on_action_remove(signal_id)

    @defer_until_registered
    def on_setting_size(self, value):
        self._driver_publish(f'm/{self._id}/g/size', int(value))

    @defer_until_registered
    def on_setting_hold(self, value):
        value = int(value)
        self._driver_publish(f'm/{self._id}/g/hold', value)

    @defer_until_registered
    def on_setting_mode(self, value):
        self._driver_publish(f'm/{self._id}/g/mode', int(value))

    def on_action_add(self, signal_id):
        if signal_id in self._signals.keys():
            self._log.info('add duplicate %s', signal_id)
            return
        self._log.info('add %s', signal_id)
        buf_id = self._signals_free.pop(0)
        unique_id, signal = signal_id.split('.')
        device = get_instance(unique_id)
        device_path = self._sources[unique_id]
        device_topic = get_topic_name(unique_id)
        signal_meta = copy.deepcopy(device.info)
        self._signals[signal_id] = [buf_id, signal_meta, 0.0]
        self._signals_reverse[buf_id] = signal_id
        device_path = device_path

        device_signal_id = signal_id.split('.')[1]
        signal_name = self.pubsub.query(f'{device_topic}/settings/signals/{device_signal_id}/name')
        ui_prefix = get_topic_name(self)
        ui_signal_prefix = f'{ui_prefix}/settings/signals/{signal_id}'
        for key, meta in _SETTINGS_PER_SIGNAL.items():
            self.pubsub.topic_add(f'{ui_signal_prefix}/{key}', meta, exists_ok=True)
        self.pubsub.publish(f'{ui_signal_prefix}/name', signal_name)
        self.pubsub.publish(f'{ui_signal_prefix}/meta', signal_meta)
        self._driver_publish(f'm/{self._id}/a/!add', buf_id)
        subtopic = device.signal_subtopics(signal, 'data')
        device_source = f'{device_path}/{subtopic}'
        buf_prefix = f'm/{self._id}/s/{buf_id:03d}'
        self._driver_publish(f'{buf_prefix}/topic', device_source)
        self._device_subscribe(f'{buf_prefix}/info', ['pub', 'pub_retain'], self._on_device_signal_info)
        self.pubsub.publish(f'{ui_prefix}/events/signals/!add', signal_id)

    def on_action_remove(self, signal_id):
        self._log.info('remove %s', signal_id)
        buf_id = self._signals.pop(signal_id)[0]
        self._signals_reverse.pop(buf_id)
        self._signals_free.append(buf_id)
        self._driver_publish(f'm/{self._id}/a/!remove', buf_id)
        ui_prefix = get_topic_name(self)
        self.pubsub.publish(f'{ui_prefix}/events/signals/!remove', signal_id)
        self.pubsub.topic_remove(f'{ui_prefix}/settings/signals/{signal_id}', defer=True)

    def on_action_clear(self):
        self._driver_publish(f'm/{self._id}/g/!clear', 0)

    def _on_buf_response(self, topic, value):
        # will be called from device's pubsub thread
        if value is None:
            self._log.warning('_on_buf_response called with None')
            return
        value = copy.deepcopy(value)
        device_req_id = value['rsp_id']
        try:
            req = self._req_bwd[device_req_id]
            value['rsp_topic'] = req[0]
            value['rsp_id'] = req[1]
            self.pubsub.publish(value['rsp_topic'], value)
        except KeyError:
            self._log.info('Unknown response: req_id=%s', device_req_id)

    def on_action_request(self, value):
        """Request data from the memory buffer.

        :param value: The buffer request structure.
            See joulescope_ui.capabilities SIGNAL_BUFFER_SOURCE
        """
        value = copy.deepcopy(value)
        signal_id = value['signal_id']
        signal_id_parts = signal_id.split('.')
        signal_id = '.'.join(signal_id_parts[-2:])
        try:
            buf_id = self._signals[signal_id][0]
        except KeyError:
            self._log.info('Request for missing signal %s', signal_id)
            return None
        pubsub_req = (value['rsp_topic'], value['rsp_id'])
        if pubsub_req in self._req_fwd:
            device_req_id = self._req_fwd[pubsub_req]
        else:
            # create and add new entry
            device_req_id = id(pubsub_req)
            self._req_fwd[pubsub_req] = device_req_id
            self._req_bwd[device_req_id] = pubsub_req
        t_now = time.time()
        self._req_time[device_req_id] = t_now  # update last used time
        value['rsp_topic'] = self._rsp_topic
        value['rsp_id'] = device_req_id
        self._driver_publish(f'm/{self._id}/s/{buf_id:03d}/!req', value, timeout=0)
        self._mem_collect(t_now)

    def on_action_annotations_request(self, value):
        self.pubsub.publish(value['rsp_topic'], None)

    def _mem_collect(self, t_now):
        if t_now - self._collect_time < _MEM_CLEANUP_PERIOD_S:
            return
        for device_req_id, t_last in list(self._req_time.items()):
            if (t_now - t_last) > _MEM_EXPIRE_INTERVAL_S:
                pubsub_req = self._req_bwd.pop(device_req_id)
                self._req_time.pop(device_req_id)
                self._req_fwd.pop(pubsub_req)
        self._mem_collect_time = t_now
