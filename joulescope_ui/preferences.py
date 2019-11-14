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

"""
Manage preferences for the entire Joulescope UI application.

https://doc.qt.io/qt-5/qsettings.html#platform-specific-notes
https://gist.github.com/dgovil/d83e7ddc8f3fb4a28832ccc6f9c7f07b
https://gist.github.com/bootchk/5330231
"""

from PySide2 import QtCore
from joulescope_ui import paths
import collections.abc
import base64
import os
import json
import copy
import logging


BASE_PROFILE = 'defaults'


log = logging.getLogger(__name__)
DTYPES_DEF = [
    ('str', str),
    ('int', int),
    ('float', float),
    ('bool', bool),
    ('bytes', bytes),
    ('dict', dict, collections.abc.Mapping),
    ('obj', 'object', object),  # WARNING CANNOT BE SERIALIZED!
    ('none', None),  # not stored, but used to signal events
    ('container', )]
DTYPES = [item for sublist in DTYPES_DEF for item in sublist]
DTYPES_MAP = {}
for t in DTYPES_DEF:
    for k in t:
        DTYPES_MAP[k] = t[0]


def to_bool(v):
    if isinstance(v, str):
        v = v.lower()
        return v not in ['false', '0', 'off', '']
    return bool(v)


def options_enum(options):
    """Enumerate all options at the present time.

    :param options: The options definition, which can be a callable.
    """
    if options is None:
        return options
    if callable(options):
        options = options()
    if isinstance(options, collections.abc.Mapping) and '__def__' in options:
        return list(options['__def__'].keys())
    elif isinstance(options, collections.abc.Mapping):
        return list(options.keys())
    elif isinstance(options, collections.abc.Sequence):
        return options
    else:
        raise ValueError(f'unsupported options format {options}')


def options_validate(options, value):
    if options is None:
        return value
    try:
        if callable(options):
            options = options()
        if isinstance(options, collections.abc.Mapping) and '__remap__' in options:
            return options['__remap__'][value]
        elif isinstance(options, collections.abc.Mapping):
            return options[value]
        elif isinstance(options, collections.abc.Sequence):
            if value not in options:
                raise ValueError(f'value {value} not in options {options}')
            return value
        else:
            raise ValueError(f'unsupported options format {options}')
    except KeyError:
        raise ValueError(f'Unsupported option value {value}')


def validate(value, dtype, options=None):
    if dtype == 'obj':
        pass  # no validation necessary
    elif dtype == 'str':
        if not isinstance(value, str):
            raise ValueError(f'expected str {value}')
        value = options_validate(options, value)
    elif dtype == 'int':
        return int(value)
    elif dtype == 'float':
        return float(value)
    elif dtype == 'bool':
        if isinstance(value, str) and value in ['off', '0', 'None', 'none']:
            return False
        return bool(value)
    elif dtype == 'bytes':
        return isinstance(value, bytes)
    elif dtype == 'dict':
        if not hasattr(value, 'keys'):
            raise ValueError(f'dtype dict but no keys')
        return value
    elif dtype == 'container':
        return value
    elif dtype == 'none':
        return value
    else:
        raise ValueError(f'unsupported dtype {dtype}')
    return value


def options_conform(options):
    if options is None:
        return None
    if callable(options):
        return options
    elif isinstance(options, collections.abc.Mapping):
        if '__remap__' in options:
            return options
        for key, value in options.items():
            value['name'] = key
    else:
        values = {}
        for v in options:
            values[v] = {'name': v}
        options = values
    remap = {}
    r = {
        '__def__': options,  # option definition
        '__remap__': remap,  #
    }
    for key, value in options.items():
        remap[key] = key
        for k in value.get('aliases', []):
            remap[k] = key
    return r


class PreferencesJsonEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, bytes):
            return {
                '__type__': 'bytes',
                'data': base64.b64encode(obj).decode('utf-8')
            }
        else:
            return obj


def json_decode_custom(obj):
    if '__type__' in obj:
        t = obj['__type__']
        if t == 'bytes':
            return base64.b64decode(obj['data'].encode('utf-8'))
    return obj


def _remove_unsaved_keys(d):
    for key in list(d.keys()):
        if '#' in key:
            del d[key]
            continue
        v = d[key]
        if isinstance(v, collections.abc.Mapping):
            _remove_unsaved_keys(v)


