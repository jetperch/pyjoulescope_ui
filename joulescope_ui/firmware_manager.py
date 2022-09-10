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


import os
from joulescope.v0.firmware_manager import load as _load, upgrade, version_required, VERSIONS
from joulescope_ui.paths import paths_current
import binascii
import pkgutil
import requests
import logging


log = logging.getLogger(__name__)


SIGNING_KEY_PUBLIC = binascii.unhexlify(b'32fe2bed04bbc42fe1b382e0371ba95ec2947045e8d919e49fdef601e24c105e')
URL = 'https://download.joulescope.com/firmware/js110/'
URL_TIMEOUT = 30.0


def _download_from_distribution(path):
    filename = os.path.basename(path)
    try:
        bin_file = pkgutil.get_data('joulescope_ui', 'firmware/js110/' + filename)
    except Exception:
        return False
    if bin_file is not None:
        with open(path, 'wb') as f:
            f.write(bin_file)
        return True
    log.info('Distribution does not contain firmware image: %s', filename)
    return False


def _download(path):
    filename = os.path.basename(path)
    url = URL + filename
    r = requests.get(url, timeout=URL_TIMEOUT)
    if r.status_code == 200:
        with open(path, 'wb') as f:
            for chunk in r:
                f.write(chunk)
        return True
    log.warning('Could not download firmware image: %s', url)
    return None


def cache_path(version=None):
    if version is None:
        version = VERSIONS['data']['production']
    version_str = version.replace('.', '_')
    filename = VERSIONS['data']['format'].format(version=version_str)

    # Attempt local cache
    firmware_path = paths_current()['dirs']['firmware']
    firmware_path = os.path.join(firmware_path, 'js110')
    if not os.path.isdir(firmware_path):
        os.makedirs(firmware_path)
    path = os.path.join(firmware_path, filename)
    return path


def cache_fill(path):
    # download to local cache
    if not _download_from_distribution(path):
        if not _download(path):
            return None
    return path


def load(version=None):
    try:
        path = cache_path(version)
        try:
            return _load(path)
        except Exception:
            pass
        cache_fill(path)
        return _load(path)
    except Exception:
        log.exception('firmware_manager.load')
        return None
