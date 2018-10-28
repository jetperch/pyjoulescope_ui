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


def is_available(usbet20_path=None):
    if usbet20_path is None:
        usbet20_path = USBET20_PATH
    return os.path.isfile(usbet20_path)


def run(data, sampling_frequency, usbet20_path=None):
    if usbet20_path is None:
        usbet20_path = USBET20_PATH
    x = np.arange(len(data), dtype=np.float) * (1.0 / sampling_frequency)
    i_mean = data[:, 0, 0]
    v_mean = data[:, 1, 0]
    valid = np.isfinite(i_mean)
    voltage = np.mean(v_mean[valid])
    x = x[valid].reshape((-1, 1))
    i_mean = i_mean[valid].reshape((-1, 1))
    values = np.hstack((x, i_mean))

    with tempfile.TemporaryDirectory(prefix='js_') as tempdir:
        filename = os.path.join(tempdir, 'inrush.csv')
        with open(filename, 'wt') as f:
            np.savetxt(f, values, ['%.8f', '%.3f'], delimiter=',')
        args = ','.join(['usbinrushcheck', filename, '%.3f' % voltage])
        log.info('Running USBET20')
        rv = subprocess.run([usbet20_path, args], capture_output=True)
        log.info('USBET returned %s\nSTDERR: %s\nSTDOUT: %s', rv.returncode, rv.stderr, rv.stdout)
    return rv.returncode

