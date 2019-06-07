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
import pyqtgraph as pg
import logging


log = logging.getLogger(__name__)


class AxisMenu(QtGui.QMenu):

    def __init__(self):
        QtGui.QMenu.__init__(self)
        self.range_group = QtGui.QActionGroup(self)
        self.range_group.setExclusive(True)

        self.range_auto = QtGui.QAction(
            '&Auto Range', self.range_group,
            checkable=True,
            statusTip='Automatically adjust the y-axis range to show all visible data.'
        )
        self.range_auto.setChecked(True)
        self.addAction(self.range_auto)
        self.range_group.addAction(self.range_auto)

        self.range_manual = QtGui.QAction(
            '&Manual Range', self.range_group,
            checkable=True,
            statusTip='Manually zoom and pan the y-axis range.'
        )
        self.addAction(self.range_manual)
        self.range_group.addAction(self.range_manual)


class YAxis(pg.AxisItem):

    def __init__(self, name):
        pg.AxisItem.__init__(self, orientation='left')
        self._name = name
        self.log = logging.getLogger(__name__ + '.' + name)
        self.menu = AxisMenu()
        self._auto_range = True
        self.menu.range_auto.triggered.connect(self._auto_range_enable)
        self.menu.range_manual.triggered.connect(self._auto_range_disable)
        self._markers = {}
        self._proxy = None
        self._popup_menu_pos = None

    def _auto_range_enable(self):
        self.log.info('auto range enable')
        self._auto_range = True

    def _auto_range_disable(self):
        self.log.info('auto range disable')
        self._auto_range = False

    def mouseClickEvent(self, event, axis=None):
        if self.linkedView() is None:
            return
        pos = event.scenePos()
        if self.geometry().contains(pos):
            self.log.info('mouseClickEvent(%s)', event)
            event.accept()
            if event.button() == QtCore.Qt.RightButton:
                self._popup_menu_pos = self.linkedView().mapSceneToView(pos)
                # self.scene().addParentContextMenus(self, self.menu, event)
                self.menu.popup(event.screenPos().toPoint())

    def mouseDragEvent(self, event, axis=None):
        pos = event.scenePos()
        if self.geometry().contains(pos):
            self.log.info('mouseDragEvent(%s)', event)
            event.accept()

    def wheelEvent(self, event, axis=None):
        pos = event.scenePos()
        if self.geometry().contains(pos):
            self.log.info('wheelEvent(%s)', event)
            event.accept()
        else:
            event.setAccepted(False)
        # p = self.mapSceneToView(ev.scenePos())
        # self.sigWheelZoomXEvent.emit(p.x(), ev.delta())
