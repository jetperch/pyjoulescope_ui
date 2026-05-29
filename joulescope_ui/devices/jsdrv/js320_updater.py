# Copyright 2026 Jetperch LLC
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

from .device import Device
from joulescope_ui import N_, CAPABILITIES, register, Metadata
from pyjoulescope_driver.program_js320 import program_js320
import copy
import threading


_ST_INITIAL = 0
_ST_RUNNING = 1
_ST_DONE = 2
_ST_ERROR = 3


class Js320Updater(Device):
    """Handle JS320 firmware updates via the in-driver fwup manager.

    Unlike :class:`Js220Updater`, this class is short-lived and stateless:
    the entire update sequence runs inside the driver's worker thread.
    This class just calls :func:`program_js320` and re-publishes the
    status callback as UI progress events.
    """

    CAPABILITIES = [CAPABILITIES.DEVICE_CLASS]
    SETTINGS = {
        'state': {
            'dtype': 'int',
            'brief': N_('Firmware update state'),
            'default': _ST_INITIAL,
            'options': [
                [_ST_INITIAL, 'initial'],
                [_ST_RUNNING, 'running'],
                [_ST_DONE,    'done'],
                [_ST_ERROR,   'error'],
            ],
            'flags': ['ro', 'tmp'],
        },
    }
    EVENTS = {
        '!progress': Metadata('obj', 'progress'),
    }

    def __init__(self, driver, device_path):
        super().__init__(driver, device_path)
        self.CAPABILITIES = [CAPABILITIES.DEVICE_OBJECT]
        _, model, serial_number = device_path.split('/')
        if model[0] == '&':
            model = model[1:]
        device_id = f'{model.upper()}-{serial_number}'
        self._device_id = device_id
        self.SETTINGS = copy.deepcopy(Js320Updater.SETTINGS)
        self.SETTINGS['name'] = {
            'dtype': 'str',
            'brief': 'JS320 Updater device name',
            'default': f'{device_id}-UPDATER',
        }
        self.SETTINGS['progress'] = {
            'dtype': 'float',
            'brief': 'progress',
            'default': 0.0,
            'flags': ['tmp'],
        }

        self._thread = None

    def _join(self):
        thread, self._thread = self._thread, None
        if thread is not None:
            self._log.info('thread join start')
            thread.join()
            self._log.info('thread join done')

    def on_pubsub_register(self):
        self._join()
        self.state = _ST_RUNNING  # set before thread starts so the JsdrvWrapper guard sees it
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def on_pubsub_unregister(self):
        self._join()

    def _publish_progress(self, completion, brief):
        completion = float(completion)
        self._ui_publish('settings/progress', completion)
        value = {
            'updater_id': self.unique_id,
            'device_id': self._device_id,
            'progress': completion,
            'brief': str(brief),
        }
        self.pubsub.publish('registry/JS320_Updater/events/!progress', value)

    def _run(self):
        self._log.info('thread start, path=%s', self.device_path)
        try:
            program_js320(self._driver, self.device_path,
                          package_path=None, progress=self._publish_progress)
            self.state = _ST_DONE
            self._log.info('JS320 firmware update complete')
        except Exception as ex:
            self.state = _ST_ERROR
            self._log.exception('JS320 firmware update failed')
            # Force progress to 1.0 so the dialog advances out of the in-progress row.
            self._publish_progress(1.0, f'Error: {ex}')
        finally:
            self._log.info('thread done, path=%s', self.device_path)
            # Drop the thread reference before unregistering so that
            # on_pubsub_unregister's _join() does not try to join the
            # current thread (which would raise RuntimeError).
            wrapper = self._wrapper
            path = self.device_path
            self._thread = None
            try:
                self.pubsub.unregister(self)
            except Exception:
                self._log.exception('unregister failed')
            # Evict the stale Js320 if it is still tracked.  The fwup worker
            # transparently survives the USB disconnect/reconnect during the
            # ctrl firmware reboot, so the wrapper typically does not see an
            # @/!remove event and the old Js320 lingers in wrapper.devices.
            # Without this, the _on_device_add call below would early-return
            # at the `if value in self.devices` guard and no fresh Js320
            # would ever be created.
            try:
                wrapper._on_device_remove(path)
            except Exception:
                self._log.exception('post-update device remove failed for %s', path)
            # Re-create the regular Js320 for this device.
            try:
                wrapper._on_device_add(path)
            except Exception:
                self._log.exception('post-update device add failed for %s', path)


register(Js320Updater, 'JS320_Updater')
