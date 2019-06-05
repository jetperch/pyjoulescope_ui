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

import pyqtgraph as pg
from PySide2 import QtCore
import logging


class SignalViewBox(pg.ViewBox):

    sigWheelZoomXEvent = QtCore.Signal(float, float)
    """A scroll wheel zoom event.
     
     :param x: The x-axis location in axis coordinates. 
     :param delta: The scroll wheel delta.
     """

    sigPanXEvent = QtCore.Signal(object, float)
    """A pan x event.
    
    :param x: The x-axis delta from the start in axis coordinates. 
    :param command: One of ['start', 'drag', 'finish', 'abort']
    """

    def __init__(self, name):
        self._name = name
        self._pan = None  # [total_x_delta in axis coordinates, last_x_scene_pos]
        self.log = logging.getLogger(__name__ + '.' + name)
        pg.ViewBox.__init__(self, enableMenu=False, enableMouse=False)

    def mouseClickEvent(self, ev, axis=None):
        self.log.debug('mouse click: %s' % (ev, ))
        ev.accept()
        p = self.mapSceneToView(ev.scenePos())
        x = p.x()

        if ev.button() & QtCore.Qt.RightButton:
            if self._pan:
                x_start, self._pan = self._pan, None
                self.sigPanXEvent.emit('abort', 0.0)

    def mouseDragEvent(self, ev, axis=None):
        self.log.debug('mouse drag: %s' % (ev, ))
        ev.accept()
        [x_min, x_max], [y_min, y_max] = self.viewRange()
        pmin = self.mapViewToScene(pg.Point(x_min, y_min))
        pmax = self.mapViewToScene(pg.Point(x_max, y_max))

        xview_range = x_max - x_min
        xscene_range = pmax.x() - pmin.x()
        pnow_x = ev.scenePos().x()

        if self._pan is not None:
            dx = (self._pan[1] - pnow_x) * xview_range / xscene_range
            self._pan[0] += dx
            self._pan[1] = pnow_x

        if ev.button() & QtCore.Qt.LeftButton:
            if ev.isFinish():
                if self._pan is not None:
                    pan_x, self._pan = self._pan[0], None
                    self.sigPanXEvent.emit('finish', pan_x)
            elif self._pan is None:
                self._pan = [0.0, pnow_x]
                self.sigPanXEvent.emit('start', 0.0)
            else:
                self.sigPanXEvent.emit('drag', self._pan[0])

    def wheelEvent(self, ev, axis=None):
        self.log.debug('mouse wheel: %s' % (ev,))
        ev.accept()
        p = self.mapSceneToView(ev.scenePos())
        self.sigWheelZoomXEvent.emit(p.x(), ev.delta())
