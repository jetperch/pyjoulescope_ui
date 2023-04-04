# Copyright 2018-2022 Jetperch LLC
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


import pkgutil
from PySide6 import QtCore, QtGui
import logging


_log = logging.getLogger(__name__)


def load_resources():
    _log.info('load_resources start')
    resources = []
    resource_names = []
    resource_list = [
        ('joulescope_ui', 'resources.rcc'),
        ('joulescope_ui', 'fonts.rcc')]
    for r in resource_list:
        _log.debug('load_resources %s', r)
        b = pkgutil.get_data(*r)
        assert(QtCore.QResource.registerResourceData(b))
        resources.append(b)
        resource_names.append('/'.join(r))
    resource_names = [f'    {r}' for r in resource_names]
    _log.info('load_resources done\n%s', '\n'.join(resource_names))
    return resources


def load_fonts():
    _log.info('load_fonts start')
    font_list = []
    iterator = QtCore.QDirIterator(':/fonts', flags=QtCore.QDirIterator.Subdirectories)
    while iterator.hasNext():
        resource_path = iterator.next()
        if resource_path.endswith('.ttf'):
            # _log.debug('load_fonts %s', resource_path)
            rv = QtGui.QFontDatabase.addApplicationFont(resource_path)
            if rv == -1:
                _log.warning(f'Could not load font {resource_path}')
            else:
                font_list.append(f'    {resource_path} => {rv}')
    _log.info('load_fonts done\n%s', '\n'.join(font_list))
    return font_list
