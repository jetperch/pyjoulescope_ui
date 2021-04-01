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
_square = QtGui.QPainterPath()
_square.addRect(QtCore.QRectF(-1, -1, 2, 2))
_hex_points = [(0.5, 0.866), (1.0, 0.0), (0.5, -0.866), (-0.5, -0.866), (-1.0, 0), (-0.5, 0.866)]
_plus_points = [(-1, -0.4), (-1, 0.4), (-0.4, 0.4),
                (-0.4, 1), (0.4, 1), (0.4, 0.4),
                (1, 0.4), (1, -0.4), (0.4, -0.4),
                (0.4, -1), (-0.4, -1), (-0.4, -0.4)]
_star_points = [(0.0, -1.25), (-0.28075, -0.38625),
                (-1.18875, -0.38625), (-0.454, 0.1475),
                (-0.73475, 1.01125), (0.0, 0.4775),
                (0.73475, 1.01125), (0.454, 0.1475),
                (1.18875, -0.38625), (0.28075, -0.38625)]


SHAPES_DEF = [
    ['d', 'diamond', _make_path((-1, 0), (0, 1), (1, 0), (0, -1))],
    ['o', 'circle', _circle],
    ['h', 'hexagon', _make_path(*_hex_points)],
    ['s', 'square', _square],
    ['*', 'star', _make_path(*_star_points)],
    ['+', 'plus', _make_path(*_plus_points)],
    ['x', 'cross', _rotate(_make_path(*_plus_points), 45)],
    ['^', 'triangle_up', _make_path((-1, 1), (0, -1), (1, 1))],
    ['v', 'triangle_down', _make_path((-1, -1), (0, 1), (1, -1))],
    ['>', 'triangle_right', _make_path((-1, 1), (-1, -1), (1, 0))],
    ['<', 'triangle_left', _make_path((1, 1), (1, -1), (-1, 0))],
]

SHAPES = [x[-1] for x in SHAPES_DEF]


def _shapes_map():
    d = {}
    for idx, (abbr, name, shape) in enumerate(SHAPES_DEF):
        d[idx] = shape
        d[abbr] = shape
        d[name] = shape
    return d


def _shapes_idx():
    d = {}
    for idx, (abbr, name, _) in enumerate(SHAPES_DEF):
        d[idx] = idx
        d[abbr] = idx
        d[name] = idx
    return d


def _shapes_name():
    d = {}
    for idx, (abbr, name, _) in enumerate(SHAPES_DEF):
        d[idx] = name
        d[abbr] = name
        d[name] = name
    return d


SHAPES_MAP = _shapes_map()
SHAPES_IDX = _shapes_idx()
SHAPES_NAME = _shapes_name()


