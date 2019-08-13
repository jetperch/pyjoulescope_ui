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
from .signal import Signal
from .signal_statistics import si_format, html_format
import logging


TIME_STYLE_DEFAULT = 'color: #FFF; background-color: #000; font-size: 8pt'


class Marker(pg.GraphicsObject):
    """A vertical x-axis marker for display on the oscilloscope.

    :param x_axis: The x-axis :class:`pg.AxisItem` instance.
    :param color: The [R,G,B] or [R,G,B,A] color for the marker.
    :param shape: The marker flag shape which is one of:
        ['full', 'left', 'right', 'none'].
    """

    sigUpdateRequest = QtCore.Signal(object)
    """Request a value update when x-axis position changes.
    
    :param marker: The :class:`Marker` instance requesting the update.
        For dual markers, the marker that moved will signal.
    """

    sigRemoveRequest = QtCore.Signal(object)
    """Indicate that the user has requested to remove this marker

    :param marker: The marker instance to remove.
    """

    sigRangeToolRequest = QtCore.Signal(str, float, float)
    """Indicate that the user has requested a tool.

    :param name: The tool name to process.
    :param x_start: The starting position in x-axis units.
    :param x_stop: The stopping position in x-axis units.

    Tools are only triggered for dual markers.  Tools for single
    markers are not supported.
    """

    def __init__(self, name, x_axis: pg.AxisItem, color=None, shape=None):
        pg.GraphicsObject.__init__(self)
        self.log = logging.getLogger('%s.%s' % (__name__, name))
        self._name = name
        self._axis = weakref.ref(x_axis)
        self.color = (64, 255, 64, 255) if color is None else color
        self._boundingRect = None
        self.picture = None
        self._shape = shape
        self.setPos(pg.Point(0, 0))
        self._x = 0.0  # in self._axis coordinates
        # self.setZValue(2000000)
        self._pair = None
        self.moving = False
        self._marker_time_text = pg.TextItem("t=0.00")
        self._delta_time_text = pg.TextItem("Δt=0.00")
        self._delta_time_text.setAnchor([0.5, 0])
        self.graphic_items = [self._marker_time_text, self._delta_time_text]
        self.text = {}  #: Dict[str, List[weakref.ReferenceType[Signal], TextItem]]

    def __str__(self):
        return f'Marker({self.name})'

    @property
    def name(self):
        return self._name

    @property
    def is_right(self):
        return self._pair is not None and self.name[1] == '2'

    @property
    def is_left(self):
        return self._pair is not None and self.name[1] == '1'

    @property
    def pair(self):
        return self._pair

    @pair.setter
    def pair(self, value):
        self._pair = value
        if self.is_left:
            self._marker_time_text.setAnchor([1, 0])
            self._delta_time_text.setVisible(True)
        else:
            self._marker_time_text.setAnchor([0, 0])
            self._delta_time_text.setVisible(False)

    def signal_add(self, signal: Signal):
        txt = pg.TextItem()
        self.text[signal.name] = [weakref.ref(signal), txt]
        signal.vb.addItem(txt)
        txt.setVisible(True)

    def signal_update(self, signal: Signal):
        if signal.name not in self.text:
            self.signal_add(signal)
        _, txt = self.text[signal.name]
        xv = self.get_pos()
        labels = signal.statistics_at(xv)
        if len(labels):
            txt_result = si_format(labels, units=signal.units)
            html = html_format(txt_result, x=xv)
            self.html_set(signal.name, html)

    def signal_update_all(self):
        for signal_ref, _ in self.text.values():
            s = signal_ref()
            if s is not None:
                self.signal_update(s)

    def signal_remove(self, name):
        if isinstance(name, Signal):
            name = name.name
        if name not in self.text:
            self.log.warning('signal_remove(%s) but not found', name)
            return
        signal_ref, txt = self.text.pop(name)
        signal = signal_ref()
        if signal is not None:
            signal.vb.scene().removeItem(txt)

    def signal_remove_all(self):
        for name in list(self.text.keys()):
            self.signal_remove(name)

    def html_set(self, signal_name, html):
        if signal_name not in self.text:
            self.log.debug('html_set(%s) but does not exist', signal_name)
            return
        signal_ref, txt = self.text[signal_name]
        signal = signal_ref()
        if signal is None:
            self.log.warning('html_set(%s) but signal ref not valid', signal_name)
            return
        xv = self.get_pos()
        vb = signal.vb
        ys = vb.geometry().top()
        yv = vb.mapSceneToView(pg.Point(0.0, ys)).y()
        txt.setPos(pg.Point(xv, yv))
        txt.setHtml(html)

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
        self.log.debug('boundingRect: %s => %s', self._x, str(self._boundingRect))
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
        self._update_marker_text()
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

    def set_pos(self, x, no_emit=None):
        """Set the x-axis position for the marker.

        :param x: The new x-axis position in Axis coordinates.
        :param no_emit: When True, do not emit any updates.
            When False or None (default) emit updates.
        """
        self._x = x
        for signal_ref, text in self.text.values():
            text.setText('')  # better to have nothing than be wrong
            s = signal_ref()
            if s is not None:
                vby = s.vb.geometry().top()
                px = s.vb.mapViewToScene(pg.Point(x, 0.0)).x()
                text.setPos(px, vby)

        # signal the update request as necessary
        if not bool(no_emit):
            self.sigUpdateRequest.emit(self)
        self._redraw()

    def _update_marker_text(self):
        x = self._x
        style = TIME_STYLE_DEFAULT
        self._marker_time_text.setHtml(f'<div><span style="{style}">t={x:.6f}</span></div>')
        axis = self._axis()
        if axis is None:
            return
        vb = axis.linkedView()
        if vb is None:
            return
        g = axis.geometry()
        axis_top = g.top()
        axis_height = axis.geometry().height()
        text_offset = axis_height // 2
        x_scene = vb.mapViewToScene(pg.Point(x, 0.0)).x()
        if self._pair is None:
            self._marker_time_text.setPos(x_scene + text_offset, axis_top)
        elif self.is_left:
            self._marker_time_text.setPos(x_scene, axis_top)
            self._update_delta_time()
        else:
            self._marker_time_text.setPos(x_scene, axis_top)
            self._pair._update_delta_time()

    def _update_delta_time(self):
        if self.is_left:
            style = TIME_STYLE_DEFAULT
            axis = self._axis()
            if axis is None:
                return
            axis_top = axis.geometry().top()
            vb = axis.linkedView()
            if vb is None:
                return
            x_left = self._x
            x_right = self._pair._x
            dx = abs(x_right - x_left)
            x_center = (x_left + x_right) / 2
            x_scene = vb.mapViewToScene(pg.Point(x_center, 0.0)).x()
            self._delta_time_text.setHtml(f'<div><span style="{style}">Δt={dx:.3g}</span></div>')
            self._delta_time_text.setPos(x_scene, axis_top)
        elif self.is_right:
            self._pair._update_delta_time()

    def get_pos(self):
        """Get the current x-axis position for the marker.

        :return: The current x-axis position in the Axis coordinates.
        """
        return self._x

    def on_xChangeSignal(self, x_min, x_max, x_count):
        self._redraw()

    def mouseClickEvent(self, ev):
        self.log.info('mouseClickEvent(%s)', ev)
        ev.accept()
        if not self.moving:
            if ev.button() == QtCore.Qt.LeftButton:
                self.moving = True
            elif ev.button() == QtCore.Qt.RightButton:
                pos = ev.screenPos().toPoint()
                self.menu_exec(pos)
        else:
            if ev.button() == QtCore.Qt.LeftButton:
                self.moving = False
            elif ev.button() == QtCore.Qt.RightButton:
                pass  # todo restore original position

    def _range_tool_constructor(self, name):
        # @QtCore.Slot()
        def fn():
            if self._pair is None:
                raise RuntimeError('analysis only available on dual markers')
            p1 = self.get_pos()
            p2 = self._pair.get_pos()
            x_start = min(p1, p2)
            x_stop = max(p1, p2)
            self.sigRangeToolRequest.emit(name, x_start, x_stop)
        return fn

    def menu_exec(self, pos):
        instances = []  # hold on to QT objects
        menu = QtGui.QMenu()
        menu.setToolTipsVisible(True)
        if self._pair is not None:
            for name in self._axis().plugins.range_tools.keys():
                t = QtGui.QAction(name, self)
                t.triggered.connect(self._range_tool_constructor(name))
                menu.addAction(t)
                instances.append(t)
        marker_remove = QtGui.QAction('&Remove', self)
        marker_remove.triggered.connect(lambda: self.sigRemoveRequest.emit(self))
        menu.addAction(marker_remove)
        menu.exec_(pos)

    def setVisible(self, visible):
        super().setVisible(visible)
        for item in self.graphic_items:
            item.setVisible(visible)
