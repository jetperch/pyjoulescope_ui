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
import logging


platform = sys.platform
APP = 'joulescope'
DIRS = ['app_path', 'config', 'log', 'firmware', 'themes', 'data', 'update']
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
                'update': os.path.join(app_path, 'update'),
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
                'update': os.path.join(app_path, 'update'),
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
                'update': os.path.join(app_path, 'update'),
            }
        }

    else:
        raise RuntimeError('unsupported platform')

    p['files'] = {
        'config': os.path.join(p['dirs']['config'], 'joulescope_config.json'),
    }
    return p


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


def initialize(paths):
    for path in paths['dirs'].values():
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)


def data_path(cmdp):
    """Get the data_path.

    :param cmdp: The :class:joulescope_ui.command_processor.CommandProcessor
        instance containing the preferences.
    :return: The data path, which is guaranteed to be valid.
    :raise ValueError: If no valid path can be found.

    Side-effect: will update 'General/data_path' parameters if the
    configured path is not available.
    """
    paths = {
        'Use fixed data_path': cmdp['General/data_path'],
        'Most recently saved': cmdp['General/_path_most_recently_saved'],
        'Most recently used': cmdp['General/_path_most_recently_used']
    }
    data_path_type = cmdp['General/data_path_type']
    config_path = paths[data_path_type]
    paths = [config_path,
             cmdp.preferences.definition_get('General/data_path')['default'],
             os.getcwd()]
    for path in paths:
        try:
            if not os.path.isdir(path):
                os.makedirs(path, exist_ok=True)
            if config_path != path:
                cmdp['General/data_path'] = path
            return path
        except Exception:
            logging.getLogger(__name__).info('Invalid path: %s', path)
    raise ValueError('No path found')


def data_path_used_set(cmdp, path):
    """Set the most recently used data path.

    :param cmdp: The :class:joulescope_ui.command_processor.CommandProcessor
        instance containing the preferences.
    :param path: The filename path.
    """
    cmdp['General/_path_most_recently_used'] = path


def data_path_saved_set(cmdp, path):
    """Set the most recently saved data path.

    :param cmdp: The :class:joulescope_ui.command_processor.CommandProcessor
        instance containing the preferences.
    :param path: The filename path.
    """
    cmdp['General/_path_most_recently_used'] = path
    cmdp['General/_path_most_recently_saved'] = path
