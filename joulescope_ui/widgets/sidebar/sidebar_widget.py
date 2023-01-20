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
from joulescope_ui import N_, register, tooltip_format, pubsub_singleton
from joulescope_ui.styles import styled_widget
from .device_control_widget import DeviceControlWidget
from .memory_widget import MemoryWidget
from .widget_settings_widget import WidgetSettingsWidget


_DEVICE_TOOLTIP = tooltip_format(
    N_('Device control'),
    N_("""\
    Click to show the device control widget which displays
    the connected devices and their settings.  Use this
    widget to open and close devices and configure their
    operation.
    """))

_WIDGETS_TOOLTIP = tooltip_format(
    N_('Widget settings'),
    N_("""\
    Click to show the widget settings which allows you
    to change the default settings for each widget type.
    Future widgets you create will use the new defaults.
    """))

_MEMORY_TOOLTIP = tooltip_format(
    N_('Memory buffer settings'),
    N_("""\
    Streaming signal sample data is stored in your host
    computer's RAM.  Click this button to show the
    memory management widget which allows you to 
    configure the memory used by this Joulescope UI instance.
    """))

_HELP_TOOLTIP = tooltip_format(
    N_('Get help'),
    N_("""\
    Click to display help options.
    """))

_SETTINGS_TOOLTIP = tooltip_format(
    N_('Additional settings and actions'),
    N_("""\
    Click to display additional settings and actions.
    """))


class Flyout(QtWidgets.QWidget):

    def __init__(self, parent, sidebar):
        self._sidebar = sidebar
        super().__init__(parent)
        self._widgets = []
        self._log = logging.getLogger(__name__)
        self.setObjectName('side_bar_flyout')
        self.setGeometry(50, 0, 0, 100)
        # self.setStyleSheet('QWidget {\n	background: #D0000000;\n}')
        self._layout = QtWidgets.QStackedLayout()
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)
        self._visible = -1
        self.show()
        self.animations = []

    def addWidget(self, widget):
        self._layout.addWidget(widget)
        idx = len(self._widgets)
        self._widgets.append(widget)
        return idx

    def animate(self, show):
        for a in self.animations:
            a.stop()
        self.animations.clear()
        if 0 <= show < len(self._widgets):
            self._layout.setCurrentIndex(show)
        x_start = self.width()
        x_end = self._sidebar.flyout_width if show >= 0 else 0
        self._log.info(f'animate {show}: {x_start} -> {x_end}')
        for p in [b'minimumWidth', b'maximumWidth']:
            a = QtCore.QPropertyAnimation(self, p)
            a.setDuration(500)
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

    def on_sidebar_geometry(self, r):
        width = self.width()
        g = self.geometry()
        self.setGeometry(r.right(), r.y(), width, r.height())
        self._log.info(f'on_sidebar_geometry {r}: {g} -> {self.geometry()}')
        self.repaint()


@register
@styled_widget(N_('sidebar'))
class SideBar(QtWidgets.QWidget):

    # Note: does NOT implement widget CAPABILITY, since not instantiable by user or available as a dock widget.

    SETTINGS = {
        'flyout_width': {
            'dtype': 'int',
            'brief': N_('The flyout width in pixels.'),
            'default': 200,
        },
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('side_bar_icons')
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)
        self._buttons = {}
        self._buttons_blink = []
        self._buttons_flyout = []

        self._flyout = Flyout(parent, self)

        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setSpacing(6)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self.setLayout(self._layout)

        self._add_blink_button('target_power', 'target_power')
        self._add_blink_button('signal_play', 'signal_stream_enable')
        self._add_blink_button('signal_record', 'signal_stream_record')
        self._add_blink_button('statistics_play', 'statistics_stream_enable')
        self._add_blink_button('statistics_record', 'statistics_stream_record')
        self._add_flyout_button('device', _DEVICE_TOOLTIP, DeviceControlWidget(self))
        self._add_flyout_button('memory', _MEMORY_TOOLTIP, MemoryWidget(self))
        self._add_button('widgets', _WIDGETS_TOOLTIP)
        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)
        self._add_button('help', _HELP_TOOLTIP)
        self._add_button('settings', _SETTINGS_TOOLTIP)

        self.mousePressEvent = self._on_mousePressEvent
        pubsub_singleton.subscribe('registry/ui/events/blink_slow', self._on_blink, ['pub', 'retain'])

    def _on_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.on_cmd_show(-1)
            event.accept()

    def _add_blink_button(self, name, app_setting):
        topic = f'registry/app/settings/{app_setting}'
        meta = pubsub_singleton.metadata(topic)
        tooltip = tooltip_format(meta.brief, meta.detail)
        button = self._add_button(name, tooltip)
        button.setProperty('blink', False)
        button.setCheckable(True)
        self._buttons_blink.append(button)

        def update_from_pubsub(value):
            block_state = button.blockSignals(True)
            button.setChecked(bool(value))
            button.blockSignals(block_state)

        pubsub_singleton.subscribe(topic, update_from_pubsub, ['pub', 'retain'])
        button.toggled.connect(lambda checked: pubsub_singleton.publish(topic, bool(checked)))
        return button

    def _add_flyout_button(self, name, tooltip, widget):
        button = self._add_button(name, tooltip)
        idx = self._flyout.addWidget(widget)
        button.clicked.connect(lambda: self.on_cmd_show(idx))

    def _add_button(self, name, tooltip):
        button = QtWidgets.QPushButton(self)
        button.setObjectName(name)
        button.setFlat(True)
        button.setFixedSize(32, 32)
        button.setToolTip(tooltip)
        self._buttons[name] = button
        self._layout.addWidget(button)
        return button

    def _on_blink(self, value):
        for b in self._buttons_blink:
            b.setProperty('blink', value)
            b.style().unpolish(b)
            b.style().polish(b)

    def on_cmd_show(self, value):
        self._flyout.on_cmd_show(value)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._flyout.on_sidebar_geometry(self.geometry())
