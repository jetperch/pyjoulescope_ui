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
from joulescope_ui.ui_util import comboBoxConfig, clear_layout
from joulescope_ui.preferences import options_enum
from joulescope_ui import preferences_defaults
from joulescope_ui.help_ui import display_help
from joulescope_ui.themes.color_picker import ColorItem
from joulescope_ui.themes.manager import theme_update, theme_loader, theme_index_loader
from PySide2 import QtCore, QtWidgets, QtGui
import copy
import collections.abc
import logging


log = logging.getLogger(__name__)


class AppearanceColors(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, index, profile):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._index = copy.deepcopy(index)
        self._profile = profile
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)
        self._layout = QtWidgets.QGridLayout(self)
        self._widgets = []
        row = 0
        for name, color in index.get('colors', {}).items():
            w = ColorItem(self, name, color)
            w.text_label = QtWidgets.QLabel(name, parent)
            self._widgets.append(w)
            self._layout.addWidget(w.text_label, row, 0, 1, 1)
            self._layout.addWidget(w.value_edit, row, 1, 1, 1)
            self._layout.addWidget(w.color_label, row, 2, 1, 1)
            w.color_changed.connect(self._on_change)
            row += 1

    def clear(self):
        clear_layout(self._layout)
        self._widgets.clear()

    def _on_timer(self):
        index = theme_update(self._index)
        topic = 'Appearance/__index__'
        self._cmdp.invoke('!preferences/preference/set', (topic, index, self._profile))

    def _on_change(self, color_name, color_value):
        self._index['colors'][color_name] = color_value
        self._timer.stop()
        self._timer.start(100)  # milliseconds


