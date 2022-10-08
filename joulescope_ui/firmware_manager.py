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


from joulescope import scan
import time
from joulescope_ui.paths import paths_current
import binascii
import json
import os
import pkgutil
import requests
import logging
import threading


_log = logging.getLogger(__name__)


URL = 'https://download.joulescope.com/firmware/js220/'
URL_TIMEOUT = 30.0


def _load_from_distribution(maturity=None):
    relpath = 'firmware/js220/'
    index_file = pkgutil.get_data('joulescope_ui', relpath + 'index.json')
    index_file = json.loads(index_file)
    result = {}
    for target, value in index_file.items():
        v = value[maturity]
        v['img'] =  pkgutil.get_data('joulescope_ui', relpath + v['path'])
        v['changelog'] = pkgutil.get_data('joulescope_ui', relpath + v['changelog'])
        result[target] = v
    return result


def _load_file_from_network(path, cache_path):
    fname = os.path.join(cache_path, path)
    if not os.path.isfile(fname):
        os.makedirs(os.path.dirname(fname), exist_ok=True)
        r = requests.get(URL + path, timeout=URL_TIMEOUT)
        if r.status_code != 200:
            raise FileNotFoundError(URL + path)
        with open(fname, 'wb') as f:
            for chunk in r:
                f.write(chunk)
    with open(fname, 'rb') as f:
        return f.read()


def _load_from_network(maturity=None):
    firmware_path = os.path.join(paths_current()['dirs']['firmware'], 'js220')
    os.makedirs(firmware_path, exist_ok=True)
    index_filename = os.path.join(firmware_path, 'index.json')
    r = requests.get(URL + 'index.json', timeout=URL_TIMEOUT)
    if r.status_code != 200:
        raise FileNotFoundError(URL + 'index.json')
    txt = r.text.replace('\r\n', '\n')
    with open(index_filename, 'wt') as f:
        f.write(txt)
    index_file = json.loads(txt)

    result = {}
    for target, value in index_file.items():
        v = value[maturity]
        v['img'] = _load_file_from_network(v['path'], firmware_path)
        v['changelog'] = _load_file_from_network(v['changelog'], firmware_path)
        result[target] = v
    return result


def firmware_build_data_files():
    firmware_path = os.path.join(paths_current()['dirs']['firmware'], 'js220')
    _load_from_network(maturity='stable')
    _load_from_network(maturity='beta')
    _load_from_network(maturity='alpha')
    index_filename = os.path.join(firmware_path, 'index.json')
    with open(index_filename, 'rt') as f:
        idx = json.load(f)
    dst = 'joulescope_ui/firmware/js220/'
    files = []

    def _create(p):
        src = os.path.join(firmware_path, p)
        d = dst + os.path.basename(maturity_value['path'])
        return (src, d)

    for target_value in idx.values():
        for maturity_value in target_value.values():
            files.append(_create(maturity_value['path']))
            files.append(_create(maturity_value['changelog']))

    return files


def load(maturity=None):
    maturity = 'stable' if maturity is None else maturity.lower()
    if maturity not in ['nightly', 'alpha', 'beta', 'stable']:
        raise ValueError(f'invalid maturity level: {maturity}')
    try:
        return _load_from_distribution(maturity)
    except Exception:
        _log.info('firmware_manager could not load from distribution')
    try:
        return _load_from_network(maturity)
    except Exception:
        _log.info('firmware_manager could not load from network')
    return None


def _device_await(device_path, scan_name=None, timeout=None):
    timeout = 5.0 if timeout is None else float(timeout)
    t_start = time.time()
    while True:
        devices = scan(scan_name)
        devices = [d for d in devices if d.device_path == device_path]
        if len(devices):
            return devices[0]
        if time.time() - t_start > 5:
            _log.warning(f'timeout waiting for {device_path}')
            return None
        time.sleep(0.1)

def _upgrade(device, fw, progress_cbk, stage_cbk, done_cbk):
    path = device.device_path
    parts = path.split('/')
    parts[1] = '&' + parts[1]
    updater_path = '/'.join(parts)
    _log.info(f'FW upgrade: reset device {path}')
    device.publish('h/!reset', 'update1')
    device.close()
    stage_cbk(f'Performing upgrade')

    for i in range(1, 11):
        progress_cbk(0)
        device = _device_await(updater_path, scan_name='bootloader')
        if device is None:
            raise RuntimeError('timeout waiting for updater')
        _log.info(f'FW upgrade: found {updater_path}')
        progress_cbk(0.05)
        _log.info(f'FW upgrade: open {updater_path}')
        device.open()
        _log.info(f'FW upgrade: open {updater_path} done')
        progress_cbk(0.1)
        _log.info(f'FW upgrade: erase ctrl_app')
        device.publish('h/mem/c/app/!erase', 0, timeout=10)
        _log.info(f'FW upgrade: erase ctrl_app done')
        progress_cbk(0.4)
        _log.info(f'FW upgrade: write ctrl_app')
        device.publish('h/mem/c/app/!write', fw['ctrl_app']['img'], timeout=5)
        _log.info(f'FW upgrade: write ctrl_app done')
        progress_cbk(0.5)
        _log.info(f'FW upgrade: erase sensor_fpga')
        device.publish('h/mem/s/app1/!erase', 0, timeout=10)
        _log.info(f'FW upgrade: erase sensor_fpga done')
        progress_cbk(0.8)
        _log.info(f'FW upgrade: write sensor_fpga')
        device.publish('h/mem/s/app1/!write', fw['sensor_fpga']['img'], timeout=5)
        _log.info(f'FW upgrade: write sensor_fpga done')
        progress_cbk(0.95)
        _log.info(f'FW upgrade: reset to app')
        device.publish('h/!reset', 'app')
        _log.info(f'FW upgrade: reset to app done')

        device = _device_await(path, timeout=2.0)
        if device is not None:
            _log.info(f'FW upgrade: found {path}')
            progress_cbk(1.0)
            if callable(done_cbk):
                done_cbk(True)
            return
        _log.info(f'FW upgrade: timed out waiting for {path}')
        progress_cbk(0.0)
        stage_cbk(f'Performing upgrade - retry {i}')

    _log.error('firmware_upgrade failed')


def upgrade(device, fw, progress_cbk=None, stage_cbk=None, done_cbk=None):
    """Full upgrade the device's firmware.

    :param device: The :class:`Device` or class:`bootloader.Bootloader` instance
        that must already be open.
    :param image: The image returned by :func:`load`.  Alternatively, a path
        suitable for :func:`load`.
    :param progress_cbk:  The optional Callable[float] which is called
        with the progress fraction from 0.0 to 1.0
    :param stage_cbk: The optional Callable[str] which is called with a
        meaningful stage description for each stage of the upgrade process.
    :param done_cbk: The optional Callback[object] which is called with
        the device on success or None on failure.  If done_cbk is provided,
        then run the upgrade in its own thread.
    :return: The :class:`Device` which is closed.
    raise IOError: on failure.
    """
    if progress_cbk is None:
        progress_cbk = lambda x: None
    if stage_cbk is None:
        stage_cbk = lambda x: None
    args = [device, fw, progress_cbk, stage_cbk, done_cbk]
    thread = threading.Thread(name='fw_upgrade', target=_upgrade, args=args)
    thread.start()
    return thread
