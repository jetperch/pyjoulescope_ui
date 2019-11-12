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

# https://doc.qt.io/qt-5/qtreeview.html
# https://doc.qt.io/qt-5/qstandarditemmodel.html
# https://doc.qt.io/qt-5/qmodelindex.html
# https://pythonspot.com/pyqt5-treeview/
# https://stackoverflow.com/questions/47102920/pyqt5-how-to-generate-a-qtreeview-from-a-list-of-dictionary-items
# https://stackoverflow.com/questions/27898718/multi-level-qtreeview
# https://stackoverflow.com/questions/25943153/how-to-access-data-stored-in-qmodelindex

from joulescope_ui.preferences_dialog import Ui_PreferencesDialog
from joulescope_ui import guiparams
from PySide2 import QtCore, QtWidgets, QtGui
import logging


log = logging.getLogger(__name__)


class PreferencesDialog(QtWidgets.QDialog):

    def __init__(self, cmdp):
        QtWidgets.QDialog.__init__(self)
        self._active_group = None
        self._params = []
        self._cmdp = cmdp
        self.ui = Ui_PreferencesDialog()
        self.ui.setupUi(self)

        self._definitions = self._cmdp.preferences.definitions
        if self._definitions['name'] != '/':
            raise ValueError('unexpected root')
        self._definitions_tree_map = {}

        self._tree_model = QtGui.QStandardItemModel(self)
        self._tree_model.setHorizontalHeaderLabels(['Name'])
        self.ui.treeView.setModel(self._tree_model)
        self.ui.treeView.setHeaderHidden(True)
        self.ui.treeView.selectionModel().currentChanged.connect(self._on_current_changed)
        self._tree_populate(self._tree_model.invisibleRootItem(), self._definitions)

        select_mode_index = self._tree_model.index(0, 0)
        self.ui.treeView.setCurrentIndex(select_mode_index)
        self._on_current_changed(select_mode_index, None)

        self.ui.okButton.pressed.connect(self.accept)
        self.ui.cancelButton.pressed.connect(self.cancel)
        self.ui.resetButton.pressed.connect(self.preferences_reset)

    def _tree_populate(self, parent, d):
        if 'children' not in d:
            return
        for name, child in d['children'].items():
            definition_name = child['name']
            if '#' in name or name.startswith('_') or not child['name'].endswith('/'):
                continue
            child_item = QtGui.QStandardItem(name)

            # WARNING: setData with dict causes key reordering.  Store str and lookup.
            print(definition_name)
            self._definitions_tree_map[definition_name] = child
            child_item.setData(definition_name, QtCore.Qt.UserRole + 1)

            parent.appendRow(child_item)
            self._tree_populate(child_item, child)

    def _clear(self):
        if self._active_group is not None:
            for param in self._params:
                param.unpopulate(self.ui.targetWidget)
            self._params = []
        self._active_group = None

    @QtCore.Slot(object, object)
    def _on_current_changed(self, model_index, model_index_old):
        self._clear()
        definition_name = self._tree_model.data(model_index, QtCore.Qt.UserRole + 1)
        data = self._definitions_tree_map[definition_name]
        self._populate_selected(data)

    def _populate_selected(self, data):
        if 'children' not in data:
            return
        self._active_group = data['name']
        for name, child in data['children'].items():
            if 'children' in child:
                continue
            if '#' in name or name.startswith('_') or child['name'].endswith('/'):
                continue
            self._populate_entry(name, child)

    def _populate_str(self, entry, name, value, tooltip):
        options = entry.get('options', None)
        if options is not None:
            options = [x['name'] for x in options['__def__'].values()]
            p = guiparams.Enum(name, value, options, tooltip=tooltip)
        else:
            p = guiparams.String(name, value, tooltip=tooltip)
        return p

    def _populate_entry(self, name, entry):
        value = self._cmdp[entry['name']]
        p = None
        tooltip = ''
        dtype = entry.get('dtype', 'str')
        if 'brief' in entry:
            tooltip = '<span><p>%s</p>' % entry['brief']
            if 'detail' in entry:
                tooltip += '<p>%s</p>' % entry['detail']
            tooltip += '</span>'
        if dtype == 'str':
            p = self._populate_str(entry, name, value, tooltip)
        elif dtype == 'bool':
            if isinstance(value, str):
                value = value.lower()
            value = value in [True, 'true', 'on']
            p = guiparams.Bool(name, value, tooltip=tooltip)
        elif dtype == 'path':
            attributes = entry.get('attributes', [])
            if 'dir' in attributes:
                p = guiparams.Directory(name, value, tooltip=tooltip)
            elif 'exists' in attributes:
                p = guiparams.FileOpen(name, value, tooltip=tooltip)
            else:
                p = guiparams.FileSave(name, value, tooltip=tooltip)
        else:
            log.info('%s: unsupported dtype %s', entry['name'], dtype)
        if p is not None:
            p.populate(self.ui.targetWidget)
            self._params.append(p)
            p.callback = lambda x: self._cmdp.publish(entry['name'], x.value)

    def on_selection_change(self, selection):
        log.info('on_selection_change(%r)', selection)
        model_index_list = selection.indexes()
        if len(model_index_list) != 1:
            # force the first item
            self.ui.groupListView.setCurrentIndex(self._model.item(0).index())
            return
        self._clear()
        name = model_index_list[0].data()
        self._populate(name)

    def cancel(self):
        QtWidgets.QDialog.reject(self)

    def preferences_reset(self):
        active_group = self._active_group
        self._clear()
        self._populate(active_group)

    def exec_(self):
        self._cmdp.invoke('!command_group/start')
        rv = QtWidgets.QDialog.exec_(self)
        self._cmdp.invoke('!command_group/end')
        if rv == 0:
            self._cmdp.invoke('!undo')
