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

import numpy as np
from joulescope_ui import get_topic_name, time64
from joulescope_ui.time_map import TimeMap
import logging
import queue
import threading
import time


_PUSH_TIMEOUT_DEFAULT = 0.5  # should never happen
_TIMEOUT_DEFAULT = 5.0
_PROGRESS_TOPIC = 'registry/progress/actions/!update'


def rsp_as_f32(rsp):
    """Get the data as f32 type.

    :param rsp: The CAPABILITIES.SIGNAL_BUFFER_SOURCE response,
        such as from RangeTool.request.
    :return: The np.ndarray with dtype=np.float32 regardless
        of the rsp['data_type'].  Coerce as needed.
    """
    length = rsp['info']['time_range_samples']['length']
    if rsp['response_type'] != 'samples':
        return rsp['data']
    y = rsp['data']
    data_type = rsp['data_type']
    if data_type == 'f32':
        pass
    elif data_type == 'u1':
        y = np.unpackbits(y, bitorder='little')[:length]
    elif data_type == 'u4':
        d = np.empty(len(y) * 2, dtype=np.uint8)
        d[0::2] = np.logical_and(y, 0x0f)
        d[1::2] = np.logical_and(np.right_shift(y, 4), 0x0f)
        y = d[:length]
    else:
        raise ValueError(f'unsupported data_type {data_type}')
    return y


class RangeTool:
    """Provides common range tool behaviors.

    :param value: The CAPABILITIES.RANGE_TOOL_CLASS compatible
        value, usually sent to the range tool's on_cls_action_run
        static method.

    This class can either be used as a base class or as a delegate class.
    """

    def __init__(self, value):
        self.pubsub = None
        self.x_range = value['x_range']
        if callable(self.x_range):
            self.x_range = self.x_range()
        assert(len(self.x_range) == 2)
        assert(self.x_range[0] <= self.x_range[1])
        self.signals = value['signals']

        self._log = logging.getLogger(__name__)
        self.abort = None
        self.rsp_topic = None
        self._rsp_id = 1
        self._queue = queue.Queue()

    def push(self, value):
        """Push a response onto the queue for processing.

        :param value: The response from the signal buffer source.
        """
        self._queue.put(value, timeout=_PUSH_TIMEOUT_DEFAULT)

    def pop(self, timeout=None):
        """Pop the next response from the queue.

        :param timeout: The timeout in float seconds.
        :return: The next value.
        :raise queue.Empty: If no message available within timeout.
        """
        return self._queue.get(timeout=timeout)

    def signal_query(self, signal, setting):
        """Query the signals settings.

        :param signal: The signal_id
        :param setting: The signal setting, one of [name, meta, range]
            as defined by CAPABILITIES.SIGNAL_BUFFER_SOURCE.
        """
        source, device, quantity = signal.split('.')
        topic = get_topic_name(source)
        return self.pubsub.query(f'{topic}/settings/signals/{device}.{quantity}/{setting}')

    def request(self, signal_id: str, time_type, start, end, length, timeout=None):
        """Request data from the signal buffer.

        :param signal_id: The signal_id string as '{source}.{device}.{quantity}'
        :param time_type: utc or samples.
        :param start: The starting time, inclusive.
        :param end: The ending time, inclusive.
        :param length: The number of entries to receive.
        :param timeout: The timeout in float seconds.  None uses the default.
        :return: See CAPABILITIES.SIGNAL_BUFFER_SOURCE response.

        To guarantee that you receive a sample response, provide either
        end or length.  If you provide end and length, then you may
        receive a summary response.
        """
        assert(self.rsp_topic is not None)
        if time_type not in ['utc', 'samples']:
            raise ValueError(f'invalid time_type: {time_type}')
        source, device, quantity = signal_id.split('.')

        rsp_id = self._rsp_id
        req = {
            'signal_id': signal_id,
            'time_type': time_type,
            'start': start,
            'end': end,
            'length': length,
            'rsp_topic': self.rsp_topic,
            'rsp_id': rsp_id,
        }
        rsp_total = None

        while True:
            self._rsp_id += 1
            self.pubsub.publish(f'{get_topic_name(source)}/actions/!request', req)
            if timeout == 0:
                return rsp_id
            if timeout is None:
                timeout = _TIMEOUT_DEFAULT
            t_end = time.time() + timeout
            while True:
                timeout = max(0.0, t_end - time.time())
                try:
                    rsp = self.pop(timeout=timeout)
                except queue.Empty:
                    raise TimeoutError(f'request timed out for {signal_id}')
                if rsp['rsp_id'] == rsp_id:
                    break
                else:
                    self._log.warning('discarding message')
            fs = rsp['info']['time_map']['counter_rate']
            period_t64 = (1.0 / fs) * time64.SECOND
            if req['time_type'] == 'samples':
                end = req['end']
                if end == 0:
                    end = req['start'] + req['length'] - 1
                is_done = rsp['info']['time_range_samples']['end'] >= end
            else:
                is_done = rsp['info']['time_range_utc']['end'] + period_t64 >= req['end']
            if is_done and rsp_total is None:
                return rsp
            if rsp_total is None:
                rsp_total = rsp
                rsp_total['data'] = [rsp_total['data']]
                if rsp['response_type'] != 'samples':
                    raise RuntimeError('Only support concat for sample responses')
                if req['time_type'] == 'utc':
                    # convert to samples
                    tm = TimeMap()
                    tm_entry = rsp['info']['time_map']
                    scale = tm_entry['counter_rate'] / time64.SECOND
                    tm.update(tm_entry['offset_counter'], tm_entry['offset_time'], scale)
                    req['time_type'] = 'samples'
                    req['length'] = 0
                    req['end'] = int(np.rint(tm.time64_to_counter(end)))
            else:
                rsp_total['data'].append(rsp['data'])
                rsp_total['info']['time_range_utc']['end'] = rsp['info']['time_range_utc']['end']
                rsp_total['info']['time_range_utc']['length'] += rsp['info']['time_range_utc']['length']
                rsp_total['info']['time_range_samples']['end'] = rsp['info']['time_range_samples']['end']
                rsp_total['info']['time_range_samples']['length'] += rsp['info']['time_range_samples']['length']
            req['start'] = rsp['info']['time_range_samples']['end'] + 1
            if req['length']:
                req['length'] -= rsp['info']['time_range_samples']['length']
            if is_done:
                rsp_total['data'] = np.concatenate(rsp_total['data'])
                return rsp_total

    def progress_start(self, progress_id, name, cancel_topic=None, brief=None, description=None):
        """Start tracking progress.

        See ProgressBarWidget.on_cls_action_update for details."""
        value = {
            'id': progress_id,
            'progress': 0.0,
            'name': name,
        }
        for v, key in [(cancel_topic, 'cancel_topic'), (brief, 'brief'), (description, 'description')]:
            if v is not None:
                value[key] = v
        self.pubsub.publish(_PROGRESS_TOPIC, value)

    def progress_update(self, progress_id, progress):
        """Update progress.

        :param progress_id: The same id provided to :meth:`progress_start`.
        :param progress: The float progress from 0.0 to 1.0.
        """
        value = {
            'id': progress_id,
            'progress': progress,
        }
        self.pubsub.publish(_PROGRESS_TOPIC, value)

    def progress_complete(self, progress_id):
        """Complete the progress.

        :param progress_id: The same id provided to :meth:`progress_start`.
        """
        self.progress_update(progress_id, 1.0)

    def error(self, msg):
        """Display an error.

        :param msg: The error message.
        """
        self.pubsub.publish('registry/ui/actions/!error_msg', msg)


