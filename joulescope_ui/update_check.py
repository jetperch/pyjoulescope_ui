# Copyright 2019 Jetperch LLC
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
from joulescope_ui import VERSION
import logging

log = logging.getLogger(__name__)
URL_BASE = 'https://download.joulescope.com/joulescope_install/'
URL_INDEX = URL_BASE + 'index.json'
DOWNLOAD_DEFAULT_URL = 'https://www.joulescope.com/download'
TIMEOUT = 30.0


_PLATFORM_MAP = {
    # Python name : Joulescope_install paths key
    'Windows': 'win10',
    'Darwin': 'macos',
    'Linux': 'ubuntu'
}


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
    return str_to_version(VERSION)


def is_newer(version):
    return str_to_version(version) > current_version()


def fetch(callback):
    try:
        response = requests.get(URL_INDEX, timeout=TIMEOUT)
        data = json.loads(response.text)

        latest_version = data.get('active', {}).get('stable', [0, 0, 0])
        if not is_newer(latest_version):
            return False
        path = _PLATFORM_MAP.get(platform.system())
        if path is None:
            path = DOWNLOAD_DEFAULT_URL
        else:
            path = data['paths'][path]
            path = path.replace('{version_major}', str(latest_version[0]))
            path = path.replace('{version_minor}', str(latest_version[1]))
            path = path.replace('{version_patch}', str(latest_version[2]))
            path = path
        callback(VERSION, version_to_str(latest_version), path)
        return True
    except Exception:
        log.warning('Could not connect to software download server')
        return False


def check(callback):
    """Check for software updates.

    :param callback: The function to call if an update is required.
        The signature is callback(current_version, latest_version, url).
    """
    if VERSION == 'UNRELEASED':
        return
    thread = threading.Thread(target=fetch, args=[callback])
    thread.daemon = True
    thread.start()
