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
from joulescope_ui import N_, register, tooltip_format
from joulescope_ui.styles import styled_widget


_SIGNAL_PLAY_TOOLTIP = tooltip_format(
    N_('Signal sample streaming'),
    N_("""\
    Enable to stream sample data from all open sample sources
    and configure all sample widgets for acquisition mode.
    
    Disable to stop sample streaming and configure
    all sample widgets for buffer mode.  
    """))

_SIGNAL_RECORD_TOOLTIP = tooltip_format(
    N_('Signal sample recording'),
    N_("""\
    Click once to enable and start recording streaming signal 
    sample data to a JLS file.
    
    Click again to stop the recording.
    
    The recording will capture data from all enabled 
    sample sources and signals at their configured sample rates.
    To reduce the file size, you can disable sources, 
    disable signals, and/or reduce the sample rates.
    """))

_STATISTICS_PLAY_TOOLTIP = tooltip_format(
    N_('Statistics display'),
    N_("""\
    Enable to display live streaming statistics.
    
    Disable to hold the existing values.  New statistics data
    is processed, but widgets displaying statistics information
    do not update.
    """))

_STATISTICS_RECORD_TOOLTIP = tooltip_format(
    N_('Statistics recording'),
    N_("""\
    Click once to enable and start recording streaming statistics
    data to CSV files.

    Click again to stop the recording.
    
    By default, Joulescopes provide statistics data at 2 Hz.
    Each device allows you to change this setting to the desired rate.
    """))

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

    def __init__(self, parent):
        super(Flyout, self).__init__(parent)
        self._log = logging.getLogger(__name__)
        self.setObjectName('side_bar_flyout')
        self.setGeometry(50, 0, 0, 100)
        self.setStyleSheet('QWidget {\n	background: #D0000000;\n}')
        self._layout = QtWidgets.QStackedLayout()
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._label = QtWidgets.QLabel()
        self._label.setWordWrap(True)
        self._label.setText('<html><body><p>Page 1</p><p>Lorem ipsum dolor sit amet, consectetuer adipiscing elit.</p></body></html>')
        self._layout.addWidget(self._label)
        self._visible = 0
        self.show()
        self.animations = []

    def animate(self, show):
        for a in self.animations:
            a.stop()
        self.animations.clear()
        x_start = self.width()
        x_end = 150 if show else 0
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
        if value == -1:
            value = 1 if self.isHidden() else 0
        if value == self._visible:
            return
        self.raise_()
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

    def __init__(self, parent):
        super(SideBar, self).__init__(parent)
        self.setObjectName('side_bar_icons')
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)
        self._buttons = {}
        self._buttons_blink = []

        # Create the flyout widget
        self._flyout = Flyout(parent)

        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setSpacing(6)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self.setLayout(self._layout)

        self._add_blink_button('signal_play', _SIGNAL_PLAY_TOOLTIP)
        self._add_blink_button('signal_record', _SIGNAL_RECORD_TOOLTIP)
        self._add_blink_button('statistics_play', _STATISTICS_PLAY_TOOLTIP)
        self._add_blink_button('statistics_record', _STATISTICS_RECORD_TOOLTIP)
        self._add_button('device', _DEVICE_TOOLTIP)
        self._add_button('widgets', _WIDGETS_TOOLTIP)
        self._add_button('memory', _MEMORY_TOOLTIP)
        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)
        self._add_button('help', _HELP_TOOLTIP)
        self._add_button('settings', _SETTINGS_TOOLTIP)

        self._blink = True
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(1000)

        # todo implement fly-out widget
        self.on_cmd_show(True)

    def _add_blink_button(self, name, tooltip):
        button = self._add_button(name, tooltip)
        button.setProperty('blink', False)
        button.setCheckable(True)
        self._buttons_blink.append(button)
        return button

    def _add_button(self, name, tooltip):
        button = QtWidgets.QPushButton(self)
        button.setObjectName(name)
        button.setFlat(True)
        button.setFixedSize(32, 32)
        button.setToolTip(tooltip)
        self._buttons[name] = button
        self._layout.addWidget(button)
        return button

    def _on_timer(self):
        self._blink = not self._blink
        for b in self._buttons_blink:
            b.setProperty('blink', self._blink)
            b.style().unpolish(b)
            b.style().polish(b)

    def on_cmd_show(self, value):
        self._flyout.on_cmd_show(value)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._flyout.on_sidebar_geometry(self.geometry())
