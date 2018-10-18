# Copyright 2018 Jetperch LLC
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

from .plot_widget import Ui_PlotDockWidget
from joulescope.stream_buffer import NAME_TO_COLUMN
from joulescope.units import unit_prefix, three_sig_figs
import weakref
import pyqtgraph as pg
from PySide2 import QtCore, QtWidgets
import numpy as np
import time
import logging
log = logging.getLogger(__name__)


NAME_TO_UNITS = {
    'current': 'A',
    'i': 'A',
    'i_raw': 'LSBs',
    'voltage': 'V',
    'v': 'V',
    'v_raw': 'LSBs',
}


class CustomViewBox(pg.ViewBox):

    def __init__(self, on_x_change):
        pg.ViewBox.__init__(self)
        self.on_x_change = on_x_change
        self.setMouseMode(self.RectMode)
        self.sigResized.connect(self.on_resize)
        self.setLimits(xMin=0, yMin=0, yMax=1.0)
        self._resize_enable_x = False
        self._resize_enable_y = False
        self._resize_highlight = None

    def signal_change(self, command, **kwargs):
        self.on_x_change.emit(command, kwargs)

    def wheelEvent(self, ev, axis=None):
        c = self.mapToView(ev.scenePos())
        x, y = c.x(), c.y()
        gain = 0.7 ** (ev.delta() / 120)
        log.info('wheelEvent(delta=%s, x=%.3f, y=%.1f) gain=>%s', ev.delta(), x, y, gain)
        if self._resize_enable_x:
            self.signal_change('span_relative', center=x, gain=gain)
        if self._resize_enable_y:
            _, (y1, y2) = self.viewRange()
            ys = (y2 - y1) * gain / 2
            self.setYRange(y - ys, y + ys)
        ev.accept()

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            (x1, x2), (y1, y2) = self.viewRange()
            if self._resize_enable_x:
                xc = (y1 + y2) / 2
                xs = (x2 - x1) / 2 * 2
                self.signal_change('span_absolute', range=[xc - xs, xc + xs])
            if self._resize_enable_y:
                yc = (y1 + y2) / 2
                ys = (y2 - y1) / 2 * 2
                self.setYRange(yc - ys, yc + ys)
        elif ev.button() == QtCore.Qt.LeftButton:
            pass
        elif ev.button() == QtCore.Qt.RightButton:
            pass
        ev.accept()

    def mouseDragEvent(self, ev):
        start_point = self.mapToView(ev.buttonDownPos())
        end_point = self.mapToView(ev.pos())

        if ev.button() == QtCore.Qt.LeftButton:
            if ev.isFinish():
                log.info('mouseDragEvent left finish: %s => %s', start_point, end_point)
                if self._resize_highlight is not None:
                    self.removeItem(self._resize_highlight)
                    self._resize_highlight = None
                if self._resize_enable_x:
                    x_range = sorted([start_point.x(), end_point.x()])
                    log.info('zoom x: %s', x_range)
                    self.signal_change('span_absolute', range=sorted([x_range[0], x_range[1]]))
                if self._resize_enable_y:
                    y_range = sorted([start_point.y(), end_point.y()])
                    log.info('zoom y: %s', y_range)
                    self.setYRange(*y_range)
            elif ev.isStart():
                log.info('mouseDragEvent left start: %s', start_point)
                if self._resize_enable_x and self._resize_enable_y:
                    self._resize_highlight = pg.RectROI(start_point, [0, 0], pen=(0, 9), parent=self)
                elif self._resize_enable_x:
                    self._resize_highlight = pg.LinearRegionItem(orientation=pg.LinearRegionItem.Vertical)
                    r = sorted([start_point.x(), end_point.x()])
                    self._resize_highlight.setRegion(r)
                elif self._resize_enable_y:
                    self._resize_highlight = pg.LinearRegionItem(orientation=pg.LinearRegionItem.Horizontal)
                    r = sorted([start_point.y(), end_point.y()])
                    self._resize_highlight.setRegion(r)
                else:
                    pass  # no resize enabled
                if self._resize_highlight is not None:
                    self.addItem(self._resize_highlight)
            else:
                if self._resize_enable_x and self._resize_enable_y:
                    self._resize_highlight.setSize(end_point - start_point)
                elif self._resize_enable_x:
                    r = sorted([start_point.x(), end_point.x()])
                    self._resize_highlight.setRegion(r)
                elif self._resize_enable_y:
                    r = sorted([start_point.y(), end_point.y()])
                    self._resize_highlight.setRegion(r)
                else:
                    pass  # no resize enabled
        if ev.button() == QtCore.Qt.RightButton:
            if ev.isFinish():
                log.info('mouseDragEvent right finish: %s => %s', start_point, end_point)
            elif ev.isStart():
                log.info('mouseDragEvent right start: %s', start_point)
            pass
        else:
            pass  # pg.ViewBox.mouseDragEvent(self, ev)
        ev.accept()

    def keyPressEvent(self, ev):
        log.info(ev.text())
        ev.accept()

    def x_length_pixels(self):
        view_range = self.viewRange()
        xrange, _ = view_range
        dx = xrange[1] - xrange[0]
        try:
            pixel_size = self.viewPixelSize()
        except np.linalg.linalg.LinAlgError:
            return  # get it next time
        x_count = int(np.round(abs(dx) / pixel_size[0]))
        return x_count

    def on_resize(self, *args, **kwargs):
        x_count = self.x_length_pixels()
        self.signal_change('resize', pixels=x_count)

    def resize_axis_enable(self, axis, enable):
        log.info('%s %s' % (axis, enable))
        if axis == 'x':
            self._resize_enable_x = bool(enable)
        elif axis == 'y':
            self._resize_enable_y = bool(enable)


