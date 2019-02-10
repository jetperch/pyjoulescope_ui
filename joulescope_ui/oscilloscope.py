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
from typing import List
import time
import logging
log = logging.getLogger(__name__)


MARKER_PEN = [100, 220, 0, 200]
CURVE_WIDTH = 1
AUTO_RANGE_FRACT = 0.45  # autorange when current range smaller than existing range by this fractional amount.


NAME_TO_UNITS = {
    'current': 'A',
    'i': 'A',
    'i_raw': 'LSBs',
    'voltage': 'V',
    'v': 'V',
    'v_raw': 'LSBs',
}


class CustomViewBox(pg.ViewBox):

    def __init__(self, on_x_change, on_marker):
        pg.ViewBox.__init__(self)
        self.on_x_change = on_x_change
        self._on_marker = on_marker
        self.setMouseMode(self.RectMode)
        self.sigResized.connect(self.on_resize)
        self.setLimits(xMin=0, yMin=0, yMax=1.0)
        self._resize_enable_x = False
        self._resize_enable_y = False
        self._resize_highlight = None
        self._last_point = None

        self.vline_pen = pg.mkPen(color=MARKER_PEN, width=1)
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=self.vline_pen)
        self.addItem(self.vline, ignoreBounds=True)
        self.left_button_mode = 'none'

    def signal_change(self, command, **kwargs):
        self.on_x_change.emit(command, kwargs)

    def wheelEvent(self, ev, axis=None):
        c = self.mapToView(ev.pos())
        x, y = c.x(), c.y()
        gain = 0.7 ** (ev.delta() / 120)
        log.info('wheelEvent(delta=%s, x=%.3f, y=%.1f) gain=>%s', ev.delta(), x, y, gain)
        if self._resize_enable_x:
            self.signal_change('span_relative', pivot=x, gain=gain)
        if self._resize_enable_y:
            _, (y1, y2) = self.viewRange()
            z1 = (1 - gain) * y + gain * y1
            z2 = z1 + (y2 - y1) * gain
            self.setYRange(z1, z2)
        ev.accept()

    def hoverEvent(self, ev):
        if ev.isExit():
            return
        p = ev.lastPos()
        p = self.mapToView(p)
        self._on_marker(p.x())

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            pass
        elif ev.button() == QtCore.Qt.LeftButton:
            pass
        elif ev.button() == QtCore.Qt.RightButton:
            pass
        ev.accept()

    def _zoom_drag(self, ev):
        start_point = self.mapToView(ev.buttonDownPos())
        end_point = self.mapToView(ev.pos())
        if ev.isFinish():
            log.info('zoom mouseDragEvent left finish: %s => %s', start_point, end_point)
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
            log.info('zoom mouseDragEvent left start: %s', start_point)
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

    def _pan_drag(self, ev):
        if ev.isStart():
            start_point = self.mapToView(ev.buttonDownPos())
            log.info('pan mouseDragEvent left start: %s', start_point)
            self._last_point = start_point
        else:
            if ev.isFinish():
                p = self.mapToView(ev.pos())
                delta = p - self._last_point
                self._last_point = p
                log.info('pan delta = %s', delta)
                # (x1, x2), (y1, y2) = self.viewRange()
                # y1 += delta.y()
                # y2 += delta.y()
                self.signal_change('span_pan', delta=-delta.x())
                log.info('pan mouseDragEvent left finish')

    def mouseDragEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            if self.left_button_mode == 'zoom':
                self._zoom_drag(ev)
            elif self.left_button_mode == 'pan':
                self._pan_drag(ev)
            elif self.left_button_mode == 'none':
                pass
            else:
                log.warning('Unsupported left_button_mode %s', self.left_button_mode)
        if ev.button() == QtCore.Qt.RightButton:
            self._zoom_drag(ev)
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


def resize_buttons_to_minimum(buttons: List[QtWidgets.QPushButton]):
    text_width = 0
    for button in buttons:
        sz = button.fontMetrics().boundingRect(button.text())
        text_width = max(sz.width(), text_width)
    # https://stackoverflow.com/questions/6639012/minimum-size-width-of-a-qpushbutton-that-is-created-from-code
    width = text_width + 10  # I hate this constant
    for button in buttons:
        button.setMinimumWidth(width)
        button.setMaximumWidth(width)


