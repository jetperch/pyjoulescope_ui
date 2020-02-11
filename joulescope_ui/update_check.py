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
from joulescope_ui import __version__
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
    return str_to_version(version) > current_version()


def fetch(callback, channel=None):
    channel = _validate_channel(channel)
    try:
        response = requests.get(URL_INDEX, timeout=TIMEOUT)
        data = json.loads(response.text)

        latest_version = data.get('active', {}).get(channel, [0, 0, 0])
        if not is_newer(latest_version):
            log.debug('software up to date: version=%s, latest=%s, channel=%s',
                      version_to_str(current_version()),
                      version_to_str(latest_version),
                      channel)
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
        callback(__version__, version_to_str(latest_version), path)
        return True
    except Exception:
        log.warning('Could not connect to software download server')
        return False


def check(callback, channel=None):
    """Check for software updates.

    :param callback: The function to call if an update is required.
        The signature is callback(current_version, latest_version, url).
    :param channel: The software update channel which is in:
        ['alpha', 'beta', 'stable'].  None (default) is equivalent to 'stable'.
    """
    if __version__ == 'UNRELEASED':
        log.info('Skip software update check: version is UNRELEASED')
        return
    channel = _validate_channel(channel)
    thread = threading.Thread(target=fetch, args=[callback, channel])
    thread.daemon = True
    thread.start()
