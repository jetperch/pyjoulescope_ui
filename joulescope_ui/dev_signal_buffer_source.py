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


from joulescope_ui import CAPABILITIES, time64, register, get_topic_name
import numpy as np
import logging


_UNITS = {
    '1.i': 'A',
    '1.v': 'V',
    '1.p': 'W',
}


@register
class DevSignalBufferSource:
    """A trivial signal buffer source for waveform widget development."""

    CAPABILITIES = []
    SETTINGS = {}

    def __init__(self, path=None):
        self._log = logging.getLogger(__name__)
        info = {
            'vendor': 'Jetperch LLC',
            'model': 'sw_dev',
            'version': '1',
            'serial_number': '000000',
        }
        self.SETTINGS = {
            'name': {
                'dtype': 'str',
                'brief': 'The source name',
                'default': 'DevSignalBufferSource',
            },
            'sources/1/name': {
                'dtype': 'str',
                'brief': 'The source name',
                'default': 'DevSignalBufferSource',
            },
            'sources/1/info': {
                'dtype': 'obj',
                'brief': 'The source info',
                'default': info,
            },
        }

        self.t_start = int((time64.now() // time64.SECOND) * time64.SECOND)
        self.t_duration = time64.SECOND * 10
        self.t_end = self.t_start + self.t_duration
        self.s_rate = 1_000_000.0
        self.s_start = 30_000_000
        self.s_duration = int(np.rint(self.t_duration * self.s_rate / time64.SECOND + 1))
        self.s_end = self.s_start + self.s_duration
        self._range = {
            'utc': [self.t_start, self.t_end],
            'samples': [self.s_start, self.s_end, self.s_duration],
            'sample_rate': self.s_rate,
        }

        for signal in ['i', 'v', 'p']:
            self.SETTINGS[f'signals/1.{signal}/name'] = {
                'dtype': 'str',
                'brief': 'The signal name',
                'default': f'1.{signal}',
            }
            self.SETTINGS[f'signals/1.{signal}/meta'] = {
                'dtype': 'obj',
                'brief': 'The signal metadata',
                'default': info,
            }
            self.SETTINGS[f'signals/1.{signal}/range'] = {
                'dtype': 'obj',
                'brief': 'The signal range',
                'default': None,
            }
        self.CAPABILITIES = [CAPABILITIES.SOURCE, CAPABILITIES.SIGNAL_BUFFER_SOURCE]

        x = np.arange(0, self.s_duration, dtype=float) * (1.0 / self.s_rate)
        self.x_samples = x + self.s_start
        self.x_time64 = self.t_start + (x * time64.SECOND).astype(np.int64)
        i = np.empty(x.shape, dtype=float)
        i_split = 4.1
        i[x < i_split] = 0.001
        i[x >= i_split] = 0.111
        self._signals = {
            '1.i': i,
            '1.v': np.sin(2 * np.pi * x),
            '1.p': np.cos(20 * np.pi * x),
        }

    def on_pubsub_register(self):
        prefix = f'{self.topic}/settings/signals'
        for signal in ['i', 'v', 'p']:
            self.pubsub.publish(f'{prefix}/1.{signal}/range', self._range)

    def on_action_request(self, value):
        """Process a signal request.

        :param value: The request.  See CAPABILITIES.SIGNAL_BUFFER_SOURCE."""
        signal_id = value['signal_id']
        y = self._signals[signal_id]
        time_type = value['time_type']
        if time_type == 'samples':
            s_start, s_end = value['start'], value['end']
            if s_start < self.s_start:
                self._log.warning('sample req start too early: %s < %s', s_start, self.s_start)
                return
            if s_end > self.s_end:
                self._log.warning('sample req end too late: %s > %s', s_end, self.s_end)
                return
            xi = np.linspace(s_start, s_end, value['length'])
            y = np.interp(xi, self.x_samples, y)
            t_start, t_end = np.interp([xi[0], xi[-1]], self.x_time64, self.x_time64)
        elif time_type == 'utc':
            t_start, t_end = value['start'], value['end']
            if t_start < self.t_start:
                self._log.warning('utc req start too early: %s < %s', t_start, self.t_start)
                return
            if t_end > self.t_end:
                self._log.warning('utc req end too late: %s > %s', t_end, self.t_end)
                return
            xi = np.linspace(t_start, t_end, value['length'])
            y = np.interp(xi, self.x_time64, y)
            s_start, s_end = np.interp([xi[0], xi[-1]], self.x_samples, self.x_samples)
        else:
            raise ValueError(f'invalid time_type {time_type}')

        rsp = {
            'version': 1,
            'rsp_id': value['rsp_id'],
            'info': {
                'field': signal_id.split('.')[1],
                'units': _UNITS[signal_id],
                'time_range_utc': {
                    'start': t_start,
                    'end': t_end,
                    'length': value['length'],
                },
                'time_range_samples': {
                    'start': s_start,
                    'end': s_end,
                    'length': value['length'],
                },
                'time_map': {
                    'offset_time': self.t_start,
                    'offset_counter': self.s_start,
                    'counter_rate': self.s_rate,
                }
            },
            'response_type': 'samples',
            'data_type': 'f32',
            'data': y,
        }
        self.pubsub.publish(value['rsp_topic'], rsp)
