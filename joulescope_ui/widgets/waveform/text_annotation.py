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
from typing import Dict
import weakref


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
        self._move_start_point = None
        y = state.get('y')
        if y is not None:
            y = float(y)

        my_id = state.get('id')
        if my_id is None:  # assign an id
            my_id = id(self)
            while my_id in _registry:
                my_id += 1
        elif my_id in _registry:
            raise RuntimeError(f'id {my_id} already in annotation registry')

        self._state = {
            'id': my_id,
            'signal_name': state['signal_name'],
            'x': float(state['x']),
            'y': y,
            'group_id': 0,
            'text': state.get('text'),
            'text_visible': True,
            'size': state.get('size', 6),
        }
        _registry[my_id] = weakref.ref(self)
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
    def state(self):
        return self._state.copy()

    @property
    def id(self):
        return self._state['id']

    @property
    def signal_name(self):
        return self._state['signal_name']

    @property
    def x_pos(self):
        return self._state['x']

    def _y_display_pos(self):
        y = self._state['y']
        if y is None:
            _, (y_min, y_max) = self._parent.viewRange()
            y = (y_max + y_min) / 2
        return y

    @x_pos.setter
    def x_pos(self, value):
        x_pos = float(value)
        self._state['x'] = x_pos
        self.setPos(self._state['x'], self._y_display_pos())

    @property
    def y_pos(self):
        return self._state['y']

    @y_pos.setter
    def y_pos(self, value):
        if value is not None:
            value = float(value)
        self._state['y'] = value
        self.setPos(self._state['x'], self._y_display_pos())

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

    def _recalculate_path(self):
        path = SHAPES_MAP[self._state['group_id']]
        tr = QtGui.QTransform()
        sz = self._state['size']
        tr.scale(sz, sz)
        path = tr.map(path)
        self._pathItem.setPath(path)
        self._update_colors()

    @group_id.setter
    def group_id(self, value):
        group_id = value
        s_len = len(SHAPES)
        if isinstance(group_id, int) and not 0 <= group_id < s_len:
            group_id = group_id % s_len
        self._state['group_id'] = SHAPES_IDX[group_id]
        self._recalculate_path()

    def update(self, state):
        undo = {}
        for key, value in state.items():
            if key not in self._state:
                continue
            old_value = self._state[key]
            if old_value == value:
                continue
            if key in ['id', 'signal_name']:
                continue  # ignore, update not allowed
            undo[key] = old_value
            if key == 'x':
                self.x_pos = value
            elif key == 'y':
                self.y_pos = value
            elif key == 'group_id':
                self.group_id = value
            elif key == 'text':
                self.text = value
            elif key == 'text_visible':
                self.setTextVisible(bool(value))
            elif key == 'size':
                self._state['size'] = float(value)
                self._recalculate_path()
        return [self.id, undo]

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
        self.setPos(self.x_pos, self._y_display_pos())
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

    def _ev_to_point(self, ev):
        pos = ev.scenePos()
        p = self._parent.mapSceneToView(pos)
        x = p.x()
        (x_min, x_max), (y_min, y_max) = self._parent.viewRange()
        x = min(max(x, x_min), x_max)
        y = p.y()
        y = min(max(y, y_min), y_max)
        return x, y

    def _mouse_move_event(self, ev):
        if self._move_start_point is None:
            return
        self.x_pos, y = self._ev_to_point(ev)
        if self._state['y'] is not None:
            self.y_pos = y

    def _move_start(self, ev):
        self._z_value_set(True)
        self._move_start_point = self.x_pos, self.y_pos

    def _move_end(self, ev):
        if self._move_start_point is None:
            return
        x_end, y_end = self._ev_to_point(ev)
        self._z_value_set(False)
        [x_start, y_start], self._move_start_point = self._move_start_point, None
        self.x_pos = x_start
        self.y_pos = y_start
        if self._state['y'] is None:
            y_end = None
        self._cmdp.invoke('!Widgets/Waveform/annotation/update', [self.id, {'x': x_end, 'y': y_end}])

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

        def fn():
            self._cmdp.invoke('!Widgets/Waveform/annotation/update', [self.id, {'group_id': value}])
        return fn

    def _edit_text(self):
        self._cmdp.invoke('!Widgets/Waveform/annotation/dialog', self.id)

    def _show_text(self):
        visible = not self.isTextVisible()
        self._cmdp.invoke('!Widgets/Waveform/annotation/update', [self.id, {'text_visible': visible}])

    def _center_y(self):
        if self._state['y'] is None:
            y_pos = self._y_display_pos()
        else:
            y_pos = None
        self._cmdp.invoke('!Widgets/Waveform/annotation/update', [self.id, {'y': y_pos}])

    def _remove(self, *args, **kwargs):
        self._cmdp.invoke('!Widgets/Waveform/annotation/remove', [self.id])

    def menu_exec(self, pos):
        menu = QtWidgets.QMenu()

        set_text = menu.addAction('&Edit text')
        set_text.triggered.connect(self._edit_text)

        show_text = menu.addAction('&Show Text')
        show_text.setCheckable(True)
        show_text.setChecked(self._text_item.isVisible())
        show_text.triggered.connect(self._show_text)

        center_y = menu.addAction('&Center Y')
        center_y.setCheckable(True)
        center_y.setChecked(self._state['y'] is None)
        center_y.triggered.connect(self._center_y)

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


# Dict[int, weakref.ReferenceType[TextAnnotation]] fails on Python 3.8
_registry: Dict[int, weakref.ReferenceType] = {}


def find(instance_id) -> TextAnnotation:
    """Find the text annotation by id.

    :param instance_id: The annotation identifier.
    :return: The TextAnnotation instance.
    :raises KeyError: If the instance is not found.
    """
    if isinstance(instance_id, TextAnnotation):
        instance_id = instance_id.id
    ref = _registry.get(instance_id)
    if ref is not None:
        obj = ref()
        if obj is not None:
            return obj
    raise KeyError(f'annotation not found with id={instance_id}')


def remove(instance_id):
    if instance_id in _registry:
        _registry.pop(instance_id)