class PreferencesDialog(QtWidgets.QDialog):

    def __init__(self, parent, cmdp):
        QtWidgets.QDialog.__init__(self, parent)
        self.setObjectName('PreferencesDialog')
        self._active_group = None
        self._active_profile = cmdp.preferences.profile
        self._params = []
        self._cmdp = cmdp

        self.ui = Ui_PreferencesDialog()
        self.ui.setupUi(self)
        self._target_widget = None

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
        self.ui.helpButton.pressed.connect(self._help)

        self.ui.okButton.pressed.connect(self.accept)
        self.ui.cancelButton.pressed.connect(self.reject)
        self.ui.resetButton.pressed.connect(self.preferences_reset)

        self._cmdp.subscribe('!preferences/profile/add', self._on_profile_add)
        self._cmdp.subscribe('!preferences/profile/remove', self._on_profile_remove)
        self._cmdp.subscribe('Appearance/Theme', self._on_theme)

        self._refresh_topic = f'!preferences/_ui/refresh_{id(self)}'
        self._cmdp.register(self._refresh_topic, self._refresh)

    def _on_theme(self, topic, value):
        profile = self._active_profile
        theme_index = theme_loader(value, profile)
        topic = 'Appearance/__index__'
        self._cmdp.invoke('!preferences/preference/set', (topic, theme_index, profile))

    def _help(self):
        display_help(self, self._cmdp, 'preferences')

    def _refresh(self, topic, value):
        self._redraw_right_pane()

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
        self._redraw_right_pane()

    def _on_profile_activate_button(self):
        self._cmdp.invoke('!preferences/profile/set', self._active_profile)
        self.ui.profileActivateButton.setEnabled(False)

    def _on_profile_reset_button(self):
        self._profile_reset()

    def _profile_reset(self, prefix=''):
        log.info('profile_reset start %s : %s', self._active_profile, prefix)
        existing = self._cmdp.preferences.state_export()['profiles'][self._active_profile]
        if self._active_profile in preferences_defaults.PROFILES_RESET:
            default_profile = preferences_defaults.Preferences(app='joulescope_config')
            preferences_defaults.defaults(default_profile)
            defaults = default_profile.state_export()['profiles'][self._active_profile]
        else:
            defaults = {}
        for key, new_value in defaults.items():
            if key.startswith(prefix):
                existing.pop(key, None)  # remove if possible
                self._cmdp.invoke('!preferences/preference/set', (key, new_value, self._active_profile))
        for key, old_value in existing.items():
            if key in ['Appearance/__index__']:
                pass
            elif '#' in key or key[-1] == '/' or '/_' in key:
                continue
            if key.startswith(prefix):
                self._cmdp.invoke('!preferences/preference/clear', (key, self._active_profile))
        # special case state preferences
        if prefix == '' or prefix == 'General':
            self._cmdp.invoke('!preferences/preference/set', ('_window', None, self._active_profile))
        self._cmdp.invoke(self._refresh_topic, None)
        log.info('profile_reset done %s : %s', self._active_profile, prefix)

    def _on_profile_new_button(self):
        profile, success = QtWidgets.QInputDialog.getText(self, 'Enter profile name', 'Profile Name:')
        if not success:
            return
        if profile in self._cmdp.preferences.profiles:
            log.warning('Already exists - switch to it')
            self._cmdp.invoke('!preferences/profile/set', profile)
        else:
            self._cmdp.invoke('!preferences/profile/add', profile)
        self._redraw_right_pane()

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
        w, self._target_widget = self._target_widget, None
        params, self._params = self._params, []
        active_group, self._active_group = self._active_group, None
        if w is None:
            return
        elif hasattr(w, 'clear'):
            w.clear()
        elif active_group is not None:
            for param in params:
                param.unpopulate(w)
        self.ui.targetLayout.removeWidget(w)
        w.deleteLater()

    @QtCore.Slot(object, object)
    def _on_tree_item_changed(self, model_index, model_index_old):
        self._clear()
        definition_name = self._tree_model.data(model_index, QtCore.Qt.UserRole + 1)
        data = self._definitions_tree_map[definition_name]
        self._populate_selected(data)

    def _populate_selected(self, data):
        if data['name'] == 'Appearance/Colors/':
            index = self._cmdp['Appearance/__index__']
            self._target_widget = AppearanceColors(self.ui.targetWidget, self._cmdp, index, self._active_profile)
            self._target_widget.setContentsMargins(0, 0, 0, 0)
            self.ui.targetLayout.addWidget(self._target_widget)
            self._active_group = data['name']
            return
        elif 'children' not in data:
            return

        self._target_widget = QtWidgets.QWidget()
        self._target_widget.setContentsMargins(0, 0, 0, 0)
        self.ui.targetLayout.addWidget(self._target_widget)
        self._active_group = data['name']
        for name, child in data['children'].items():
            if 'children' in child:
                continue
            if '#' in name or name.startswith('_') or child['name'].endswith('/'):
                continue
            self._populate_entry(name, child)

    def _populate_entry(self, name, entry):
        p = widget_factory(self._cmdp, entry['name'], profile=self._active_profile)
        if p is not None:
            p.populate(self._target_widget)
            self._params.append(p)

    def preferences_reset(self):
        self._profile_reset(self._active_group)

    def exec_(self):
        self._cmdp.invoke('!command_group/start')
        rv = QtWidgets.QDialog.exec_(self)
        self._cmdp.invoke('!command_group/end')
        self._clear()
        if rv == 0:
            self._cmdp.invoke('!undo')
        return rv

    def _redraw_right_pane(self):
        self._clear()
        self._on_tree_item_changed(self.ui.treeView.currentIndex(), None)


def _str_factory(entry, name, value, tooltip):
    options = options_enum(entry.get('options', None))
    if options is not None:
        p = guiparams.Enum(name, value, options, tooltip=tooltip)
    else:
        p = guiparams.String(name, value, tooltip=tooltip)
    return p


def _int_factory(entry, name, value, tooltip):
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


def widget_factory(cmdp, topic, profile=None):
    value = cmdp.preferences.get(topic, profile=profile)
    entry = cmdp.preferences.definition_get(topic)
    name = topic.split('/')[-1]
    p = None
    tooltip = ''
    dtype = entry.get('dtype', 'str')
    if 'brief' in entry and entry['brief'] is not None:
        tooltip = '<span><p>%s</p>' % entry['brief']
        if 'detail' in entry and entry['detail'] is not None:
            tooltip += '<p>%s</p>' % entry['detail']
        tooltip += '</span>'
    if dtype == 'str':
        p = _str_factory(entry, name, value, tooltip)
    elif dtype == 'int':
        p = _int_factory(entry, name, value, tooltip)
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

    if p is None:
        return None

    def cbk(value):
        log.info('widget set %s, %s, %s', topic, value.value, profile)
        cmdp.invoke('!preferences/preference/set', (topic, value.value, profile))

    p.callback = cbk
    cmdp.subscribe(topic, p.update_as_topic_subscriber)
    return p
