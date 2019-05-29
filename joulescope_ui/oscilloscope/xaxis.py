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

from PySide2 import QtGui, QtCore, QtWidgets
from .marker import Marker
import pyqtgraph as pg


class AxisMenu(QtGui.QMenu):

    def __init__(self):
        QtGui.QMenu.__init__(self)
        self._annotations = self.addMenu('&Annotations')

        self._cursor = QtGui.QAction('&Cursor')
        self._cursor.setCheckable(True)
        self._cursor.setChecked(True)
        self._annotations.addAction(self._cursor)

        self._dual = QtGui.QAction('&Markers')
        self._dual.setCheckable(True)
        self._dual.setChecked(False)
        self._annotations.addAction(self._dual)


class XAxis(pg.AxisItem):

    def __init__(self):
        pg.AxisItem.__init__(self, orientation='top')
        self.menu = AxisMenu()
        self._markers = {}
        self._proxy = None

    def marker_add(self, name, shape):
        self.marker_remove(name)
        marker = Marker(x_axis=self, shape=shape)
        self.scene().addItem(marker)
        self._markers[name] = marker
        marker.show()
        if self._proxy is None:
            self._proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._mouseMoveEvent)
        return marker

    def marker_remove(self, name):
        marker = self._markers.get(name)
        if marker is not None:
            self.scene().removeItem(marker)
            del self._markers[name]

    def _mouseMoveEvent(self, ev):
        """Handle mouse movements for every mouse movement within the widget"""
        pos = ev[0]
        b1 = self.geometry()
        if pos.y() < b1.top():
            return
        p = self.linkedView().mapSceneToView(pos)
        x = p.x()
        x_min, x_max = self.range
        if x < x_min:
            x = x_min
        elif x > x_max:
            x = x_max

        cursor = self._markers.get('cursor')
        if cursor:
            cursor.set_pos(x)

    def mouseClickEvent(self, event):
        if self.linkedView() is None:
            return
        if self.geometry().contains(event.scenePos()):
            if event.button() == QtCore.Qt.RightButton:
                event.accept()
                # self.scene().addParentContextMenus(self, self.menu, event)
                self.menu.popup(event.screenPos().toPoint())
