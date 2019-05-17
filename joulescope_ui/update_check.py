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
from joulescope_ui import VERSION
import logging

log = logging.getLogger(__name__)
URL = 'https://www.joulescope.com/app_download/version.json'
TIMEOUT = 30.0


def is_newer(version):
    current_version = VERSION.split('.')
    latest_version = version.split('.')
    return latest_version > current_version


def fetch(callback):
    try:
        response = requests.get(URL, timeout=TIMEOUT)
        data = json.loads(response.text)

        latest_version = data.get('production', '0.0.0')
        if is_newer(latest_version):
            callback(VERSION, latest_version)
            return True
        return False
    except Exception:
        log.warning('Could not connect to software download server')
        return False

def check(callback):
    """Check for software updates.

    :param callback: The function to call if an update is required.
        The signature is callback(current_version, latest_version).
    """
    if VERSION == 'UNRELEASED':
        return
    thread = threading.Thread(target=fetch, args=[callback])
    thread.daemon = True
    thread.start()
