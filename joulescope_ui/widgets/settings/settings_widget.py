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
from joulescope_ui import pubsub_singleton, N_, register_decorator, \
    get_instance, get_unique_id, get_topic_name, Metadata
from joulescope_ui.ui_util import comboBoxConfig, comboBoxSelectItemByText
from joulescope_ui.styles import styled_widget, font_as_qfont, font_as_qss
from joulescope_ui.styles.color_picker import ColorItem
from joulescope_ui.styles.color_scheme import COLOR_SCHEMES
from joulescope_ui.styles.font_scheme import FONT_SCHEMES
from joulescope_ui.styles.manager import style_settings
import copy
import logging


class _GridWidget(QtWidgets.QWidget):
    """Base grid widget for all settings tabs.

    Subclasses use the _widgets and _grid attributes.
    """

    def __init__(self, parent=None):
        self._widgets = []
        super().__init__(parent=parent)
        self.setObjectName('grid_widget')
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._grid_widget = QtWidgets.QWidget(self)
        self._grid = QtWidgets.QGridLayout(self)
        self._grid_widget.setLayout(self._grid)
        self._layout.addWidget(self._grid_widget)
        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)
        self.setLayout(self._layout)

    def clear(self):
        while len(self._widgets):
            w = self._widgets.pop()
            self._grid.removeWidget(w)
            w.deleteLater()

    def __len__(self):
        rows = self._grid.rowCount()
        if rows >= 1:
            return rows - 1
        else:
            return 0


class SettingsEditorWidget(_GridWidget):

    def __init__(self, parent=None):
        self._obj = None
        self._unsub = []
        self._row = 1
        super().__init__(parent=parent)
        self.setObjectName('settings_editor_widget')

    def clear(self):
        for topic, fn in self._unsub:
            pubsub_singleton.unsubscribe(topic, fn)
        self._unsub.clear()
        super().clear()

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        if self._obj is not None:
            self.clear()
        if obj is None:
            self._obj = None
            return
        self._obj = get_instance(obj)
        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        self._widgets.append(name_label)
        value_label = QtWidgets.QLabel(N_('Value'), self)
        self._grid.addWidget(value_label, 0, 1, 1, 2)
        self._widgets.append(value_label)

        topic = f'{get_topic_name(obj)}/settings'
        styles = style_settings('__invalid_name__')
        styles.pop('name')
        settings = pubsub_singleton.enumerate(topic, absolute=False, traverse=True)
        for setting in settings:
            if setting in styles:
                continue
            self._insert(topic, setting)

    def _insert(self, topic, setting):
        label = QtWidgets.QLabel(setting, self)
        self._grid.addWidget(label, self._row, 0, 1, 1)
        self._widgets.append(label)

        settings_topic = f'{topic}/{setting}'
        meta: Metadata = pubsub_singleton.metadata(settings_topic)
        if meta.options is not None and len(meta.options):
            self._insert_combobox(settings_topic, meta)
        elif meta.dtype == 'bool':
            self._insert_bool(settings_topic)
        elif meta.dtype == 'str':
            self._insert_str(settings_topic, meta)
        else:
            pass
        self._row += 1

    def _subscribe(self, topic, update_fn):
        pubsub_singleton.subscribe(topic, update_fn, ['pub', 'retain'])
        self._unsub.append((topic, update_fn))

    def _insert_bool(self, topic):
        widget = QtWidgets.QCheckBox(self)
        self._grid.addWidget(widget, self._row, 1, 1, 1)
        self._widgets.append(widget)
        widget.clicked.connect(lambda: pubsub_singleton.publish(topic, widget.isChecked()))

        def handle(v):
            block_state = widget.blockSignals(True)
            widget.setChecked(bool(v))
            widget.blockSignals(block_state)

        self._subscribe(topic, handle)

    def _insert_str(self, topic, meta):
        widget = QtWidgets.QLineEdit(self)
        self._grid.addWidget(widget, self._row, 1, 1, 1)
        self._widgets.append(widget)
        widget.textChanged.connect(lambda txt: pubsub_singleton.publish(topic, txt))

        def handle(v):
            block_state = widget.blockSignals(True)
            widget.setText(str(v))
            widget.blockSignals(block_state)

        self._subscribe(topic, handle)

    def _insert_combobox(self, topic, meta):
        widget = QtWidgets.QComboBox(self)
        self._grid.addWidget(widget, self._row, 1, 1, 1)
        self._widgets.append(widget)
        options = [option[1 if len(option) > 1 else 0] for option in meta.options]
        comboBoxConfig(widget, options, meta.default)
        widget.currentIndexChanged.connect(lambda idx: pubsub_singleton.publish(topic, options[idx]))

        def handle(v):
            if isinstance(v, str):
                comboBoxSelectItemByText(widget, v, block=True)
            elif isinstance(v, int):
                widget.setCurrentIndex(v)

        self._subscribe(topic, handle)


