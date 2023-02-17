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

from joulescope_ui import CAPABILITIES, N_, Metadata, get_topic_name
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
        'flags': ['ro', 'hidden'],
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
        'flags': ['ro', 'hidden'],
    }),
    'range': Metadata({
        'dtype': 'obj',
        'brief': N_('Signal time range'),
        'default': None,
        'flags': ['ro', 'hidden'],
    }),
}


"""
        * settings/signals/{signal_id}/name
        * settings/signals/{signal_id}/meta: obj with keys:
          * vendor
          * model
          * version
          * serial_number
          * field: (current, voltage, power, ...)
          * units
          * source: (unique_id, if not same as this instance)
          * source_topic: (fully qualified topic, if not from this instance)
          * sample_freq: (output)
        * settings/signals/{signal_id}/range: [t_start, t_end] in time64 (read-only)
        * actions/signals/{signal_id}/!req obj with keys:
          * time_start: The start time as time64.
          * time_end: The end time as time64.
          * length: The desired number of response entries.
          * rsp_topic: When computed, the results will be sent to this topic.
            The results can be either sample data or summary data.
            To guarantee sample data, specify either time64_end or length.
            Other requests may return sample data or summary data.
          * rsp_id: The arbitrary, immutable argument for rsp_topic.  Examples
            included int, string, and callables.
        * actions/!signal_add {signal_id}: (optional, only for dynamic sources)
        * actions/!signal_remove {signal_id}:  (optional, only for dynamic sources)
        * settings/sources: list of source_id (read only)
        * settings/signals: list of signal_id (read only)
"""


