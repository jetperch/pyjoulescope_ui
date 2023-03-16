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


from PySide6 import QtCore, QtWidgets
import logging
from joulescope_ui import N_, register
from joulescope_ui.styles import styled_widget


_ANIMATION_DURATION_MS = 500


@register
@styled_widget(N_('flyout'))
class FlyoutWidget(QtWidgets.QWidget):

    def __init__(self, parent, sidebar):
        self._sidebar = sidebar
        super().__init__(parent)
        self._widgets = []
        self._log = logging.getLogger(__name__)
        self.setObjectName('flyout1')
        self.setGeometry(50, 0, 0, 100)  # unused, see on_sidebar_geometry() and sidebar setting "flyout_width"
        self._layout1 = QtWidgets.QVBoxLayout()
        self._layout1.setSpacing(0)
        self._layout1.setContentsMargins(3, 3, 3, 3)

        self._inner = QtWidgets.QWidget(self)
        self._inner.setObjectName('flyout2')
        self._layout2 = QtWidgets.QVBoxLayout()
        self._layout2.setSpacing(0)
        self._layout2.setContentsMargins(9, 9, 9, 9)

        self._stacked_widget = QtWidgets.QWidget(self)
        self._stacked_widget.setObjectName('flyout_stack')
        self._stacked_layout = QtWidgets.QStackedLayout()
        self._stacked_layout.setSpacing(0)
        self._stacked_layout.setContentsMargins(0, 0, 0, 0)
        self._stacked_widget.setLayout(self._stacked_layout)

        self._layout2.addWidget(self._stacked_widget)
        self._inner.setLayout(self._layout2)
        self._layout1.addWidget(self._inner)
        self.setLayout(self._layout1)

        self._visible = -1
        self.show()
        self.animations = []

    def addWidget(self, widget):
        self._stacked_layout.addWidget(widget)
        widget.setParent(self._stacked_widget)
        idx = len(self._widgets)
        self._widgets.append(widget)
        return idx

    def animate(self, show):
        for a in self.animations:
            a.stop()
        self.animations.clear()
        if 0 <= show < len(self._widgets):
            self._stacked_layout.setCurrentIndex(show)
        x_start = self.width()
        x_end = self._sidebar.flyout_width if show >= 0 else 0
        self._log.info(f'animate {show}: {x_start} -> {x_end}')
        for p in [b'minimumWidth', b'maximumWidth']:
            a = QtCore.QPropertyAnimation(self, p)
            a.setDuration(_ANIMATION_DURATION_MS)
            a.setStartValue(x_start)
            a.setEndValue(x_end)
            a.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
            a.start()
            self.animations.append(a)
        self._visible = show

    def on_cmd_show(self, value):
        """Show the widget by index.

        :param value: The widget index or -1 to hide.
        """
        if value == -1:
            if self._visible < 0:
                return  # duplicate hide
        elif value < len(self._widgets):
            if value == self._visible:
                value = -1  # close on duplicate request
            else:
                self.raise_()
        else:
            raise ValueError(f'Unsupported value {value}')
        self.animate(value)
        return value

    def on_sidebar_geometry(self, r):
        width = self.width()
        # g = self.geometry()
        self.setGeometry(r.right(), r.y(), width, r.height())
        # self._log.info(f'on_sidebar_geometry {r}: {g} -> {self.geometry()}')
        self.repaint()
