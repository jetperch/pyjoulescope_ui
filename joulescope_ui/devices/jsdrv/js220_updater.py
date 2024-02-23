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

from .device import Device
from joulescope_ui import N_, CAPABILITIES, get_topic_name, register, Metadata
from pyjoulescope_driver.release import release_get, release_to_segments, \
    SUBTYPE_CTRL_APP, SUBTYPE_CTRL_UPDATER2, \
    SUBTYPE_CTRL_UPDATER1, SUBTYPE_SENSOR_FPGA, \
    TARGETS, \
    CTRL_TYPE_UPD1, CTRL_TYPE_UPD2, CTRL_TYPE_APP
import copy
import numpy as np
import threading


_SUBTYPE_TO_NAMES = {
    SUBTYPE_CTRL_UPDATER1: 'update1',
    SUBTYPE_CTRL_UPDATER2: 'update2',
    SUBTYPE_SENSOR_FPGA:   None,
    SUBTYPE_CTRL_APP:      'app',
}


TARGET_ID_TO_NAMES = {
    CTRL_TYPE_UPD1: 'update1',
    CTRL_TYPE_UPD2: 'update2',
    CTRL_TYPE_APP: 'app',
}


_ST_INITIAL          = 0
_ST_UPDATER1_VERSION = 1
_ST_UPDATER2_VERSION = 2
_ST_UPDATER1_PROGRAM = 3
_ST_UPDATER2_PROGRAM = 4
_ST_FPGA_PROGRAM     = 5
_ST_APP_PROGRAM      = 6


