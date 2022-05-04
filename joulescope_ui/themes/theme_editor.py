# Copyright 2020 Jetperch LLC
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


from PySide6 import QtCore, QtWidgets
from joulescope_ui.themes.color_picker import ColorItem
import json
import os


MYPATH = os.path.dirname(os.path.abspath(__file__))


def theme_finder():
    themes = []
    for fname in os.listdir(MYPATH):
        path = os.path.join(MYPATH, fname)
        if not os.path.isdir(path):
            continue
        if not os.path.isfile(os.path.join(path, 'index.json')):
            continue
        themes.append(fname)
    return themes


class ThemeEditor(QtWidgets.QWidget):

    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self, parent)
        self._themes = theme_finder()
        self._index = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._top = QtWidgets.QWidget(self)
        self._layout.addWidget(self._top)
        self._top_layout = QtWidgets.QHBoxLayout(self._top)

        self._theme_label = QtWidgets.QLabel('Theme: ', self._top)
        self._top_layout.addWidget(self._theme_label)
        self._theme_combo = QtWidgets.QComboBox(self._top)
        for theme in self._themes:
            self._theme_combo.addItem(theme)
        self._top_layout.addWidget(self._theme_combo)

        self._middle_scroll = QtWidgets.QScrollArea(self)
        self._middle_scroll.setObjectName(u"middle_scroll")
        self._middle_scroll.setWidgetResizable(True)
        self._middle = QtWidgets.QWidget(self)
        self._color_widgets = []
        self._grid = QtWidgets.QGridLayout(self._middle)
        self._middle_scroll.setWidget(self._middle)
        self._layout.addWidget(self._middle_scroll)

        self._bottom = QtWidgets.QWidget(self)
        self._bottom_layout = QtWidgets.QHBoxLayout(self._bottom)
        self._add_button = QtWidgets.QPushButton('Add', self._bottom)
        self._bottom_layout.addWidget(self._add_button)
        self._save_button = QtWidgets.QPushButton('Save', self._bottom)
        self._bottom_layout.addWidget(self._save_button)
        self._layout.addWidget(self._bottom)

        self.theme_selection(self._theme_combo.currentText())

    def color_list(self):
        colors = []
        for c in self._index['colors'].values():
            color_set = set(colors)
            for name in c.keys():
                if name not in color_set:
                    color_set.add(name)
                    colors.append(name)
        return colors

    def theme_selection(self, theme):
        # todo clear self._middle, self._color_widgets

        if theme not in self._themes:
            raise ValueError('theme not found')
        path = os.path.join(MYPATH, theme, 'index.json')
        with open(path, 'r', encoding='utf-8') as f:
            self._index = json.load(f)

        name_label = QtWidgets.QLabel('Color', self._middle)
        self._color_widgets.append(name_label)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        for style_idx, style in enumerate(self._index['colors'].keys()):
            style_label = QtWidgets.QLabel(style, self._middle)
            self._color_widgets.append(style_label)
            self._grid.addWidget(style_label, 0, 1 + style_idx * 2, 1, 2)

        row = 1
        colors = self.color_list()
        max_color_length = max(colors, key=len)
        max_color_length = max(len(max_color_length), 20)
        max_color_length = name_label.fontMetrics().boundingRect('0' * max_color_length).width()

        for name in self.color_list():
            label = QtWidgets.QLineEdit(name, self._middle)
            label.setMinimumWidth(max_color_length)
            self._grid.addWidget(label, row, 0, 1, 1)
            self._color_widgets.append(label)
            for style_idx, (style, style_d) in enumerate(self._index['colors'].items()):
                color = style_d.get(name, '#000000')
                w = ColorItem(self._middle, name, color)
                self._color_widgets.append(w)
                self._grid.addWidget(w.value_edit, row, 1 + 2 * style_idx, 1, 1)
                self._grid.addWidget(w.color_label, row, 2 + 2 * style_idx, 1, 1)
            row += 1


if __name__ == '__main__':
    import ctypes
    import sys

    if sys.platform.startswith('win'):
        ctypes.windll.user32.SetProcessDPIAware()
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    app = QtWidgets.QApplication()
    window = QtWidgets.QMainWindow()
    widget = ThemeEditor(window)
    window.setCentralWidget(widget)
    window.show()
    app.exec_()
