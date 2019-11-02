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

"""Display and update application preferences"""

from joulescope_ui.preferences_dialog import Ui_PreferencesDialog
from joulescope_ui import guiparams
from joulescope_ui.config import find_child_by_name, validate
from joulescope_ui.ui_util import confirmDiscard
from PySide2 import QtCore, QtWidgets, QtGui
import logging
import copy


log = logging.getLogger(__name__)


class PreferencesDialog(QtWidgets.QDialog):

    def __init__(self, cfg_def, cfg):
        QtWidgets.QDialog.__init__(self)
        self._active_group = None
        self._params = []
        self._cfg_def = cfg_def
        self.cfg_orig = cfg
        self._cfg = copy.deepcopy(cfg)
        self.ui = Ui_PreferencesDialog()
        self.ui.setupUi(self)
        self._model = QtGui.QStandardItemModel()
        for entry in self._cfg_def['children']:
            item = QtGui.QStandardItem(entry['name'])
            self._model.appendRow(item)
        self.ui.groupListView.setModel(self._model)
        self.ui.groupListView.selectionModel().selectionChanged.connect(self.on_selection_change)
        self.ui.groupListView.setCurrentIndex(self._model.item(0).index())
        self.ui.okButton.pressed.connect(self.accept)
        self.ui.cancelButton.pressed.connect(self.cancel)
        self.ui.resetButton.pressed.connect(self.cfg_reset)

    def update(self):
        if self._active_group is None:
            return
        for param in self._params:
            self._cfg[self._active_group][param.name] = param.value

    def _clear(self):
        if self._active_group is not None:
            for param in self._params:
                param.unpopulate(self.ui.targetWidget)
            self._params = []
        self._active_group = None

    def _populate(self, group_name: str):
        group = find_child_by_name(self._cfg_def, group_name)
        if group is None:
            return
        self._active_group = group_name

        for entry in group['children']:
            name = entry['name']
            value = self._cfg[self._active_group][name]
            p = None
            tooltip = ''
            if 'brief' in entry:
                tooltip = '<span><p>%s</p>' % entry['brief']
                if 'detail' in entry:
                    tooltip += '<p>%s</p>' % entry['detail']
                tooltip += '</span>'
            if entry['type'] == 'str' and 'options' in entry:
                options = [x['name'] for x in entry['options']]
                p = guiparams.Enum(name, value, options, tooltip=tooltip)
            elif entry['type'] == 'bool':
                if isinstance(value, str):
                    value = value.lower()
                value = value in [True, 'true', 'on']
                p = guiparams.Bool(name, value, tooltip=tooltip)
            elif entry['type'] == 'path':
                attributes = entry.get('attributes', [])
                if 'dir' in attributes:
                    p = guiparams.Directory(name, value, tooltip=tooltip)
                elif 'exists' in attributes:
                    p = guiparams.FileOpen(name, value, tooltip=tooltip)
                else:
                    p = guiparams.FileSave(name, value, tooltip=tooltip)
            if p is not None:
                p.populate(self.ui.targetWidget)
                self._params.append(p)

    def on_selection_change(self, selection):
        log.info('on_selection_change(%r)', selection)
        model_index_list = selection.indexes()
        if len(model_index_list) != 1:
            # force the first item
            self.ui.groupListView.setCurrentIndex(self._model.item(0).index())
            return

        self.update()
        self._clear()

        name = model_index_list[0].data()
        self._populate(name)

    def cancel(self):
        self.update()
        if self.cfg_orig == self._cfg:
            QtWidgets.QDialog.reject(self)
        elif confirmDiscard(self):
            QtWidgets.QDialog.reject(self)

    def cfg_reset(self):
        active_group = self._active_group
        self._clear()
        self._cfg = validate(self._cfg_def, {})
        self._populate(active_group)

    def exec_(self):
        if QtWidgets.QDialog.exec_(self) == 1:
            self.update()
            return self._cfg  # accepted!
        return None