class Js220Updater(Device):
    """Handle JS220 firmware updates.

    This class handles repeated connect/disconnects as the device
    ungoes the update process.  This class loosely implements a finite
    state machine that manages the update process.  States dispatch
    to a method.  Events are reconnects or internally generated.
    """

    CAPABILITIES = [CAPABILITIES.DEVICE_CLASS]
    SETTINGS = {
        'state': {
            'dtype': 'int',
            'brief': N_('Firmware update state'),
            'default': 0,
            'options': [
                [_ST_INITIAL,          'initial'],
                [_ST_UPDATER1_VERSION, 'Updater 1 version check'],
                [_ST_UPDATER2_VERSION, 'Updater 2 version check'],
                [_ST_UPDATER1_PROGRAM, 'Updater 1 program'],
                [_ST_UPDATER2_PROGRAM, 'Updater 2 program'],
                [_ST_FPGA_PROGRAM, 'Program FPGA'],
                [_ST_APP_PROGRAM, 'Program APP'],
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
        self._state_handlers = {  # must match with "state" options above
            _ST_INITIAL:          self._state_initial,
            _ST_UPDATER1_VERSION: self._state_updater1_version_check,
            _ST_UPDATER2_VERSION: self._state_updater2_version_check,
            _ST_UPDATER1_PROGRAM: self._state_updater1_program,
            _ST_UPDATER2_PROGRAM: self._state_updater2_program,
            _ST_FPGA_PROGRAM:     self._state_fpga_program,
            _ST_APP_PROGRAM:      self._state_app_program,
        }
        self._progress_vector = np.array([
            0.00,  # start
            0.02,  # Initial
            0.06,  # Updater 1 version
            0.10,  # Updater 2 version
            0.20,  # Updater 2 program
            0.30,  # Updater 1 program
            0.65,  # FPGA program
            1.00,  # App program
        ])
        _, model, serial_number = device_path.split('/')
        name = f'{model[1:].upper()}-{serial_number}'
        self._device_id = name
        self.SETTINGS = copy.deepcopy(Js220Updater.SETTINGS)
        self.SETTINGS['name'] = {
            'dtype': 'str',
            'brief': 'JS220 Updater device name',
            'default': name,
        }
        self.SETTINGS['versions'] = {
            'dtype': 'obj',
            'brief': 'versions',
            'default': None,
            'flags': ['tmp'],
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
        self._join()  # should not be necessary
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def on_pubsub_unregister(self):
        self._join()

    def _state_progress(self, progress):
        state = self.state
        p0 = self._progress_vector[state]
        p1 = self._progress_vector[state + 1]
        p = p0 + (p1 - p0) * float(progress)
        self._ui_publish('settings/progress', p)
        value = {
            'updater_id': self.unique_id,
            'device_id': self._device_id,
            'progress': p,
            'brief': '',
        }
        self.pubsub.publish('registry/JS220_Updater/events/!progress', value)

    @property
    def firmware_channel(self):
        unique_id = self.unique_id.replace('-UPDATER', '')
        topic = f'{get_topic_name(unique_id)}/settings/firmware_channel'
        return self.pubsub.query(topic, default='stable')

    def erase(self, subtype):
        target = TARGETS[subtype]
        region = target['mem_region']
        self._driver_publish(f'{region}/!erase', 0, timeout=10)

    def write(self, subtype):
        target = TARGETS[subtype]
        image = release_get(self.firmware_channel)
        segments = release_to_segments(image)
        segment = segments[subtype]
        region = target['mem_region']
        self._driver_publish(f'{region}/!write', segment['img'], timeout=10)

    def program(self, subtype):
        """Program a segment.

        :param subtype: The release subtype integer, one of
            [SUBTYPE_CTRL_UPDATER1, SUBTYPE_CTRL_UPDATER2, SUBTYPE_CTRL_APP, SUBTYPE_SENSOR_FPGA]
        """
        for attempt in range(10):
            try:
                self._state_progress(0.0)
                self.erase(subtype)
                self._state_progress(0.4)
                self.write(subtype)
                self._state_progress(1.0)
                return
            except Exception:
                self._log.exception('retry %d', attempt + 1)
        raise RuntimeError('Could not program')

    @property
    def version(self):
        return self._driver_query('c/fw/version')

    @property
    def _target(self):
        target_id = self._driver_query('c/target')
        return TARGET_ID_TO_NAMES[target_id]

    def _reset_to(self, subtype):
        if isinstance(subtype, str):
            name = subtype
        else:
            name = _SUBTYPE_TO_NAMES[subtype]
        self._log.info('reset_to %s', name)
        self._driver_publish('h/!reset', name)

    def _abnormal_restart(self):
        self._log.warning('Abnormal condition state=%s, target=%s, restart', self.state, self._target)
        self.state = _ST_INITIAL
        self._reset_to(SUBTYPE_CTRL_UPDATER1)

    def _state_initial(self):
        self._log.info('initial: target=%s', self._target)
        self.state = _ST_UPDATER1_VERSION
        self.versions = {
            'updater1': None,
            'updater2': None,
        }
        if self._target != 'update1':
            self._reset_to(SUBTYPE_CTRL_UPDATER1)
        else:
            self._state_progress(1.0)
            self._state_updater1_version_check()

    def _state_updater1_version_check(self):
        self._log.info('updater1_version_check')
        if self._target == 'update1':
            self.versions['updater1'] = self.version
            self._state_progress(1.0)
            self.state = _ST_UPDATER2_VERSION
            self._reset_to(SUBTYPE_CTRL_UPDATER2)
        elif self._target == 'update2':  # abnormal
            self._log.warning('updater1_version_check, but in update2, program update1')
            self.program(SUBTYPE_CTRL_UPDATER1)
            self._reset_to(SUBTYPE_CTRL_UPDATER1)
        else:  # should never get here, but just in case
            self._log.warning('updater1_version_check, but in %s', self._target)
            self._reset_to(SUBTYPE_CTRL_UPDATER1)

    def _state_updater2_version_check(self):
        self._log.info('updater2_version_check')
        if self._target == 'update2':
            self.versions['updater2'] = self.version
            self._state_progress(1.0)
            self.state = _ST_UPDATER1_PROGRAM
            self._state_updater1_program()
        elif self._target == 'update1':  # abnormal
            self._log.warning('updater2_version_check, but in update1, program update2')
            self.program(SUBTYPE_CTRL_UPDATER2)
            self._reset_to(SUBTYPE_CTRL_UPDATER2)
        else:  # should never get here, but just in case
            self._log.warning('updater2_version_check, but in %s', self._target)
            self._reset_to(SUBTYPE_CTRL_UPDATER2)

    def _state_updater1_program(self):
        self._log.info('updater1_program')
        if self._target == 'update2':
            self.program(SUBTYPE_CTRL_UPDATER1)
            self.state = _ST_UPDATER2_PROGRAM
            self._reset_to(SUBTYPE_CTRL_UPDATER1)
        else:
            self._abnormal_restart()

    def _state_updater2_program(self):
        self._log.info('updater2_program')
        if self._target == 'update1':
            self.program(SUBTYPE_CTRL_UPDATER2)
            self.state = _ST_FPGA_PROGRAM
            self._reset_to(SUBTYPE_CTRL_UPDATER2)
        else:
            self._abnormal_restart()

    def _state_fpga_program(self):
        self._log.info('program FPGA')
        if self._target == 'update2':
            self.program(SUBTYPE_SENSOR_FPGA)
            self.state = _ST_APP_PROGRAM
            self._state_app_program()
        else:
            self._abnormal_restart()

    def _state_app_program(self):
        self._log.info('program app')
        if self._target == 'update2':
            self.program(SUBTYPE_CTRL_APP)
            self.state = _ST_INITIAL
            self._reset_to(SUBTYPE_CTRL_APP)
        else:
            self._abnormal_restart()

    def _state_unknown(self):
        self._log.info('unknown')
        self._abnormal_restart()

    def _run(self):
        self._log.info('thread start, path=%s, state=%s', self.device_path, self.state)
        try:
            self._driver.open(self.device_path, mode='restore')
        except Exception:
            self._log.exception('driver open failed')
            return  # any error recovery possible?
        try:
            self._log.info('handle state %s, target %s', self.state, self._target)
            self._state_progress(0.0)
            fn = self._state_handlers.get(self.state, self._state_unknown)
            fn()
        finally:
            self._driver.close(self.device_path)
        self._log.info('thread done')


register(Js220Updater, 'JS220_Updater')
