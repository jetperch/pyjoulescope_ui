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
from joulescope_ui import pubsub_singleton, N_, get_instance, get_topic_name
import os
import logging


MYPATH = os.path.dirname(os.path.abspath(__file__))


class ColorEditorWidget(QtWidgets.QWidget):

    def __init__(self, parent, obj):
        from joulescope_ui.styles.manager import load_colors

        self._log = logging.getLogger(__name__)
        self._obj = get_instance(obj)
        self._topic = get_topic_name(self._obj)
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName('color_editor_widget')
        self._grid = QtWidgets.QGridLayout(self)

        self._color_widgets = []

        self.colors = load_colors(obj)
        name_label = QtWidgets.QLabel('Name', self)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        color_label = QtWidgets.QLabel('Color', self)
        self._grid.addWidget(color_label, 0, 1, 1, 2)
        self._color_widgets.append([name_label, color_label])

        row = 0
        for name, color in self.colors.items():
            row += 1
            name_label = QtWidgets.QLabel(name, self)
            self._grid.addWidget(name_label, row, 0, 1, 1)
            w = ColorItem(self, name, color)
            self._grid.addWidget(w.value_edit, row, 1, 1, 1)
            self._grid.addWidget(w.color_label, row, 2, 1, 1)
            self._color_widgets.append([name_label, w])
            w.color_changed.connect(self._on_change)
        self.setLayout(self._grid)

    def _on_change(self, name, color):
        if len(color) == 7:
            color += 'ff'
        elif len(color) != 9:
            self._log.warning('invalid color %s', color)
            return
        self.colors[name] = color
        pubsub_singleton.publish(f'{self._topic}/settings/colors', dict(self.colors))


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
        self._widgets.append([ColorEditorWidget(self, self.obj), N_('Colors')])

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


class StyleEditorDialog(QtWidgets.QDialog):

    def __init__(self, parent=None, obj=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowTitle(N_('Style Editor'))
        self._layout = QtWidgets.QVBoxLayout()
        self._editor = StyleEditorWidget(self, obj=obj)
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
