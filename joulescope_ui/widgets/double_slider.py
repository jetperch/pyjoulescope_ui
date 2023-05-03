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


import sys
from PySide6 import QtCore, QtGui, QtWidgets


class DoubleSlider(QtWidgets.QWidget):
    """A slider where the user can select the full range.

    :param parent: The parent QWidget.
    :param value_range: The [v_min, v_max] extents for the
        selection.  Call :meth:`setValues` to initialize.
    """

    values_changed = QtCore.Signal(int, int)
    """Signal(v_min, v_max) emitted on value selection changes."""

    def __init__(self, parent, value_range):
        super(DoubleSlider, self).__init__(parent)
        self._x_margin = 4
        v_min, v_max = value_range
        if v_min > v_max:
            v_min, v_max = v_max, v_min
        self._values_range = [v_min, v_max]
        self._values = [v_min, v_max]
        r = v_max + 1 - v_min
        self.setMinimumSize(self._x_margin * (r + 2), 10)

        self._NO_PEN = QtGui.QPen(QtGui.Qt.NoPen)  # prevent memory leak
        self._background = QtGui.QBrush(QtGui.QColor(200, 200, 200))
        self._foreground = QtGui.QBrush(QtGui.QColor(100, 100, 255))
        self._handles = QtGui.QBrush(QtGui.QColor(50, 50, 255))

        self.setMouseTracking(True)
        self._pressed = None

    @property
    def background(self):
        return self._background.color()

    @background.setter
    def background(self, value):
        self._background = QtGui.QBrush(QtGui.QColor(value))

    @property
    def foreground(self):
        return self._foreground.color()

    @background.setter
    def foreground(self, value):
        self._foreground = QtGui.QBrush(QtGui.QColor(value))

    @property
    def handles(self):
        return self._handles.color()

    @background.setter
    def handles(self, value):
        self._handles = QtGui.QBrush(QtGui.QColor(value))

    @property
    def values(self):
        return (self._values[0], self._values[1])

    @values.setter
    def values(self, value):
        v_min, v_max = value
        if v_min > v_max:
            v_min, v_max = v_max, v_min
        v_min = max(v_min, self._values_range[0])
        v_max = min(v_max, self._values_range[1])
        self._values = [v_min, v_max]
        self.values_changed.emit(*self._values)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        width = self.width() - 2 * self._x_margin
        v0, v1 = self._values
        y0, y1 = self._values_range
        v0, v1 = v0 - y0, v1 - y0
        k = y1 - y0

        # Draw background
        painter.setPen(self._NO_PEN)
        painter.setBrush(self._background)
        painter.drawRect(self._x_margin, 0, width, self.height())

        # Draw range
        painter.setBrush(self._foreground)
        x0 = v0 * width / k + self._x_margin
        x1 = v1 * width / k + self._x_margin
        painter.drawRect(x0, 0, x1 - x0, self.height())

        # Draw handles
        painter.setBrush(self._handles)
        painter.drawEllipse(x0 - self._x_margin, 0, 2 * self._x_margin, self.height())
        painter.drawEllipse(x1 - self._x_margin, 0, 2 * self._x_margin, self.height())

    def get_handle_rect(self, pos):
        pos -= self._values_range[0]
        width = self.width() - 2 * self._x_margin
        k = self._values_range[1] - self._values_range[0]
        return QtCore.QRectF(pos * width / k, 0, 2 * self._x_margin, self.height())

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            pos = event.position()
            min_slider_rect = self.get_handle_rect(self._values[0])
            max_slider_rect = self.get_handle_rect(self._values[1])
            if min_slider_rect.contains(pos) and max_slider_rect.contains(pos):
                self._pressed = 'both'
            elif min_slider_rect.contains(pos):
                if self._values[0] == self._values[1] == self._values_range[0]:
                    self._pressed = 'max'
                else:
                    self._pressed = 'min'
            elif max_slider_rect.contains(pos):
                if self._values[0] == self._values[1] == self._values_range[1]:
                    self._pressed = 'min'
                else:
                    self._pressed = 'max'

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._pressed is not None:
            width = self.width() - 2 * self._x_margin
            k = self._values_range[1] - self._values_range[0]
            pos = round((event.position().x() - self._x_margin) / width * k) + self._values_range[0]
            changed = False
            pos = max(self._values_range[0], min(pos, self._values_range[1]))

            if self._pressed == 'both':
                if pos > self._values[0]:
                    self._pressed = 'max'
                elif pos < self._values[0]:
                    self._pressed = 'min'

            if self._pressed == 'min':
                p = min(self._values[1], pos)
                changed = p != self._values[0]
                self._values[0] = p
            elif self._pressed == 'max':
                p = max(self._values[0], pos)
                changed = p != self._values[1]
                self._values[1] = p
            if changed:
                self.values_changed.emit(*self._values)
                self.update()

    def mouseReleaseEvent(self, event):
        self._pressed = None


class DoubleSliderDemo(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Double Sider Demo')
        self._central_widget = QtWidgets.QWidget(self)
        self._central_widget.setObjectName('central_widget')
        self.setCentralWidget(self._central_widget)

        layout = QtWidgets.QHBoxLayout(self._central_widget)

        self.v_min = QtWidgets.QLabel(self)
        self.double_slider = DoubleSlider(self, [2, 8])
        self.double_slider.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.v_max = QtWidgets.QLabel(self)

        layout.addWidget(self.v_min)
        layout.addWidget(self.double_slider)
        layout.addWidget(self.v_max)

        self.double_slider.values_changed.connect(self._on_values)
        self.double_slider.values = (3, 5)

        self.setLayout(layout)

    @QtCore.Slot(int, int)
    def _on_values(self, v_min, v_max):
        self.v_min.setText(str(v_min))
        self.v_max.setText(str(v_max))


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    window = DoubleSliderDemo()
    window.show()

    sys.exit(app.exec())
