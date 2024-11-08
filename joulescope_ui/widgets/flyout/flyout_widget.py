# Copyright 2019-2023 Jetperch LLC
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
import logging
from joulescope_ui import N_, register
from joulescope_ui.styles import styled_widget


_ANIMATION_DURATION_MS = 500


@register
@styled_widget(N_('flyout'))
class FlyoutWidget(QtWidgets.QScrollArea):

    width_changed = QtCore.Signal(int)

    def __init__(self, parent, sidebar):
        self._sidebar = sidebar
        super().__init__(parent)
        self._log = logging.getLogger(__name__)
        self.setObjectName('flyout1')
        self.setGeometry(50, 0, 0, 100)  # unused, see on_sidebar_geometry() and sidebar setting "flyout_width"
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._resize_active = None
        self.animations = []
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_HOR = QtGui.QCursor(QtGui.Qt.SizeHorCursor)
        self.setMouseTracking(True)

    def flyout_widget_set(self, widget, width=0):
        for a in self.animations:
            a.stop()
        self.animations.clear()
        if widget is not None:
            w = self.takeWidget()
            if w is not None:
                w.hide()
                w.setMouseTracking(False)
            self.setWidget(widget)
            widget.show()
            widget.setMouseTracking(True)

        x_start = self.width()
        x_end = width
        self._log.info(f'animate: {x_start} -> {x_end}')
        for p in [b'minimumWidth', b'maximumWidth']:
            a = QtCore.QPropertyAnimation(self, p)
            a.setDuration(_ANIMATION_DURATION_MS)
            a.setStartValue(x_start)
            a.setEndValue(x_end)
            a.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
            a.finished.connect(self._on_animation_finished)
            a.start()
            self.animations.append(a)

    @QtCore.Slot()
    def _on_animation_finished(self):
        if self.width() == 0:
            w = self.takeWidget()
            if w is not None:
                w.hide()
        for a in self.animations:
            a.stop()
        self.animations.clear()

    def on_sidebar_geometry(self, r):
        width = self.width()
        self.setGeometry(r.right() + 3, r.y(), width, r.height())
        self.update()

    def leaveEvent(self, event: QtCore.QEvent):
        if self.width() == 0:
            return
        pos = self.mapFromGlobal(QtGui.QCursor.pos())
        if (pos.x() + 1) >= self.width():
            if len(self.animations) == 0 or self.animations[-1].endValue() != 0:
                self._sidebar.on_cmd_show(None)
        return super().leaveEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self.width() == 0:
            return
        x = event.position().x()
        if self._resize_active is not None:
            w = max(100, x - self._resize_active)
            self.setMinimumWidth(w)
            self.setMaximumWidth(w)
            self.update()
        elif x >= (self.width() - 5):
            self.setCursor(self._CURSOR_SIZE_HOR)
        else:
            self.setCursor(self._CURSOR_ARROW)
        event.accept()

    def mousePressEvent(self, event):
        if self.width() == 0:
            return
        x = event.position().x()
        if x >= (self.width() - 5):
            self._resize_active = x - self.width()
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resize_active is not None:
            self.width_changed.emit(self.width())
            self._resize_active = None