class ColorEditorWidget(_GridWidget):

    def __init__(self, parent=None):
        self._colors = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        super().__init__(parent)
        self.setObjectName('color_editor_widget')
        self._color_widgets = []

    def _on_change(self, name, color):
        if len(color) == 7:
            color += 'ff'
        elif len(color) != 9:
            self._log.warning('invalid color %s', color)
            return
        self._colors[name] = color
        pubsub_singleton.publish(f'{self._topic}/settings/colors', copy.deepcopy(self._colors))

    def clear(self):
        while len(self._color_widgets):
            w = self._color_widgets.pop()
            if isinstance(w, ColorItem):
                self._grid.removeWidget(w.color_label)
                self._grid.removeWidget(w.value_edit)
            else:
                self._grid.removeWidget(w)
            w.deleteLater()
        super().clear()

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        from joulescope_ui.styles.manager import load_colors
        if self._obj is not None:
            self.clear()
        if obj is None:
            self._obj = None
            return
        self._obj = get_instance(obj)
        self._topic = get_topic_name(self._obj)
        self._colors = copy.deepcopy(load_colors(self._obj))

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        self._widgets.append(name_label)
        if isinstance(self._obj, type):
            for col, color_scheme in enumerate(COLOR_SCHEMES.values()):
                color_label = QtWidgets.QLabel(color_scheme['name'], self)
                self._grid.addWidget(color_label, 0, 1 + col * 2, 1, 2)
                self._widgets.append(color_label)
            colors = self._colors
        else:
            color_label = QtWidgets.QLabel(N_('Color'), self)
            self._grid.addWidget(color_label, 0, 1, 1, 2)
            self._widgets.append(color_label)
            colors = {'__active__': self._colors}

        row_map = {}
        for col, color in enumerate(colors.values()):
            for row, (name, value) in enumerate(color.items()):
                if col == 0:
                    row_map[name] = row
                    name_label = QtWidgets.QLabel(name, self)
                    self._grid.addWidget(name_label, row + 1, 0, 1, 1)
                    self._color_widgets.append(name_label)
                elif name in row_map:
                    row = row_map[name]
                else:
                    row = len(row_map)
                    row_map[name] = row
                w = ColorItem(self, name, value)
                self._grid.addWidget(w.value_edit, row + 1, 1 + col * 2, 1, 1)
                self._grid.addWidget(w.color_label, row + 1, 2 + col * 2, 1, 1)
                self._color_widgets.append(w)
                w.color_changed.connect(self._on_change)


class QFontLabel(QtWidgets.QLabel):

    changed = QtCore.Signal(str, str)

    def __init__(self, parent, name, value):
        QtWidgets.QLabel.__init__(self, parent)
        self._name = name
        self._value = value
        self.setText('0123456789 µΔσ∫')
        self.setFont(font_as_qfont(self._value))
        self._changed()

    def _changed(self):
        self.setFont(font_as_qfont(self._value))

    def mousePressEvent(self, ev):
        ok, font = QtWidgets.QFontDialog.getFont(font_as_qfont(self._value), self.parent())
        if ok:
            self._value = font_as_qss(font)
            self._changed()
            self.changed.emit(self._name, self._value)
        ev.accept()


