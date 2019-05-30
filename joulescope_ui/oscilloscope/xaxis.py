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
import logging


log = logging.getLogger(__name__)


class AxisMenu(QtGui.QMenu):

    def __init__(self):
        QtGui.QMenu.__init__(self)
        self.annotations = self.addMenu('&Annotations')

        self.single_marker = QtGui.QAction('&Single Marker')
        self.annotations.addAction(self.single_marker)

        self.dual_markers = QtGui.QAction('&Dual Markers')
        self.annotations.addAction(self.dual_markers)


class XAxis(pg.AxisItem):

    def __init__(self):
        pg.AxisItem.__init__(self, orientation='top')
        self.menu = AxisMenu()
        self.menu.single_marker.triggered.connect(self.on_singleMarker)
        self.menu.dual_markers.triggered.connect(self.on_dualMarkers)
        self._markers = {}
        self._marker_pairs = {}
        self._proxy = None

    def on_singleMarker(self):
        idx = 0
        while True:
            if idx not in self._markers:
                marker = self.marker_add(idx, shape='full')
                xa, xb = self.range
                marker.set_pos((xa + xb) / 2)
                marker.moving = True
                break
            idx += 1

    def on_dualMarkers(self):
        letter = 'A'
        while ord(letter) <= ord('Z'):
            if letter not in self._markers:
                xa, xb = self.range
                xc = (xa + xb) / 2
                xr = (xb - xa) * 0.1
                mleft = self.marker_add(letter + '1', shape='left')
                mleft.set_pos(xc - xr)
                mright = self.marker_add(letter + '2', shape='right')
                mright.set_pos(xc + xr)
                mleft.pair = mright
                mright.pair = mleft
                mleft.moving = True
                self._marker_pairs[letter] = [mleft, mright]
                break
            letter = chr(ord(letter) + 1)

    def linkedViewChanged(self, view, newRange=None):
        pg.AxisItem.linkedViewChanged(self, view=view, newRange=newRange)
        for marker in self._markers.values():
            marker.viewTransformChanged()

    def marker_add(self, name, shape):
        self.marker_remove(name)
        marker = Marker(name=name, x_axis=self, shape=shape)
        scene = self.scene()
        if scene is not None and scene is not marker.scene():
            scene.addItem(marker)
        marker.setParentItem(self.parentItem())

        self.scene().addItem(marker)
        self._markers[name] = marker
        marker.show()
        marker.sigRemoveRequest.connect(self._on_marker_remove)
        if self._proxy is None:
            self._proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._mouseMoveEvent)
        return marker

    @QtCore.Slot(object)
    def _on_marker_remove(self, marker: Marker):
        self.marker_remove(marker.name)

    def marker_remove(self, name):
        marker = self._markers.pop(name, None)
        if marker is not None:
            marker.sigRemoveRequest.disconnect(self._on_marker_remove)
            marker.setVisible(False)
            # marker.prepareGeometryChange()
            # self.scene().removeItem(marker)  # removing from scene causes crash... ugh
            if marker.pair:
                other, marker.pair = marker.pair, None
                other.pair = None
                self.marker_remove(other.name)
                self._marker_pairs.pop(name[:1], None)

    def markers(self):
        return list(self._markers.values())

    def markers_single(self):
        m = self._markers.values()
        m = [x for x in m if not isinstance(x.name, str)]
        return m

    def markers_dual(self):
        return self._marker_pairs.values()

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

        for marker in self._markers.values():
            if marker.moving:
                marker.set_pos(x)

    def mouseClickEvent(self, event):
        if self.linkedView() is None:
            return
        log.info('mouseClickEvent(%s)', event)
        if self.geometry().contains(event.scenePos()):
            if event.button() == QtCore.Qt.RightButton:
                event.accept()
                # self.scene().addParentContextMenus(self, self.menu, event)
                self.menu.popup(event.screenPos().toPoint())
