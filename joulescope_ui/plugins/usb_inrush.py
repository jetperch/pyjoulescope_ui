# Copyright 2018 Jetperch LLC
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
# "C:\Program Files (x86)\USB-IF Test Suite\USBET20\USBET20.exe"

import numpy as np
import tempfile
import os
import subprocess
import logging


log = logging.getLogger(__name__)
USBET20_PATH = r"C:\Program Files (x86)\USB-IF Test Suite\USBET20\USBET20.exe"


PLUGIN = {
    'name': 'USB Inrush',
    'description': 'Run the USBET tool validate USB inrush current',
    # config: additional configuration options for this plugin
}


def is_available():
    return os.path.isfile(USBET20_PATH)


class UsbInrush:

    def run(self, data):  # RangeToolInvocation
        duration = data.sample_count / data.sample_frequency
        if not is_available():
            return f'USBET tool not found.'
        if not 0.1 < duration < 0.5:  # todo: confirm range
            return f'Invalid duration {duration:.2f}, must be between 0.1 and 0.5 seconds.'
        usbet20_path = USBET20_PATH
        d = data.samples_get()
        current = d['current']['value']
        voltage = d['voltage']['value']
        x = np.arange(len(current), dtype=np.float) * (1.0 / data.sample_frequency)
        valid = np.isfinite(current)
        voltage = np.mean(voltage[valid])
        x = x[valid].reshape((-1, 1))
        i_mean = current[valid].reshape((-1, 1))
        values = np.hstack((x, i_mean))

        with tempfile.TemporaryDirectory(prefix='js_') as tempdir:
            filename = os.path.join(tempdir, 'inrush.csv')
            with open(filename, 'wt') as f:
                np.savetxt(f, values, ['%.8f', '%.3f'], delimiter=',')
            args = ','.join(['usbinrushcheck', filename, '%.3f' % voltage])
            log.info('Running USBET20')
            rv = subprocess.run([usbet20_path, args], capture_output=True)
            log.info('USBET returned %s\nSTDERR: %s\nSTDOUT: %s', rv.returncode, rv.stderr, rv.stdout)


def plugin_register(api):
    """Register the USB Inrush plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    if not is_available():
        log.info('USBET20 tool not found - skip usb_inrush plugin')
        return True  # not an error, normal operation

    api.range_tool_register('Analysis/USB Inrush', UsbInrush)
    return True
