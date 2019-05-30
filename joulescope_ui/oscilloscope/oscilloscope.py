# Copyright 2019 Jetperch LLC
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

from PySide2 import QtGui, QtCore, QtWidgets
from .signal import Signal
from .scrollbar import ScrollBar
from .xaxis import XAxis
import pyqtgraph as pg
import logging


log = logging.getLogger(__name__)


class Oscilloscope(QtWidgets.QWidget):
    """Oscilloscope-style waveform view for multiple signals.

    :param parent: The parent :class:`QWidget`.
    """

    on_xChangeSignal = QtCore.Signal(float, float, int)
    """Indicate that an x-axis range change was requested.

    :param x_min: The minimum x_axis value to display in the range.
    :param x_max: The maximum x_axis value to display in the range.
    :param x_count: The desired number of samples in the range.
    """

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self._x_limits = [0.0, 30.0]

        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.win = pg.GraphicsLayoutWidget(parent=self, show=True, title="Oscilloscope layout")
        self.win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.layout.addWidget(self.win)

        self._signals = {}

        self.win.addLabel('Time (seconds)', row=0, col=1)

        self._scrollbar = ScrollBar()
        self._scrollbar.regionChange.connect(self.on_scrollbarRegionChange)
        self.win.addItem(self._scrollbar, row=1, col=1)

        self._x_axis = XAxis()
        self.win.addItem(self._x_axis, row=2, col=1)
        self._x_axis.setGrid(128)

        self.win.ci.layout.setRowStretchFactor(0, 1)
        self.win.ci.layout.setRowStretchFactor(1, 1)
        self.win.ci.layout.setRowStretchFactor(2, 1)
        self.win.ci.layout.setColumnStretchFactor(0, 1)
        self.win.ci.layout.setColumnStretchFactor(1, 1000)

        self.win.ci.layout.setColumnAlignment(0, QtCore.Qt.AlignRight)
        self.win.ci.layout.setColumnAlignment(1, QtCore.Qt.AlignLeft)
        self.win.ci.layout.setColumnAlignment(2, QtCore.Qt.AlignLeft)

        self.win.ci.layout.setColumnStretchFactor(2, -1)

    def set_display_mode(self, mode):
        """Configure the display mode.

        :param mode: The oscilloscope display mode which is one of:
            * 'realtime': Display realtime data, and do not allow x-axis time scrolling
              away from present time.
            * 'browse': Display stored data, either from a file or a buffer,
              with a fixed x-axis range.

        Use :meth:`set_xview` and :meth:`set_xlimits` to configure the current
        view and the total allowed range.
        """
        self._scrollbar.set_display_mode(mode)

    def set_sampling_frequency(self, freq):
        """Set the sampling frequency.

        :param freq: The sampling frequency in Hz.

        This value is used to request appropriate x-axis ranges.
        """
        self._scrollbar.set_sampling_frequency(freq)

    def set_xview(self, x_min, x_max):
        self._scrollbar.set_xview(x_min, x_max)

    def set_xlimits(self, x_min, x_max):
        self._x_limits = [x_min, x_max]
        self._scrollbar.set_xlimits(x_min, x_max)
        for signal in self._signals.values():
            signal.set_xlimits(x_min, x_max)

    def signal_add(self, name, units=None, y_limit=None):
        s = Signal(name=name, units=units, y_limit=y_limit)
        s.addToLayout(self.win, row=self.win.ci.layout.rowCount())
        self._signals[name] = s
        self._vb_relink()  # Linking to last axis makes grid draw correctly
        return s

    def _vb_relink(self):
        vb = self.win.ci.layout.itemAt(self.win.ci.layout.rowCount() - 1, 1)
        self._x_axis.linkToView(vb)
        for p in self._signals.values():
            if p.vb == vb:
                p.vb.setXLink(None)
            else:
                p.vb.setXLink(vb)

    def values_column_hide(self):
        for idx in range(self.win.ci.layout.rowCount()):
            item = self.win.ci.layout.itemAt(idx, 2)
            if item is not None:
                item.hide()
                item.setMaximumWidth(0)

    def values_column_show(self):
        for idx in range(self.win.ci.layout.rowCount()):
            item = self.win.ci.layout.itemAt(idx, 2)
            if item is not None:
                item.show()
                item.setMaximumWidth(16777215)

    def data_update(self, x, data):
        for name, value in data.items():
            s = self._signals.get(name)
            if s is not None:
                self._signals[name].update(x, value)

    def data_clear(self):
        pass

    def x_state_get(self):
        """Get the x-axis state.

        :return: (length: int in pixels, (x_min: float, x_max: float))
        """
        length = self.win.ci.layout.itemAt(0, 1).geometry().width()
        length = int(length)
        return length, tuple(self._x_limits)

    @QtCore.Slot(float, float, float)
    def on_scrollbarRegionChange(self, x_min, x_max, x_count):
        row_count = self.win.ci.layout.rowCount()
        if x_min > x_max:
            x_min = x_max
        if row_count > 3:
            log.info('on_scrollbarRegionChange(%s, %s, %s)', x_min, x_max, x_count)
            vb = self.win.ci.layout.itemAt(self.win.ci.layout.rowCount() - 1, 1)
            vb.setXRange(x_min, x_max, padding=0)
        else:
            log.info('on_scrollbarRegionChange(%s, %s, %s) with no ViewBox', x_min, x_max, x_count)
        self.on_xChangeSignal.emit(x_min, x_max, x_count)
