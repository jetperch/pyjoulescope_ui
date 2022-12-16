# -*- coding: utf-8 -*-
# Copyright 2019-2022 Jetperch LLC
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



PLAY_TOOLTIP = """\
<html><head/><body><p>
<p>Click to stream data from the selected Joulescope.</p>
Click again to stop data streaming.
</p></body></html>
"""

RECORD_TOOLTIP = """\
<html><head/><body>
<p>Click to start recording streaming Joulescope data to a file.</p>

<p>Click again to stop the recording. Only new data is recorded.</p>

<p>
By default, your Joulescope streams and records 2 million
samples per second which is 8 MB/s.
You can downsample for smaller file sizes when you do not need the full
bandwidth.  See File → Preferences → Device → setting → sampling_frequency.
</p>
</body></html>
"""

STATISTICS_TOOLTIP = """\
<html><head/><body>
<p>Click to start recording statistics Joulescope data to a CSV file.</p>

<p>Click again to stop the recording. Only new data is recorded.</p>

<p>
By default, your Joulescope records statistics 2 times per second.
You can adjust this statistics rate.
See File → Preferences → Device → setting → reduction_frequency.
</p>
</body></html>
"""


class Flyout(QtWidgets.QWidget):

    def __init__(self, parent):
        super(Flyout, self).__init__(parent)
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
        print(f'animate {show}: {x_start} -> {x_end}')
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
        print(f'{r}: {g} -> {self.geometry()}')
        self.repaint()


class SideBar(QtWidgets.QWidget):

    def __init__(self, parent):
        super(SideBar, self).__init__(parent)
        self.setObjectName('side_bar_icons')
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)

        # Create the flyout widget
        self._flyout = Flyout(parent)

        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setSpacing(6)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self.setLayout(self._layout)

        self._playButton = QtWidgets.QPushButton(self)
        self._playButton.setObjectName('play')
        self._playButton.setProperty('blink', False)
        self._playButton.setCheckable(True)
        self._playButton.setFlat(True)
        self._playButton.setProperty('blink', False)
        self._playButton.setFixedSize(24, 24)
        self._playButton.setToolTip(PLAY_TOOLTIP)
        self._layout.addWidget(self._playButton)

        self._recordButton = QtWidgets.QPushButton(self)
        self._recordButton.setObjectName('record')
        self._recordButton.setEnabled(True)
        self._recordButton.setProperty('blink', False)
        self._recordButton.setCheckable(True)
        self._recordButton.setFlat(True)
        self._recordButton.setFixedSize(24, 24)
        self._recordButton.setToolTip(RECORD_TOOLTIP)
        self._layout.addWidget(self._recordButton)

        self._recordStatisticsButton = QtWidgets.QPushButton(self)
        self._recordStatisticsButton.setObjectName('record_statistics')
        self._recordStatisticsButton.setEnabled(True)
        self._recordStatisticsButton.setProperty('blink', False)
        self._recordStatisticsButton.setCheckable(True)
        self._recordStatisticsButton.setFlat(True)
        self._recordStatisticsButton.setFixedSize(24, 24)
        self._recordStatisticsButton.setToolTip(STATISTICS_TOOLTIP)
        self._layout.addWidget(self._recordStatisticsButton)

        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._blink = True
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(1000)

        # todo implement fly-out widget

    def _on_timer(self):
        self._blink = not self._blink
        for b in [self._playButton, self._recordButton, self._recordStatisticsButton]:
            b.setProperty('blink', self._blink)
            b.style().unpolish(b)
            b.style().polish(b)

    def on_cmd_show(self, value):
        self._flyout.on_cmd_show(value)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._flyout.on_sidebar_geometry(self.geometry())