class FontEditorWidget(_GridWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fonts = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        self.setObjectName('font_editor_widget')

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        from joulescope_ui.styles.manager import load_fonts
        if self._obj is not None:
            self.clear()
        if obj is None:
            self._obj = None
            return
        self._obj = get_instance(obj)
        self._topic = get_topic_name(self._obj)
        self._fonts = load_fonts(self._obj)
        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        self._widgets.append(name_label)
        if isinstance(self._obj, type):
            for col, font_scheme in enumerate(FONT_SCHEMES.values()):
                font_label = QtWidgets.QLabel(font_scheme['name'], self)
                self._grid.addWidget(font_label, 0, 1 + col, 1, 1)
                self._widgets.append(font_label)
            fonts = self._fonts
        else:
            font_label = QtWidgets.QLabel(N_('Font'), self)
            self._grid.addWidget(font_label, 0, 1, 1, 1)
            self._widgets.append(font_label)
            fonts = {'__active__': self._fonts}

        row_map = {}
        for col, fonts_by_scheme in enumerate(fonts.values()):
            for row, (name, value) in enumerate(fonts_by_scheme.items()):
                if col == 0:
                    row_map[name] = row
                    name_label = QtWidgets.QLabel(name, self)
                    self._grid.addWidget(name_label, row + 1, 0, 1, 1)
                    self._widgets.append(name_label)
                elif name in row_map:
                    row = row_map[name]
                else:
                    row = len(row_map)
                    row_map[name] = row
                w = QFontLabel(self, name, value)
                w.changed.connect(self._on_change)
                self._grid.addWidget(w, row + 1, 1 + col, 1, 1)
                self._widgets.append(w)
                # todo w.changed.connect(self._on_change)

    def _on_change(self, name, value):
        self._fonts[name] = value
        pubsub_singleton.publish(f'{self._topic}/settings/fonts', dict(self._fonts))


class StyleDefineEditorWidget(_GridWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = {}
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        self.setObjectName('style_define_editor_widget')

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        from joulescope_ui.styles.manager import load_style_defines
        if self._obj is not None:
            self.clear()
        if obj is None:
            self._obj = None
            return
        self._obj = get_instance(obj)
        self._topic = get_topic_name(self._obj)
        self._entries = load_style_defines(self._obj)
        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        self._widgets.append(name_label)
        font_label = QtWidgets.QLabel(N_('Define'), self)
        self._grid.addWidget(font_label, 0, 1, 1, 1)
        self._widgets.append(font_label)

        for row, (name, value) in enumerate(self._entries.items()):
            name_label = QtWidgets.QLabel(name, self)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            self._widgets.append(name_label)
            w = QtWidgets.QLineEdit(self)
            w.setText(value)
            w.changed.connect(self._on_change)  # todo
            self._grid.addWidget(w, row + 1, 1, 1, 1)
            self._widgets.append(w)

    def _on_change(self, name, value):
        self._entries[name] = value
        pubsub_singleton.publish(f'{self._topic}/settings/style_defines', dict(self._entries))


@register_decorator(unique_id='settings')
@styled_widget(N_('settings'))
class SettingsWidget(QtWidgets.QWidget):

    SETTINGS = {
        'target': {
            'dtype': 'str',
            'brief': 'The unique_id for the target widget.',
            'default': '',
        }
    }

    def __init__(self, parent=None):
        super(SettingsWidget, self).__init__(parent)
        self._obj = None
        self.setObjectName(f'settings_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setObjectName('settings_widget_layout')
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._widgets = []
        widgets = [
            [SettingsEditorWidget(self), N_('Settings')],
            [ColorEditorWidget(self), N_('Colors')],
            [FontEditorWidget(self), N_('Fonts')],
            [StyleDefineEditorWidget(self), N_('Defines')],
        ]

        self._tabs = QtWidgets.QTabWidget(self)
        for widget, title in widgets:
            scroll = QtWidgets.QScrollArea(self._tabs)
            scroll.setObjectName(widget.objectName() + '_scroll')
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self._tabs.addTab(scroll, title)
            self._widgets.append([widget, scroll])
        self._layout.addWidget(self._tabs)
        self.setLayout(self._layout)

    def closeEvent(self, event):
        self.object = None
        return super().closeEvent(event)

    def on_setting_target(self, value):
        if isinstance(value, str) and not len(value):
            return  # default value, ignore
        self.object = get_instance(value)

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        for widget, _ in self._widgets:
            widget.object = obj
        self._obj = obj

    @staticmethod
    def on_cls_action_edit(pubsub, topic, value):
        w = SettingsWidget()
        active_view = pubsub.query('registry/view/settings/active')
        unique_id = pubsub.register(w, parent=active_view)
        pubsub.publish('registry/view/actions/!widget_open',
                       {'value': w, 'floating': True})
        pubsub.publish(f'{get_topic_name(unique_id)}/settings/target',
                       get_unique_id(value))
