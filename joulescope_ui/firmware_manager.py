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


from zipfile import ZipFile
import os
from joulescope_ui.config import APP_PATH
import monocypher
import binascii
import pkgutil
import json
import requests
import logging


log = logging.getLogger(__name__)


SIGNING_KEY_PUBLIC = binascii.unhexlify(b'32fe2bed04bbc42fe1b382e0371ba95ec2947045e8d919e49fdef601e24c105e')
FIRMWARE_PATH = os.path.join(APP_PATH, 'firmware', 'js110')
URL = 'https://www.joulescope.com/firmware/js110/'
URL_TIMEOUT = 30.0


if not os.path.isdir(FIRMWARE_PATH):
    os.makedirs(FIRMWARE_PATH)


VERSIONS = {
    'namespace': 'joulescope',
    'type': 'firmware-versions',
    'version': 1,
    'data': {
        'format': 'js110_{version}.img',
        # alpha
        # beta
        'production': '1.1.0',
        'available': ['1.1.0']
    }
}


def _download_from_distribution(path):
    package = 'joulescope_ui.firmware.js110'
    filename = os.path.basename(path)
    try:
        bin_file = pkgutil.get_data(package, filename)
    except:
        return False
    if bin_file is not None:
        with open(path, 'wb') as f:
            f.write(bin_file)
        return True
    log.info('Distribution does not contain firmware image: %s, %s', package, filename)
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


def _load(path):
    with ZipFile(path, mode='r') as f_zip:
        with f_zip.open('index.json', 'r') as f:
            index_bytes = f.read()
        with f_zip.open('index.sig', 'r') as f:
            index_sig = binascii.unhexlify(f.read())

        if not monocypher.signature_check(index_sig, SIGNING_KEY_PUBLIC, index_bytes):
            log.warning('integrity check failed: index.json')
            return None

        index = json.loads(index_bytes.decode('utf-8'))
        for image in index['target']['images']:
            with f_zip.open(index['data'][image]['image'], 'r') as f:
                index['data'][image]['image'] = f.read()
            sig = binascii.unhexlify(index['data'][image]['signature'])
            if not monocypher.signature_check(sig, SIGNING_KEY_PUBLIC, index['data'][image]['image']):
                log.warning('integrity check failed: %s' % (image, ))
                return None
    return index


def load(version=None):
    try:
        if version is None:
            version = VERSIONS['data']['production']
        version_str = version.replace('.', '_')
        filename = VERSIONS['data']['format'].format(version=version_str)

        # Attempt local cache
        path = os.path.join(FIRMWARE_PATH, filename)
        try:
            return _load(path)
        except:
            pass

        # download to local cache
        if not _download_from_distribution(path):
            if not _download(path):
                return None
        return _load(path)
    except:
        log.exception('firmware_manager.load')
        return None


def version_required(release=None):
    release = 'production' if release is None else str(release)
    v = VERSIONS['data'][release]
    return tuple([int(x) for x in v.split('.')])
