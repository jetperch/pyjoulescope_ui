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

# pip3 install requests fs

from fs.tarfs import TarFS
from fs.appfs import UserDataFS
import hashlib
import json
import os
import platform
import requests

URL = 'https://formulae.brew.sh/api/formula/libusb.json'

VERSION_MAP = {
    # friendly name, darwin version
    'arm64_ventura': 'arm64_22',
    'arm64_monterey': 'arm64_21',
    'arm64_big_sur': 'arm64_20',
    'monterey': 'x86_64_21',
    'big_sur': 'x86_64_20',
    'catalina': 'x86_64_19',
    'mojave': 'x86_64_18',
    'x86_64_linux': None,
}

HEADERS = {
    "Accept-Language": "en",
    "Authorization": "Bearer QQ=="
}


def _mac_binaries_index():
    try:
        r = requests.get(URL)
        d = r.json()
        d_str = json.dumps(d, indent=2)
        # print(json.dumps(d, indent=2))
        print('VERSION = {}'.format(d['versions']['stable']))
        return d, d_str
    except Exception:
        return None, None


def mac_binaries():
    """Retrieve the latest libusb dynamic libraries for each Mac OS version."""
    binaries = []
    with UserDataFS('joulescope_ui_build', create=True) as f_out:
        print('Working directory: %s' % f_out.getospath('').decode('utf-8'))
        d, d_str = _mac_binaries_index()
        if f_out.isfile('libusb.json'):
            with f_out.open('libusb.json', 'rt') as f:
                d_str_now = f.read()
            if bool(d_str_now) and d_str_now == d_str:
                with f_out.open('binaries.json', 'rt') as f:
                    return json.load(f)

        for os_name, k in d['bottle']['stable']['files'].items():
            if os_name not in VERSION_MAP:
                print(f'WARNING: unknown os_name {os_name} - skip')
                continue
            darwin_ver = VERSION_MAP[os_name]
            if darwin_ver is None or platform.machine() not in darwin_ver:
                print(f'Skip {os_name}, not needed')
                continue  # not needed
            # download and save the .tar.gz for each version
            path = os_name + '.zip'
            print(f'{path}: {darwin_ver} from {k["url"]}')
            r = requests.get(k['url'], headers=HEADERS)
            #print(hashlib.sha256(r.content).hexdigest())
            if hashlib.sha256(r.content).hexdigest() != k['sha256']:
                print('sha mismatch')
                continue
                pass # raise RuntimeError('sha mismatch')
            path_os = f_out.getospath(path).decode('utf-8')
            with f_out.open(path, 'wb') as f:
                f.write(r.content)

            # Extract and save the dynamic library
            with TarFS(path_os) as f_in:
                zip_path = 'libusb/%s/lib/libusb-1.0.0.dylib' % (d['versions']['stable'], )
                lib_path = '%s_libusb-1.0.0.dylib' % (VERSION_MAP[os_name], )
                with f_in.open(zip_path, 'rb') as a:
                    with f_out.open(lib_path, 'wb') as b:
                        b.write(a.read())
                    binaries.append(f_out.getospath(lib_path).decode('utf-8'))
        with f_out.open('binaries.json', 'wt') as f:
            json.dump(binaries, f, indent=2)
        with f_out.open('libusb.json', 'wt') as f:
            json.dump(d, f, indent=2)
    return binaries


if __name__ == '__main__':
    print(mac_binaries())
