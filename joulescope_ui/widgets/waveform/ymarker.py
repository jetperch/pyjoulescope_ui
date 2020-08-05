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

from PySide2 import QtWidgets, QtGui, QtCore
from joulescope.units import three_sig_figs
from .marker import Z_MARKER_MOVING
import pyqtgraph as pg
import weakref
import logging


TIME_STYLE_DEFAULT = 'color: #FFF; background-color: #000; font-size: 8pt'


class YMarker(pg.GraphicsObject):
    """A horizontal y-axis marker for display on the oscilloscope.

    :param cmdp: The command processor instance.
    :param name: The name for the marker.  By convention, single markers are
        number strings, like '1', and marker pairs are like 'A1' and 'A2'.
    :param view: The ViewBox instance.
    :param units: The units for this marker.
    :param state: Additional state values.
    """
    def __init__(self, cmdp, name, view, units, state):
        pg.GraphicsObject.__init__(self)
        state.setdefault('pos', None)
        state.setdefault('color', (64, 255, 64, 255))
        self._cmdp = cmdp
        self.log = logging.getLogger('%s.%s' % (__name__, name))
        self._name = name
        self._view = weakref.ref(view)
        self._units = units
        self._y = None  # in signal coordinates
        self._pair: YMarker = None
        self.moving = False
        self.moving_offset = 0.0
        self.start_pos = 0.0

        self._instance_prefix = f'Widgets/Waveform/YMarkers/_state/instances/{view.name}/{name}/'
        for key, value in state.items():
            self._cmdp.preferences.set(self._instance_prefix + key, value)
        self.set_pos(state.get('pos'))
        self.setZValue(10)
        self._redraw()

    def __str__(self):
        return f'YMarker({self.name})'

    def remove(self):
        state = {
            'signal': self._view().name,
            'name': self._name,
            'pos': self.get_pos()
        }
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
    def pair(self):
        return self._pair

    @pair.setter
    def pair(self, value):
        self._pair = value
        self._redraw()

    def scene_pos_y(self):
        point = pg.Point(0.0, self._y)
        y = self._view().mapViewToScene(point).y()
        return y

    def boundingRect(self):
        vb = self._view()
        y = self.scene_pos_y()
        g = vb.geometry()
        return QtCore.QRectF(g.left(), y - 10, g.width(), 20)

    def paint(self, p, opt, widget):
        vb = self._view()
        color = self._cmdp[self._instance_prefix + 'color']
        p.resetTransform()
        vb_rect = vb.geometry()
        y = self.scene_pos_y()
        p1 = pg.Point(vb_rect.left(), y)
        p2 = pg.Point(vb_rect.right(), y)

        pen = pg.mkPen(color)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawLine(p1, p2)

        pen = pg.mkPen([255, 255, 255, 255])
        p.setPen(pen)
        if self.pair is None:
            txt = three_sig_figs(self._y, self._units)
        else:
            dy = abs(self._y - self.pair._y)
            t1 = three_sig_figs(self._y, self._units)
            t2 = three_sig_figs(dy, self._units)
            txt = f'y={t1}, Δ={t2}'
        p.drawText(p1 - 2, txt)

    def _redraw(self):
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

    def set_pos(self, y):
        """Set the y-axis position for the marker.

        :param y: The new y-axis position in Axis coordinates.
        """
        if y == self._y:
            return
        self._y = y
        self._cmdp.publish(self._instance_prefix + 'pos', y, no_undo=True)
        self._redraw()
        if self._pair is not None:
            self._pair._redraw()

    def get_pos(self):
        """Get the current y-axis position for the marker.

        :return: The current y-axis position in the Axis coordinates.
        """
        return self._y

    def _move_start(self, ev):
        signal = self._view().name
        self.moving_offset = 0.0
        self.moving = True
        self.start_pos = self.get_pos()
        self.setZValue(Z_MARKER_MOVING)
        # https://doc.qt.io/qt-5/qt.html#KeyboardModifier-enum
        if int(QtGui.Qt.ControlModifier & ev.modifiers()) and self.pair is not None:
            self.pair.moving = True
            self.pair.moving_offset = self.pair.get_pos() - self.get_pos()
        if self.pair is not None:
            self.pair.start_pos = self.pair.get_pos()

    def _move_end(self):
        signal = self._view().name
        self.moving = False
        moved = [[signal, self.name, self.get_pos(), self.start_pos]]
        activate = [[signal, self.name]]
        if self.pair is not None:
            self.pair.moving = False
            self.pair.moving_offset = 0.0
            moved.append([signal, self.pair.name, self.pair.get_pos(), self.pair.start_pos])
            activate.append([signal, self.pair.name])
        self._cmdp.invoke('!command_group/start', None)
        self._cmdp.invoke('!Widgets/Waveform/YMarkers/activate', activate)
        self._cmdp.invoke('!Widgets/Waveform/YMarkers/move', moved)
        self._cmdp.invoke('!command_group/end', None)

    def mouseClickEvent(self, ev):
        self.log.info('mouseClickEvent(%s)', ev)
        ev.accept()
        if not self.moving:
            if ev.button() == QtCore.Qt.LeftButton:
                self._move_start(ev)
            elif ev.button() == QtCore.Qt.RightButton:
                pos = ev.screenPos().toPoint()
                self._context_menu_exec(pos)
        else:
            if ev.button() == QtCore.Qt.LeftButton:
                self._move_end()
            elif ev.button() == QtCore.Qt.RightButton:
                self.moving = False
                self.set_pos(self.start_pos)
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

    def _context_menu_exec(self, pos):
        menu = QtWidgets.QMenu()
        marker_remove = menu.addAction('&Remove')
        marker_remove.triggered.connect(self._remove)
        menu.exec_(pos)

    def _remove(self, *args, **kwargs):
        cmd = [[self._view().name, self.name]]
        self._cmdp.invoke('!Widgets/Waveform/YMarkers/remove', cmd)
