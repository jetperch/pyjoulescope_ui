# Copyright 2021 Jetperch LLC
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

# Based upon pyqtgraph/examples/customGraphicsItem.py

from PySide2 import QtWidgets, QtGui, QtCore
import numpy as np
import pyqtgraph as pg
import logging


Z_ANNOTATION_NORMAL = 15


def _make_path(*args):
    path = QtGui.QPainterPath()
    path.moveTo(*args[0])
    for arg in args[1:]:
        path.lineTo(*arg)
    path.closeSubpath()
    return path


def _rotate(path, angle):
    tr = QtGui.QTransform()
    tr.rotate(angle)
    return tr.map(path)


_circle = QtGui.QPainterPath()
_circle.addEllipse(-1, -1, 2, 2)
_rectangle = QtGui.QPainterPath()
_rectangle.addRect(QtCore.QRectF(-1, -1, 2, 2))
_plus_points = [(-1, -0.4), (-1, 0.4), (-0.4, 0.4),
                (-0.4, 1), (0.4, 1), (0.4, 0.4),
                (1, 0.4), (1, -0.4), (0.4, -0.4),
                (0.4, -1), (-0.4, -1), (-0.4, -0.4)]
_star_points = [(0.0, -1.25), (-0.28075, -0.38625),
                (-1.18875, -0.38625), (-0.454, 0.1475),
                (-0.73475, 1.01125), (0.0, 0.4775),
                (0.73475, 1.01125), (0.454, 0.1475),
                (1.18875, -0.38625), (0.28075, -0.38625)]


SHAPES = [
    _make_path((-1, 0), (0, 1), (1, 0), (0, -1)),   # diamond
    _circle,                                        # circle
    _rectangle,                                     # rectangle
    _make_path(*_star_points),                      # star
    _make_path(*_plus_points),                      # plus
    _rotate(_make_path(*_plus_points), 45),         # x
    _make_path((-1, 1), (0, -1), (1, 1)),           # triangle up
    _make_path((-1, -1), (0, 1), (1, -1)),          # triangle down
    _make_path((-1, 1), (-1, -1), (1, 0)),          # triangle right
    _make_path((1, 1), (1, -1), (-1, 0)),           # triangle left
]


class TextAnnotation(pg.GraphicsObject):
    """A user-defined text annotation applied to a signal.

    :param parent: The parent signal's ViewBox.
    :param state: The map of the text annotation state, which includes keys:
        * id: The text annotation id.
        * signal_name: The signal name for this annotation.
        * x: The initial x-axis position in signal coordinates.
        * text: The text to display.
        * fill_color: The fill color.
        * border_color: The border color.
    """
    def __init__(self, parent, state):
        pg.GraphicsObject.__init__(self, parent)
        self._parent = parent
        self._log = logging.getLogger('%s.%s' % (__name__, state['x']))
        self._state = {
            'id': state.get('id', id(self)),
            'signal_name': state['signal_name'],
            'x': state['x'],
            'group_id': int(state.get('group_id', 0)),
            'text': state.get('text'),
            'fill_color': state.get('fill_color', (64, 192, 128, 255)),
            # 'border_color': state.get('border_color', (64, 255, 128, 255)),
            'text_color': state.get('text_color', (192, 192, 192, 255)),
            'size': state.get('size', 6),
        }
        self._pathItem = QtGui.QGraphicsPathItem()
        self._pathItem.setParentItem(self)

        self._lastTransform = None
        self._lastScene = None
        self._fill = pg.mkBrush(None)
        self._border = pg.mkPen(None)

        self._group_id_set(self._state['group_id'])
        self.setPos(self._state['x'], 0.0)

        brush = pg.mkBrush(self._state['fill_color'])
        # pen = pg.mkPen(self._state['border_color'])
        self.setBrush(brush)
        # self.setPen(pen)
        self.setZValue(Z_ANNOTATION_NORMAL)

        self._text_item = QtGui.QGraphicsTextItem(self)
        self._text_item.setParentItem(self)
        self._text_item.setDefaultTextColor(pg.mkColor(self._state['text_color']))
        self._text_item.setPlainText(self._state['text'])
        self.prepareGeometryChange()

    def _group_id_set(self, group_id):
        s_len = len(SHAPES)
        group_id = group_id % s_len
        path = SHAPES[group_id]
        tr = QtGui.QTransform()
        sz = self._state['size']
        tr.scale(sz, sz)
        path = tr.map(path)
        self._pathItem.setPath(path)

    def setBrush(self, brush):
        self._pathItem.setBrush(brush)

    def setZValue(self, zValue):
        self._pathItem.setZValue(zValue)
        super().setZValue(zValue)

    def boundingRect(self):
        return self._pathItem.mapRectToParent(self._pathItem.boundingRect())

    def paint(self, p, *args):
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        self._pathItem.paint(p, *args)

    def viewTransformChanged(self):
        # called whenever view transform has changed.
        # Do this here to avoid double-updates when view changes.
        self.updateTransform()

    def updateTransform(self, force=True):
        if not self.isVisible():
            return
        # update transform such that this item has the correct orientation
        # and scaling relative to the scene, but inherits its position from its
        # parent.
        # This is similar to setting ItemIgnoresTransformations = True, but
        # does not break mouse interaction and collision detection.
        p = self.parentItem()
        if p is None:
            pt = QtGui.QTransform()
        else:
            pt = p.sceneTransform()

        if not force and pt == self._lastTransform:
            return

        t = pt.inverted()[0]
        # reset translation
        _, (y_min, y_max) = self._parent.viewRange()
        y_center = (y_max + y_min) / 2
        t.setMatrix(t.m11(), t.m12(), t.m13(), t.m21(), t.m22(), t.m23(), 0, y_center, t.m33())
        self.setTransform(t)
        self._lastTransform = pt

    def mouseClickEvent(self, ev):
        scene_pos = ev.scenePos()
        item_pos = self.mapFromScene(scene_pos)
        ev.accept()
        print(f'mouseClickEvent({ev})')
        print(f'boundingRect={self.boundingRect()}')
        print(f'shape={self.shape()}')
        print(f'item_pos={item_pos}')
