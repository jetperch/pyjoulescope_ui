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

"""Manage Joulescope application configurations"""

import json5
import os
import collections
import logging

log = logging.getLogger(__name__)


try:
    from win32com.shell import shell, shellcon
    USER_PATH = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
    APPDATA_PATH = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
    APP_PATH = os.path.join(APPDATA_PATH, 'joulescope')
except:
    USER_PATH = os.path.expanduser('~')
    APP_PATH = os.path.join(USER_PATH, '.joulescope')

SAVE_PATH_DEFAULT = os.path.join(USER_PATH, 'joulescope')
CONFIG_PATH = os.path.join(APP_PATH, 'config.json5')


if not os.path.isdir(APP_PATH):
    os.makedirs(APP_PATH)


def substitute(entry, value):
    if entry.get('type') == 'path':
        attributes = entry.get('attributes', [])
        if value == '__SAVE_PATH__':
            value = SAVE_PATH_DEFAULT
            if 'exists' in attributes and not os.path.exists(value):
                os.makedirs(value)
        elif 'exists' in attributes and not os.path.exists(value):
            raise ValueError('path does not exist: %s' % (value, ))
    return value


def validate(config_def, cfg, path=''):
    if 'info' in config_def:  # handle top level
        config_def = config_def['children']
    y = {}
    k2 = list(cfg.keys())
    for entry in config_def:  # list of entry dicts
        t = entry.get('type', 'str')
        key = entry['name']
        p = path + '.' + key
        if t == 'map':
            if key in cfg:
                v = cfg[key]
                if isinstance(v, collections.abc.Mapping):
                    y[key] = validate(entry['children'], v)
                else:
                    raise ValueError('%s should be map' % (p, ))
            else:
                y[key] = validate(entry['children'], {})
        else:
            v = cfg.get(key, entry.get('default'))
            if v is not None:
                if t == 'str' and 'options' in entry:
                    values = [x['name'] for x in entry['options']]
                    if v not in values:
                        raise ValueError('%s: Value "%s" not in %s' % (p, v, values))
                y[key] = substitute(entry, v)
        if key in k2:
            k2.remove(key)
    for k in k2:
        p = path + '.' + k
        log.warning('Unexpected entry: %s', p)
    return y


def find_child_by_name(d, name):
    for entry in d['children']:
        if entry['name'] == name:
            return entry
    return None


def _cfg_def_normalize(d):
    child_map = {}
    for entry in d:
        if 'name' not in entry:
            raise ValueError('entry missing name')
        name = entry['name']
        if name in child_map:
            raise ValueError('duplicate name')
            child_map[name] = entry
        t = entry.get('type', 'str')
        entry['type'] = t  # ensure all entries have type
        if t == 'str' and 'options' in entry:
            values = []
            for v in entry['options']:
                if isinstance(v, collections.abc.Mapping):
                    values.append(v)
                else:
                    x = {
                        'name': v,
                        'brief': '',
                    }
                    values.append(x)
            entry['options'] = values
        elif t == 'map':
            entry['children'] = _cfg_def_normalize(entry['children'])
    return d


def load_config_def(path: str):
    if not os.path.isfile(path):
        raise ValueError('config_def does not exist: %s' % (path, ))
    log.info('load_config_def %s', path)
    with open(path, 'r') as f:
        d = json5.load(f)
    # todo: validate the validator?
    d['children'] = _cfg_def_normalize(d['children'])
    return d


def load_config(config_def, path=None):
    if path is None:
        path = CONFIG_PATH
    if not isinstance(path, str):
        cfg = json5.load(path)
    elif not os.path.isfile(path):
        log.info('Configuration file not found: %s', path)
        cfg = {}
    else:
        log.info('Load configuration file: %s', path)
        with open(path, 'r') as f:
            cfg = json5.load(f)
    y = validate(config_def, cfg)
    return y


def save_config(cfg, path=None):
    if path is None:
        path = CONFIG_PATH
    if not isinstance(path, str):
        json5.dump(cfg, path, indent=2)
    else:
        with open(path, 'w') as f:
            json5.dump(cfg, f, indent=2)
