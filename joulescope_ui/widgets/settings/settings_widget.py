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
    get_instance, get_unique_id, get_topic_name, Metadata, tooltip_format
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
        tooltip = tooltip_format(meta.brief, meta.detail)
        label.setToolTip(tooltip)
        w = None
        if meta.options is not None and len(meta.options):
            w = self._insert_combobox(settings_topic, meta)
        elif meta.dtype == 'bool':
            w = self._insert_bool(settings_topic)
        elif meta.dtype == 'str':
            w = self._insert_str(settings_topic, meta)
        else:
            pass
        if w is not None:
            w.setToolTip(tooltip)
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
        return widget

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
        return widget

    def _insert_combobox(self, topic, meta):
        widget = QtWidgets.QComboBox(self)
        self._grid.addWidget(widget, self._row, 1, 1, 1)
        self._widgets.append(widget)
        values = [option[0] for option in meta.options]
        options = [option[1 if len(option) > 1 else 0] for option in meta.options]
        if meta.default in values:
            default = options[values.index(meta.default)]
        else:
            default = meta.default
        comboBoxConfig(widget, options, default)
        widget.currentIndexChanged.connect(lambda idx: pubsub_singleton.publish(topic, options[idx]))

        def handle(v):
            if isinstance(v, str):
                comboBoxSelectItemByText(widget, v, block=True)
            elif isinstance(v, int):
                widget.setCurrentIndex(values.index(v))

        self._subscribe(topic, handle)
        return widget


class ColorEditorWidget(_GridWidget):

    def __init__(self, parent=None):
        self._colors = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        self._color_scheme = pubsub_singleton.query('registry/style/settings/color_scheme', default='dark')
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
        topic = f'{self._topic}/settings/colors'
        colors = pubsub_singleton.query(topic)
        if colors is None:
            colors = {self._color_scheme: {name: color}}
        else:
            colors = copy.deepcopy(colors)
            if self._color_scheme not in colors:
                colors[self._color_scheme] = {}
            colors[self._color_scheme][name] = color
        pubsub_singleton.publish(f'{self._topic}/settings/colors', colors)

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
        if self._obj is not None:
            self.clear()
            self._obj = None
        if obj is None:
            self._obj = None
            return
        self._obj = get_instance(obj)
        if not hasattr(obj, 'style_obj') or obj.style_obj is None:
            return
        self._topic = get_topic_name(self._obj)

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        self._widgets.append(name_label)
        cls = obj.__class__
        colors = copy.deepcopy(cls._style_cls['load']['colors'])
        cls_colors = pubsub_singleton.query(f'{get_topic_name(obj.__class__)}/settings/colors')
        if cls_colors is not None:
            for color_scheme, k in cls_colors.items():
                for color_name, color_value in k.items():
                    colors[color_scheme][color_name] = color_value
        if isinstance(self._obj, type):
            for col, color_scheme in enumerate(COLOR_SCHEMES.values()):
                color_label = QtWidgets.QLabel(color_scheme['name'], self)
                self._grid.addWidget(color_label, 0, 1 + col * 2, 1, 2)
                self._widgets.append(color_label)
        else:
            colors = colors[self._color_scheme]
            if obj.colors is not None:
                for key, value in obj.colors[self._color_scheme].items():
                    colors[key] = value
            color_label = QtWidgets.QLabel(N_('Color'), self)
            self._grid.addWidget(color_label, 0, 1, 1, 2)
            self._widgets.append(color_label)
            colors = {'__active__': colors}
        self._colors = colors

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
        self._font_scheme = pubsub_singleton.query('registry/style/settings/font_scheme', default='js1')
        self._log = logging.getLogger(__name__)
        self.setObjectName('font_editor_widget')

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        if self._obj is not None:
            self.clear()
            self._obj = None
        if obj is None:
            self._obj = None
            return
        self._obj = get_instance(obj)
        self._topic = get_topic_name(self._obj)
        if not hasattr(obj, 'style_obj') or obj.style_obj is None:
            return
        cls = obj.__class__

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        self._widgets.append(name_label)

        fonts = copy.deepcopy(cls._style_cls['load']['fonts'][self._font_scheme])
        cls_fonts = pubsub_singleton.query(f'{get_topic_name(obj.__class__)}/settings/fonts')
        if cls_fonts is not None:
            for font_name, font_value in cls_fonts[self._font_scheme].items():
                fonts[font_name] = font_value
        if not isinstance(self._obj, type):
            if obj.fonts is not None:
                for key, value in obj.fonts[self._font_scheme].items():
                    fonts[key] = value
            font_label = QtWidgets.QLabel(N_('Font'), self)
            self._grid.addWidget(font_label, 0, 1, 1, 1)
            self._widgets.append(font_label)
        self._fonts = fonts

        row_map = {}
        for row, (name, value) in enumerate(fonts.items()):
            row_map[name] = row
            name_label = QtWidgets.QLabel(name, self)
            self._grid.addWidget(name_label, row + 1, 0, 1, 1)
            self._widgets.append(name_label)
            w = QFontLabel(self, name, value)
            w.changed.connect(self._on_change)
            self._grid.addWidget(w, row + 1, 1, 1, 1)
            self._widgets.append(w)

    def _on_change(self, name, value):
        self._fonts[name] = value
        topic = f'{self._topic}/settings/fonts'
        fonts = pubsub_singleton.query(topic)
        if fonts is None:
            fonts = {self._font_scheme: {name: value}}
        else:
            fonts = copy.deepcopy(fonts)
            if self._font_scheme not in fonts:
                fonts[self._font_scheme] = {}
            fonts[self._font_scheme][name] = value
        pubsub_singleton.publish(f'{self._topic}/settings/fonts', fonts)


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
        if self._obj is not None:
            self.clear()
            self._obj = None
        if obj is None:
            self._obj = None
            return
        if not hasattr(obj, 'style_obj') or obj.style_obj is None:
            return

        obj = get_instance(obj)
        self._obj = obj
        self._topic = get_topic_name(self._obj)
        cls = obj.__class__
        entries = copy.deepcopy(cls._style_cls['load']['style_defines'])
        cls_entries = pubsub_singleton.query(f'{get_topic_name(obj.__class__)}/settings/style_defines')
        if cls_entries is not None:
            for e_name, e_value in cls_entries.items():
                entries[e_name] = e_value
        if not isinstance(obj, type) and obj.style_defines is not None:
            for e_name, e_value in obj.style_defines.items():
                entries[e_name] = e_value
        self._entries = entries

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
        pubsub.register(w, parent=active_view)
        pubsub.publish('registry/view/actions/!widget_open',
                       {'value': w, 'floating': True})
        pubsub.publish(f'{get_topic_name(w)}/settings/target',
                       get_unique_id(value))
