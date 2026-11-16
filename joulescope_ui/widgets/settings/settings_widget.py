# Copyright 2022-2023 Jetperch LLC
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


from PySide6 import QtCore, QtGui, QtWidgets
from .unique_strings_widget import UniqueStringsWidget
from joulescope_ui import pubsub_singleton, N_, register_decorator, \
    get_instance, get_unique_id, get_topic_name, Metadata, tooltip_format
from joulescope_ui.pubsub import REGISTRY_MANAGER_TOPICS
from joulescope_ui.pubsub_proxy import PubSubProxy
from joulescope_ui.ui_util import comboBoxConfig, clear_layout
from joulescope_ui.styles import styled_widget, font_as_qfont, font_as_qss
from joulescope_ui.styles.color_picker import ColorItem
from joulescope_ui.styles.manager import style_settings, style_cls_ensure
from joulescope_ui.widget_tools import CallableSlotAdapter
from joulescope_ui import settings_reset
import copy
import logging


_NAME = N_('Settings')
_STYLE_AVOID = ['ui']  # list of unique_id values to not display style info


def _styled_class(obj):
    """The styled class for a class or instance, or None if not styled."""
    if not isinstance(obj, type):
        return obj.__class__ if hasattr(obj, 'style_obj') else None
    if 'style_obj' not in getattr(obj, 'SETTINGS', {}):
        return None
    return obj


