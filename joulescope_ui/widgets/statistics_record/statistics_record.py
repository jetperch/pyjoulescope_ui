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

from joulescope_ui import pubsub_singleton, register, CAPABILITIES, Metadata, get_topic_name
from .statistics_record_config_widget import StatisticsRecordConfigDialog
from pyjoulescope_driver import time64
import logging
import numpy as np


@register
class StatisticsRecord:
    CAPABILITIES = []
    _instances = []
    _log = logging.getLogger(f'{__name__}.cls')
    EVENTS = {
        '!stop': Metadata('bool', 'Recording stopped', flags=['ro', 'skip_undo']),
    }

    def __init__(self, topic, filename, config=None):
        parent = pubsub_singleton.query('registry/app/instance')
        time_format = config.get('time_format', None)
        if time_format is None:
            time_format = 'relative'
        if time_format not in ['relative', 'UTC', 'off']:
            raise ValueError(f'invalid time_format {time_format}')
        self._time_format = time_format
        self._topic = topic
        self._log = logging.getLogger(f'{__name__}.obj')
        self.CAPABILITIES = [CAPABILITIES.STATISTIC_STREAM_SINK]
        self._log.info('JLS record %s to %s', topic, filename)
        self._file = open(filename, 'wt')
        self._offsets = None
        self._time_format_str = ''

        pubsub_singleton.publish('registry/paths/actions/!mru_save', filename)
        pubsub_singleton.register(self, parent=parent)
        pubsub_singleton.subscribe(self._topic, self._on_data, ['pub'])

    def _on_data(self, topic, value):
        if self._file is None:
            return
        t = value['time']['utc']['value'][1]  # time64 format
        i = value['signals']['current']['avg']['value']
        v = value['signals']['voltage']['avg']['value']
        p = value['signals']['power']['avg']['value']
        c = value['accumulators']['charge']['value']
        e = value['accumulators']['energy']['value']

        if self._offsets is None:
            self._offsets = {
                'time': t,
                'charge': c,
                'energy': e,
            }
            hdr = '#' if self._time_format == 'off' else '#time,'
            hdr += 'current,voltage,power,charge,energy\n'
            self._file.write(hdr)
            freq = 1.0 / value['time']['delta']['value']
            freq_log10 = int(np.ceil(max(0, np.log10(freq))))
            if self._time_format == 'relative':
                fmt_str = f'%.{freq_log10}f,'
                def relative_format(t_now):
                    dt = (t_now - self._offsets['time'])
                    dt /= time64.SECOND
                    return fmt_str % dt
                self._time_format_fn = relative_format
            elif self._time_format == 'UTC':
                def utc_format(t_now):
                    d = time64.as_datetime(t_now)
                    if freq_log10 == 0:
                        s = d.strftime('%Y%m%dT%H%M%SZ,')
                    else:
                        s = d.strftime('%Y%m%dT%H%M%S.%f')
                        if freq_log10 < 6:
                            s = s[:-6+freq_log10]
                        s += 'Z,'
                    return s
                self._time_format_fn = utc_format
            else:
                self._time_format_fn = lambda t_now: ''

        c -= self._offsets['charge']
        e -= self._offsets['energy']
        line = '%g,%g,%g,%g,%g\n' % (i, v, p, c, e)
        self._file.write(self._time_format_fn(t) + line)

    def on_action_stop(self, value):
        self._log.info('stop')
        pubsub_singleton.unsubscribe(self._topic, self._on_data, ['pub'])
        f, self._file = self._file, None
        f.close()
        if self in StatisticsRecord._instances:
            StatisticsRecord._instances.remove(self)
        pubsub_singleton.unregister(self, delete=True)

    @staticmethod
    def on_cls_action_start(pubsub, topic, value):
        config = value.get('config', {})
        StatisticsRecord._log.info('on_cls_action_start')
        for topic, filename in value['sources']:
            obj = StatisticsRecord(topic, filename, config)
            StatisticsRecord._instances.append(obj)

    @staticmethod
    def on_cls_action_toggled(pubsub, topic, value):
        if bool(value):
            StatisticsRecord._log.info('start_request')
            StatisticsRecordConfigDialog()
        else:
            StatisticsRecord._log.info('stop')
            while len(StatisticsRecord._instances):
                obj = StatisticsRecord._instances.pop()
                obj.on_action_stop(value)
            pubsub.publish(f'{get_topic_name(StatisticsRecord)}/events/!stop', True)
