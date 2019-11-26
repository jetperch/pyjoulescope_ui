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
from joulescope_ui.ui_util import comboBoxConfig
from joulescope_ui.preferences import options_enum
from joulescope_ui import preferences_defaults
from PySide2 import QtCore, QtWidgets, QtGui
import collections.abc
import logging
import weakref


log = logging.getLogger(__name__)


class PreferencesDialog(QtWidgets.QDialog):

    def __init__(self, parent, cmdp):
        QtWidgets.QDialog.__init__(self, parent)
        self._active_group = None
        self._active_profile = cmdp.preferences.profile
        self._params = []
        self._cmdp = cmdp
        self.ui = Ui_PreferencesDialog()
        self.ui.setupUi(self)

        print(self._cmdp['Widgets/#enum'])

        self._definitions = self._cmdp.preferences.definitions
        if self._definitions['name'] != '/':
            raise ValueError('unexpected root')
        self._definitions_tree_map = {}

        self._tree_model = QtGui.QStandardItemModel(self)
        self._tree_model.setHorizontalHeaderLabels(['Name'])
        self.ui.treeView.setModel(self._tree_model)
        self.ui.treeView.setHeaderHidden(True)
        self.ui.treeView.selectionModel().currentChanged.connect(self._on_tree_item_changed)
        self._tree_populate(self._tree_model.invisibleRootItem(), self._definitions)

        select_mode_index = self._tree_model.index(0, 0)
        self.ui.treeView.setCurrentIndex(select_mode_index)
        self.ui.treeView.expandAll()
        self._on_tree_item_changed(select_mode_index, None)
        self.ui.profileComboBox.currentIndexChanged.connect(self._on_profile_combo_box_change)
        self._profile_combobox_update()

        self.ui.profileActivateButton.pressed.connect(self._on_profile_activate_button)
        self.ui.profileResetButton.pressed.connect(self._on_profile_reset_button)
        self.ui.profileNewButton.pressed.connect(self._on_profile_new_button)

        self.ui.okButton.pressed.connect(self.accept)
        self.ui.cancelButton.pressed.connect(self.reject)
        self.ui.resetButton.pressed.connect(self.preferences_reset)

        self._cmdp.subscribe('!preferences/profile/add', weakref.WeakMethod(self._on_profile_add))
        self._cmdp.subscribe('!preferences/profile/remove', weakref.WeakMethod(self._on_profile_remove))

    def _on_profile_combo_box_change(self, index):
        profile = self.ui.profileComboBox.currentText()
        self._profile_change(profile)

    def _on_profile_add(self, topic, data):
        log.info('_on_profile_add(%s)  %s', data, self._active_profile)
        self._profile_change(data)

    def _on_profile_remove(self, topic, data):
        log.info('_on_profile_remove(%s) : %s', data, self._active_profile)
        if data == self._active_profile:
            self._profile_change()

    def _profile_change(self, profile=None):
        if profile is None:
            profile = self._cmdp.preferences.profile
        if profile == self._active_profile:
            return
        if profile != self._active_profile:
            self._active_profile = profile
            self._profile_combobox_update()
            self._on_tree_item_changed(self.ui.treeView.currentIndex(), None)

    def _on_profile_activate_button(self):
        self._cmdp.invoke('!preferences/profile/set', self._active_profile)
        self.ui.profileActivateButton.setEnabled(False)

    def _on_profile_reset_button(self):
        if self._active_profile in preferences_defaults.PROFILES_RESET:
            preferences_defaults.restore(self._cmdp.preferences, self._active_profile)
        else:
            self._cmdp.invoke('!preferences/profile/remove', self._active_profile)

    def _on_profile_new_button(self):
        profile, success = QtWidgets.QInputDialog.getText(self, 'Enter profile name', 'Profile Name:')
        if not success:
            return
        if profile in self._cmdp.preferences.profiles:
            log.warning('Already exists - switch to it')
            self._cmdp.invoke('!preferences/profile/set', profile)
        else:
            self._cmdp.invoke('!preferences/profile/add', profile)

    def _profile_combobox_update(self):
        if self._active_profile not in self._cmdp.preferences.profiles:
            self._active_profile = self._cmdp.preferences.profile
        comboBoxConfig(self.ui.profileComboBox, self._cmdp.preferences.profiles, self._active_profile)
        reset_text = 'Reset' if self._active_profile in preferences_defaults.PROFILES_RESET else 'Erase'
        self.ui.profileResetButton.setText(reset_text)
        self.ui.profileActivateButton.setEnabled(self._active_profile != self._cmdp.preferences.profile)

    def _tree_populate(self, parent, d):
        if 'children' not in d:
            return

        for name, child in d['children'].items():
            definition_name = child['name']
            if '#' in name or name.startswith('_') or not child['name'].endswith('/'):
                continue
            child_children = [x for x in child.get('children', {}).keys() if '#' not in x and not x.startswith('_')]
            if not len(child_children):
                continue
            child_item = QtGui.QStandardItem(name)

            # WARNING: setData with dict causes key reordering.  Store str and lookup.
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
    def _on_tree_item_changed(self, model_index, model_index_old):
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
        options = options_enum(entry.get('options', None))
        if options is not None:
            p = guiparams.Enum(name, value, options, tooltip=tooltip)
        else:
            p = guiparams.String(name, value, tooltip=tooltip)
        return p

    def _populate_int(self, entry, name, value, tooltip):
        options = entry.get('options', None)
        if options is None:
            return None  # todo
        if callable(options):
            options = options_enum(options)
        if isinstance(options, collections.abc.Sequence):
            return guiparams.Enum(name, value, options, tooltip=tooltip)
        else:
            # todo range
            return None

    def _populate_entry(self, name, entry):
        value = self._cmdp.preferences.get(entry['name'], profile=self._active_profile)
        p = None
        tooltip = ''
        dtype = entry.get('dtype', 'str')
        if 'brief' in entry and entry['brief'] is not None:
            tooltip = '<span><p>%s</p>' % entry['brief']
            if 'detail' in entry and entry['detail'] is not None:
                tooltip += '<p>%s</p>' % entry['detail']
            tooltip += '</span>'
        if dtype == 'str':
            p = self._populate_str(entry, name, value, tooltip)
        elif dtype == 'int':
            p = self._populate_int(entry, name, value, tooltip)
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
        elif dtype == 'color':
            p = guiparams.Color(name, value, tooltip=tooltip)
        elif dtype == 'font':
            p = guiparams.Font(name, value, tooltip=tooltip)
        else:
            log.info('%s: unsupported dtype %s', entry['name'], dtype)
        if p is not None:
            p.populate(self.ui.targetWidget)
            self._params.append(p)
            p.callback = lambda x: self._cmdp.invoke('!preferences/preference/set',
                                                     (entry['name'], x.value, self._active_profile))

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
