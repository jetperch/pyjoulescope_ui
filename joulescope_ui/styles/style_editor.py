# Copyright 2020-2022 Jetperch LLC
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


from PySide6 import QtWidgets
from .color_picker import ColorItem
from .color_scheme import COLOR_SCHEMES
from joulescope_ui import pubsub_singleton, N_, get_instance, get_topic_name
import os
import logging


MYPATH = os.path.dirname(os.path.abspath(__file__))


class ColorEditorWidget(QtWidgets.QWidget):

    def __init__(self, parent, obj):
        self._colors = None
        self._obj = None
        self._topic = None
        self._log = logging.getLogger(__name__)
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName('color_editor_widget')
        self._grid = QtWidgets.QGridLayout(self)

        self._header_widgets = []
        self._color_widgets = []
        self.update_object(obj)
        self.setLayout(self._grid)

    def _on_change(self, name, color):
        if len(color) == 7:
            color += 'ff'
        elif len(color) != 9:
            self._log.warning('invalid color %s', color)
            return
        self._colors[name] = color
        pubsub_singleton.publish(f'{self._topic}/settings/colors', dict(self._colors))

    def update_object(self, obj):
        while len(self._color_widgets):
            w = self._color_widgets.pop()
            if isinstance(w, ColorItem):
                self._grid.removeWidget(w.color_label)
                self._grid.removeWidget(w.value_edit)
            else:
                self._grid.removeWidget(w)
            w.close()
        while len(self._header_widgets):
            w = self._header_widgets.pop()
            self._grid.removeWidget(w)
            w.close()

        from joulescope_ui.styles.manager import load_colors
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


# todo
#class FontEditorWidget(QtWidgets.QWidget):
#
#    def __init__(self, parent):
#        QtWidgets.QWidget.__init__(self, parent)
#
#
#class StyleDefineEditorWidget(QtWidgets.QWidget):
#
#    def __init__(self, parent):
#        QtWidgets.QWidget.__init__(self, parent)


class StyleEditorWidget(QtWidgets.QWidget):

    def __init__(self, parent, obj):
        self.obj = get_instance(obj)
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName('style_editor_widget')
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setObjectName('style_editor_layout')
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._widgets = []
        self._color_widget = ColorEditorWidget(self, self.obj)
        self._widgets.append([self._color_widget, N_('Colors')])

        self._tabs = QtWidgets.QTabWidget(self)
        for idx, (widget, title) in enumerate(self._widgets):
            scroll = QtWidgets.QScrollArea(self._tabs)
            scroll.setObjectName(widget.objectName() + '_scroll')
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self._tabs.addTab(scroll, title)
            self._widgets[idx].append(scroll)
        self._layout.addWidget(self._tabs)

        self.setLayout(self._layout)

    def update_object(self, obj):
        self.obj = get_instance(obj)
        self._color_widget.update_object(obj)


class StyleEditorDialog(QtWidgets.QDialog):

    def __init__(self, parent=None, obj=None):
        self._obj = get_instance(obj)
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowTitle(N_('Style Editor'))
        self._layout = QtWidgets.QVBoxLayout()

        self._header = QtWidgets.QWidget(self)
        self._header.setObjectName('style_editor_header')
        if isinstance(self._obj, type):
            pass  # simple header
        else:
            self._grid = QtWidgets.QGridLayout(self._header)
            self._instance_radio_button = QtWidgets.QRadioButton(N_('Modify this instance'), self._header)
            self._instance_radio_button.setChecked(True)
            self._instance_radio_button.toggled.connect(self._update_target)
            self._instance_button = QtWidgets.QPushButton(self._header)
            self._instance_button.setText(N_('Clear'))
            self._class_radio_button = QtWidgets.QRadioButton(N_('Modify class default'), self._header)
            self._class_radio_button.toggled.connect(self._update_target)
            self._class_button = QtWidgets.QPushButton(self._header)
            self._class_button.setText(N_('Clear'))
            widgets = [
                [self._instance_radio_button, self._instance_button],
                [self._class_radio_button, self._class_button]
            ]
            for row, row_widgets in enumerate(widgets):
                for col, widget in enumerate(row_widgets):
                    self._grid.addWidget(widget, row, col, 1, 1)
            self._header.setLayout(self._grid)
        self._layout.addWidget(self._header)

        self._editor = StyleEditorWidget(self, obj=self._obj)
        self._layout.addWidget(self._editor)

        self._buttons = QtWidgets.QFrame(self)
        self._buttons.setObjectName('style_editor_button_frame')
        self._buttons.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self._buttons.setFrameShadow(QtWidgets.QFrame.Raised)
        self._buttons_layout = QtWidgets.QHBoxLayout(self._buttons)
        self._buttons_layout.setObjectName('style_editor_button_layout')
        self._buttons_spacer = QtWidgets.QSpacerItem(40, 20,
                                                     QtWidgets.QSizePolicy.Expanding,
                                                     QtWidgets.QSizePolicy.Minimum)
        self._buttons_layout.addItem(self._buttons_spacer)

        self._reset_button = QtWidgets.QPushButton(self._buttons)
        self._reset_button.setObjectName('style_editor_button_reset')
        self._reset_button.setText(N_('Reset to Defaults'))
        self._buttons_layout.addWidget(self._reset_button)

        self._cancel_button = QtWidgets.QPushButton(self._buttons)
        self._cancel_button.setObjectName('style_editor_button_cancel')
        self._cancel_button.setText(N_('Cancel'))
        self._cancel_button.pressed.connect(self.reject)
        self._buttons_layout.addWidget(self._cancel_button)

        self._ok_button = QtWidgets.QPushButton(self._buttons)
        self._ok_button.setObjectName('style_editor_button_accept')
        self._ok_button.setText(N_('Ok'))
        self._ok_button.pressed.connect(self.accept)
        self._buttons_layout.addWidget(self._ok_button)
        self._buttons.setLayout(self._buttons_layout)

        self._layout.addWidget(self._buttons)
        self.setLayout(self._layout)

    def _update_target(self, _):
        if self._instance_radio_button.isChecked():
            self._editor.update_object(self._obj)
        else:
            self._editor.update_object(self._obj.__class__)
