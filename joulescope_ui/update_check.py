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

"""Check for software updates"""

import requests
import json
import threading
import platform
from joulescope_ui import __version__
from joulescope_ui.paths import paths_current
import logging
import hashlib
import os
import shutil
import subprocess


log = logging.getLogger(__name__)
URL_BASE = 'https://download.joulescope.com/joulescope_install/'
URL_INDEX = URL_BASE + 'index_v2.json'
TIMEOUT = 30.0


def _validate_channel(channel):
    if channel is None:
        channel = 'stable'
    channel = str(channel).lower()
    if channel not in ['alpha', 'beta', 'stable']:
        raise ValueError(f'Unsupported update channel "{channel}"')
    return channel


def str_to_version(v):
    if isinstance(v, str):
        v = v.split('.')
    if len(v) != 3:
        raise ValueError('invalid version - needs [major, minor, patch]')
    return [int(x) for x in v]


def version_to_str(v):
    if isinstance(v, str):
        v = str_to_version(v)
    if len(v) != 3:
        raise ValueError('invalid version - needs [major, minor, patch]')
    return '.'.join(str(x) for x in v)


def current_version():
    return str_to_version(__version__)


def is_newer(version):
    if 'dev' in __version__:
        return False
    return str_to_version(version) > current_version()


def _platform_name():
    psys = platform.system()
    if psys == 'Windows':
        if platform.machine() == 'AMD64':
            return 'win10_x86_64'  # for both win10 and win11
    elif psys == 'Linux':
        # assume all Linux is the supported Ubuntu version for now
        return 'ubuntu_22_04_x86_64'
    elif psys == 'Darwin':
        release, _, machine = platform.mac_ver()
        # use "machine" to add arm64 support here
        release_major = int(release.split('.')[0])
        if release_major >= 12:
            if platform.machine() == 'arm64':
                return 'macos_12_0_arm64'
            else:
                return 'macos_12_0_x86_64'
        elif release_major == 10:
            return 'macos_10_15_x86_64'
        else:
            raise RuntimeError(f'unsupported macOS version {release}')
    else:
        raise RuntimeError(f'unsupported platform {psys}')


def fetch_info(channel=None):
    """Fetch the update information.

    :param channel: The software update channel which is one of
        ['alpha', 'beta', 'stable'].  None (default) is equivalent to 'stable'.
    :return: None on error or dict containing:
        * channel: The update channel.
        * current_version: The currently running version string.
        * available_version: The available version string.
        * download_url: The URL to download the available version.
        * sha256_url: The URL to download the SHA256 over the download contents.
        * changelog_url: The URL to download the changelog for the available version.
    """
    channel = _validate_channel(channel)
    platform_name = _platform_name()

    try:
        response = requests.get(URL_INDEX, timeout=TIMEOUT)
    except Exception:
        log.warning('Could not connect to software download server')
        return None

    try:
        data = json.loads(response.text)
    except Exception:
        log.warning('Could not parse software metadata')
        return None

    try:
        active = data.get('active', {}).get(channel, {})
        latest_version = active.get('version', [0, 0, 0])
        if not is_newer(latest_version):
            log.debug('software up to date: version=%s, latest=%s, channel=%s',
                      __version__,
                      version_to_str(latest_version),
                      channel)
            _download_cleanup()
            return None
        return {
            'channel': channel,
            'current_version': __version__,
            'available_version': version_to_str(latest_version),
            'download_url': URL_BASE + active['releases'][platform_name],
            'changelog_url': URL_BASE + active['changelog']
        }
    except Exception:
        log.exception('Unexpected error checking available software')
        return None


def _download_cleanup():
    path = paths_current()['dirs']['update']
    shutil.rmtree(path, ignore_errors=True)


def _download(url):
    path = paths_current()['dirs']['update']
    os.makedirs(path, exist_ok=True)
    fname = url.split('/')[-1]
    path = os.path.join(path, fname)

    try:
        response = requests.get(url + '.sha256', timeout=TIMEOUT)
    except Exception:
        log.warning('Could not download %s', url)
        return None
    sha256_hex = response.text.split(' ')[0]

    def validate_hash():
        if os.path.isfile(path):
            m = hashlib.sha256()
            with open(path, 'rb') as f:
                m.update(f.read())
            return m.hexdigest() == sha256_hex
        return False

    if validate_hash():  # skip download if already downloaded
        return path
    try:
        response = requests.get(url, timeout=TIMEOUT)
    except Exception:
        log.warning('Could not download %s', url)
        return None

    path_tmp = path + '.tmp'
    with open(path_tmp, 'wb') as f:
        f.write(response.content)
    os.rename(path_tmp, path)
    if validate_hash():
        return path
    raise RuntimeError('Invalid sha256 hash')


def _run(callback, channel):
    try:
        info = fetch_info(channel)
        if info is None:
            return None
        info['download_path'] = _download(info['download_url'])
        #info['changelog_path'] = _download(info['changelog_url'])
        callback(info)
    except Exception:
        log.info('Software update check failed')


def check(callback, channel=None):
    """Check for software updates.

    :param callback: The function to call if an update is required.
        The signature is callback(info).  The info dict contains keys:
        * channel: The update channel.
        * current_version: The currently running version string.
        * available_version: The available version string.
        * download_path: The path to the available version installer.
        * changelog_path: The path to the changelog for the available version.
    :param channel: The software update channel which is in:
        ['alpha', 'beta', 'stable'].  None (default) is equivalent to 'stable'.
    """
    if __version__ == 'UNRELEASED':
        log.info('Skip software update check: version is UNRELEASED')
        return
    channel = _validate_channel(channel)
    _platform_name()
    thread = threading.Thread(name='sw_update_check', target=_run, args=[callback, channel])
    thread.daemon = True
    thread.start()


def apply(info):
    path = info['download_path']
    if platform.system() == 'Windows':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([path, '/SILENT'], creationflags=flags)


if __name__ == '__main__':
    _run(lambda x: print(x), 'stable')
