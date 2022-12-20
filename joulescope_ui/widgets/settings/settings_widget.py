# Copyright 2022 Jetperch LLC
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
    get_instance, get_unique_id, get_topic_name
from joulescope_ui.styles import styled_widget
from joulescope_ui.styles.color_picker import ColorItem
from joulescope_ui.styles.color_scheme import COLOR_SCHEMES
from joulescope_ui.styles.font_scheme import FONT_SCHEMES
import logging


class ColorEditorWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        self._colors = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName('color_editor_widget')
        self._grid = QtWidgets.QGridLayout(self)

        self._header_widgets = []
        self._color_widgets = []
        self._count = 0
        self.setLayout(self._grid)

    def __len__(self):
        return self._count

    def _on_change(self, name, color):
        if len(color) == 7:
            color += 'ff'
        elif len(color) != 9:
            self._log.warning('invalid color %s', color)
            return
        self._colors[name] = color
        pubsub_singleton.publish(f'{self._topic}/settings/colors', dict(self._colors))

    def clear(self):
        self._count = 0
        while len(self._color_widgets):
            w = self._color_widgets.pop()
            if isinstance(w, ColorItem):
                self._grid.removeWidget(w.color_label)
                self._grid.removeWidget(w.value_edit)
            else:
                self._grid.removeWidget(w)
            w.deleteLater()
        while len(self._header_widgets):
            w = self._header_widgets.pop()
            self._grid.removeWidget(w)
            w.deleteLater()

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        from joulescope_ui.styles.manager import load_colors
        self.clear()
        self._obj = get_instance(obj)
        self._topic = get_topic_name(self._obj)
        self._colors = load_colors(self._obj)

        name_label = QtWidgets.QLabel(N_('Name'), self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        self._header_widgets.append(name_label)
        if isinstance(self._obj, type):
            for col, color_scheme in enumerate(COLOR_SCHEMES.values()):
                color_label = QtWidgets.QLabel(color_scheme['name'], self)
                self._grid.addWidget(color_label, 0, 1 + col * 2, 1, 2)
                self._header_widgets.append(color_label)
            colors = self._colors
        else:
            color_label = QtWidgets.QLabel(N_('Color'), self)
            self._grid.addWidget(color_label, 0, 1, 1, 2)
            self._header_widgets.append(color_label)
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
        self._count = len(row_map)


def qfont_to_qss_font(qfont: QtGui.QFont) -> str:
    """Convert QFont to QSS font specification.

    :param qfont: The qfont instance.
    :return: The qss font string specification.
        Example: bold italic 12pt "Times New Roman"
    """
    # https://doc.qt.io/qt-6/qfont.html
    # https://doc.qt.io/qt-6/stylesheet-reference.html
    bold = 'bold ' if qfont.bold() else ''
    italic = 'italic ' if qfont.italic() else ''
    size = f'{qfont.pointSize()}pt '
    return f'{bold}{italic}{size}{qfont.family()}'


class QFontLabel(QtWidgets.QLabel):

    changed = QtCore.Signal(str, str)

    def __init__(self, parent, name, value):
        QtWidgets.QLabel.__init__(self, parent)
        self._name = name
        self._value = value
        self.setText('0123456789 µΔσ∫')
        self._changed()

    def _changed(self):
        self.setStyleSheet(f'QLabel {{ font: {self._value}; }}')

    def mousePressEvent(self, ev):
        self.font()
        font = QtGui.QFont()
        font.fromString(self._value)
        ok, font = QtWidgets.QFontDialog.getFont(self.font(), self.parent())
        if ok:
            self._value = qfont_to_qss_font(font)
            self._changed()
            self.changed.emit(self._name, self._value)
        ev.accept()


class FontEditorWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self._count = 0
        self._fonts = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        self.setObjectName('font_editor_widget')
        self._grid = QtWidgets.QGridLayout(self)
        self._widgets = []
        self.setLayout(self._grid)

    def __len__(self):
        return self._count

    def clear(self):
        while len(self._widgets):
            w = self._widgets.pop()
            self._grid.removeWidget(w)
            w.deleteLater()

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        from joulescope_ui.styles.manager import load_fonts
        self.clear()
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
        self._count = len(row_map)

    def _on_change(self, name, value):
        self._fonts[name] = value
        pubsub_singleton.publish(f'{self._topic}/settings/fonts', dict(self._fonts))


class StyleDefineEditorWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self._entries = {}
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        self.setObjectName('style_define_editor_widget')
        self._grid = QtWidgets.QGridLayout(self)
        self._widgets = []
        self.setLayout(self._grid)

    def __len__(self):
        return len(self._entries)

    def clear(self):
        while len(self._widgets):
            w = self._widgets.pop()
            self._grid.removeWidget(w)
            w.deleteLater()

    @property
    def object(self):
        return self._obj

    @object.setter
    def object(self, obj):
        from joulescope_ui.styles.manager import load_style_defines
        self.clear()
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
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setObjectName('settings_widget_layout')
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._widgets = []
        widgets = [
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
