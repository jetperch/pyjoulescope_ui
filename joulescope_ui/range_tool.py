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


from joulescope_ui import get_topic_name
import logging
import queue
import threading
import time


_PUSH_TIMEOUT_DEFAULT = 0.5  # should never happen
_TIMEOUT_DEFAULT = 5.0
_PROGRESS_TOPIC = 'registry/progress/actions/!update'


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

        :param signal: The (source_unique_id, signal_id).
        :param setting: The signal setting, one of [name, meta, range]
            as defined by CAPABILITIES.SIGNAL_BUFFER_SOURCE.
        """
        source_unique_id, signal_id = signal
        topic = get_topic_name(source_unique_id)
        return self.pubsub.query(f'{topic}/settings/signals/{signal_id}/{setting}')

    def request(self, signal, time_type, start, end, length, timeout=None):
        """Request data from the signal buffer.

        :param signal: The (source_id, signal_id) signal definition.
        :param time_type: utc or samples.
        :param start: The starting time, inclusive.
        :param end: The ending time, inclusive.
        :param length: The number of entries to receive.
        :param timeout: The timeout in float seconds.  None uses the default.

        To guarantee that you receive a sample response, provide either
        end or length.  If you provide end and length, then you may
        receive a summary response.
        """
        assert(self.rsp_topic is not None)
        if time_type not in ['utc', 'samples']:
            raise ValueError(f'invalid time_type: {time_type}')
        rsp_id = self._rsp_id
        if isinstance(signal, dict):
            signal = signal['signal']
        req = {
            'signal_id': signal[1],
            'time_type': time_type,
            'start': start,
            'end': end,
            'length': length,
            'rsp_topic': self.rsp_topic,
            'rsp_id': rsp_id,
        }
        self._rsp_id += 1
        self.pubsub.publish(f'{get_topic_name(signal[0])}/actions/!request', req)
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
                raise TimeoutError(f'request timed out for {signal}')
            if rsp['rsp_id'] == rsp_id:
                return rsp
            else:
                self._log.warning('discarding message')

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
        self.pubsub.publish('registry/app/actions/!error', msg)


class RangeToolBase:

    CAPABILITIES = ['range_tool@']
    _instances = []

    def __init__(self, value, name, brief=None, description=None):
        """Configure this instance.

        :param value: The range-tool value.  See CAPABILITIES.RANGE_TOOL_CLASS
            for the definition.
        :param name: The localized name for this instance.
        :param brief: The localized brief description for this instance.
        :param description: The more detailed description for this instance.
        """
        self._log = logging.getLogger(f'{__name__}.{name}')
        RangeToolBase._instances.append(self)
        self.x_range = value['x_range']
        self.signals = value['signals']
        self.kwargs = value['kwargs']
        self._name = name
        self._brief = brief
        self._description = description
        self.value = value
        self._rt = RangeTool(value)
        self._thread = None
        self._name = None
        self._brief = None
        self._description = None

    def on_pubsub_register(self):
        self._rt.rsp_topic = f'{get_topic_name(self.topic)}/callbacks/!data'
        self._rt.pubsub = self.pubsub
        self._rt.progress_start(
            progress_id=self.unique_id,
            name=self._name,
            cancel_topic=f'{get_topic_name(self)}/actions/!cancel',
            brief=self._brief,
            description=self._description,
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
        self._run()
        if not self.abort:
            self.pubsub.publish(f'{get_topic_name(self)}/actions/!finalize', None)

    def _run(self):
        raise NotImplementedError()

    def on_callback_data(self, value):
        self._rt.push(value)

    def on_action_finalize(self):
        self._log.info('finalize')
        self.on_pubsub_unregister()

    def on_action_cancel(self):
        self._log.info('cancel')
        self.on_pubsub_unregister()
