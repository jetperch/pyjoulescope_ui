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
from collections.abc import Iterable


class DoubleSlider(QtWidgets.QWidget):
    """A slider where the user can select the full range.

    :param parent: The parent QWidget.
    :param value_range: The [v_min, v_max] extents for the
        selection.  Call :meth:`setValues` to initialize.
        If v_min > v_max, then the slider is configured in
        descending order.
    """

    values_changed = QtCore.Signal(int, int)
    """Signal(v_min, v_max) emitted on value selection changes."""

    def __init__(self, parent, value_range):
        if not isinstance(value_range, Iterable) or len(value_range) != 2:
            raise ValueError(f'invalid value_range {value_range}')
        self._value_range = [int(v) for v in value_range]  # in external value coordinates
        super().__init__(parent)
        self._x_margin = 4
        self._values_offset = min(value_range)
        self._values_length = abs(value_range[1] - value_range[0]) + 1
        self._values = [0, 0]
        self.values = self._value_range
        self.setMinimumSize(self._x_margin * (self._values_length + 2), 10)

        self._NO_PEN = QtGui.QPen(QtGui.Qt.NoPen)  # prevent memory leak
        self._background = QtGui.QBrush(QtGui.QColor(128, 128, 128))
        self._foreground = QtGui.QBrush(QtGui.QColor(100, 100, 255))
        self._handles = QtGui.QBrush(QtGui.QColor(50, 50, 255))
        self._handles_hover = QtGui.QBrush(QtGui.QColor(128, 192, 255))

        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_HOR = QtGui.QCursor(QtGui.Qt.SizeHorCursor)

        self.setMouseTracking(True)
        self._mouse_pos = None
        self._pressed = None

    def _value_map_to_internal(self, v):
        if isinstance(v, Iterable):
            return [self._value_map_to_internal(x) for x in v]
        v = int(v) - self._values_offset
        if self._value_range[0] > self._value_range[1]:
            v = self._values_length - 1 - v
        return v

    def _value_map_to_external(self, v):
        if isinstance(v, Iterable):
            return [self._value_map_to_external(x) for x in v]
        if self._value_range[0] > self._value_range[1]:
            v = self._values_length - 1 - v
        v += self._values_offset
        return v

    @property
    def background(self):
        return self._background.color()

    @background.setter
    def background(self, value):
        self._background = QtGui.QBrush(QtGui.QColor(value))

    @property
    def foreground(self):
        return self._foreground.color()

    @foreground.setter
    def foreground(self, value):
        self._foreground = QtGui.QBrush(QtGui.QColor(value))

    @property
    def handles(self):
        return self._handles.color()

    @handles.setter
    def handles(self, value):
        self._handles = QtGui.QBrush(QtGui.QColor(value))

    @property
    def handles_hover(self):
        return self._handles_hover.color()

    @handles_hover.setter
    def handles_hover(self, value):
        self._handles_hover = QtGui.QBrush(QtGui.QColor(value))

    @property
    def values(self):
        return self._value_map_to_external(self._values)

    @values.setter
    def values(self, value):
        v0, v1 = self._value_map_to_internal(value)
        if v0 > v1:  # correct inconsistent order
            v0, v1 = v1, v0
        self._values = [v0, v1]
        self.values_changed.emit(*self._value_map_to_external(self._values))
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        width = self.width() - 2 * self._x_margin
        v0, v1 = self._values
        y0, y1 = 0, self._values_length - 1
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
        handles = {
            'min': (x0 - self._x_margin, 0, 2 * self._x_margin, self.height()),
            'max': (x1 - self._x_margin, 0, 2 * self._x_margin, self.height()),
        }
        handles['both'] = handles['min']
        painter.drawEllipse(*handles['min'])
        painter.drawEllipse(*handles['max'])

        if self._pressed is not None:
            handle = self._pressed
            painter.setBrush(self._handles_hover)
            painter.drawEllipse(*handles[handle])
        else:
            handle = self._position_to_handle(self._mouse_pos)
            if handle is not None:
                painter.setBrush(self._handles_hover)
                painter.drawEllipse(*handles[handle])

    def get_handle_rect(self, pos):
        width = self.width() - 2 * self._x_margin
        k = self._values_length - 1
        return QtCore.QRectF(pos * width / k, 0, 2 * self._x_margin, self.height())

    def _position_to_handle(self, pos):
        if pos is None:
            return None
        min_slider_rect = self.get_handle_rect(self._values[0])
        max_slider_rect = self.get_handle_rect(self._values[1])
        if min_slider_rect.contains(pos) and max_slider_rect.contains(pos):
            return 'both'
        elif min_slider_rect.contains(pos):
            if self._values[0] == self._values[1] == 0:
                return 'max'
            else:
                return 'min'
        elif max_slider_rect.contains(pos):
            if self._values[0] == self._values[1] == (self._values_length - 1):
                return 'min'
            else:
                return 'max'
        else:
            return None

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            pos = event.position()
            self._pressed = self._position_to_handle(pos)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        self._mouse_pos = event.position()
        if self._pressed is not None:
            width = self.width() - 2 * self._x_margin
            k = self._values_length - 1
            pos = round((self._mouse_pos.x() - self._x_margin) / width * k)
            changed = False
            pos = max(0, min(pos, self._values_length - 1))

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
                self.values_changed.emit(*self._value_map_to_external(self._values))
                self.update()
        else:
            if self._position_to_handle(self._mouse_pos) is not None:
                cursor = self._CURSOR_SIZE_HOR
            else:
                cursor = self._CURSOR_ARROW
            self.setCursor(cursor)
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
        self.double_slider = DoubleSlider(self, [8, 2])
        self.double_slider.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.v_max = QtWidgets.QLabel(self)

        layout.addWidget(self.v_min)
        layout.addWidget(self.double_slider)
        layout.addWidget(self.v_max)

        self.double_slider.values_changed.connect(self._on_values)
        self.double_slider.values = (3, 5)  # order is corrected

    @QtCore.Slot(int, int)
    def _on_values(self, v_min, v_max):
        self.v_min.setText(str(v_min))
        self.v_max.setText(str(v_max))


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)

    window = DoubleSliderDemo()
    window.show()

    sys.exit(app.exec())
