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
import logging


log = logging.getLogger(__name__)
DTYPES = ['str', 'int', 'float', 'bool', 'bytes', 'dict', 'container']


def validate(value, dtype, options=None):
    if dtype == 'str':
        if not isinstance(value, str):
            raise ValueError(f'expected str {value}')
        if options is not None and value not in options:
            raise ValueError(f'Unsupported option value {value}')
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
    else:
        raise ValueError(f'unsuppored dtype {dtype}')
    return value


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


class Preferences(QtCore.QObject):
    """Store and manage application preferences.

    :param parent: The Qt parent object.
    :param app: The application name, which is used to determine the storage
        paths.

    This class duplicates some functionality from
    QSettings https://doc.qt.io/qt-5/qsettings.html.  However, this class adds
    profile and listener support.
    """

    sigProfileChanging = QtCore.Signal(str)  # profile name
    sigProfileChanged = QtCore.Signal(str)   # profile name
    sigPreferenceChanged = QtCore.Signal(str, object)  # preference name, value

    def __init__(self, parent=None, app=None):
        super(Preferences, self).__init__(parent)
        self._app = app
        self._path = paths.paths_current(self._app)['files']['config']
        self._defines = {}
        self._profiles = {'all': {}}
        self._profile_active = 'all'
        self._listeners = {}
        self.define(name='/', dtype='container')

    def flatten(self):
        values = self._profiles['all'].copy()
        if self._profile_active != 'all':
            for key, value in self._profiles[self._profile_active].items():
                values[key] = value
        return values

    def load(self):
        with open(self._path, 'r') as f:
            p = json.load(f, object_hook=json_decode_custom)
        if p['type'] != 'joulescope_config':
            raise ValueError('Unsupported config')
        if p['version'] != 2:
            raise ValueError('config migration not supported')
        flat_old = self.flatten()
        self._profiles = p['profiles']
        if self._profile_active not in self._profiles:
            log.warning('load does not contain active profile %s', self._profile_active)
            self._bulk_changer(profile_name='all', flat_old=flat_old)
        else:
            self._bulk_changer(flat_old=flat_old)
        return self

    def save(self):
        p = {
            'type': 'joulescope_config',
            'version': 2,
            'profiles': self._profiles,
        }
        tmp_file = self._path + '.tmp'
        with open(tmp_file, 'w') as f:
            json.dump(p, f, cls=PreferencesJsonEncoder)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self._path)
        return self

    def define(self, name, brief=None, detail=None, dtype=None, options=None, default=None):
        # todo support int ranges: min, max, step
        if dtype is None:
            if name.endswith('/'):
                dtype = 'container'
            else:
                dtype = 'str'
        if dtype not in DTYPES:
            raise ValueError(f'invalid dtype {dtype} for {name}')
        if dtype == 'str' and options is not None:
            values = {}
            if isinstance(options, collections.abc.Mapping):
                for key, value in options:
                    value['name'] = key
            else:
                for v in options:
                    values[v] = {'name': v}
            options = values
        if dtype != 'container' and name not in self._profiles['all']:
            self._profiles['all'][name] = default
        self._defines[name] = {
            'name': name,
            'brief': brief,
            'detail': detail,
            'dtype': dtype,
            'options': options,
            'default': default,
        }

    def definition_get(self, name):
        return self._defines[name]

    @property
    def definitions(self):
        """Get the definitions hierarchical data structure.

        :return: A complex data structure of dicts.  Leafs are normal defines.
            Nodes only have 'nam'e, 'brief', 'detail' and 'children.

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

    def listener_add(self, name, on_change_fn):
        """Add a new listener on a preference name.

        :param name: The preference name.
        :param on_change_fn: The callable(name, value) that is called with the
            updated value.
        """
        listeners = self._listeners.get(name, [])
        listeners.append(on_change_fn)
        self._listeners[name] = listeners

    def listener_remove(self, name, on_change_fn):
        listeners = self._listeners.get(name, [])
        try:
            listeners.remove(on_change_fn)
        except ValueError:
            log.info('listener could not be removed (not found) for %s', name)
            return False
        return True

    def get(self, name, **kwargs):
        profile = kwargs.get('profile', self._profile_active)
        try:
            return self._profiles[profile][name]
        except KeyError:
            if profile != 'all':
                try:
                    return self._profiles['all'][name]
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
        self._profiles[profile][name] = value
        if profile == self._profile_active or (profile == 'all' and name not in self._profiles[self._profile_active]):
            self._listener_update(name, value)

    def __len__(self):
        return len(self._profiles['all'])

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

    def validate(self, name, value):
        d = self._defines.get(name)
        if d is None:
            return value
        return validate(value, d.get('dtype', 'str'), d.get('options'))

    def is_valid(self, name, value):
        try:
            return self.validate(name, value)
        except:
            return False

    def is_in_profile(self, name, profile=None):
        profile = self._profile_active if profile is None else str(profile)
        return name in self._profiles.get(profile, {})

    def _listener_update(self, name, value):
        self._listeners.get(name, [])
        for listener in self._listeners.get(name, []):
            listener(name, value)
        listener_parts = name.split('/')
        while len(listener_parts):
            listener_parts[-1] = ''
            n = '/'.join(listener_parts)
            for listener in self._listeners.get(n, []):
                listener(name, value)
            listener_parts.pop()

    def clear(self, name, profile=None):
        profile = self._profile_active if profile is None else str(profile)
        del self._profiles[profile][name]

    def profile_add(self, name, activate=False):
        if name in self._profiles:
            raise KeyError(f'profile {name} already exists')
        self._profiles[name] = {}
        if bool(activate):
            self.profile = name

    def profile_remove(self, name):
        if name == 'all':
            raise KeyError('cannot remove profile all')
        if name == self._profile_active:
            self.profile = 'all'
        del self._profiles[name]

    @property
    def profiles(self):
        return list(self._profiles.keys())

    @property
    def profile(self):
        return self._profile_active

    @profile.setter
    def profile(self, name):
        self._bulk_changer(profile_name=name)

    def _bulk_changer(self, profile_name=None, flat_old=None):
        if flat_old is None:
            flat_old = self.flatten()
        if profile_name is not None:
            if profile_name not in self._profiles:
                raise KeyError(f'invalid profile {profile_name}')
            self.sigProfileChanging.emit(profile_name)
            self._profile_active = profile_name
        flat_new = self.flatten()
        for key, value in flat_new.items():
            if key not in flat_old or flat_new[key] != flat_old[key]:
                self._listener_update(key, value)
        if profile_name is not None:
            self.sigProfileChanged.emit(profile_name)
        return self