class JsdrvStreamBuffer:
    """Joulescope stream buffer.

    The Joulescope driver provides up to 254 stream buffer instances,
    each of which are represented by an instance of this class.
    """
    CAPABILITIES = []
    EVENTS = {}

    def __init__(self, wrapper, id):
        self._pubsub = None
        self.CAPABILITIES = _CAPABILITIES_OBJECT
        self.EVENTS = _EVENTS
        self.SETTINGS = _SETTINGS
        self._wrapper = wrapper  #: JsdrvWrapper
        self._id = f'{int(id):03d}'
        self._rsp_topic = f'_/mem_{self._id}/!rsp'
        self._log = logging.getLogger(f'{__name__}.{self._id}')
        self._driver_subscriptions = []
        self._sources = {}
        self._signals = {}
        self._device_subscriptions = {}

    def __str__(self):
        return f'JsdrvStreamBuffer({self._id})'

    def device_add(self, device: Device):
        self._sources[device.unique_id] = device
        topic = get_topic_name(self.unique_id)
        source_topic = f'{topic}/settings/{device.unique_id}'
        for name, meta in _SETTINGS_PER_SOURCE.items():
            self._pubsub.topic_add(f'{source_topic}/{name}', meta)
        device_topic = get_topic_name(device)
        for signal in self._pubsub.enumerate(f'{device_topic}/settings/signals'):
            self._pubsub.subscribe(f'{device_topic}/settings/signals/{signal}/enable',
                                   self._on_signal_enable, ['pub', 'retain'])
        # todo publish source info
        self._pubsub.publish(f'{topic}/events/sources/!add', device.unique_id)

    def device_remove(self, device: Device):
        topic = get_topic_name(self.unique_id)
        source_topic = f'{topic}/settings/{device.unique_id}'
        self._pubsub.publish(f'{topic}/events/sources/!remove', device.unique_id)
        for name, meta in _SETTINGS_PER_SOURCE.items():
            self._pubsub.topic_remove(f'{source_topic}/{name}')
        for topic in list(self._device_subscriptions.keys()):
            if topic.startswith(device.device_path):
                fn = self._device_subscriptions.pop(topic)
                self._wrapper.driver.unsubscribe(topic, fn)
        del self._sources[device.unique_id]

    def _device_subscribe(self, topic, flags, fn):
        self._device_subscriptions[topic] = fn
        self._wrapper.driver.subscribe(topic, flags, fn)

    def on_pubsub_register(self, pubsub):
        self._pubsub = pubsub
        self._device_publish('m/@/!add', int(self._id))
        self._device_subscribe(self._rsp_topic, 'pub', self._on_mem_response)

    def on_pubsub_unregister(self):
        self._wrapper.driver.unsubscribe(self._rsp_topic, 'pub', self._on_mem_response_fn)
        for topic, fn in self._device_subscriptions:
            self._wrapper.driver.unsubscribe(topic, fn)
        self._device_publish('m/@/!remove', int(self._id))
        self._pubsub.unsubscribe(self._on_pubsub_req)

    def _on_pubsub_req(self, topic, value):
        """Request data from the buffer.


        """
        print(topic)

    def _on_signal_enable(self, topic, value):
        p = topic.split('/')
        source = p[1]
        signal = p[4]
        signal_id = f'{source}.{signal}'
        value = bool(value)
        ui_prefix = get_topic_name(self)
        req_topic = f'{topic}/actions/signals/{signal_id}/!req'
        if value:
            self._pubsub.register_command(req_topic, self._on_pubsub_req)
            for key, meta in _SETTINGS_PER_SIGNAL.items():
                self._pubsub.topic_add(f'{ui_prefix}/settings/signals/{signal_id}/{key}', meta)
            # todo publish signal metadata
            self._pubsub.publish(f'{ui_prefix}/events/signals/!add', signal_id)
        elif signal_id in self._signals:
            self._pubsub.publish(f'{ui_prefix}/events/signals/!remove', signal_id)
            self._pubsub.topic_remove(f'{ui_prefix}/settings/signals/{signal_id}')
            self._pubsub.unregister_command(req_topic, self._on_pubsub_req)

    def _device_publish(self, topic, value):
        self._wrapper.driver.publish(topic, value)

    def on_setting_size(self, value):
        self._device_publish(f'm/{self._id}/g/size', int(value))

    def on_setting_hold(self, value):
        value = int(value)
        self._device_publish(f'm/{self._id}/g/hold', value)

    def on_setting_mode(self, value):
        self._device_publish(f'm/{self._id}/g/mode', int(value))

    def on_action_signal__add(self, value):
        data_topic = value
        signal_id = self._mem_signals_free.pop(0)
        self._mem[data_topic] = signal_id
        self.driver.publish(f'm/{self._id}/a/!add', signal_id)
        self.driver.publish(f'm/{self._id}/s/{signal_id:03d}/topic', data_topic)

    def on_action_signal__remove(self, value):
        data_topic = value
        signal_id = self._mem.pop(data_topic)
        self.driver.publish(f'm/{self._id}/a/!remove', signal_id)
        self._mem_signals_free.append(0, signal_id)

    def _on_mem_response(self, topic, value):
        # will be called from device's pubsub thread
        value = copy.deepcopy(value)
        device_req_id = value['rsp_id']
        try:
            req = self._mem_req_bwd[device_req_id]
            value['rsp_topic'] = req[0]
            value['rsp_id'] = req[1]
            self.pubsub.publish(value['rsp_topic'], value)
        except KeyError:
            self._log.info('Unknown response: req_id=%s', device_req_id)

    def on_action_signal__request(self, value):
        """Request data from the memory buffer.

        :param value: The dict defining the request with keys:
            * signal: The source data topic for the signal.
            * time_type: 'utc' or 'samples'.
            * rsp_topic: The arbitrary response topic.
            * rsp_id: The optional and arbitrary response immutable object.
              Valid values include integers, strings, and callables.
              If providing method calls, be sure to save the binding to a
              member variable and reuse the same binding so that deduplication
              can work correctly.  Otherwise, each call will use a new binding
              that is different and will not allow deduplication matching.
            * start: The starting time (UTC or samples).
            * end: The ending time (UTC or samples).
            * length: The number of requested entries evenly spread from start to end.
        """
        value = copy.deepcopy(value)
        data_topic = value['signal']
        if data_topic not in self._mem:
            return  # todo handle
        signal_id = self._mem[data_topic]
        pubsub_req = (value['rsp_topic'], value['rsp_id'])
        if pubsub_req in self._mem_req_fwd:
            device_req_id = self._mem_req_fwd[pubsub_req]
        else:
            # create and add new entry
            device_req_id = id(pubsub_req)
            self._mem_req_fwd[pubsub_req] = device_req_id
            self._mem_req_bwd[device_req_id] = pubsub_req
        t_now = time.time()
        self._mem_req_time[device_req_id] = t_now  # update last used time
        value['rsp_topic'] = self._rsp_topic
        value['rsp_id'] = device_req_id
        self.driver.publish(f'm/{self._id}/s/{signal_id:03d}/!req', value)
        self._mem_collect(t_now)

    def _mem_collect(self, t_now):
        if t_now - self._mem_collect_time < _MEM_CLEANUP_PERIOD_S:
            return
        for device_req_id, t_last in list(self._mem_req_time.items()):
            if (t_now - t_last) > _MEM_EXPIRE_INTERVAL_S:
                pubsub_req = self._mem_req_bwd.pop(device_req_id)
                del self._mem_req_fwd.pop[pubsub_req]
                del self._mem_req_time[device_req_id]
        self._mem_collect_time = t_now