class Oscilloscope(QtCore.QObject):
    on_xChangeSignal = QtCore.Signal(str, object)
    on_markerSignal = QtCore.Signal(object)
    """List of command, kwargs:
    * ['resize', {pixels: }]
    * ['span_absolute', {range: [start, stop]}]
    * ['span_pan', {delta: }]
    * ['span_relative', {pivot: , gain: }]
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
        self.vb = CustomViewBox(self.on_xChangeSignal, self.on_markerSignal.emit)
        self.on_markerSignal.connect(self.on_marker)
        self.plot = pg.PlotWidget(name=self._field, viewBox=self.vb)
        self.ui.mainLayout.addWidget(self.plot)
        self.ui.zoomButton.clicked.connect(self.on_zoom_button)
        self.ui.zoomXButton.clicked.connect(self.on_zoom_x_button)
        self.ui.zoomYButton.clicked.connect(self.on_zoom_y_button)
        self.ui.zoomAutoYButton.clicked.connect(self.on_zoom_auto_y_button)
        self.ui.panButton.clicked.connect(self.on_pan_button)

        self.on_zoom_x_button(True)
        self.on_zoom_auto_y_button(True)
        self.on_pan_button(True)

        self._x = None
        self._y = None

        self.plot.disableAutoRange()
        self.plot.hideButtons()
        self.plot.setXRange(0.0, 1.0)

        parent.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.widget)
        self._pen_min_max = pg.mkPen(color=(255, 64, 64), width=CURVE_WIDTH)
        self._pen_mean = pg.mkPen(color=(255, 255, 64), width=CURVE_WIDTH)
        self._curve_min = self.plot.plot([], [], pen=self._pen_min_max).curve
        self._curve_max = self.plot.plot([], [], pen=self._pen_min_max).curve
        self._curve_mean = self.plot.plot([], [], pen=self._pen_mean).curve

        value_labels = [
            self.ui.meanValue,
            self.ui.stdValue,
            self.ui.p2pValue,
            self.ui.minValue,
            self.ui.maxValue
        ]
        # https://stackoverflow.com/a/19502467/888653
        width = self.ui.meanValue.fontMetrics().boundingRect("Z9.99 AA").width()
        for label in value_labels:
            label.setMinimumWidth(width)

        self.x_label = pg.TextItem(anchor=(0, 0))
        self.plot.addItem(self.x_label)

        # https://stackoverflow.com/questions/28296049/pyqtgraph-plotting-time-series?rq=1
        # https://stackoverflow.com/questions/17103698/plotting-large-arrays-in-pyqtgraph

    def setVisible(self, is_visible):
        self.widget.setVisible(is_visible)

    def clear(self):
        self.update(None, None)

    def on_zoom_button(self, enable):
        self.ui.zoomButton.setChecked(enable)
        if enable:
            self.on_pan_button(False)
            self.vb.left_button_mode = 'zoom'
        else:
            self.vb.left_button_mode = 'none'

    def on_zoom_x_button(self, enable):
        self.ui.zoomXButton.setChecked(enable)
        self.vb.resize_axis_enable('x', enable)

    def on_zoom_y_button(self, enable):
        self.ui.zoomYButton.setChecked(enable)
        if enable:
            self.ui.zoomAutoYButton.setChecked(False)
        self.vb.resize_axis_enable('y', enable)

    def on_zoom_auto_y_button(self, enable):
        self.ui.zoomAutoYButton.setChecked(enable)
        log.info('on_zoom_auto_y_button(%s)', enable)
        if enable:
            self.ui.zoomYButton.setChecked(False)
            self.vb.resize_axis_enable('y', False)
            self.on_xChangeSignal.emit('refresh', {})

    def on_pan_button(self, enable):
        self.ui.panButton.setChecked(enable)
        if enable:
            self.on_zoom_button(False)
            self.vb.left_button_mode = 'pan'
        else:
            self.vb.left_button_mode = 'none'

    def update(self, x, data):
        self._x = x
        self._y = data
        if x is not None and data is not None:
            z_mean = data[:, self._column, 0]
            self._curve_mean.updateData(x, z_mean)
            self._curve_min.updateData(x,  data[:, self._column, 2])
            self._curve_max.updateData(x, data[:, self._column, 3])

            z_valid = np.isfinite(z_mean)
            z_mean = z_mean[z_valid]

            z_var = data[z_valid, self._column, 1]
            z_min = data[z_valid, self._column, 2]
            z_max = data[z_valid, self._column, 3]

            if not len(z_mean):
                v_mean = np.nan
                v_std = np.nan
                v_min = np.nan
                v_max = np.nan
            else:
                v_mean = np.mean(z_mean)
                v_min = np.min(z_min)
                if not np.isfinite(v_min):
                    v_min = np.min(z_mean)
                v_max = np.max(z_max)
                if not np.isfinite(v_max):
                    v_max = np.max(z_mean)
                mean_delta = z_mean - v_mean
                # combine variances across the combined samples
                v_std = np.sqrt(np.sum(np.square(mean_delta, out=mean_delta) + z_var) / len(z_mean))
                if self.ui.zoomAutoYButton.isChecked():
                    _, (vb_min, vb_max) = self.vb.viewRange()
                    vb_range = vb_max - vb_min
                    v_range = v_max - v_min
                    update_range = (v_max > vb_max) or (v_min < vb_min)
                    if vb_range > 0:
                        update_range |= (v_range / vb_range) < AUTO_RANGE_FRACT
                    if update_range:
                        self.vb.setYRange(v_min, v_max)

            self.ui.meanValue.setText(three_sig_figs(v_mean, self._units))
            self.ui.stdValue.setText(three_sig_figs(v_std, self._units))
            self.ui.p2pValue.setText(three_sig_figs(v_max - v_min, self._units))
            self.ui.minValue.setText(three_sig_figs(v_min, self._units))
            self.ui.maxValue.setText(three_sig_figs(v_max, self._units))
            self.vb.setXRange(x[0], x[-1], padding=0.0)
            self.plot.update()
            self.on_marker()
            return

        self._curve_min.clear()
        self._curve_min.update()
        self._curve_max.clear()
        self._curve_max.update()
        self._curve_mean.clear()
        self._curve_mean.update()
        self.ui.meanValue.setText('')
        self.ui.stdValue.setText('')
        self.ui.p2pValue.setText('')
        self.ui.minValue.setText('')
        self.ui.maxValue.setText('')
        self.plot.update()

    @QtCore.Slot(object)
    def on_marker(self, x=None):
        if x is None:
            x = self.vb.vline.getPos()[0]
        if self._x is not None and len(self._x):
            values = ['t=%.6f' % (x, )]
            idx = np.argmax(self._x >= x)
            y = self._y[idx, self._column, :].tolist()
            y[1] = np.sqrt(y[1])
            if np.isfinite(y[2]):
                labels = ['μ', 'σ', 'min', 'max']
            elif np.isfinite(y[0]):
                labels = ['μ']
                y = y[:1]
            else:
                y = [0.0]
                labels = []
            max_value = float(np.max(np.abs(y)))
            _, prefix, scale = unit_prefix(max_value)
            scale = 1.0 / scale
            if not len(prefix):
                prefix = '&nbsp;'
            units = f'{prefix}{self._units}'
            for lbl, v in zip(labels, y):
                v *= scale
                if abs(v) < 0.000005:  # minimum display resolution
                    v = 0
                v_str = ('%+6f' % v)[:8]
                values.append('%s=%s %s' % (lbl, v_str, units))
            s = '<br>'.join(values)
            html = '<div><span style="color: #FFF;">%s</span></div>' % (s, )
            ymin, ymax = self.vb.viewRange()[1]
            self.x_label.setPos(x, ymax)
        else:
            html = ""
        self.x_label.setHtml(html)

        #self.vb.vline.label.setHtml(html)
        #self.vb.vline.label.setFormat(html)
        # self.x_pos.setAnchor([0.5, 0.5])
        self.vb.vline.setPos(x)

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
