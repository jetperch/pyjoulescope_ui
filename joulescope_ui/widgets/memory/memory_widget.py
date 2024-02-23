# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtWidgets, QtGui, QtCore
from joulescope_ui import N_, register
from joulescope_ui.tooltip import tooltip_format
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.units import elapsed_time_formatter
import numpy as np
import os
import psutil

_TOPIC = 'registry/JsdrvStreamBuffer:001'
_TOPIC_CLEAR_ON_PLAY = f'{_TOPIC}/settings/clear_on_play'
_TOPIC_SIZE = f'{_TOPIC}/settings/size'
_TOPIC_DURATION = f'{_TOPIC}/settings/duration'
_GB_FACTOR = 1024 ** 3
_SZ_MIN = int(0.01 * _GB_FACTOR)
_COLOR_TEXT = '   '


def _mem_proc():
    return psutil.Process(os.getpid()).memory_info().rss


def _format(sz):
    sz = sz / _GB_FACTOR
    return f'{sz:.2f}'


class MemSet(QtWidgets.QWidget):

    def __init__(self, parent=None):
        self.sizes = np.array([0, 0, 0, 1], dtype=float)
        super().__init__(parent=parent)
        self._height = 30
        self._x_pos = 0
        self._drag = None
        self._width = 1
        self.setMinimumHeight(self._height)
        self.setMaximumHeight(self._height)
        self.setMouseTracking(True)
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_HOR = QtGui.QCursor(QtGui.Qt.SizeHorCursor)

    @property
    def is_active(self):
        return self._drag is not None

    def update(self, base, available, used):
        if self._drag is None:
            self.sizes[0] = base
            self.sizes[2] = available
            self.sizes[3] = used
            self.repaint()

    def update_size(self, size):
        if self._drag is None:
            self.sizes[1] = size

    def show_size(self, size):
        self.parent()._on_size(size)
        self.repaint()

    def _pixel_boundaries(self):
        w = self.width()
        sizes = np.array(self.sizes, dtype=float)
        total = np.sum(sizes)
        pixels = np.rint(sizes * (w / total)).astype(np.uint64)
        return pixels

    def paintEvent(self, event):
        if self.parent().style_obj is None:
            return
        v = self.parent().style_obj['vars']
        widget_w, widget_h = self.width(), self.height()
        p = QtGui.QPainter(self)

        pixels = self._pixel_boundaries()
        self._width = np.sum(pixels)

        colors = [
            color_as_qcolor(v['memory.base']),
            color_as_qcolor(v['memory.size']),
            color_as_qcolor(v['memory.available']),
            color_as_qcolor(v['memory.used']),
        ]

        x = 0
        for idx, pixel in enumerate(pixels):
            b1 = QtGui.QBrush(colors[idx])
            p.setBrush(b1)
            if pixel:
                p.fillRect(x, 0, pixel, widget_h, b1)
            x += pixel
            if idx == 1:
                self._x_pos = x

    def is_mouse_active(self, x):
        return abs(x - self._x_pos) < 10

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x = event.position().x()
        if self.is_mouse_active(x):
            cursor = self._CURSOR_SIZE_HOR
        else:
            cursor = self._CURSOR_ARROW
        self.setCursor(cursor)
        if self._drag is not None:
            total = np.sum(self.sizes)
            sz = x / self._width * total - self.sizes[0]
            sz_max = self.sizes[1] + self.sizes[2]
            sz = max(_SZ_MIN, min(sz, sz_max))
            dsz = sz - self.sizes[1]
            self.sizes[1] += dsz
            self.sizes[2] -= dsz
            self.show_size(sz)

    def abort(self):
        if self._drag is None:
            return
        self.show_size(self._drag[1])
        self.sizes, self._drag = self._drag, None

    def mousePressEvent(self, event):
        event.accept()
        x = event.position().x()
        if event.button() == QtCore.Qt.LeftButton:
            if self._drag is None and self.is_mouse_active(x):
                self._drag = np.copy(self.sizes)
        elif self._drag is not None:
            self.abort()
        self.repaint()

    def mouseReleaseEvent(self, event):
        event.accept()
        if self._drag is None:
            return
        if event.button() == QtCore.Qt.LeftButton:
            self.parent().size = self.sizes[1]
            self._drag = None
        else:
            self.abort()


class MemSizeWidget(QtWidgets.QLineEdit):

    value = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._validator = QtGui.QDoubleValidator(self)
        self._validator.setRange(_SZ_MIN / _GB_FACTOR, 1, 3)
        self.setValidator(self._validator)
        self.editingFinished.connect(self._on_finished)

    def max_set(self, value):
        value = float(value)
        self._validator.setTop(value)

    @QtCore.Slot()
    def _on_finished(self):
        value = float(self.text()) * _GB_FACTOR
        self.value.emit(value)


