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

"""Manager for external serial port devices."""

from joulescope_ui import get_topic_name, N_
from joulescope_ui.capabilities import CAPABILITIES
from joulescope_ui.metadata import Metadata
from .serial_device import ExternalSerialDevice
import logging
import re


def _sanitize_port(port):
    """Create a pubsub-safe unique ID from a port path."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', port).strip('_')


class ExternalSerialManager:
    """Singleton manager for external serial port devices.

    Manages the lifecycle of ExternalSerialDevice instances.
    Port configurations persist across sessions via pubsub settings.
    """

    CAPABILITIES = [CAPABILITIES.DEVICE_FACTORY]
    SETTINGS = {
        'ports': {
            'dtype': 'obj',
            'brief': N_('Configured external serial ports'),
            'default': [],
            'flags': ['hide'],
        },
    }
    EVENTS = {
        '!port_add': Metadata('obj', 'External serial port added'),
        '!port_remove': Metadata('str', 'External serial port removed'),
    }

    def __init__(self):
        self._log = logging.getLogger(__name__)
        self._devices = {}  # port_path -> ExternalSerialDevice

    def on_pubsub_register(self):
        self._log.info('on_pubsub_register')
        # Auto-open any ports marked for auto_open
        for port_config in (self.ports or []):
            if port_config.get('auto_open', False):
                try:
                    self._open_port(port_config)
                except Exception:
                    self._log.warning('Failed to auto-open %s', port_config.get('port', '?'))

    def on_action_finalize(self):
        self._log.info('finalize')
        for port in list(self._devices.keys()):
            self._close_port(port)

    def on_action_port_add(self, value):
        """Add a port configuration.

        :param value: dict with keys 'port', 'baud_rate', 'name', 'auto_open'.
        """
        port = value['port']
        self._log.info('port_add %s', port)
        ports = list(self.ports or [])
        # Remove existing config for this port if present
        ports = [p for p in ports if p['port'] != port]
        ports.append(value)
        self.pubsub.publish(f'{get_topic_name(self)}/settings/ports', ports)

    def on_action_port_remove(self, value):
        """Remove a port configuration.

        :param value: The port path string to remove.
        """
        port = value
        self._log.info('port_remove %s', port)
        if port in self._devices:
            self._close_port(port)
        ports = list(self.ports or [])
        ports = [p for p in ports if p['port'] != port]
        self.pubsub.publish(f'{get_topic_name(self)}/settings/ports', ports)

    def on_action_port_open(self, value):
        """Open a configured port.

        :param value: The port path string to open.
        """
        port = value
        self._log.info('port_open %s', port)
        port_config = self._find_port_config(port)
        if port_config is None:
            self._log.error('Port config not found: %s', port)
            return
        self._open_port(port_config)

    def on_action_port_close(self, value):
        """Close an open port.

        :param value: The port path string to close.
        """
        port = value
        self._log.info('port_close %s', port)
        self._close_port(port)

    def _find_port_config(self, port):
        for cfg in (self.ports or []):
            if cfg['port'] == port:
                return cfg
        return None

    def _open_port(self, port_config):
        port = port_config['port']
        if port in self._devices:
            self._log.info('Port already open: %s', port)
            return
        device = ExternalSerialDevice(self, port_config)
        unique_id = f'ExtSerial-{_sanitize_port(port)}'
        self.pubsub.register(device, unique_id)
        try:
            device.open()
        except Exception:
            self.pubsub.unregister(device)
            raise
        self._devices[port] = device

    def _close_port(self, port):
        device = self._devices.pop(port, None)
        if device is None:
            return
        device.close()
        self.pubsub.unregister(device)

    def is_port_open(self, port):
        """Check if a port is currently open."""
        return port in self._devices
