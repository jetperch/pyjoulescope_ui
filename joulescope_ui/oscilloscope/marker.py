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

from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg
import weakref
import logging


log = logging.getLogger(__name__)


class Marker(pg.GraphicsObject):
    """A vertical x-axis marker for display on the oscilloscope.

    :param x_axis: The x-axis :class:`pg.AxisItem` instance.
    :param color: The [R,G,B] or [R,G,B,A] color for the marker.
    :param shape: The marker flag shape which is one of:
        ['full', 'left', 'right', 'none'].
    """

    sigRemoveRequest = QtCore.Signal(object)
    """Indicate that the user has requested to remove this marker

    :param marker: The marker instance to remove.
    """

    def __init__(self, name, x_axis: pg.AxisItem, color=None, shape=None):
        pg.GraphicsObject.__init__(self)
        self._name = name
        self._axis = weakref.ref(x_axis)
        self.color = (64, 255, 64, 255) if color is None else color
        self._boundingRect = None
        self.picture = None
        self._shape = shape
        self.setPos(pg.Point(0, 0))
        self._x = 0.0  # in self._axis coordinates
        # self.setZValue(2000000)
        self.signals = {}  # name: (Signal weakref, TextItem)
        self.pair = None
        self.moving = False
        self.text = {}

    @property
    def name(self):
        return self._name

    def _endpoints(self):
        """Get the endpoints in the scene's (parent) coordinates.

        :return: (top, bottom) pg.Point instances
        """
        axis = self._axis()
        if axis is None:
            return None, None
        vb = axis.linkedView()
        if vb is None:
            return None, None
        bounds = axis.geometry()
        tickBounds = vb.geometry()
        point = pg.Point(self._x, 0.0)
        x = vb.mapViewToScene(point).x()
        p1 = pg.Point(x, bounds.bottom())
        p2 = pg.Point(x, tickBounds.bottom())
        return p1, p2

    def boundingRect(self):
        r = self._boundingRect
        if r is not None:  # use cache
            return r
        axis = self._axis()
        if axis is None:
            return QtCore.QRectF()
        top = axis.geometry().top()
        h = axis.geometry().height()
        w = h // 2 + 1
        p1, p2 = self._endpoints()
        if p2 is None:
            return QtCore.QRectF()
        x = p2.x()
        bottom = p2.y()
        self._boundingRect = QtCore.QRectF(x - w, top, 2 * w, bottom - top)
        log.info('boundingRect: %s => %s', self._x, str(self._boundingRect))
        return self._boundingRect

    def paint_flag(self, painter, p1):
        axis = self._axis()
        if axis is None:
            return
        h = axis.geometry().height()
        he = h // 3
        w2 = h // 2
        if self._shape in [None, 'none']:
            return
        if self._shape in ['right']:
            wl, wr = -w2, 0
        elif self._shape in ['left']:
            wl, wr = 0, w2
        else:
            wl, wr = -w2, w2

        brush = pg.mkBrush(self.color)
        painter.setBrush(brush)
        painter.setPen(None)
        painter.resetTransform()

        painter.translate(p1)
        painter.drawConvexPolygon([
            pg.Point(0, 0),
            pg.Point(wl, -he),
            pg.Point(wl, -h),
            pg.Point(wr, -h),
            pg.Point(wr, -he)
        ])

    def paint(self, p, opt, widget):
        profiler = pg.debug.Profiler()
        axis = self._axis()
        if axis is None or axis.linkedView() is None:
            return
        if self.picture is None:
            try:
                p.resetTransform()
                picture = QtGui.QPicture()
                painter = QtGui.QPainter(picture)
                pen = pg.mkPen(self.color)
                pen.setWidth(1)
                painter.setPen(pen)
                p1, p2 = self._endpoints()
                painter.drawLine(p1, p2)
                self.paint_flag(painter, p1)
                profiler('draw picture')
            finally:
                painter.end()
            self.picture = picture
        self.picture.play(p)

    def _redraw(self):
        self.picture = None
        self._boundingRect = None
        self.prepareGeometryChange()
        self.update()

    def resizeEvent(self, ev=None):
        self._redraw()

    def viewRangeChanged(self):
        self._redraw()

    def viewTransformChanged(self):
        self._redraw()

    def linkedViewChanged(self, view, newRange=None):
        self._redraw()

    def set_pos(self, x):
        """Set the x-axis position for the marker.

        :param x: The new x-axis position in Axis coordinates.
        """
        self._x = x
        self._redraw()

    def get_pos(self):
        """Get the current x-axis position for the marker.

        :return: The current x-axis position in the Axis coordinates.
        """
        return self._x

    def on_xChangeSignal(self, x_min, x_max, x_count):
        self._redraw()

    def mouseClickEvent(self, ev):
        ev.accept()
        if not self.moving:
            if ev.button() == QtCore.Qt.LeftButton:
                self.moving = True
            elif ev.button() == QtCore.Qt.RightButton:
                self.sigRemoveRequest.emit(self)
        else:
            if ev.button() == QtCore.Qt.LeftButton:
                self.moving = False
            elif ev.button() == QtCore.Qt.RightButton:
                pass  # todo restore original position
