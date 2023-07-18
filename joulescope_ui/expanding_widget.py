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
    def __init__(self, parent):
        self._log = logging.getLogger(__name__)
        self._parent = parent
        self._header_ex_widget = None
        self._body_widget = None
        self._body_show = False
        self._body_animations = []
        super().__init__(parent=parent)

        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._header = QtWidgets.QWidget(self)
        self._header_layout = QtWidgets.QHBoxLayout()
        self._header_layout.setContentsMargins(0, 3, 0, 3)
        self._header_icon = QtWidgets.QPushButton(self._header)
        self._header_icon.setFixedSize(16, 16)
        self._header_icon.setFlat(True)
        self._header_icon.setObjectName('expanding_widget_icon')
        self._header_icon.setProperty('expanded', False)
        self._header_icon.clicked.connect(self._toggle_body)
        self._header_title = QtWidgets.QLabel('', self._header)
        self._header_title_active = self._header_title
        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._layout.addWidget(self._header_icon, 0, 0, 1, 1)
        self._header_layout.addWidget(self._header_title)
        self._header_layout.addItem(self._spacer)
        self._header.setLayout(self._header_layout)
        self._header.mousePressEvent = self._on_header_mousePressEvent
        self._layout.addWidget(self._header, 0, 1, 1, 1)

        self.setLayout(self._layout)

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
        self._layout.replaceWidget(self._header_title_active, txt)
        txt.setVisible(True)
        self._header_title_active = txt

    @property
    def body_widget(self):
        return self._body_widget

    @body_widget.setter
    def body_widget(self, w: QtWidgets.QWidget):
        if self._body_widget is not None:
            self._layout.removeWidget(self._body_widget)
            self._body_widget = None
        if w is not None:
            if self._body_show is not None:
                w.setMaximumHeight(0)
                w.hide()
            self._body_widget = w
            self._layout.addWidget(w, 1, 1, 1, 1)
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
        for a in self._body_animations:
            a.stop()
        self._body_animations.clear()
        self._header_icon.setProperty('expanded', self._body_show)
        self._header_icon.style().unpolish(self._header_icon)
        self._header_icon.style().polish(self._header_icon)

        w = self._body_widget
        if w is None:
            return
        y_start = w.height()
        y_end = w.sizeHint().height() if self._body_show else 0
        self._log.info(f'animate {self._body_show}: {y_start} -> {y_end}')
        if self._body_show:
            w.show()
        for p in [b'minimumHeight', b'maximumHeight']:
            a = QtCore.QPropertyAnimation(w, p)
            a.setDuration(500)
            a.setStartValue(y_start)
            a.setEndValue(y_end)
            a.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
            a.start()
            self._body_animations.append(a)
        if not self._body_show:
            self._body_animations[0].finished.connect(w.hide)

    def _toggle_body(self):
        if self._body_widget is not None:
            self._body_show = not self._body_show
            self.animate()

    @property
    def expanded(self):
        return self._body_show

    @expanded.setter
    def expanded(self, value):
        self._body_show = bool(value)
        self.animate()

    def _on_header_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
            self._toggle_body()
