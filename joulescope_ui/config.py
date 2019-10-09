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

from joulescope_ui.config_def import CONFIG
import json5
import json
import os
import pkgutil
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
CONFIG_PATH_LIST = [
    os.path.join(APP_PATH, 'config.json'),
    os.path.join(APP_PATH, 'config.json5')
]


if not os.path.isdir(APP_PATH):
    os.makedirs(APP_PATH)


def _substitute(entry, value):
    if entry.get('type') == 'path':
        attributes = entry.get('attributes', [])
        if value == '__SAVE_PATH__':
            value = SAVE_PATH_DEFAULT
            if 'exists' in attributes and not os.path.exists(value):
                os.makedirs(value)
        elif 'exists' in attributes and not os.path.exists(value):
            raise ValueError('path does not exist: %s' % (value, ))
    return value


def validate(config_def, cfg, path=None, default_on_error=None):
    """Validate that the configuration is valid.

    :param config_def: The configuration definition data structure.
        See config_def.py for the data structure format.
    :param cfg: The configuration to validate against the config_def.
    :param path: The path used recursively by this function.
        This value should not be provided by the initial caller.
    :param default_on_error: When true, presume the default value on
        validation errors.
    :return: True on validate success, False on failure.
    """
    path = '' if path is None else str(path)
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
                    y[key] = validate(entry['children'], v, default_on_error=default_on_error)
                else:
                    raise ValueError('%s should be map' % (p, ))
            else:
                y[key] = validate(entry['children'], {}, default_on_error=default_on_error)
        else:
            v = cfg.get(key, entry.get('default'))
            if v is not None:
                if t == 'str' and 'options' in entry:
                    values = {}
                    for x in entry['options']:
                        n = x['name']
                        for e in [n] + x.get('aliases', []):
                            if e in values:
                                raise ValueError('Invalid configuration: duplicate key %s' % (e, ))
                            values[e] = n
                    if v not in values:
                        if bool(default_on_error):
                            d = entry.get('default')
                            log.warning('%s: Value "%s" invalid, use default "%s"', p, v, d)
                            v = d
                        else:
                            raise ValueError('%s: Value "%s" not in %s' % (p, v, values))
                    v = values[v]
                y[key] = _substitute(entry, v)
        if key in k2:
            k2.remove(key)
    for k in k2:
        p = path + '.' + k
        log.info('Unexpected entry: %s', p)
    return y


def find_child_by_name(d, name):
    """Find a specification configuration definition child.

    :param d: The configuration definition list with dict elements that
        have a key 'name'.
    :param name: The name to match against the 'name' key in each list
        element.
    :return: The matching element or None.

    Fastest implementation, no.
    Simplest while maintaining guaranteed order, yes.
    """
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


def load_config_def(path: str=None):
    """Load a configuration definition.

    :param path: The full path to the configuration definition.
        None (default) uses the config_def.py included with this
        package.
    :return: The configuration definition.
        See config_def.py for the data structure format.
    """
    if path is None:
        d = CONFIG
    elif not os.path.isfile(path):
        raise ValueError('config_def does not exist: %s' % (path,))
    else:
        log.info('load_config_def %s', path)
        with open(path, 'r') as f:
            d = json5.load(f)
    # todo: validate the validator?
    d['children'] = _cfg_def_normalize(d['children'])
    return d


def load_config(config_def, path=None, default_on_error=None):
    """Load the configuration.

    :param config_def: The configuration definition used to validate the
        loaded configuration.
        See config_def.json5 for the data structure format.
    :param path: The full path to the configuration definition.
        None (default) uses the platform-dependent path.
    :param default_on_error: When true, presume the default value on
        validation errors.
    :return: The loaded configuration which consists of a two level dictionary
        that mirrors the configuration definition. (key -> key -> value).
    """
    if path is None:
        for p in CONFIG_PATH_LIST:
            if os.path.isfile(p):
                path = p
                break
    if not isinstance(path, str):
        cfg = json.load(path)
    elif not os.path.isfile(path):
        log.info('Configuration file not found: %s', path)
        cfg = {}
    else:
        log.info('Load configuration file: %s', path)
        with open(path, 'r') as f:
            if path.endswith('json5'):
                cfg = json5.load(f)
            else:
                cfg = json.load(f)
    y = validate(config_def, cfg, default_on_error=default_on_error)
    return y


def save_config(cfg, path=None):
    """Save the configuration.

    :param cfg: The configuration which consists of a two level dictionary
        that mirrors the configuration definition. (key -> key -> value).
    :param path: The full save path.
        None (default) uses the platform-dependent path.
    """
    if path is None:
        path = CONFIG_PATH_LIST[0]
    if not isinstance(path, str):
        json.dump(cfg, path, indent=2)
    else:
        with open(path, 'w') as f:
            json.dump(cfg, f, indent=2)
