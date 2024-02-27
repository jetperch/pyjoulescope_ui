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
from joulescope_ui.styles.manager import style_settings
from joulescope_ui.widget_tools import CallableSlotAdapter
import copy
import logging


_NAME = N_('Settings')
_STYLE_AVOID = ['ui']  # list of unique_id values to not display style info


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

    def clear(self):
        clear_layout(self._grid)

    def __len__(self):
        rows = self._grid.rowCount()
        if rows >= 1:
            return rows - 1
        else:
            return 0


class SettingsEditorWidget(_GridWidget):

    def __init__(self, parent=None):
        self.pubsub = None
        self._obj = None
        self._row = 1
        super().__init__(parent=parent)
        self.setObjectName('settings_editor_widget')

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

    def _insert(self, topic, setting):
        settings_topic = f'{topic}/{setting}'
        meta: Metadata = self.pubsub.metadata(settings_topic)
        if meta is None:
            return
        elif 'hide' in meta.flags:
            return
        else:
            tooltip = tooltip_format(meta.brief, meta.detail)

        label = QtWidgets.QLabel(setting, self)
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
        if not hasattr(obj, 'style_obj') or obj.style_obj is None:
            return
        active_view = self.pubsub.query('registry/view/settings/active', default='view')
        active_view_topic = get_topic_name(active_view)
        self._color_scheme = self.pubsub.query(f'{active_view_topic}/settings/color_scheme', default='dark')
        self._obj = obj
        self._topic = get_topic_name(obj)
        cls = obj.__class__
        colors = copy.deepcopy(cls._style_cls['load']['colors'][self._color_scheme])
        cls_colors = self.pubsub.query(f'{get_topic_name(obj.__class__)}/settings/colors', default=None)
        if cls_colors is not None:
            for color_name, color_value in cls_colors[self._color_scheme].items():
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
            name_label = QtWidgets.QLabel(name, self)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            w = ColorItem(self, name, value)
            self._grid.addWidget(w.value_edit, row + 1, 1, 1, 1)
            self._grid.addWidget(w.color_label, row + 1, 2, 1, 1)
            self._color_widgets.append(w)
            w.color_changed.connect(self._on_change)


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
        if not hasattr(obj, 'style_obj') or obj.style_obj is None:
            return
        active_view = self.pubsub.query('registry/view/settings/active', default='view')
        active_view_topic = get_topic_name(active_view)
        self._font_scheme = self.pubsub.query(f'{active_view_topic}/settings/font_scheme', default='js1')
        self._obj = obj
        self._topic = get_topic_name(obj)
        cls = obj.__class__

        fonts = copy.deepcopy(cls._style_cls['load']['fonts'][self._font_scheme])
        cls_fonts = self.pubsub.query(f'{get_topic_name(obj.__class__)}/settings/fonts', default=None)
        if cls_fonts is not None:
            for font_name, font_value in cls_fonts[self._font_scheme].items():
                fonts[font_name] = font_value
        if not isinstance(obj, type):
            if obj.fonts is not None:
                for key, value in obj.fonts[self._font_scheme].items():
                    fonts[key] = value
        self._fonts = fonts

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        font_label = QtWidgets.QLabel(N_('Font'), self)
        self._grid.addWidget(font_label, 0, 1, 1, 1)

        for row, (name, value) in enumerate(fonts.items()):
            name_label = QtWidgets.QLabel(name, self)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            w = QFontLabel(self, name, value)
            w.changed.connect(self._on_change)
            self._grid.addWidget(w, row + 1, 1, 1, 1)

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


class StyleDefineEditorWidget(_GridWidget):

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
        if not hasattr(obj, 'style_obj') or obj.style_obj is None:
            return

        self._obj = obj
        self._topic = get_topic_name(obj)
        cls = obj.__class__
        entries = copy.deepcopy(cls._style_cls['load']['style_defines'])
        cls_entries = self.pubsub.query(f'{get_topic_name(obj.__class__)}/settings/style_defines', default=None)
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
            name_label = QtWidgets.QLabel(name, self)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            w = QtWidgets.QLineEdit(self)
            w.setText(value)
            self._connect(name, w)
            self._grid.addWidget(w, row + 1, 1, 1, 1)

    def _connect(self, name, w):
        adapter = CallableSlotAdapter(w, lambda value: self._on_change(name, value))
        w.textChanged.connect(adapter.slot)

    def _on_change(self, name, value):
        self._entries[name] = value
        self.pubsub.publish(f'{self._topic}/settings/style_defines', dict(self._entries))


def _class_items(capability):
    entries = []
    classes = pubsub_singleton.query(f'registry_manager/capabilities/{capability}/list')
    for clz in classes:
        instances = pubsub_singleton.query(f'{get_topic_name(clz)}/instances')
        children = [[None, x, None] for x in instances if get_instance(x, default=None) is not None]
        entries.append([None, clz, children])
    return entries


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

        widgets = [
            [SettingsEditorWidget(self), N_('Settings')],
            [ColorEditorWidget(self), N_('Colors')],
            [FontEditorWidget(self), N_('Fonts')],
            [StyleDefineEditorWidget(self), N_('Defines')],
        ]
        for widget, title in widgets:
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            scroll = QtWidgets.QScrollArea(self._tabs)
            scroll.setObjectName(widget.objectName() + '_scroll')
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self._tabs.addTab(scroll, title)
            self._widgets.append([widget, scroll])

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

    def _on_populate(self):
        self._left.populate()

    def on_pubsub_register(self):
        self._left.pubsub = self.pubsub
        self.pubsub.subscribe('registry/view/settings/active', self._on_populate, ['pub', 'retain'])
        for c in [REGISTRY_MANAGER_TOPICS.REGISTRY_ADD, REGISTRY_MANAGER_TOPICS.REGISTRY_REMOVE]:
            self.pubsub.subscribe(c, self._on_populate, ['pub'])

    @staticmethod
    def on_cls_action_edit(pubsub, topic, value):
        w = SettingsWidget()
        w.view_skip_undo = True
        active_view = pubsub.query('registry/view/settings/active')
        pubsub.register(w, parent=active_view)
        pubsub.publish('registry/view/actions/!widget_open',
                       {'value': w, 'floating': True})
        pubsub.publish(f'{get_topic_name(w)}/settings/target',
                       get_unique_id(value))
