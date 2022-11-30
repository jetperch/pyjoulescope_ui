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
import shutil
import sys
import logging


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