class RangeToolBase:
    """The subclass MUST define the following class attributes:

    NAME: The localized name for this range tool.
        This name will be displayed in menus.
    BRIEF: The localized brief description for this range tool.
        This will be used for tooltips.
    DESCRIPTION: The more detailed description for this instance.
        This will be used for tooltips.
    """

    CAPABILITIES = ['range_tool@']
    _instances = []

    def __init__(self, value):
        """Configure this instance.

        :param value: The range-tool value.  See CAPABILITIES.RANGE_TOOL_CLASS
            for the definition.
        """
        self._log = logging.getLogger(f'{__name__}.{self.NAME}')
        RangeToolBase._instances.append(self)
        self.signals = value['signals']
        self.range_tool_kwargs = value.get('range_tool', {})
        self.kwargs = value.get('kwargs', {})
        self.value = value
        self._rt = RangeTool(value)
        self.x_range = self._rt.x_range
        value['x_range'] = self.x_range  # modify in place (necessary for callables)
        self._thread = None

    def on_pubsub_register(self):
        self._rt.rsp_topic = f'{get_topic_name(self.topic)}/callbacks/!data'
        self._rt.pubsub = self.pubsub
        self._rt.progress_start(
            progress_id=self.unique_id,
            name=self.NAME,
            cancel_topic=f'{get_topic_name(self)}/actions/!cancel',
            brief=self.BRIEF,
            description=self.DESCRIPTION,
        )
        self._log.info('start %s', self.unique_id)
        self._thread = threading.Thread(target=self.__run_outer)
        self._thread.start()

    @property
    def abort(self):
        if self._rt is not None:
            return self._rt.abort
        return False

    def on_pubsub_unregister(self):
        self._log.info('complete %s', self.unique_id)
        thread, self._thread = self._thread, None
        rt, self._rt = self._rt, None
        if rt is not None:
            rt.abort = True
        if thread is not None:
            thread.join(5.0)
        if rt is not None:
            rt.progress_complete(self.unique_id)

    def progress(self, progress):
        """Update progress for this range tool instance.

        :param progress: The float progress from 0.0 to 1.0.
        """
        if self._rt is not None:
            self._rt.progress_update(self.unique_id, progress)

    def signal_query(self, signal, setting):
        """See :meth:`RangeTool.signal_query`."""
        if self._rt is not None:
            return self._rt.signal_query(signal, setting)
        else:
            raise RuntimeError('signal_query but closed')

    def request(self, signal, time_type, start, end, length, timeout=None):
        """See :meth:`RangeTool.request`."""
        if self._rt is not None:
            return self._rt.request(signal, time_type, start, end, length, timeout)
        else:
            raise RuntimeError('request but closed')

    def error(self, msg):
        if self._rt is not None:
            self._rt.error(msg)

    def __run_outer(self):
        for cbk in self.range_tool_kwargs.get('start_callbacks', []):
            self.pubsub.publish(cbk, self.value)
        self._run()
        for cbk in self.range_tool_kwargs.get('done_callbacks', []):
            self.pubsub.publish(cbk, self.value)
        if not self.abort:
            self.pubsub.publish(f'{get_topic_name(self)}/actions/!finalize', None)

    def _run(self):
        """The subclass should define this method to perform processing.

        Note that this runs from a python thread, so Qt interactions are not
        possible.  Use pubsub_singleton.publish to invoke actions on the
        Qt event thread.
        """
        raise NotImplementedError()

    def on_callback_data(self, value):
        if self._rt is not None:
            self._rt.push(value)

    def on_action_finalize(self):
        self._log.info('finalize')
        self.pubsub.unregister(self, delete=True)

    def on_action_cancel(self):
        self._log.info('cancel')
        self.pubsub.unregister(self, delete=True)