class TextAnnotation(pg.GraphicsObject):
    """A user-defined text annotation applied to a signal.

    :param parent: The parent signal's ViewBox.
    :param cmdp: The command processor.
    :param state: The map of the text annotation state, which includes keys:
        * id: The text annotation id.
        * signal_name: The signal name for this annotation.
        * x: The initial x-axis position in signal coordinates.
        * text: The text to display.
        * fill_color: The fill color.
        * border_color: The border color.
    """
    def __init__(self, parent, cmdp, state):
        pg.GraphicsObject.__init__(self, parent)
        self._parent = parent
        self._cmdp = cmdp
        self._log = logging.getLogger('%s.%s' % (__name__, state['x']))
        self._move_x_start = None
        self._state = {
            'id': state.get('id', id(self)),
            'signal_name': state['signal_name'],
            'x': state['x'],
            'group_id': 0,
            'text': state.get('text'),
            'text_visible': True,
            'size': state.get('size', 6),
        }
        self._pathItem = QtGui.QGraphicsPathItem()
        self._pathItem.setParentItem(self)

        self._text_item = QtGui.QGraphicsTextItem(self)
        self._text_item.setParentItem(self)
        self._text_item.setVisible(bool(self._state['text_visible']))

        self.group_id = state.get('group_id', 0)

        self._lastTransform = None
        self._lastScene = None
        self._fill = pg.mkBrush(None)
        self._border = pg.mkPen(None)

        self.group_id = self._state['group_id']
        self.setPos(self._state['x'], 0.0)
        self._z_value_set()

        self.text = self._state['text']
        self._update_colors()
        self.prepareGeometryChange()

    def _update_colors(self):
        theme = self._cmdp['Appearance/__index__']
        name = SHAPES_NAME[self.group_id]
        fg = theme['colors'].get(f'annotation_{name}', '#40C080')
        pen = pg.mkPen(fg)
        self.setPen(pen)
        brush = pg.mkBrush(fg)
        self.setBrush(brush)
        txt = theme['colors'].get('annotation_text', '#C0C0C0')
        self._text_item.setDefaultTextColor(pg.mkColor(txt))
        #waveform_background

    def _z_value_set(self, offset=None):
        z_value = self._parent.zValue()
        z_value = 0 if z_value >= 0 else -z_value
        z_value += Z_ANNOTATION_NORMAL
        if offset is not None:
            z_value += int(offset)
        self.setZValue(z_value)

    @property
    def signal_name(self):
        return self._state['signal_name']

    @property
    def x_pos(self):
        return self._state['x']

    @x_pos.setter
    def x_pos(self, value):
        x_pos = float(value)
        self._state['x'] = x_pos
        _, (y_min, y_max) = self._parent.viewRange()
        y_pos = (y_max + y_min) / 2
        self.setPos(self._state['x'], y_pos)

    @property
    def text(self):
        return self._state['text']

    @text.setter
    def text(self, value):
        if value is None:
            text = ''
        else:
            text = str(value)
        self._state['text'] = text
        self._text_item.setPlainText(text)

    def isTextVisible(self):
        return self._text_item.isVisible()

    def setTextVisible(self, visible):
        visible = bool(visible)
        self._state['text_visible'] = visible
        self._text_item.setVisible(visible)

    @property
    def group_id(self):
        return self._state['group_id']

    @group_id.setter
    def group_id(self, value):
        group_id = value
        s_len = len(SHAPES)
        if isinstance(group_id, int) and not 0 <= group_id < s_len:
            group_id = group_id % s_len
        path = SHAPES_MAP[group_id]
        tr = QtGui.QTransform()
        sz = self._state['size']
        tr.scale(sz, sz)
        path = tr.map(path)
        self._pathItem.setPath(path)
        self._state['group_id'] = SHAPES_IDX[group_id]
        self._update_colors()

    def setPen(self, pen):
        self._pathItem.setPen(pen)

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
        self.setPos(self.x_pos, y_center)
        t.setMatrix(t.m11(), t.m12(), t.m13(), t.m21(), t.m22(), t.m23(), 0, 0, t.m33())
        self.setTransform(t)
        self._lastTransform = pt

    def mouseClickEvent(self, ev):
        ev.accept()
        self._log.debug(f'mouseClickEvent({ev})')
        if ev.button() == QtCore.Qt.LeftButton:
            self._show_text()
        elif ev.button() == QtCore.Qt.RightButton:
            pos = ev.screenPos().toPoint()
            self.menu_exec(pos)

    def _ev_to_x(self, ev):
        pos = ev.scenePos()
        p = self._parent.mapSceneToView(pos)
        x = p.x()
        (x_min, x_max), _ = self._parent.viewRange()
        x = min(max(x, x_min), x_max)
        return x

    def _mouse_move_event(self, ev):
        if self._move_x_start is None:
            return
        self.x_pos = self._ev_to_x(ev)

    def _move_start(self, ev):
        self._z_value_set(True)
        self._move_x_start = self.x_pos

    def _move_end(self, ev):
        if self._move_x_start is None:
            return
        x_end = self._ev_to_x(ev)
        self._z_value_set(False)
        x_start, self._move_x_start = self._move_x_start, None
        self.x_pos = x_start
        self._cmdp.invoke('!Widgets/Waveform/annotation/move', [self.signal_name, x_start, x_end])

    def mouseDragEvent(self, ev, axis=None):
        self._log.info('mouse drag: %s', ev)
        ev.accept()
        if ev.button() & QtCore.Qt.LeftButton:
            if ev.isStart():
                self._move_start(ev)
            self._mouse_move_event(ev)
            if ev.isFinish():
                self._move_end(ev)

    def _group_id_setter(self, value):
        x_pos = self.x_pos

        def fn():
            self._cmdp.invoke('!Widgets/Waveform/annotation/group_id', [self.signal_name, x_pos, value])
        return fn

    def _text(self):
        text = self._state['text']
        self._cmdp.invoke('!Widgets/Waveform/annotation/text_dialog', [self.signal_name, self.x_pos, text])

    def _show_text(self):
        visible = not self.isTextVisible()
        self._cmdp.invoke('!Widgets/Waveform/annotation/text_visible', [self.signal_name, self.x_pos, visible])

    def _remove(self, *args, **kwargs):
        self._cmdp.invoke('!Widgets/Waveform/annotation/remove', [self.signal_name, self.x_pos])

    def menu_exec(self, pos):
        menu = QtWidgets.QMenu()

        remove = menu.addAction('Set &Text')
        remove.triggered.connect(self._text)

        remove = menu.addAction('&Show Text')
        remove.setCheckable(True)
        remove.setChecked(self._text_item.isVisible())
        remove.triggered.connect(self._show_text)

        group_id = self._state['group_id']
        appearance_menu = menu.addMenu('&Appearance')
        appearance_group = QtWidgets.QActionGroup(appearance_menu)
        appearance_actions = []
        for idx, (_, name, shape) in enumerate(SHAPES_DEF):
            action = appearance_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(group_id == idx)
            action.triggered.connect(self._group_id_setter(name))
            appearance_group.addAction(action)
            appearance_actions.append(action)

        remove = menu.addAction('&Remove')
        remove.triggered.connect(self._remove)
        menu.exec_(pos)