class Preferences(QtCore.QObject):
    """Store and manage application preferences.

    :param parent: The Qt parent object.
    :param app: The application name, which is used to determine the storage
        paths.

    This class duplicates some functionality from
    QSettings https://doc.qt.io/qt-5/qsettings.html.  However, this class adds
    profile and listener support.
    """
    sigProfileChanged = QtCore.Signal(str)   # profile name

    def __init__(self, parent=None, app=None):
        super(Preferences, self).__init__(parent)
        self._app = app
        self._path = paths.paths_current(self._app)['files']['config']
        self._defines = {}
        self._profiles = {BASE_PROFILE: {}}
        self._profile_active = BASE_PROFILE
        self.define(name='/', dtype='container')

    def flatten(self):
        values = self._profiles[BASE_PROFILE].copy()
        if self._profile_active != BASE_PROFILE:
            for key, value in self._profiles[self._profile_active].items():
                values[key] = value
        return values

    def load(self):
        if not os.path.isfile(self._path):
            log.info('preferences file does not exist: %s', self._path)
            return self
        with open(self._path, 'r') as f:
            p = json.load(f, object_hook=json_decode_custom)
        self.state_restore(p)
        return self

    def state_export(self):
        state = {
            'type': 'joulescope_config',
            'version': 2,
            'profile': self._profile_active,
            'profiles': copy.deepcopy(self._profiles),
        }
        _remove_unsaved_keys(state['profiles'])
        return state

    def state_restore(self, state):
        if state['type'] != 'joulescope_config':
            raise ValueError('Unsupported config')
        if state['version'] != 2:
            raise ValueError('config migration not supported')
        self._profiles = state['profiles']
        if state['profile'] not in self._profiles:
            log.warning('state_restore does not contain profile %s, use "all"', state['profile'])
            self.profile = BASE_PROFILE
        self.profile = state['profile']

    def save(self):
        p = self.state_export()
        tmp_file = self._path + '.tmp'
        with open(tmp_file, 'w') as f:
            json.dump(p, f, cls=PreferencesJsonEncoder)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self._path)
        return self

    def define(self, name, brief=None, detail=None, dtype=None, options=None, default=None,
               default_profile_only=None):
        # todo support int ranges: min, max, step
        if dtype is None:
            if name.endswith('/'):
                dtype = 'container'
            else:
                dtype = 'str'
        if dtype not in DTYPES_MAP:
            raise ValueError(f'invalid dtype {dtype} for {name}')
        dtype = DTYPES_MAP[dtype]
        if dtype == 'str' and options is not None:
            options = options_conform(options)
        if dtype != 'container' and name not in self._profiles[BASE_PROFILE]:
            self._profiles[BASE_PROFILE][name] = default
        if default is not None:
            default = validate(default, dtype, options=options)
        self._defines[name] = {
            'name': name,
            'brief': brief,
            'detail': detail,
            'dtype': dtype,
            'options': options,
            'default': default,
            'default_profile_only': bool(default_profile_only),
        }

    def definition_get(self, name):
        return self._defines[name]

    def definition_options(self, name):
        options = self._defines[name]['options']
        return options_enum(options)

    @property
    def definitions(self):
        """Get the definitions hierarchical data structure.

        :return: A complex data structure of dicts.  Leafs are normal defines.
            Nodes only have 'name', 'brief', 'detail' and 'children.

        This method can be used to automatically populate a UI preferences dialog.
        """
        d = {}
        for value in self._defines.values():
            prefix = []
            name_parts = value['name'].split('/')
            k = d
            while True:
                if name_parts[0] == '':
                    k['name'] = value['name']
                    k['brief'] = value['brief']
                    k['detail'] = value['detail']
                    break
                elif len(name_parts) == 1:
                    if 'children' not in k:
                        k['children'] = {}
                    k['children'][name_parts[0]] = value
                    break
                else:
                    if 'children' not in k:
                        k['children'] = {}
                    if name_parts[0] not in k['children']:
                        k['children'][name_parts[0]] = {
                            'name': '/'.join(prefix) + '/'
                        }
                    k = k['children'][name_parts[0]]
                prefix.append(name_parts.pop(0))
        return d

    def get(self, name, **kwargs):
        profile = kwargs.get('profile', self._profile_active)
        try:
            return self._profiles[profile][name]
        except KeyError:
            if profile != BASE_PROFILE:
                try:
                    return self._profiles[BASE_PROFILE][name]
                except KeyError:
                    pass
            if 'default' in kwargs:
                return kwargs['default']
            raise

    def set(self, name, value, profile=None):
        profile = self._profile_active if profile is None else str(profile)
        if profile not in self._profiles:
            raise KeyError(f'invalid profile {profile}')
        value = self.validate(name, value)
        if name in self._defines and self._defines[name]['default_profile_only']:
            self._profiles[BASE_PROFILE][name] = value
        else:
            self._profiles[profile][name] = value

    def purge(self, name):
        """Completely remove a preference from the system.

        :param name: The name of the preference.
        :return: A dict suitable for :meth:`restore` to completely
            undo this operation.
        """
        state = {'name': name, 'profiles': {}, 'defines': {}}
        if name[-1] == '/':
            # traverse EVERYTHING: could improve efficiency if needed
            for pname in list(self._profiles.keys()):
                profile = self._profiles[pname]
                state['profiles'][pname] = {}
                for key in list(profile.keys()):
                    if key.startswith(name):
                        state['profiles'][pname][key] = profile.pop(key)
            for dname in list(self._defines):
                if dname.startswith(name):
                    state['defines'][dname] = self._defines.pop(dname)
        else:
            for pname, profile in self._profiles.items():
                if name in profile:
                    state['profiles'][pname] = {name: profile.pop(name)}
            if name in self._defines:
                state['defines'][name] = self._defines.pop(name)
        return state

    def restore(self, value):
        """Restore a preference removed by :meth:`purge`.

        :param value: The value returned by :meth:`purge`.
        """
        if 'defines' in value:
            for key, d in value['defines'].items():
                self._defines[key] = d
        for pname, profile in value['profiles'].items():
            for key, v in profile.items():
                self._profiles[pname][key] = v

    def __len__(self):
        return len(self._profiles[BASE_PROFILE])

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __delitem__(self, key):
        self.clear(key)

    def __iter__(self):
        yield from self.flatten().items()

    def __contains__(self, key):
        try:
            self.get(key)
            return True
        except KeyError:
            return False

    def items(self, prefix=None):
        if prefix is None:
            return self.flatten().items()
        return [(key, self[key]) for key in self._profiles[BASE_PROFILE].keys() if key.startswith(prefix)]

    def validate(self, name, value):
        d = self._defines.get(name)
        if d is None:
            return value
        try:
            return validate(value, d.get('dtype', 'str'), d.get('options'))
        except ValueError as ex:
            raise ValueError(f'{name}: {str(ex)}') from ex

    def is_valid(self, name, value):
        try:
            return self.validate(name, value)
        except:
            return False

    def is_in_profile(self, name, profile=None):
        profile = self._profile_active if profile is None else str(profile)
        return name in self._profiles.get(profile, {})

    def match(self, pattern, profile=None):
        """Find all preferences matching pattern.

        :param pattern: The pattern to match.
        :param profile: The profile name.  None (default) matches only on the
           currently active profile.
        :return: The list of matching preference names.
        """
        profile = self._profile_active if profile is None else str(profile)
        if pattern[-1] == '/':
            return [k for k in self._profiles[profile].keys() if k.startswith(pattern)]
        elif pattern in self._profiles[profile]:
            return [pattern]
        else:
            return []

    def clear(self, name, profile=None):
        profile = self._profile_active if profile is None else str(profile)
        value = self._profiles[profile].pop(name)
        if profile == BASE_PROFILE and name in self._defines and self._defines[name]['default'] is not None:
            self._profiles[profile][name] = self._defines[name]['default']
        return value

    def profile_add(self, name, activate=False):
        if name in self._profiles:
            raise KeyError(f'profile {name} already exists')
        self._profiles[name] = {}
        if bool(activate):
            self.profile = name

    def profile_remove(self, name):
        if name == BASE_PROFILE:
            raise KeyError('cannot remove profile all')
        if name == self._profile_active:
            self.profile = BASE_PROFILE
        del self._profiles[name]

    @property
    def profiles(self):
        return list(self._profiles.keys())

    @property
    def profile(self):
        return self._profile_active

    @profile.setter
    def profile(self, name):
        if name not in self._profiles:
            raise KeyError(f'invalid profile {name}')
        self._profile_active = name
        self.sigProfileChanged.emit(name)