def resize_button_to_minimum(button: QtWidgets.QPushButton):
    # https://stackoverflow.com/a/19502467/888653
    text = button.text()
    width = button.fontMetrics().boundingRect(text).width() + 7
    button.setMinimumWidth(width)
    button.setMaximumWidth(width)


class Oscilloscope(QtCore.QObject):
    on_xChangeSignal = QtCore.Signal(str, object)
    """List of command, kwargs:
    * ['resize', {pixels: }]
    * ['span_absolute', {range: [start, stop]}]
    * ['span_relative', {center: , gain: }]
    """

    def __init__(self, parent, field):
        QtCore.QObject.__init__(self)
        self._parent = weakref.ref(parent)
        self._field = field
        self._column = NAME_TO_COLUMN[field.lower()]
        self._units = NAME_TO_UNITS[field.lower()]
        self.refresh = 0.05
        self.last_refresh = time.time()
        self.widget = QtWidgets.QDockWidget(self._field, parent)
        #self.title = QtWidgets.QWidget(self.widget)
        #self.layout = QtWidgets.QVBoxLayout(self.title)
        #self.button1 = QtWidgets.QPushButton(self.title)
        #self.button1.setObjectName('hi')
        #self.layout.addWidget(self.button1)
        #self.widget.setTitleBarWidget(self.title)

        self.ui = Ui_PlotDockWidget()
        self.ui.setupUi(self.widget)
        self.widget.setWindowTitle(field)
        self.vb = CustomViewBox(self.on_xChangeSignal)
        self.plot = pg.PlotWidget(name=self._field, viewBox=self.vb)
        self.ui.mainLayout.addWidget(self.plot)
        resize_button_to_minimum(self.ui.selectXButton)
        self.ui.selectXButton.clicked.connect(lambda enable: self.vb.resize_axis_enable('x', enable))
        resize_button_to_minimum(self.ui.selectYButton)
        self.ui.selectYButton.clicked.connect(lambda enable: self.vb.resize_axis_enable('y', enable))

        self.plot.disableAutoRange()
        self.plot.hideButtons()
        self.plot.setXRange(0.0, 1.0)

        parent.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.widget)
        self._curve_min = self.plot.plot([], [], pen=(255, 64, 64)).curve
        self._curve_max = self.plot.plot([], [], pen=(255, 64, 64)).curve
        self._curve_mean = self.plot.plot([], [], pen=(255, 255, 64)).curve
        # https://stackoverflow.com/questions/28296049/pyqtgraph-plotting-time-series?rq=1
        # https://stackoverflow.com/questions/17103698/plotting-large-arrays-in-pyqtgraph

    def clear(self):
        self.update(None, None)

    def update(self, x, data):
        if x is not None and data is not None:
            z_mean = data[:, self._column, 0]
            z_valid = np.isfinite(z_mean)
            z_mean = z_mean[z_valid]
            xv = x[z_valid]

            if len(z_mean):
                z_var = data[z_valid, self._column, 1]
                z_min = data[z_valid, self._column, 2]
                z_max = data[z_valid, self._column, 3]
                self._curve_mean.updateData(xv, z_mean)

                v_mean = np.mean(z_mean)
                mean_delta = z_mean - v_mean
                # combine variances across the combined samples
                v_std = np.sqrt(np.sum(np.square(mean_delta, out=mean_delta) + z_var) / len(z_mean))
                if np.isfinite(z_min[0]):
                    self._curve_min.updateData(xv, z_min)
                    self._curve_max.updateData(xv, z_max)
                    v_min = np.min(z_min)
                    v_max = np.max(z_max)
                else:
                    self._curve_min.clear()
                    self._curve_max.clear()
                    v_min = np.min(z_mean)
                    v_max = np.max(z_mean)
                self.ui.meanValue.setText(three_sig_figs(v_mean, self._units))
                self.ui.stdValue.setText(three_sig_figs(v_std, self._units))
                self.ui.p2pValue.setText(three_sig_figs(v_max - v_min, self._units))
                self.ui.minValue.setText(three_sig_figs(v_min, self._units))
                self.ui.maxValue.setText(three_sig_figs(v_max, self._units))
                self.plot.setXRange(x[0], x[-1], padding=0.0)
                self.plot.update()
                return

        self._curve_min.clear()
        self._curve_max.clear()
        self._curve_mean.clear()
        self.ui.meanValue.setText('')
        self.ui.stdValue.setText('')
        self.ui.p2pValue.setText('')
        self.ui.minValue.setText('')
        self.ui.maxValue.setText('')
        self.plot.update()

    def y_limit_set(self, y_min, y_max, update=None):
        self.vb.setLimits(yMin=y_min, yMax=y_max)
        if update:
            self.plot.setYRange(y_min, y_max)

    def x_state_get(self):
        """Get the x-axis state.

        :return: (length: int in pixels, (x_min: float, x_max: float))
        """
        view_box = self.plot.getPlotItem().getViewBox()
        length = view_box.x_length_pixels()
        x_range, _ = view_box.viewRange()
        return length, x_range
