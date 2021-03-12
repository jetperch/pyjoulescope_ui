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


# Thank you to Selmen Dridi (https://www.upwork.com/freelancers/~011110a60ad4c49eb9)
# who investigated https://github.com/pyqtgraph/pyqtgraph/issues/1612
# and created this workaround.


import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np


class PathItem(pg.GraphicsObject):

    def __init__(self, parent=None):
        pg.GraphicsObject.__init__(self, parent)
        self.pathItem = QtGui.QGraphicsPathItem()
        self.pathItem.setParentItem(self)

        self._lastTransform = None
        self.angle = 0
        self.rotateAxis = None
        self._lastScene = None
        self.fill = pg.mkBrush(None)
        self.border = pg.mkPen(None)

    def setPosition(self, x, y):
        self.pathItem.setPos(x, y)

    def setPath(self, path):
        self.pathItem.setPath(path)

    def setBrush(self, brush):
        self.pathItem.setBrush(brush)

    def setZValue(self, zValue):
        self.pathItem.setZValue(zValue)

    def boundingRect(self):
        return self.pathItem.mapRectToParent(self.pathItem.boundingRect())

    def paint(self, p, *args):
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        self.pathItem.paint(p, *args)

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
        t.setMatrix(t.m11(), t.m12(), t.m13(), t.m21(), t.m22(), t.m23(), 0, 0, t.m33())

        # apply rotation
        angle = -self.angle
        if self.rotateAxis is not None:
            d = pt.map(self.rotateAxis) - pt.map(pg.Point(0, 0))
            a = np.arctan2(d.y(), d.x()) * 180 / np.pi
            angle += a
        t.rotate(angle)
        self.setTransform(t)
        self._lastTransform = pt
