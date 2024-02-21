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
from joulescope_ui.styles import color_file
import os


MYPATH = os.path.dirname(os.path.abspath(__file__))


class ColorEditor(QtWidgets.QWidget):

    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self, parent)
        self._index = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._top = QtWidgets.QWidget(self)
        self._layout.addWidget(self._top)
        self._top_layout = QtWidgets.QHBoxLayout(self._top)

        self._middle_scroll = QtWidgets.QScrollArea(self)
        self._middle_scroll.setObjectName(u"middle_scroll")
        self._middle_scroll.setWidgetResizable(True)
        self._middle = QtWidgets.QWidget(self._middle_scroll)
        self._color_widgets = []
        self._grid = QtWidgets.QGridLayout(self._middle)
        self._middle_scroll.setWidget(self._middle)
        self._layout.addWidget(self._middle_scroll)

        #self._bottom = QtWidgets.QWidget(self)
        #self._bottom_layout = QtWidgets.QHBoxLayout(self._bottom)
        #self._add_button = QtWidgets.QPushButton('Add', self._bottom)
        #self._bottom_layout.addWidget(self._add_button)
        #self._save_button = QtWidgets.QPushButton('Save', self._bottom)
        #self._bottom_layout.addWidget(self._save_button)
        #self._layout.addWidget(self._bottom)
        self.populate()

    def color_list(self):
        colors = []
        for c in self._index['colors'].values():
            color_set = set(colors)
            for name in c.keys():
                if name not in color_set:
                    color_set.add(name)
                    colors.append(name)
        return colors

    def populate(self):
        c_dark = color_file.load(os.path.join(MYPATH, '../styles/color_schemes/color_dark.txt'))
        c_light = color_file.load(os.path.join(MYPATH, '../styles/color_schemes/color_light.txt'))
        color_map = {
            'dark': c_dark,
            'light': c_light,
        }
        colors = set(c_dark.keys())
        colors = colors.union(c_light.keys())

        name_label = QtWidgets.QLabel('Color', self._middle)
        self._color_widgets.append(name_label)
        self._grid.addWidget(name_label, 0, 0, 1, 1)
        for color_scheme_idx, color_scheme in enumerate(color_map.keys()):
            style_label = QtWidgets.QLabel(color_scheme, self._middle)
            self._color_widgets.append(style_label)
            self._grid.addWidget(style_label, 0, 1 + color_scheme_idx * 2, 1, 2)

        row = 1
        max_color_length = max(colors, key=len)
        max_color_length = max(len(max_color_length), 20)
        max_color_length = name_label.fontMetrics().boundingRect('0' * max_color_length).width()

        for name in sorted(colors):
            label = QtWidgets.QLineEdit(name, self._middle)
            label.setMinimumWidth(max_color_length)
            self._grid.addWidget(label, row, 0, 1, 1)
            self._color_widgets.append(label)
            for color_scheme_idx, color_scheme in enumerate(color_map.values()):
                color = color_scheme.get(name, '#00000000')
                w = ColorItem(self._middle, name, color)
                self._color_widgets.append(w)
                self._grid.addWidget(w.value_edit, row, 1 + 2 * color_scheme_idx, 1, 1)
                self._grid.addWidget(w.color_label, row, 2 + 2 * color_scheme_idx, 1, 1)
            row += 1


def run():
    app = QtWidgets.QApplication()
    window = QtWidgets.QMainWindow()
    widget = ColorEditor(window)
    window.setCentralWidget(widget)
    window.show()
    app.exec()


if __name__ == '__main__':
    run()
