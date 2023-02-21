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

from PySide6 import QtWidgets, QtGui, QtCore
import pyqtgraph as pg
import weakref
from joulescope.units import three_sig_figs
import logging


TIME_STYLE_DEFAULT = 'color: {foreground}; background-color: {background}; font-size: 8pt'


Z_MARKER_NORMAL = 10
Z_MARKER_ACTIVE = 11
Z_MARKER_MOVING = 12


class Marker(pg.GraphicsObject):
    """A vertical x-axis marker for display on the oscilloscope.

    :param cmdp: The command processor instance.
    :param name: The name for the marker.  By convention, single markers are
        number strings, like '1', and marker pairs are like 'A1' and 'A2'.
    :param x_axis: The x-axis :class:`pg.AxisItem` instance.
    :param state: The dict of state attributes.
    """

    def __init__(self, cmdp, name, x_axis: pg.AxisItem, state=None):
        pg.GraphicsObject.__init__(self)
        state.setdefault('pos', None)
        state.setdefault('color', (64, 255, 64, 255))
        state.setdefault('shape', 'full')
        state.setdefault('statistics', 'right')
        self._cmdp = cmdp
        self.log = logging.getLogger('%s.%s' % (__name__, name))
        self._name = name
        self._axis = weakref.ref(x_axis)
        self._boundingRect = None
        self.picture = None
        self._x = None  # in self._axis coordinates
        self._pair = None
        self.moving = False
        self.moving_offset = 0.0
        self.start_pos = 0.0
        self._marker_time_text = pg.TextItem("")
        self._delta_time_text = pg.TextItem("")
        self._delta_time_text.setAnchor([0.5, 0])
        self._delta_time_text.setVisible(False)
        self.graphic_items = [self._marker_time_text, self._delta_time_text]
        self.text = {}  #: Dict[str, List[weakref.ReferenceType[Signal], TextItem]]

        self._instance_prefix = f'Widgets/Waveform/Markers/_state/instances/{name}/'
        for key, value in state.items():
            self._cmdp.preferences.set(self._instance_prefix + key, value)
        self.set_pos(state.get('pos'))

    def __str__(self):
        return f'Marker({self.name})'

    @property
    def statistics_show(self):
        p = self._instance_prefix + 'statistics'
        return self._cmdp.preferences.get(p, default='right')

    @statistics_show.setter
    def statistics_show(self, value):
        p = self._instance_prefix + 'statistics'
        return self._cmdp.publish(p, value)

    def remove(self):
        state = {'name': self._name}
        preferences = self._cmdp.preferences.match(self._instance_prefix)
        for p in preferences:
            state[p.split('/')[-1]] = self._cmdp.preferences.clear(p)
        return state

    @property
    def name(self):
        return self._name

    @property
    def is_single(self):
        return self._pair is None

    @property
    def is_right(self):
        return self._pair is not None and self.name[-1] == 'b'

    @property
    def is_left(self):
        return self._pair is not None and self.name[-1] == 'a'

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
        self._redraw()

    def _endpoints(self):
        """Get the endpoints in the scene's (parent) coordinates.

        :return: (top, bottom) pg.Point instances
        """
        axis = self._axis()
        if axis is None:
            return None, None
        vb = axis.linkedView()
        if vb is None or self._x is None:
            return None, None
        bounds = axis.geometry()
        tickBounds = vb.geometry()
        point = pg.Point(self._x, 0.0)
        x = vb.mapViewToScene(point).x()
        p1 = pg.Point(x, bounds.bottom())
        p2 = pg.Point(x, tickBounds.bottom())
        return p1, p2

    def _flag_bounds_relative(self):
        """Get the bound region for the flag.

        :return: width left, width right, height bezel, height total
        """
        axis = self._axis()
        if axis is None:
            return 0, 0, 0
        h = axis.geometry().height()
        he = h // 3
        shape = self._cmdp[self._instance_prefix + 'shape']
        if shape in [None, 'none']:
            return 0, 0, he, h
        if shape in ['right']:
            return -h, 0, he, h
        elif shape in ['left']:
            return 0, h, he, h
        else:
            w2 = h // 2
            return -w2, w2, he, h

    def boundingRect(self):
        r = self._boundingRect
        if r is not None:  # use cache
            return r
        axis = self._axis()
        if axis is None:
            return QtCore.QRectF()
        top = axis.geometry().top()
        p1, p2 = self._endpoints()
        if p2 is None:
            return QtCore.QRectF()
        wl, wr, he, h = self._flag_bounds_relative()
        x = p2.x()
        bottom = p2.y()
        w = max(abs(wl), abs(wr))
        self._boundingRect = QtCore.QRectF(x - w - 1, top, w * 2 + 2, bottom - top)
        # self.log.debug('boundingRect: %s => %s', self._x, str(self._boundingRect))
        return self._boundingRect

    def paint_flag(self, painter, p1):
        wl, wr, he, h = self._flag_bounds_relative()
        if not h:
            return
        color = self._cmdp[self._instance_prefix + 'color']
        brush = pg.mkBrush(color)
        painter.setBrush(brush)
        painter.setPen(QtCore.Qt.NoPen)
        painter.resetTransform()

        painter.translate(p1)
        painter.drawConvexPolygon([
            pg.Point(0, 0),
            pg.Point(wl, -he),
            pg.Point(wl, -h),
            pg.Point(wr, -h),
            pg.Point(wr, -he)
        ])
        text_pen = pg.mkPen([0, 0, 0, 128])
        painter.setPen(text_pen)
        txt = self._name
        # r = painter.fontMetrics().boundingRect(txt)
        r = QtCore.QRect(wl, -h, wr - wl, -he + h)
        painter.drawText(r, QtCore.Qt.AlignCenter, txt)

    def paint(self, p, opt, widget):
        profiler = pg.debug.Profiler()
        axis = self._axis()
        if axis is None or axis.linkedView() is None:
            return
        color = self._cmdp[self._instance_prefix + 'color']
        if self.picture is None:
            try:
                p.resetTransform()
                picture = QtGui.QPicture()
                painter = QtGui.QPainter(picture)
                pen = pg.mkPen(color)
                pen.setWidth(1)
                painter.setPen(pen)
                p1, p2 = self._endpoints()
                if p1 is not None and p2 is not None:
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

    def set_pos(self, x):
        """Set the x-axis position for the marker.

        :param x: The new x-axis position in Axis coordinates.
        """
        if x == self._x:
            return
        self._x = x
        self._axis().marker_moving_emit(self.name, x)
        self._cmdp.publish(self._instance_prefix + 'pos', x, no_undo=True)
        self._redraw()

    def _time_style(self):
        theme = self._cmdp['Appearance/__index__']
        return TIME_STYLE_DEFAULT.format(
            foreground=theme['colors']['waveform_font_color'],
            background=theme['colors']['waveform_background'],
        )

    def _update_marker_text(self):
        x = self._x
        style = self._time_style()
        if self._x is None:
            html = ''
        else:
            html = f'<div><span style="{style}">t={x:.6f}</span></div>'
        self._marker_time_text.setHtml(html)
        axis = self._axis()
        if axis is None:
            return
        vb = axis.linkedView()
        if vb is None or self._x is None:
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
            style = self._time_style()
            axis = self._axis()
            if axis is None:
                return
            axis_top = axis.geometry().top()
            vb = axis.linkedView()
            if vb is None:
                return
            x_left = self._x
            x_right = self._pair._x
            if x_left is None or x_right is None:
                self._delta_time_text.setHtml('')
                return
            dx = abs(x_right - x_left)
            x_center = (x_left + x_right) / 2
            x_scene = vb.mapViewToScene(pg.Point(x_center, 0.0)).x()
            dx_str = three_sig_figs(dx, 's')
            self._delta_time_text.setHtml(f'<div><span style="{style}">Δt={dx_str}</span></div>')
            self._delta_time_text.setPos(x_scene, axis_top)
        elif self.is_right:
            self._pair._update_delta_time()

    def get_pos(self):
        """Get the current x-axis position for the marker.

        :return: The current x-axis position in the Axis coordinates.
        """
        return self._x

    def _move_start(self, ev):
        self.moving_offset = 0.0
        self.moving = True
        self.start_pos = self.get_pos()
        self.setZValue(Z_MARKER_MOVING)
        # https://doc.qt.io/qt-6/qt.html#KeyboardModifier-enum
        if int(QtCore.Qt.KeyboardModifier.ControlModifier & ev.modifiers()) and self.pair is not None:
            self.pair.moving = True
            self.pair.moving_offset = self.pair.get_pos() - self.get_pos()
        if self.pair is not None:
            self.pair.start_pos = self.pair.get_pos()

    def _move_end(self):
        self._cmdp.invoke('!command_group/start', None)
        if self.moving:
            moved = [[self.name, self.get_pos(), self.start_pos]]
            self._cmdp.invoke('!Widgets/Waveform/Markers/move', moved)
            self.moving = False
        activate = [self.name]
        if self.pair is not None:
            moved = [[self.pair.name, self.pair.get_pos(), self.pair.start_pos]]
            if self.pair.moving:
                self._cmdp.invoke('!Widgets/Waveform/Markers/move', moved)
            self.pair.moving = False
            self.pair.moving_offset = 0.0
            activate.append(self.pair.name)
        self._cmdp.invoke('!Widgets/Waveform/Markers/activate', activate)
        self._cmdp.invoke('!command_group/end', None)

    def mouseClickEvent(self, ev):
        self.log.info('mouseClickEvent(%s)', ev)
        ev.accept()
        if not self.moving:
            if ev.button() == QtCore.Qt.LeftButton:
                self._move_start(ev)
            elif ev.button() == QtCore.Qt.RightButton:
                pos = ev.screenPos().toPoint()
                self.menu_exec(pos)
        else:
            if ev.button() == QtCore.Qt.LeftButton:
                self._move_end()
            elif ev.button() == QtCore.Qt.RightButton:
                self.set_pos(self.start_pos)
                self.moving = False
                if self.pair is not None:
                    self.pair.moving = False
                    self.pair.set_pos(self.pair.start_pos)

    def mouseDragEvent(self, ev, axis=None):
        self.log.debug('mouse drag: %s' % (ev, ))
        ev.accept()
        if ev.button() & QtCore.Qt.LeftButton:
            if ev.isStart():
                self._move_start(ev)
            if ev.isFinish():
                self._move_end()

    def _range_tool_factory(self, range_tool_name):
        def fn(*args, **kwargs):
            if self._pair is None:
                raise RuntimeError('analysis only available on dual markers')
            p1 = self.get_pos()
            p2 = self._pair.get_pos()
            value = {
                'name': range_tool_name,
                'x_start': min(p1, p2),
                'x_stop': max(p1, p2)
            }
            self._cmdp.invoke('!RangeTool/run', value)
        return fn

    def _remove(self, *args, **kwargs):
        if self.pair is not None:
            removes = [self.name, self.pair.name]
        else:
            removes = [self.name]
        self._cmdp.invoke('!Widgets/Waveform/Markers/remove', [removes])

    def menu_exec(self, pos):
        instances = []  # hold on to QT objects
        menu = QtWidgets.QMenu()
        menu.setToolTipsVisible(True)
        submenus = {}
        if self._pair is not None:
            plugins = self._cmdp['Plugins/#registered']
            for name in plugins.range_tools.keys():
                m, subm = menu, submenus
                name_parts = name.split('/')
                while len(name_parts) > 1:
                    name_part = name_parts.pop(0)
                    if name_part not in subm:
                        subm[name_part] = [m.addMenu(name_part), {}]
                        m, subm = subm[name_part]
                    else:
                        m, subm = subm[name_part]
                t = QtGui.QAction(name_parts[0], self)
                t.triggered.connect(self._range_tool_factory(name))
                m.addAction(t)
                instances.append(t)
            zoom = menu.addAction('&Zoom to fit')
            zoom.triggered.connect(self._on_zoom)

        show_stats_menu = menu.addMenu('&Show statistics')
        show_stats_group = QtGui.QActionGroup(show_stats_menu)

        left = show_stats_menu.addAction('&Left')
        left.setCheckable(True)
        left.setChecked(self.statistics_show == 'left')
        left.triggered.connect(lambda: self._on_statistics_show('left'))
        show_stats_group.addAction(left)

        right = show_stats_menu.addAction('&Right')
        right.setCheckable(True)
        right.setChecked(self.statistics_show == 'right')
        right.triggered.connect(lambda: self._on_statistics_show('right'))
        show_stats_group.addAction(right)

        off = show_stats_menu.addAction('&Off')
        off.setCheckable(True)
        off.setChecked(self.statistics_show == 'off')
        off.triggered.connect(lambda: self._on_statistics_show('off'))
        show_stats_group.addAction(off)

        marker_remove = menu.addAction('&Remove')
        marker_remove.triggered.connect(self._remove)
        menu.exec_(pos)

    def _on_zoom(self):
        x1 = self.get_pos()
        x2 = self.pair.get_pos()
        x1, x2 = min(x1, x2), max(x1, x2)
        k = (x2 - x1) * 0.01
        x1, x2 = x1 - k, x2 + k
        self._cmdp.invoke('!Widgets/Waveform/x-axis/range', (x1, x2))
        self.log.info('zoom %s %s', x1, x2)

    def _on_statistics_show(self, value):
        self.statistics_show = value

    def setVisible(self, visible):
        super().setVisible(visible)
        for item in self.graphic_items:
            item.setVisible(visible)
