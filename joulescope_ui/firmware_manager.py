# Copyright 2019-2022 Jetperch LLC
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


from joulescope.v1 import DriverWrapper
from pyjoulescope_driver.release import release_get, release_to_available
from pyjoulescope_driver.program import release_program
import time
from joulescope_ui.paths import paths_current
import json
import os
import pkgutil
import requests
import logging
import threading


_log = logging.getLogger(__name__)


def version_as_list(v):
    if isinstance(v, int):
        return [(v >> 24) & 0xff, (v >> 16) & 0xff, v & 0xffff]
    elif isinstance(v, str):
        return [int(x) for x in v.split('.')]
    else:
        return v


def version_as_str(v):
    v = version_as_list(v)
    ver = [str(x) for x in v]
    return '.'.join(ver)


def version_as_u32(v):
    v = version_as_list(v)
    return ((v[0] & 0xff) << 24) | ((v[1] & 0xff) << 16) | (v[2] & 0xffff)


def load(maturity=None):
    """Load the available firmware.

    :param maturity: The desired firmware maturity level, which is one of:
        * alpha
        * beta
        * stable
    :return: The binary release image.
    """
    return release_get(maturity)


def is_upgrade_available(device, image):
    """Determine if an upgrade is available

    :param device: The open device.
    :param image: The binary release image.
    :return: None or dict[name: str, (from: str, to: str)]
    """
    r = release_to_available(image)
    app_from = version_as_u32(device.query('c/fw/version'))
    fpga_from = version_as_u32(device.query('s/fpga/version'))
    app_to = r['app']
    fpga_to = r['fpga']
    if app_to > app_from or fpga_to > fpga_from:
        return {
            'app': (version_as_str(app_from), version_as_str(app_to)),
            'fpga': (version_as_str(fpga_to), version_as_str(fpga_from)),
        }
    else:
        return None


def _upgrade(device, image, progress_cbk):
    driver_wrapper = DriverWrapper()
    driver = driver_wrapper.driver
    try:
        return release_program(driver, device.device_path, image, progress=progress_cbk)
    except Exception:
        progress_cbk(1.0, 'Upgrade failed')
        raise


def upgrade(device, image, progress_cbk=None):
    """Full upgrade the device's firmware.

    :param device: The :class:`Device` instance that must already be open.
    :param image: The image returned by :func:`load`.  Alternatively, a path
        suitable for :func:`load`.
    :param progress_cbk: An optional callable(completion: float, msg: str) callback.
        When provided, this function will be called to provide progress updates.
        * completion: The completion status from 0.0 (not started) to 1.0 (done).
        * msg: A user-meaningful status message.
    :return: The :class:`Device` which is closed.
    raise IOError: on failure.
    """
    if progress_cbk is None:
        progress_cbk = lambda x: None
    args = [device, image, progress_cbk]
    thread = threading.Thread(name='fw_upgrade', target=_upgrade, args=args)
    thread.start()
    return thread
