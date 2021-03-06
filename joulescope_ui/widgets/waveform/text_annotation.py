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
import pyqtgraph as pg
import logging

Z_ANNOTATION_NORMAL = 15


class TextAnnotation(QtGui.QGraphicsPathItem):
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
        QtGui.QGraphicsPathItem.__init__(self, parent)
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
        self._path = self._make_path()
        self.setPath(self._path)
        self.setFlags(self.flags() | self.ItemIgnoresTransformations)
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

    def _make_path(self):
        sz = self._state['size']
        path = QtGui.QPainterPath()
        path.moveTo(-sz, 0)
        path.lineTo(0, sz)
        path.lineTo(sz, 0)
        path.lineTo(0, -sz)
        path.lineTo(-sz, 0)
        return path

    def paint(self, p, *args):
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        super().paint(p, *args)

    def shape(self):
        return self._path

    def mouseClickEvent(self, ev):
        scene_pos = ev.scenePos()
        item_pos = self.mapFromScene(scene_pos)
        ev.accept()
        print(f'mouseClickEvent({ev})')
        print(f'boundingRect={self.boundingRect()}')
        print(f'shape={self.shape()}')
        print(f'item_pos={item_pos}')
