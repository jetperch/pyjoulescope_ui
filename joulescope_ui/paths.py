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

# https://doc.qt.io/qt-5/qsettings.html#platform-specific-notes


import os
import shutil
import sys
import json


platform = sys.platform
APP = 'joulescope'
DIRS = ['app_path', 'config', 'log', 'firmware', 'themes', 'data']
FILES = ['config']


def paths_v2(app=None):
    """Paths for the most recent software version.

    :param app: The optional application name.  None is :data:`APP`.
    :return: The dict data structure containing 'dirs' key contains
        keys mapping :data:`DIRS` to their paths.  The 'files' key
        contains keys mapping :data:`FILES` to their paths.
    """
    app = APP if app is None else str(app)
    if 'win32' in sys.platform:
        from win32com.shell import shell, shellcon
        user_path = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
        appdata_path = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
        app_path = os.path.join(appdata_path, app)
        p = {
            'dirs': {
                'app_path': app_path,
                'config': os.path.join(app_path, 'config'),
                'log': os.path.join(app_path, 'log'),
                'firmware': os.path.join(app_path, 'firmware'),
                'themes': os.path.join(app_path, 'themes'),
                'data': os.path.join(user_path, app),
            }
        }

    elif 'darwin' in sys.platform:
        user_path = os.path.expanduser('~')
        app_path = os.path.join(user_path, 'Library', 'Application Support', app)
        p = {
            'dirs': {
                'app_path': app_path,
                'config': os.path.join(app_path, 'config'),
                'log': os.path.join(app_path, 'log'),
                'firmware': os.path.join(app_path, 'firmware'),
                'themes': os.path.join(app_path, 'themes'),
                'data': os.path.join(user_path, 'Documents', app),
            }
        }

    elif 'linux' in sys.platform:
        user_path = os.path.expanduser('~')
        app_path = os.path.join(user_path, '.' + app)
        p = {
            'dirs': {
                'app_path': app_path,
                'config': os.path.join(app_path, 'config'),
                'log': os.path.join(app_path, 'log'),
                'firmware': os.path.join(app_path, 'firmware'),
                'themes': os.path.join(app_path, 'themes'),
                'data': os.path.join(user_path, 'Documents', app),
            }
        }

    else:
        raise RuntimeError('unsupported platform')

    p['files'] = {
        'config': os.path.join(p['dirs']['config'], 'joulescope_config.json'),
    }
    return p


def paths_v1(app=None):
    """Paths for Joulescope software for 0.6.10 and earlier.

    :param app: The optional application name.  None is :data:`APP`.
    :return: The dict of name to path.  See :meth:`paths` for details.
    """
    app = APP if app is None else str(app)
    try:
        from win32com.shell import shell, shellcon
        user_path = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
        appdata_path = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
        app_path = os.path.join(appdata_path, app)
    except:
        user_path = os.path.expanduser('~')
        app_path = os.path.join(user_path, '.' + app)

    return {
        'dirs': {
            'app_path': app_path,
            'config': app_path,
            'log': os.path.join(app_path, 'log'),
            'firmware': os.path.join(app_path, 'firmware'),
            'themes': os.path.join(app_path, 'themes'),
            'data': os.path.join(user_path, app),
        },
        'files': {
            'config': os.path.join(app_path, 'config.json'),
        }
    }


paths_current = paths_v2
"""Paths for the most current software version"""


def clear(app=None, delete_data=False):
    """Clear all application data.

    :param app: The optional application name.  None is :data:`APP`.
    :param delete_data: True also delete associated data, which may delete
        data that the user has created!  Defaults to False.
    """
    for key, path in paths_current(app)['dirs'].items():
        if os.path.isdir(path):
            if key in ['data'] and not bool(delete_data):
                continue
            shutil.rmtree(path)


def migrate_1_to_2(app=None):
    paths_old = paths_v1(app)
    paths_new = paths_v2(app)

    cfg = None
    cfg_file = paths_old['files']['config']
    if os.path.isfile(cfg_file):
        with open(cfg_file, 'r') as f:
            cfg_old = json.load(f)
        cfg = {
            'type': 'joulescope_config',
            'version': 2,
            'profiles': {
                'all': cfg_old
            }
        }

    for name, path in paths_new['dirs'].items():
        path_old = paths_old['dirs'][name]
        if name in ['app_data', 'config']:
            continue
        if path_old != path and os.path.isdir(path_old) and not os.path.isdir(path):
            shutil.move(path_old, path)
    initialize(paths_new)
    if cfg is not None:
        with open(paths_new['files']['config'], 'w') as f:
            json.dump(cfg, f)


def initialize(paths):
    for path in paths['dirs'].values():
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
