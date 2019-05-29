
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
