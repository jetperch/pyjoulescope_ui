# Copyright 2023 Jetperch LLC
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

from PySide6 import QtWidgets, QtGui, QtCore
import logging


class ExpandingWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        self._header_ex_widget = None
        self._contents: QtWidgets.QWidget = None
        self._show = False
        self._animations = []
        self._animation_group = None
        super().__init__(parent=parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._header = QtWidgets.QWidget(self)
        self._header_layout = QtWidgets.QHBoxLayout(self._header)
        self._header_layout.setContentsMargins(0, 3, 0, 3)
        self._header_layout.setSpacing(6)
        self._header_icon = QtWidgets.QPushButton(self._header)
        self._header_icon.setFixedSize(16, 16)
        self._header_icon.setFlat(True)
        self._header_icon.setObjectName('expanding_widget_icon')
        self._header_icon.setProperty('expanded', False)  #
        self._header_icon.clicked.connect(self._toggle_body)
        self._header_layout.addWidget(self._header_icon)
        self._header_title = QtWidgets.QLabel('', self._header)
        self._header_title_active = self._header_title
        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._header_layout.addWidget(self._header_title)
        self._header_layout.addItem(self._spacer)
        self._header.mousePressEvent = self._on_header_mousePressEvent
        self._header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._layout.addWidget(self._header)

    @property
    def title(self):
        if self._header_title_active == self._header_title:
            return self._header_title.text()
        return self._header_title_active

    @title.setter
    def title(self, txt):
        if isinstance(txt, str):
            self._header_title.setText(txt)
            if self._header_title_active == self._header_title:
                return
            txt = self._header_title
        if not isinstance(txt, QtWidgets.QWidget):
            raise ValueError('invalid value %s', txt)
        self._header_title_active.setVisible(False)
        self._header_layout.replaceWidget(self._header_title_active, txt)
        txt.setVisible(True)
        self._header_title_active = txt

    @property
    def body_widget(self):
        return self._contents

    @body_widget.setter
    def body_widget(self, w: QtWidgets.QWidget):
        if self._contents is not None:
            self._layout.removeWidget(self._contentsy)
        if w is not None:
            if self._show is not None:
                w.setMaximumHeight(0)
                w.hide()
            self._contents = w
            self._layout.addWidget(w)
        self.animate()

    @property
    def header_ex_widget(self):
        return self._header_ex_widget

    @header_ex_widget.setter
    def header_ex_widget(self, w: QtWidgets.QWidget):
        if self._header_ex_widget is not None:
            self._header_layout.removeWidget(self._header_ex_widget)
            self._header_ex_widget = None
        if w is not None:
            self._header_ex_widget = w
            self._header_layout.addWidget(w)

    def animate(self):
        if self._animation_group is not None:
            self._animation_group.stop()
            self._animation_group = None
        self._animations.clear()
        self._header_icon.setProperty('expanded', self._show)
        self._header_icon.style().unpolish(self._header_icon)
        self._header_icon.style().polish(self._header_icon)

        w = self._contents
        if w is None:
            return
        y_start = w.height()
        y_end = w.sizeHint().height() if self._show else 0
        self._log.info(f'animate {self._show}: {y_start} -> {y_end}')
        if self._show:
            w.show()
        g = QtCore.QParallelAnimationGroup(self)
        for p in b'minimumHeight', b'maximumHeight':
            a = QtCore.QPropertyAnimation(w, p)
            a.setDuration(400)
            a.setStartValue(y_start)
            a.setEndValue(y_end)
            a.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
            a.valueChanged.connect(self._on_value_changed)
            self._animations.append(a)
            g.addAnimation(a)
        self._animation_group = g
        g.start()

    @QtCore.Slot(object)
    def _on_value_changed(self, v):
        w = self.parentWidget()
        while w is not None:
            if isinstance(w, ExpandingWidget):
                h = w._contents.sizeHint().height()
                w._contents.setFixedHeight(h)
            w = w.parentWidget()

    @QtCore.Slot()
    def _toggle_body(self):
        if self._contents is not None:
            self._show = not self._show
            self.animate()

    @property
    def expanded(self):
        return self._show

    @expanded.setter
    def expanded(self, value):
        self._show = bool(value)
        self.animate()

    def _on_header_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
            self._toggle_body()


def demo():
    app = QtWidgets.QApplication([])
    main = QtWidgets.QMainWindow()
    central = QtWidgets.QWidget(main)
    central.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    central_layout = QtWidgets.QVBoxLayout(central)
    main.setCentralWidget(central)

    scroll_area = QtWidgets.QScrollArea(central)
    scroll_area.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll_area.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    scroll_area.setWidgetResizable(True)
    scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    central_layout.addWidget(scroll_area)

    scroll = QtWidgets.QWidget(scroll_area)
    scroll_area.setWidget(scroll)
    layout = QtWidgets.QVBoxLayout(scroll)
    layout.setSpacing(0)
    widgets = []

    def body_contents():
        w = QtWidgets.QWidget()
        w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        w_layout = QtWidgets.QVBoxLayout(w)
        w_layout.setContentsMargins(0, 0, 0, 0)
        w_layout.setSpacing(0)
        w1 = QtWidgets.QLabel('Label 1')
        w1.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        w2 = QtWidgets.QLabel('Label 2')
        w2.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        w_layout.addWidget(w1)
        w_layout.addWidget(w2)
        return w, w_layout, w1, w2

    for idx in range(3):
        e1 = ExpandingWidget()
        e1.title = f'Expanding {idx}.1'
        z1 = body_contents()
        e1.body_widget = z1[0]

        e2 = ExpandingWidget()
        e2.title = f'Sub {idx}.2'
        z2 = body_contents()
        e2.body_widget = z2[0]

        e3 = ExpandingWidget()
        e3.title = f'Sub {idx}.3'
        z3 = body_contents()
        e3.body_widget = z3[0]
        z2[1].addWidget(e3)

        z1[1].addWidget(e2)
        widgets.append([e1, e2, z1, z2, e3, z3])
        layout.addWidget(e1)

    spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
    layout.addItem(spacer)

    arrow_down = """\
    <svg width="10" height="10" version="1.1" xmlns="http://www.w3.org/2000/svg">
      <path d="M 1.5 3.25 L 5 8.25 L 8.5 3.25" style="fill:none;stroke-width:2;stroke:#000000"/>
    </svg>"""

    arrow_right = """\
    <svg width="10" height="10" version="1.1" xmlns="http://www.w3.org/2000/svg">
      <path d="M 3.25 1.5 L 8.25 5 L 3.25 8.5" style="fill:none;stroke-width:2;stroke:#000000"/>
    </svg>"""
    arrow_down_file = QtCore.QTemporaryFile(main)
    arrow_down_file.open()
    arrow_down_file.write(arrow_down.encode('utf-8'))
    arrow_down_file.close()

    arrow_right_file = QtCore.QTemporaryFile(main)
    arrow_right_file.open()
    arrow_right_file.write(arrow_right.encode('utf-8'))
    arrow_right_file.close()
    main.setStyleSheet(f"""\
        QPushButton#expanding_widget_icon[expanded=true] {{
          image: url({arrow_down_file.fileName()});
        }}
        QPushButton#expanding_widget_icon[expanded=false] {{
          image: url({arrow_right_file.fileName()});
        }}""")
    main.show()
    app.exec()


if __name__ == '__main__':
    demo()
