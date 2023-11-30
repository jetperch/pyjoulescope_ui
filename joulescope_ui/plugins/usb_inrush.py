# Copyright 2018-2023 Jetperch LLC
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


# https://www.usb.org/document-library/usbet20

from joulescope_ui import register, N_, time64
from joulescope_ui.range_tool import RangeToolBase
import datetime
import numpy as np
import os
import subprocess
import logging


_log = logging.getLogger(__name__)
USBET20_PATHS = [
    r"C:\Program Files\USB-IF Test Suite\USBET20\USBET20.exe",
    r"C:\Program Files (x86)\USB-IF Test Suite\USBET20\USBET20.exe",
]


def find_usbet20():
    path = [p for p in USBET20_PATHS if os.path.isfile(p)]
    if len(path):
        return path[0]
    return None


def construct_path(base_path):
    time_start = datetime.datetime.utcnow()
    timestamp_str = time_start.strftime('%Y%m%d_%H%M%S')
    base = f'{timestamp_str}'
    p = os.path.join(base_path, 'usbet', base)
    if not os.path.isdir(p):
        os.makedirs(p, exist_ok=True)
    return p


class UsbInrush(RangeToolBase):
    NAME = N_('USB Inrush')
    BRIEF = N_('Perform USB Inrush testing')
    DESCRIPTION = N_("""\
        Use dual markers to select at least 100 milliseconds
        after enabling power to the target device.  This tool
        will send the selected data to the USBET tool for analysis.""")

    def __init__(self, value):
        self._signals = {}
        super().__init__(value)

    def _find_signals(self):
        for signal_id in self.signals:
            if signal_id.endswith('.i'):
                i_signal_id = signal_id
                signal_parts = signal_id.split('.')[:-1]
                signal_parts.append('v')
                v_signal_id = '.'.join(signal_parts)
                if v_signal_id in self.signals:
                    return i_signal_id, v_signal_id
        return None, None

    def _run(self):
        dpath = self.pubsub.query('common/settings/paths/data')
        dpath = construct_path(dpath)
        duration = (self.x_range[1] - self.x_range[0]) / time64.SECOND

        usbet20_path = find_usbet20()
        if usbet20_path is None:
            self.error('USBET tool not found.')
            return
        elif not 0.1 < duration < 0.5:
            self.error(f'Invalid duration {duration:.2f}, must be between 0.1 and 0.5 seconds.')
            return

        i_signal, v_signal = self._find_signals()
        if i_signal is None or v_signal is None:
            self.error(f'Current and voltage signals not found.')
            return

        i = self.request(i_signal, 'utc', *self.x_range, 0, timeout=30000.0)
        v = self.request(v_signal, 'utc', *self.x_range, 0, timeout=30000.0)
        fs = i['info']['time_map']['counter_rate']

        current = i['data']
        voltage = v['data']
        x = np.arange(len(current), dtype=np.float64) * (1.0 / fs)
        valid = np.isfinite(current)
        voltage = np.mean(voltage[valid])
        x = x[valid].reshape((-1, 1))
        i_mean = current[valid].reshape((-1, 1))
        values = np.hstack((x, i_mean))

        filename = os.path.join(dpath, 'inrush.csv')
        with open(filename, 'wt') as f:
            np.savetxt(f, values, ['%.8f', '%.3f'], delimiter=',')
        args = ','.join(['usbinrushcheck', filename, '%.3f' % voltage])
        _log.info('Running USBET20')
        rv = subprocess.run([usbet20_path, args], capture_output=True)
        _log.info('USBET returned %s\nSTDERR: %s\nSTDOUT: %s', rv.returncode, rv.stderr, rv.stdout)

    @staticmethod
    def on_cls_action_run(pubsub, topic, value):
        pubsub.register(UsbInrush(value))


def usb_inrush_register():
    """Register the USB Inrush range tool if USBET is available.
    """
    path = find_usbet20()
    if path is not None:
        register(UsbInrush)


usb_inrush_register()
