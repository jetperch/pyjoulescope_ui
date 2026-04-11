# Copyright 2026 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""External serial port device for reading UART data from system serial ports."""

from joulescope_ui import N_, get_topic_name
from joulescope_ui.capabilities import CAPABILITIES
from joulescope_ui.metadata import Metadata
from pyjoulescope_driver import time64
import copy
import logging
import serial
import threading


_CAPABILITIES_OPEN = [
    CAPABILITIES.SOURCE,
    CAPABILITIES.SERIAL_SOURCE,
]


EVENTS = {
    'signals/S/!data': Metadata('obj', 'Serial data'),
}

_SETTINGS = {
    'name': {
        'dtype': 'str',
        'brief': N_('Device name'),
        'default': None,
    },
    'info': {
        'dtype': 'obj',
        'brief': N_('Device information'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],
    },
    'state': {
        'dtype': 'int',
        'brief': N_('Device state'),
        'options': [
            [0, 'closed'],
            [1, 'opening'],
            [2, 'open'],
            [3, 'closing'],
        ],
        'default': 0,
        'flags': ['ro', 'hide', 'skip_undo'],
    },
    'sources/1/name': {
        'dtype': 'str',
        'brief': N_('Device name'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],
    },
    'sources/1/info': {
        'dtype': 'obj',
        'brief': N_('Device information'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],
    },
    'signals/S/name': {
        'dtype': 'str',
        'brief': N_('Signal name'),
        'flags': ['hide'],
        'default': N_('Serial'),
    },
    'signals/S/enable': {
        'dtype': 'bool',
        'brief': N_('Serial'),
        'detail': N_('External serial data stream'),
        'flags': ['hide'],
        'default': True,
    },
}


class ExternalSerialDevice:
    """An external serial port device that reads UART data.

    :param manager: The ExternalSerialManager instance.
    :param port_config: dict with keys 'port', 'baud_rate', 'name', 'auto_open'.
    """

    CAPABILITIES = []
    EVENTS = {}
    SETTINGS = {}

    def __init__(self, manager, port_config):
        self._manager = manager
        self._port = port_config['port']
        self._baud_rate = int(port_config.get('baud_rate', 115200))
        self._name = port_config.get('name', self._port)
        self._log = logging.getLogger(__name__ + '.' + self._port)
        self._serial = None
        self._thread = None
        self._quit = False
        self._sample_id = 0

        self.CAPABILITIES = []
        self.EVENTS = copy.deepcopy(EVENTS)
        self.SETTINGS = copy.deepcopy(_SETTINGS)

        self._info = {
            'vendor': 'External',
            'model': 'Serial',
            'version': None,
            'serial_number': self._port,
        }
        self.SETTINGS['name']['default'] = self._name
        self.SETTINGS['info']['default'] = self._info
        self.SETTINGS['sources/1/name']['default'] = self._name
        self.SETTINGS['sources/1/info']['default'] = self._info

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        self.pubsub.publish(f'{topic}/settings/info', self._info)
        self.pubsub.publish(f'{topic}/settings/sources/1/info', self._info)

    def open(self):
        """Open the serial port and start the reader thread."""
        if self._thread is not None:
            return
        self._log.info('open %s at %d baud', self._port, self._baud_rate)
        topic = get_topic_name(self)
        self.pubsub.publish(f'{topic}/settings/state', 1)  # opening
        try:
            self._serial = serial.Serial(
                self._port,
                baudrate=self._baud_rate,
                timeout=0.5,
            )
        except serial.SerialException as ex:
            self._log.error('Failed to open %s: %s', self._port, ex)
            self.pubsub.publish(f'{topic}/settings/state', 0)  # closed
            raise
        self._quit = False
        self._thread = threading.Thread(target=self._run, name=f'ext_serial_{self._port}', daemon=True)
        self._thread.start()
        self.pubsub.publish(f'{topic}/settings/state', 2)  # open
        self.pubsub.capabilities_append(self, _CAPABILITIES_OPEN)

    def close(self):
        """Close the serial port and stop the reader thread."""
        if self._thread is None:
            return
        self._log.info('close %s', self._port)
        topic = get_topic_name(self)
        self.pubsub.publish(f'{topic}/settings/state', 3)  # closing
        self.pubsub.capabilities_remove(self, _CAPABILITIES_OPEN)
        self._quit = True
        self._thread.join(timeout=2.0)
        self._thread = None
        s, self._serial = self._serial, None
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
        self.pubsub.publish(f'{topic}/settings/state', 0)  # closed

    def _run(self):
        """Background thread: read lines from serial port and publish."""
        self._log.info('reader thread start')
        buf = b''
        while not self._quit:
            try:
                data = self._serial.read(self._serial.in_waiting or 1)
            except serial.SerialException as ex:
                self._log.warning('Serial read error on %s: %s', self._port, ex)
                break
            except Exception:
                if self._quit:
                    break
                raise
            if not data:
                continue
            buf += data
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                line = line.rstrip(b'\r')
                if not line:
                    continue
                t_time64 = time64.now()
                t_str = time64.as_datetime(t_time64).isoformat()
                try:
                    message = line.decode('utf-8')
                except Exception:
                    message = line  # keep as bytes if decode fails
                m = {
                    'sample_id': self._sample_id,
                    'time64': t_time64,
                    'time_str': t_str,
                    'message': message,
                }
                self._sample_id += 1
                topic = f'{get_topic_name(self)}/events/signals/S/!data'
                self.pubsub.publish(topic, m)
        self._log.info('reader thread stop')
        # If we broke out due to error (not quit), clean up from UI thread
        if not self._quit:
            s, self._serial = self._serial, None
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
            topic = get_topic_name(self)
            self.pubsub.capabilities_remove(self, _CAPABILITIES_OPEN)
            self.pubsub.publish(f'{topic}/settings/state', 0)

    def on_action_finalize(self):
        self.close()

    def on_setting_name(self, value):
        self._name = value
        self.pubsub.publish(f'{get_topic_name(self)}/settings/sources/1/name', value)
