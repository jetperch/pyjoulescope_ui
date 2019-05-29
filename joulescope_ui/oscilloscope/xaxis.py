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

    def mouseClickEvent(self, event):
        if self.linkedView() is None:
            return
        if self.geometry().contains(event.scenePos()):
            if event.button() == QtCore.Qt.RightButton:
                event.accept()
                # self.scene().addParentContextMenus(self, self.menu, event)
                self.menu.popup(event.screenPos().toPoint())
