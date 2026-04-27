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
# Width of the right-edge gutter that is reserved as the resize hot-zone.
# It is allocated by laying the inner QScrollArea inside FlyoutWidget at
# (0, 0, width - _RESIZE_GUTTER_PX, height); the rightmost _RESIZE_GUTTER_PX
# pixels are pure FlyoutWidget territory, so the inner scrollbar cannot
# steal mouse events there.
_RESIZE_GUTTER_PX = 6


@register
@styled_widget(N_('flyout'))
class FlyoutWidget(QtWidgets.QWidget):

    width_changed = QtCore.Signal(int)

    def __init__(self, parent, sidebar):
        self._sidebar = sidebar
        super().__init__(parent)
        self._log = logging.getLogger(__name__)
        self.setObjectName('flyout1')
        self.setGeometry(50, 0, 0, 100)  # unused, see on_sidebar_geometry() and sidebar setting "flyout_width"

        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        self._resize_active = None
        self._content_min_width = 0
        self.animations = []
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_HOR = QtGui.QCursor(QtGui.Qt.SizeHorCursor)
        self.setMouseTracking(True)
        self._scroll.verticalScrollBar().rangeChanged.connect(self._on_vbar_range_changed)

    def widget(self):
        """Return the active content widget, or None.  Mirrors QScrollArea.widget()."""
        return self._scroll.widget()

    def _compute_content_min_width(self, widget) -> int:
        if widget is None:
            return 0
        widget.ensurePolished()
        widget.adjustSize()
        scrollbar_w = self._scroll.verticalScrollBar().sizeHint().width()
        return widget.minimumSizeHint().width() + scrollbar_w + _RESIZE_GUTTER_PX

    @QtCore.Slot(int, int)
    def _on_vbar_range_changed(self, vmin: int, vmax: int):
        # When content reflow makes the vertical scrollbar active and the
        # flyout is currently below the content floor, grow it so the
        # scrollbar + gutter fit without consuming the resize hot-zone.
        if self.width() == 0 or self._content_min_width == 0:
            return
        if self._resize_active is not None or len(self.animations) > 0:
            return
        if vmax > vmin and self.width() < self._content_min_width:
            self.setMinimumWidth(self._content_min_width)
            self.setMaximumWidth(self._content_min_width)

    def flyout_widget_set(self, widget, width=0):
        for a in self.animations:
            a.stop()
        self.animations.clear()
        if widget is not None:
            w = self._scroll.takeWidget()
            if w is not None:
                w.hide()
                w.setMouseTracking(False)
            self._scroll.setWidget(widget)
            widget.show()
            widget.setMouseTracking(True)
            self._content_min_width = self._compute_content_min_width(widget)
        else:
            self._content_min_width = 0

        x_start = self.width()
        x_end = width if width == 0 else max(width, self._content_min_width)
        self._log.info(f'animate: {x_start} -> {x_end} (content_min={self._content_min_width})')
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
            w = self._scroll.takeWidget()
            if w is not None:
                w.hide()
        for a in self.animations:
            a.stop()
        self.animations.clear()

    def on_sidebar_geometry(self, r):
        width = self.width()
        self.setGeometry(r.right() + 3, r.y(), width, r.height())
        self.update()

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        inner_w = max(0, self.width() - _RESIZE_GUTTER_PX)
        self._scroll.setGeometry(0, 0, inner_w, self.height())

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
            w = max(self._content_min_width, x - self._resize_active)
            self.setMinimumWidth(w)
            self.setMaximumWidth(w)
            self.update()
        elif x >= (self.width() - _RESIZE_GUTTER_PX):
            self.setCursor(self._CURSOR_SIZE_HOR)
        else:
            self.setCursor(self._CURSOR_ARROW)
        event.accept()

    def mousePressEvent(self, event):
        if self.width() == 0:
            return
        x = event.position().x()
        if x >= (self.width() - _RESIZE_GUTTER_PX):
            self._resize_active = x - self.width()
            self.setCursor(self._CURSOR_SIZE_HOR)
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resize_active is not None:
            self.width_changed.emit(self.width())
            self._resize_active = None
        self.setCursor(self._CURSOR_ARROW)
