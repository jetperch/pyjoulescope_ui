from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg


class Marker(pg.GraphicsObject):
    """A vertical x-axis marker for display on the oscilloscope.

    :param x_axis: The x-axis :class:`pg.AxisItem` instance.
    :param color: The [R,G,B] or [R,G,B,A] color for the marker.
    :param shape: The marker flag shape which is one of:
        ['full', 'left', 'right', 'none'].
    """

    def __init__(self, x_axis: pg.AxisItem, color=None, shape=None):
        pg.GraphicsObject.__init__(self)
        self._axis = x_axis
        self.color = (64, 255, 64, 255) if color is None else color
        self._boundingRect = None
        self.picture = None
        self._shape = shape
        self.setPos(pg.Point(0, 0))
        self._x = 0.0  # in self._axis coordinates
        # self.setZValue(2000000)

    def _endpoints(self):
        """Get the endpoints in the scene's (parent) coordinates.

        :return: (top, bottom) pg.Point instances
        """
        vb = self._axis.linkedView()
        if vb is None:
            return None, None
        bounds = self._axis.geometry()
        # print(bounds)
        tickBounds = vb.mapRectToItem(self, self._axis.boundingRect())
        point = pg.Point(self._x, 1000.0)
        x = self._axis.linkedView().mapViewToScene(point).x()
        p1 = pg.Point(x, bounds.bottom())
        p2 = pg.Point(x, tickBounds.bottom())
        # print('%s, %s' % (p1, p2))
        return p1, p2

    def _invalidateCache(self):
        self.picture = None
        self._boundingRect = None
        self.prepareGeometryChange()

    def boundingRect(self):
        r = self._boundingRect
        if r is not None:  # use cache
            return r
        top = self._axis.geometry().top()
        h = self._axis.geometry().height()
        w = h // 2 + 1
        p1, p2 = self._endpoints()
        if p2 is None:
            return QtCore.QRectF(0, 0, 0, 0)
        x = p2.x()
        bottom = p2.y()
        self._boundingRect = QtCore.QRectF(x - w, top, 2 * w, bottom - top)
        return self._boundingRect

    def paint_flag(self, painter, p1):
        h = self._axis.geometry().height()
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
        if self._axis.linkedView() is None:
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

    def resizeEvent(self, ev=None):
        self._invalidateCache()
        self.update()

    def linkedViewChanged(self, view, newRange=None):
        self._invalidateCache()
        self.update()

    def set_pos(self, x):
        """Set the x-axis position for the marker.

        :param x: The new x-axis position in Axis coordinates.
        """
        self._x = x
        self._invalidateCache()
        self.update()

    def get_pos(self):
        """Get the current x-axis position for the marker.

        :return: The current x-axis position in the Axis coordinates.
        """
        return self._x