class _GridWidget(QtWidgets.QWidget):
    """Base grid widget for all settings tabs.

    Subclasses use the _widgets and _grid attributes.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('grid_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._grid_widget = QtWidgets.QWidget(self)
        self._grid = QtWidgets.QGridLayout(self._grid_widget)
        self._layout.addWidget(self._grid_widget)
        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

    _TAB = None  # The settings_reset tab name

    def clear(self):
        clear_layout(self._grid)
        self._labels = {}

    def __len__(self):
        """The number of rows."""
        return len(getattr(self, '_labels', {}))

    def _scheme(self):
        """The active color or font scheme for this tab, if any."""
        return None

    def _name_label(self, name):
        """Create the row name label, which shows and resets modified rows.

        See docs/plans/settings_reset.md.
        """
        label = QtWidgets.QLabel(name, self)
        label.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda pos: self._on_name_menu(name, label, pos))
        if not hasattr(self, '_labels'):
            self._labels = {}
        self._labels[name] = label
        return label

    def _modified_update(self, *args):
        if self._obj is None or not len(self):
            return
        names = settings_reset.modified(self.pubsub, get_unique_id(self._obj), self._TAB, self._scheme())
        for name, label in self._labels.items():
            label.setStyleSheet('font-weight: bold;' if name in names else '')

    def _on_name_menu(self, name, label, pos):
        unique_id = get_unique_id(self._obj)
        names = settings_reset.modified(self.pubsub, unique_id, self._TAB, self._scheme())
        menu = QtWidgets.QMenu(self)
        action = menu.addAction(_reset_text(self.pubsub, unique_id, one=True),
                                lambda: self._reset_name(name))
        action.setEnabled(name in names)
        menu.popup(label.mapToGlobal(pos))

    def _reset_name(self, name):
        value = {'target': get_unique_id(self._obj), 'tabs': [self._TAB], 'names': [name]}
        scheme = self._scheme()
        if scheme is not None:
            value['schemes'] = {self._TAB: scheme}
        self.pubsub.publish(settings_reset.RESET_TOPIC, value)
        self._refresh()

    def _refresh(self):
        """Show the published values after a reset."""
        self._modified_update()


class SettingsEditorWidget(_GridWidget):

    def __init__(self, parent=None):
        self.pubsub = None
        self._obj = None
        self._row = 1
        super().__init__(parent=parent)
        self.setObjectName('settings_editor_widget')

    _TAB = 'settings'

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        obj = get_instance(obj, default=None)
        if self._obj is not None:
            self.clear()
        if obj is None:
            self._obj = None
            return
        self._obj = obj
        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        value_label = QtWidgets.QLabel(N_('Value'), self)
        self._grid.addWidget(value_label, 0, 1, 1, 2)

        topic = f'{get_topic_name(obj)}/settings'
        styles = style_settings('__invalid_name__')
        styles.pop('name')
        settings = self.pubsub.enumerate(topic, absolute=False, traverse=True)
        for setting in settings:
            if setting in styles:
                continue
            self._insert(topic, setting)
        self.pubsub.subscribe(topic, self._modified_update, ['pub'])
        self._modified_update()

    def _insert(self, topic, setting):
        settings_topic = f'{topic}/{setting}'
        meta: Metadata = self.pubsub.metadata(settings_topic)
        if meta is None:
            return
        elif 'hide' in meta.flags:
            return
        else:
            tooltip = tooltip_format(meta.brief, meta.detail)

        label = self._name_label(setting)
        if tooltip is not None:
            label.setToolTip(tooltip)
        self._grid.addWidget(label, self._row, 0, 1, 1)
        w = None
        if meta.dtype == 'unique_strings':
            w = self._insert_unique_strings(settings_topic, meta)
        elif meta.options is not None and len(meta.options):
            w = self._insert_combobox(settings_topic, meta)
        elif meta.dtype == 'bool':
            w = self._insert_bool(settings_topic)
        elif meta.dtype == 'str':
            w = self._insert_str(settings_topic, meta)
        else:
            pass
        if w is not None and tooltip is not None:
            w.setToolTip(tooltip)
        self._row += 1

    def _insert_bool(self, topic):
        widget = QtWidgets.QCheckBox(self)
        self._grid.addWidget(widget, self._row, 1, 1, 1)
        adapter = CallableSlotAdapter(widget, lambda: self.pubsub.publish(topic, widget.isChecked()))
        widget.clicked.connect(adapter.slot)

        def handle(v):
            block_state = widget.blockSignals(True)
            widget.setChecked(bool(v))
            widget.blockSignals(block_state)

        self.pubsub.subscribe(topic, handle, ['pub', 'retain'])
        return widget

    def _insert_str(self, topic, meta):
        widget = QtWidgets.QLineEdit(self)
        self._grid.addWidget(widget, self._row, 1, 1, 1)
        adapter = CallableSlotAdapter(widget, lambda txt: self.pubsub.publish(topic, txt))
        widget.textChanged.connect(adapter.slot)

        def handle(v):
            block_state = widget.blockSignals(True)
            widget.setText(str(v))
            widget.blockSignals(block_state)

        self.pubsub.subscribe(topic, handle, ['pub', 'retain'])
        return widget

    def _insert_combobox(self, topic, meta):
        widget = QtWidgets.QComboBox(self)
        widget.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._grid.addWidget(widget, self._row, 1, 1, 1)
        values = [option[0] for option in meta.options]
        options = [option[1 if len(option) > 1 else 0] for option in meta.options]
        if meta.default in values:
            default = options[values.index(meta.default)]
        else:
            default = meta.default
        comboBoxConfig(widget, options, default)
        adapter = CallableSlotAdapter(widget, lambda idx: self.pubsub.publish(topic, options[idx]))
        widget.currentIndexChanged.connect(adapter.slot)

        def handle(v):
            if v in values:
                widget.setCurrentIndex(values.index(v))
            elif v in options:
                widget.setCurrentIndex(options.index(v))
            else:
                raise ValueError(f'Unable to match {v} in {values} or {options}')

        self.pubsub.subscribe(topic, handle, ['pub', 'retain'])
        return widget

    def _insert_unique_strings(self, topic, meta):
        w = UniqueStringsWidget(self, meta.options)
        self._grid.addWidget(w, self._row, 1, 1, 1)
        adapter = CallableSlotAdapter(w, lambda v: self.pubsub.publish(topic, v))
        w.changed.connect(adapter.slot)

        def handle(v):
            w.value = v

        self.pubsub.subscribe(topic, handle, ['pub', 'retain'])
        return w


class ColorEditorWidget(_GridWidget):

    _TAB = 'colors'

    def _scheme(self):
        return self._color_scheme

    def _refresh(self):
        self.object = self._obj  # rebuild with the published values

    def __init__(self, parent=None):
        self.pubsub = None
        self._colors = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__ + '.color')
        self._color_scheme = None
        super().__init__(parent)
        self.setObjectName('color_editor_widget')
        self._color_widgets = []

    @QtCore.Slot(str, str)
    def _on_change(self, name, color):
        if len(color) == 7:
            color += 'ff'
        elif len(color) != 9:
            self._log.warning('invalid color %s', color)
            return
        self._colors[name] = color
        topic = f'{self._topic}/settings/colors'
        colors = self.pubsub.query(topic)
        if colors is None:
            colors = {self._color_scheme: {name: color}}
        else:
            colors = copy.deepcopy(colors)
            if self._color_scheme not in colors:
                colors[self._color_scheme] = {}
            colors[self._color_scheme][name] = color
        self.pubsub.publish(f'{self._topic}/settings/colors', colors)
        self._modified_update()

    def clear(self):
        for w in self._color_widgets:
            w.deleteLater()
        self._color_widgets.clear()
        super().clear()

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        obj = get_instance(obj, default=None)
        if self._obj is not None:
            self.clear()
            self._obj = None
        if obj is None:
            self._obj = None
            return
        if obj.unique_id in _STYLE_AVOID:
            return
        cls = _styled_class(obj)
        if cls is None:
            return
        active_view = self.pubsub.query('registry/view/settings/active', default='view')
        active_view_topic = get_topic_name(active_view)
        self._color_scheme = self.pubsub.query(f'{active_view_topic}/settings/color_scheme', default='dark')
        self._obj = obj
        self._topic = get_topic_name(obj)
        colors = copy.deepcopy(style_cls_ensure(cls)['load']['colors'][self._color_scheme])
        cls_colors = self.pubsub.query(f'{get_topic_name(cls)}/settings/colors', default=None)
        if cls_colors is not None:
            for color_name, color_value in cls_colors.get(self._color_scheme, {}).items():
                colors[color_name] = color_value
        if not isinstance(obj, type):
            if obj.colors is not None and obj.colors.get(self._color_scheme) is not None:
                for key, value in obj.colors[self._color_scheme].items():
                    colors[key] = value
        self._colors = colors

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        color_label = QtWidgets.QLabel(N_('Color'), self)
        self._grid.addWidget(color_label, 0, 1, 1, 2)
        for row, (name, value) in enumerate(self._colors.items()):
            name_label = self._name_label(name)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            w = ColorItem(self, name, value)
            self._grid.addWidget(w.value_edit, row + 1, 1, 1, 1)
            self._grid.addWidget(w.color_label, row + 1, 2, 1, 1)
            self._color_widgets.append(w)
            w.color_changed.connect(self._on_change)
        self._modified_update()


class QFontLabel(QtWidgets.QLabel):

    changed = QtCore.Signal(str, str)

    def __init__(self, parent, name, value):
        QtWidgets.QLabel.__init__(self, parent)
        self._name = name
        self._value = font_as_qss(value)
        self._dialog = None
        self.setText('0123456789 µΔσ∫')
        self._changed()

    def _changed(self):
        self.setStyleSheet(f"QWidget {{ font: {self._value}; }}")
        self.style().unpolish(self)
        self.style().polish(self)

    @QtCore.Slot(int)
    def _on_finished(self, value):
        if self._dialog is None:
            return
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._value = font_as_qss(self._dialog.currentFont())
            self._changed()
            self.changed.emit(self._name, self._value)
        self._dialog.close()
        self._dialog = None

    def mousePressEvent(self, ev):
        self._dialog = QtWidgets.QFontDialog(font_as_qfont(self._value), self.parent())
        self._dialog.finished.connect(self._on_finished)
        self._dialog.open()
        ev.accept()


class FontEditorWidget(_GridWidget):

    _TAB = 'fonts'

    def _scheme(self):
        return self._font_scheme

    def _refresh(self):
        self.object = self._obj  # rebuild with the published values

    def __init__(self, parent=None):
        self.pubsub = None
        self._font_scheme = None
        super().__init__(parent)
        self._fonts = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__ + '.font')
        self.setObjectName('font_editor_widget')

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        obj = get_instance(obj, default=None)
        if self._obj is not None:
            self.clear()
            self._obj = None
        if obj is None:
            self._obj = None
            return
        if obj.unique_id in ['ui']:
            return
        if obj.unique_id in _STYLE_AVOID:
            return
        cls = _styled_class(obj)
        if cls is None:
            return
        active_view = self.pubsub.query('registry/view/settings/active', default='view')
        active_view_topic = get_topic_name(active_view)
        self._font_scheme = self.pubsub.query(f'{active_view_topic}/settings/font_scheme', default='js1')
        self._obj = obj
        self._topic = get_topic_name(obj)

        fonts = copy.deepcopy(style_cls_ensure(cls)['load']['fonts'][self._font_scheme])
        cls_fonts = self.pubsub.query(f'{get_topic_name(cls)}/settings/fonts', default=None)
        if cls_fonts is not None:
            for font_name, font_value in cls_fonts.get(self._font_scheme, {}).items():
                fonts[font_name] = font_value
        if not isinstance(obj, type):
            if obj.fonts is not None:
                for key, value in obj.fonts.get(self._font_scheme, {}).items():
                    fonts[key] = value
        self._fonts = fonts

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        font_label = QtWidgets.QLabel(N_('Font'), self)
        self._grid.addWidget(font_label, 0, 1, 1, 1)

        for row, (name, value) in enumerate(fonts.items()):
            name_label = self._name_label(name)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            w = QFontLabel(self, name, value)
            w.changed.connect(self._on_change)
            self._grid.addWidget(w, row + 1, 1, 1, 1)
        self._modified_update()

    @QtCore.Slot(str, str)
    def _on_change(self, name, value):
        self._fonts[name] = value
        topic = f'{self._topic}/settings/fonts'
        fonts = self.pubsub.query(topic)
        if fonts is None:
            fonts = {self._font_scheme: {name: value}}
        else:
            fonts = copy.deepcopy(fonts)
            if self._font_scheme not in fonts:
                fonts[self._font_scheme] = {}
            fonts[self._font_scheme][name] = value
        self.pubsub.publish(f'{self._topic}/settings/fonts', fonts)
        self._modified_update()


class StyleDefineEditorWidget(_GridWidget):

    _TAB = 'style_defines'

    def _refresh(self):
        self.object = self._obj  # rebuild with the published values

    def __init__(self, parent=None):
        self.pubsub = None
        super().__init__(parent)
        self._entries = {}
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__ + '.style')
        self.setObjectName('style_define_editor_widget')

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        obj = get_instance(obj, default=None)
        if self._obj is not None:
            self.clear()
            self._obj = None
        if obj is None:
            self._obj = None
            return
        cls = _styled_class(obj)
        if cls is None:
            return

        self._obj = obj
        self._topic = get_topic_name(obj)
        entries = copy.deepcopy(style_cls_ensure(cls)['load']['style_defines'])
        cls_entries = self.pubsub.query(f'{get_topic_name(cls)}/settings/style_defines', default=None)
        if cls_entries is not None:
            for e_name, e_value in cls_entries.items():
                entries[e_name] = e_value
        if not isinstance(obj, type) and obj.style_defines is not None:
            for e_name, e_value in obj.style_defines.items():
                entries[e_name] = e_value
        self._entries = entries

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        font_label = QtWidgets.QLabel(N_('Define'), self)
        self._grid.addWidget(font_label, 0, 1, 1, 1)

        for row, (name, value) in enumerate(self._entries.items()):
            name_label = self._name_label(name)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            w = QtWidgets.QLineEdit(self)
            w.setText(value)
            self._connect(name, w)
            self._grid.addWidget(w, row + 1, 1, 1, 1)
        self._modified_update()

    def _connect(self, name, w):
        adapter = CallableSlotAdapter(w, lambda value: self._on_change(name, value))
        w.textChanged.connect(adapter.slot)

    def _on_change(self, name, value):
        self._entries[name] = value
        topic = f'{self._topic}/settings/style_defines'
        entries = dict(self.pubsub.query(topic, default=None) or {})  # overrides only
        entries[name] = value
        self.pubsub.publish(topic, entries)
        self._modified_update()


def _class_items(capability):
    entries = []
    classes = pubsub_singleton.query(f'registry_manager/capabilities/{capability}/list')
    for clz in classes:
        instances = pubsub_singleton.query(f'{get_topic_name(clz)}/instances')
        children = [[None, x, None] for x in instances if get_instance(x, default=None) is not None]
        entries.append([None, clz, children])
    return entries


def _is_resettable(unique_id):
    """True for a tree entry that has settings: not a group row."""
    if unique_id is None:
        return False
    unique_id = get_unique_id(unique_id)
    return not unique_id.startswith('__') and get_instance(unique_id, default=None) is not None


def _reset_text(pubsub, unique_id, tab=None, one=False):
    """The reset action text, see docs/plans/settings_reset.md."""
    factory = settings_reset.base_topic(pubsub, unique_id) is None
    if one:
        return N_('Reset to factory default') if factory else N_('Reset to default')
    if tab is None:
        return N_('Reset to factory defaults') if factory else N_('Reset to defaults')
    if factory:
        return N_('Reset {tab} to factory defaults').format(tab=tab)
    return N_('Reset {tab} to defaults').format(tab=tab)


class SelectorWidget(QtWidgets.QTreeView):

    def __init__(self, parent=None):
        self.pubsub = None
        self._log = logging.getLogger(__name__ + '.selector')
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
        self.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._model = QtGui.QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels(['Name'])

        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setModel(self._model)
        self.setHeaderHidden(True)
        self.selectionModel().currentChanged.connect(self._on_changed)

    def contextMenuEvent(self, event):
        index = self.indexAt(event.pos())
        unique_id = self._model.data(index, QtCore.Qt.UserRole + 1) if index.isValid() else None
        if not _is_resettable(unique_id):
            return super().contextMenuEvent(event)
        menu = QtWidgets.QMenu(self)
        menu.addAction(_reset_text(self.pubsub, unique_id) + '…',
                       lambda: self.parent().reset_request(unique_id))
        menu.popup(event.globalPos())
        event.accept()

    @QtCore.Slot(object, object)
    def _on_changed(self, model_index, model_index_old):
        unique_id = self._model.data(model_index, QtCore.Qt.UserRole + 1)
        self._log.info('on_changed(%s)', unique_id)
        self.parent().object = unique_id

    def _populate(self, parent, items):
        existing = []
        current = [x[1] for x in items]
        for row in range(parent.rowCount() - 1, -1, -1):
            child_item = parent.child(row, 0)
            if child_item is None:
                continue
            unique_id = child_item.data(QtCore.Qt.UserRole + 1)
            if unique_id not in current:
                self._log.debug('remove row=%s, unique_id=%s', row, unique_id)
                parent.removeRow(row)
            else:
                existing.append(unique_id)
        for row, (name, unique_id, children) in enumerate(items):
            if unique_id not in existing:
                if name is None:
                    name = self.pubsub.query(f'{get_topic_name(unique_id)}/settings/name', default=unique_id)
                self._log.debug(f'insert row={row}, unique_id={unique_id}, name={name}')
                child_item = QtGui.QStandardItem(name)
                child_item.setData(unique_id, QtCore.Qt.UserRole + 1)
                if row >= parent.rowCount():
                    parent.appendRow([child_item])
                else:
                    parent.insertRow(row, [child_item])
            child_item = parent.child(row, 0)
            if child_item.data(QtCore.Qt.UserRole + 1) != unique_id:
                self._log.warning('sync warning')
            if children is not None:
                self._populate(child_item, children)
            elif child_item.rowCount():
                child_item.removeRows(0, child_item.rowCount())
            row += 1

    def _has_unique_id(self, parent, unique_id):
        for row in range(parent.rowCount()):
            child_item = parent.child(row, 0)
            if child_item.data(QtCore.Qt.UserRole + 1) == unique_id:
                return True
            if child_item.rowCount():
                if self._has_unique_id(parent, child_item):
                    return True
        return False

    def populate(self):
        view = self.pubsub.query('registry/view/settings/active')
        items = [
            # [name, unique_id, children]
            [N_('Common'), 'app', None],
            [None, 'ui', None],
            [None, 'paths', None],
            [N_('View defaults'), 'view', None],
            [N_('View'), view, None],
            [N_('Devices'), '__devices__', _class_items('device.class')],
            [N_('Widgets'), '__widgets__', _class_items('widget.class')],
        ]
        self._populate(self._model.invisibleRootItem(), items)


@register_decorator(unique_id='settings')
@styled_widget(_NAME)
class SettingsWidget(QtWidgets.QSplitter):
    CAPABILITIES = ['widget@']

    SETTINGS = {
        'target': {
            'dtype': 'str',
            'brief': 'The unique_id for the target widget.',
            'default': None,
        }
    }

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        self._obj = None
        self._widgets = []
        self._object_pubsub = None
        super().__init__(parent)
        self.setObjectName(f'settings_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._left = SelectorWidget(self)
        self.addWidget(self._left)
        self._tabs = QtWidgets.QTabWidget(self)
        self._tabs.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.addWidget(self._tabs)

        widgets = [  # widget, title, settings_reset tab
            [SettingsEditorWidget(self), N_('Settings'), 'settings'],
            [ColorEditorWidget(self), N_('Colors'), 'colors'],
            [FontEditorWidget(self), N_('Fonts'), 'fonts'],
            [StyleDefineEditorWidget(self), N_('Defines'), 'style_defines'],
        ]
        self._tab_info = []
        for widget, title, tab in widgets:
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            scroll = QtWidgets.QScrollArea(self._tabs)
            scroll.setObjectName(widget.objectName() + '_scroll')
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self._tabs.addTab(scroll, title)
            self._widgets.append([widget, scroll])
            self._tab_info.append([title, tab])

        # Reset: tab bar corner button and tab right-click menu
        self._reset_menu = QtWidgets.QMenu(self)
        self._reset_menu.aboutToShow.connect(self._reset_menu_populate)
        self._reset_button = QtWidgets.QToolButton(self._tabs)
        self._reset_button.setObjectName('reset_button')
        self._reset_button.setText(N_('Reset'))
        self._reset_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self._reset_button.setMenu(self._reset_menu)
        self._tabs.setCornerWidget(self._reset_button, QtCore.Qt.Corner.TopRightCorner)
        tab_bar = self._tabs.tabBar()
        tab_bar.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._on_tab_context_menu)

    def closeEvent(self, event):
        self.object = None
        self._widgets.clear()
        if self._object_pubsub is not None:
            self._object_pubsub.unsubscribe_all()
            self._object_pubsub = None
        return super().closeEvent(event)

    def on_setting_target(self, value):
        if isinstance(value, str) and not len(value):
            return  # default value, ignore
        self._left.setVisible(value is None)
        self.object = get_instance(value, default=None)

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        if self._object_pubsub is not None:
            self._object_pubsub.unsubscribe_all()
        self._object_pubsub = PubSubProxy(self.pubsub)
        obj_str = '[None]' if obj is None else get_unique_id(obj)
        self._log.info('object <= %s', obj_str)
        for widget, _ in self._widgets:
            widget.pubsub = self._object_pubsub
            widget.object = obj
        self._obj = obj
        self._reset_button.setEnabled(_is_resettable(obj))

    def _reset_tab_action(self, menu, index):
        title, tab = self._tab_info[index]
        unique_id = get_unique_id(self._obj)
        action = menu.addAction(_reset_text(self.pubsub, unique_id, title),
                                lambda: self.reset_request(unique_id, tab))
        action.setEnabled(len(self._widgets[index][0]) > 0)  # no rows: nothing to reset

    def _reset_menu_populate(self):
        self._reset_menu.clear()
        if not _is_resettable(self._obj):
            return
        unique_id = get_unique_id(self._obj)
        self._reset_tab_action(self._reset_menu, self._tabs.currentIndex())
        self._reset_menu.addAction(_reset_text(self.pubsub, unique_id) + '…',
                                   lambda: self.reset_request(unique_id))

    def _on_tab_context_menu(self, pos):
        index = self._tabs.tabBar().tabAt(pos)
        if index < 0 or not _is_resettable(self._obj):
            return
        menu = QtWidgets.QMenu(self)
        self._reset_tab_action(menu, index)
        menu.popup(self._tabs.tabBar().mapToGlobal(pos))

    def reset_request(self, unique_id, tab=None):
        """Reset settings, see :func:`joulescope_ui.settings_reset.reset`.

        :param unique_id: The instance or class to reset.
        :param tab: The settings_reset tab name, or None to confirm and
            then reset all tabs.
        """
        unique_id = get_unique_id(unique_id)
        value = {'target': unique_id}
        if tab is None:
            name = self.pubsub.query(f'{get_topic_name(unique_id)}/settings/name', default=unique_id)
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle(_reset_text(self.pubsub, unique_id))
            box.setText(N_('Reset all settings for {name}?').format(name=name))
            box.setInformativeText(N_('Undo restores them.'))
            box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
            box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
            if box.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        else:
            value['tabs'] = [tab]
            view_topic = get_topic_name(self.pubsub.query('registry/view/settings/active'))
            value['schemes'] = {
                'colors': self.pubsub.query(f'{view_topic}/settings/color_scheme', default='dark'),
                'fonts': self.pubsub.query(f'{view_topic}/settings/font_scheme', default='js1'),
            }
        self._log.info('reset %s', value)
        self.pubsub.publish(settings_reset.RESET_TOPIC, value)
        if self._obj is not None and get_unique_id(self._obj) == unique_id:
            self.object = self._obj  # refresh the style editors

    def _on_populate(self):
        self._left.populate()

    def on_pubsub_register(self):
        self._left.pubsub = self.pubsub
        self.pubsub.subscribe('registry/view/settings/active', self._on_populate, ['pub', 'retain'])
        for c in [REGISTRY_MANAGER_TOPICS.REGISTRY_ADD, REGISTRY_MANAGER_TOPICS.REGISTRY_REMOVE]:
            self.pubsub.subscribe(c, self._on_populate, ['pub'])

    @staticmethod
    def on_cls_action_reset(pubsub, topic, value):
        """Reset settings to their defaults as one undo step.

        :param value: The map with keys target, and optionally tabs and
            schemes.  See :func:`joulescope_ui.settings_reset.reset_values`.
        """
        return settings_reset.reset(pubsub, value)

    @staticmethod
    def on_cls_action_edit(pubsub, topic, value):
        w = SettingsWidget()
        w.view_skip_undo = True
        pubsub.publish('registry/view/actions/!widget_open',
                       {'value': w, 'floating': True})
        pubsub.publish(f'{get_topic_name(w)}/settings/target',
                       get_unique_id(value))