@register
@styled_widget(N_('Memory'))
class MemoryWidget(QtWidgets.QWidget):
    CAPABILITIES = ['widget@']

    def __init__(self, parent=None):
        self._base = 0
        self._size = 0  # in bytes
        self._used = 0
        self._timer = None
        super().__init__(parent=parent)
        self.setObjectName('memory_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(6)

        self._memset = MemSet(self)
        self._layout.addWidget(self._memset)

        self._grid_widget = QtWidgets.QWidget(parent=self)
        self._grid_layout = QtWidgets.QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 10, 0, 10)
        self._layout.addWidget(self._grid_widget)

        vm = psutil.virtual_memory()
        self._mem_size_widget = MemSizeWidget(self._grid_widget)
        self._mem_size_widget.value.connect(self._on_mem_size_text)
        self._widgets = {
            'size_color': QtWidgets.QLabel(_COLOR_TEXT, self._grid_widget),
            'size_label': QtWidgets.QLabel(N_('Memory buffer size'), self._grid_widget),
            'size_value': self._mem_size_widget,
            'size_units': QtWidgets.QLabel('GB', self._grid_widget),
            'total_color': QtWidgets.QLabel(_COLOR_TEXT, self._grid_widget),
            'total_label': QtWidgets.QLabel(N_('Total RAM size'), self._grid_widget),
            'total_value': QtWidgets.QLabel(_format(vm.total), self._grid_widget),
            'total_units': QtWidgets.QLabel('GB', self._grid_widget),
            'available_color': QtWidgets.QLabel(_COLOR_TEXT, self._grid_widget),
            'available_label': QtWidgets.QLabel(N_('Available RAM size'), self._grid_widget),
            'available_value': QtWidgets.QLabel(f'0', self._grid_widget),
            'available_units': QtWidgets.QLabel('GB', self._grid_widget),
            'used_color': QtWidgets.QLabel(_COLOR_TEXT, self._grid_widget),
            'used_label': QtWidgets.QLabel(N_('Used RAM size'), self._grid_widget),
            'used_value': QtWidgets.QLabel(f'0', self._grid_widget),
            'used_units': QtWidgets.QLabel('GB', self._grid_widget),
            'duration_color': QtWidgets.QLabel(_COLOR_TEXT, self._grid_widget),
            'duration_label': QtWidgets.QLabel(N_('Duration'), self._grid_widget),
            'duration_value': QtWidgets.QLabel('', self._grid_widget),
            'duration_units': QtWidgets.QLabel('', self._grid_widget),
        }

        for row, s in enumerate(['size', 'available', 'used', 'total', 'duration']):
            color_widget = self._widgets[f'{s}_color']
            color_widget.setObjectName(f'{s}_color')
            self._grid_layout.addWidget(color_widget, row, 0)
            self._grid_layout.addWidget(self._widgets[f'{s}_label'], row, 1)
            self._grid_layout.addWidget(self._widgets[f'{s}_value'], row, 2)
            self._grid_layout.addWidget(self._widgets[f'{s}_units'], row, 3)

        self._clear = QtWidgets.QPushButton(N_('Clear'), self)
        self._clear.pressed.connect(self._on_clear)
        self._layout.addWidget(self._clear)

        self._clear_on_play = QtWidgets.QPushButton(N_('Clear on play'), self)
        self._clear_on_play.clicked.connect(self._on_clear_on_play_clicked)
        self._clear_on_play.setCheckable(True)
        self._layout.addWidget(self._clear_on_play)

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

    def _update(self, size=None):
        if size is None:
            size = self._size
        vm = psutil.virtual_memory()
        my_mem = psutil.Process(os.getpid()).memory_info().rss

        used = vm.used - my_mem
        s = _format(used)
        self._widgets['used_value'].setText(s)

        available = vm.total - (self._base + size + used)
        self._mem_size_widget.max_set(available / _GB_FACTOR)
        s = _format(available)
        self._widgets['available_value'].setText(s)
        self._memset.update(self._base, available, used)

    def on_pubsub_register(self):
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(100)

    def on_pubsub_unregister(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _on_timer(self):
        if self._base == 0:
            mem = _mem_proc()
            sz = self.pubsub.query(_TOPIC_SIZE)
            if mem > sz:
                self._base = mem - sz
            else:
                self._base = mem
            self.pubsub.subscribe(_TOPIC_CLEAR_ON_PLAY, self._on_clear_on_play_publish, ['pub', 'retain'])
            self.pubsub.subscribe(_TOPIC_SIZE, self._on_size, ['pub', 'retain'])
            self.pubsub.subscribe(_TOPIC_DURATION, self._on_duration, ['pub', 'retain'])
            meta = self.pubsub.metadata(_TOPIC_CLEAR_ON_PLAY)
            if meta is not None:
                self._clear_on_play.setToolTip(tooltip_format(meta.brief, meta.detail))

            self._timer.start(1000)
        if not self._memset.is_active:
            self._update()

    def _on_clear(self):
        self.pubsub.publish(f'{_TOPIC}/actions/!clear', None)

    def _on_clear_on_play_clicked(self, value):
        self.pubsub.publish(_TOPIC_CLEAR_ON_PLAY, bool(value))

    def _on_clear_on_play_publish(self, value):
        self._clear_on_play.setChecked(bool(value))

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, value):
        self.pubsub.publish(_TOPIC_SIZE, int(value))

    def _on_size(self, value):
        self._size = int(value)
        s = _format(self._size)
        self._widgets['size_value'].setText(s)
        self._memset.update_size(value)
        self._update(value)

    @QtCore.Slot(str)
    def _on_mem_size_text(self, size):
        self.size = size
        self._on_size(size)

    def _on_duration(self, value):
        dt = 0.0 if value is None else float(value)
        time_str, units_str = elapsed_time_formatter(dt, fmt='standard', precision=3)
        self._widgets[f'duration_value'].setText(time_str)
        self._widgets[f'duration_units'].setText(units_str)
