
from PySide2 import QtGui, QtCore, QtWidgets
from .marker import Marker
from .signal import Signal
from .scrollbar import ScrollBar
from .xaxis import XAxis
import pyqtgraph as pg


class Oscilloscope(QtWidgets.QWidget):
    """Oscilloscope-style waveform view for multiple signals.

    :param parent: The parent :class:`QWidget`.
    """

    on_xChangeSignal = QtCore.Signal(str, object)
    """Indicate that an x-axis range change was requested.

    :param command: The command string.
    :param kwargs: The keyword argument dict for the command.

    List of command, kwargs:
    * ['resize', {pixels: }]
    * ['span_absolute', {range: [start, stop]}]
    * ['span_pan', {delta: }]
    * ['span_relative', {pivot: , gain: }]
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

        self.marker = Marker(x_axis=self._x_axis, shape='none')
        self.win.sceneObj.addItem(self.marker)

        for p in self._signals.values():
            p.vb.sigResized.connect(self.marker.linkedViewChanged)
            p.vb.sigXRangeChanged.connect(self.marker.linkedViewChanged)
        self.marker.show()
        self._proxy = pg.SignalProxy(self.win.scene().sigMouseMoved, rateLimit=60, slot=self._mouseMoveEvent)

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

    def _mouseMoveEvent(self, ev):
        """Handle mouse movements for every mouse movement within the widget"""
        pos = ev[0]
        b1 = self._x_axis.geometry()
        if pos.y() < b1.top():
            return
        p = self._x_axis.linkedView().mapSceneToView(pos)
        x = p.x()
        x_min, x_max = self._x_axis.range
        if x < x_min:
            x = x_min
        elif x > x_max:
            x = x_max
        self.marker.set_pos(x)

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

        # Linking to last axis makes grid draw correctly
        self._vb_relink()
        list(self._signals.values())[-1].vb.setXRange(28.0, 30.0, padding=0)
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
        # marker.update()

    def data_clear(self):
        pass

    def x_state_get(self):
        """Get the x-axis state.

        :return: (length: int in pixels, (x_min: float, x_max: float))
        """
        length = self.win.ci.layout.itemAt(0, 1).geometry().width()
        length = int(length)
        return length, tuple(self._x_limits)

    @QtCore.Slot(float, float)
    def on_scrollbarRegionChange(self, x_min, x_max):
        row_count = self.win.ci.layout.rowCount()
        if row_count > 3:
            vb = self.win.ci.layout.itemAt(self.win.ci.layout.rowCount() - 1, 1)
            vb.setXRange(x_min, x_max, padding=0)
        self.on_xChangeSignal.emit('span_absolute', {'range': [x_min, x_max]})

    def resizeEvent(self, ev):
        vb = self.win.ci.layout.itemAt(0, 1)
        width = vb.geometry().width()
        width = int(width)
        self.on_xChangeSignal.emit('resize', {'pixels': width})
