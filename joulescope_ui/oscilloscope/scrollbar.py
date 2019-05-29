
from PySide2 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import logging


log = logging.getLogger(__name__)


class ScrollBar(pg.ViewBox):
    regionChange = QtCore.Signal(float, float)  # x_min, x_max

    def __init__(self, parent=None):
        pg.ViewBox.__init__(self, parent=parent, enableMouse=False)
        self._region = CustomLinearRegionItem()
        self._region.setZValue(-10)
        self.addItem(self._region)
        self._region.sigRegionChanged.connect(self.on_regionChange)

    def wheelEvent(self, ev, axis=None):
        ev.accept()

    def set_xview(self, x_min, x_max):
        self._region.setRegion([x_min, x_max])

    def set_xlimits(self, x_min, x_max):
        self.setXRange(x_min, x_max, padding=0)
        self._region.setBounds([x_min, x_max])

    def set_display_mode(self, mode):
        self._region.set_display_mode(mode)

    def wheelEvent(self, ev, axis=None):
        self._region.wheelEvent(ev)

    def mouseDragEvent(self, ev):
        # delegate to the RegionItem
        ev.currentItem = self._region
        self._region.mouseDragEvent(ev)

    @QtCore.Slot(object)
    def on_regionChange(self, obj):
        self.regionChange.emit(*self._region.getRegion())


class CustomLinearRegionItem(pg.LinearRegionItem):

    def __init__(self):
        pg.LinearRegionItem.__init__(self, orientation='vertical', swapMode='sort')
        self._mode = 'normal'
        self._x_down = None
        self._x_range_start = None

    def on_mouse_drag_event(self, ev):
        if not self.movable or int(ev.button() & QtCore.Qt.LeftButton) == 0:
            return
        ev.accept()

        x_pos = ev.pos().x()
        if ev.isStart():
            self._x_down = ev.buttonDownPos().x()
            self._x_range_start = [l.pos().x() for l in self.lines]
            self.moving = True

        if not self.moving:
            return

        self.lines[0].blockSignals(True)  # only want to update once
        delta = x_pos - self._x_down
        if self._mode == 'realtime':
            self.lines[0].setPos(self._x_range_start[0] + delta)
        else:
            for i, l in enumerate(self.lines):
                l.setPos(self._x_range_start[i] + delta)
        self.lines[0].blockSignals(False)
        self.prepareGeometryChange()

        if ev.isFinish():
            self.moving = False
            self.sigRegionChangeFinished.emit(self)
        else:
            self.sigRegionChanged.emit(self)

    def mouseDragEvent(self, ev):
        self.on_mouse_drag_event(ev)

    def set_display_mode(self, mode):
        if self._mode == mode:
            return
        log.info('set_display_mode(%s)', mode)
        self._mode = mode
        if mode == 'realtime':
            r1, r2 = self.getRegion()
            _, x_max = self.lines[0].bounds()
            rdelta = abs(r2 - r1)
            self.setRegion([x_max - rdelta, x_max])
            self.lines[1].setMovable(False)
        elif mode in ['normal', None]:
            self.lines[1].setMovable(True)
        else:
            raise RuntimeError('invalid mode')
        self.sigRegionChanged.emit(self)

    def wheelEvent(self, ev):
        gain = 0.7 ** (ev.delta() / 120)
        log.info('wheelEvent(delta=%s) gain=>%s', ev.delta(), gain)
        r1, r2 = self.getRegion()
        x_min, x_max = self.lines[0].bounds()
        rdelta = r2 - r1
        rdelta *= gain
        if self._mode == 'realtime':
            ra = x_max - rdelta
            rb = x_max
            ra = max(ra, x_min)
        else:
            rc = (r1 + r2) / 2
            ra = max(rc - rdelta / 2, x_min)
            rb = min(rc + rdelta / 2, x_max)
        self.setRegion([ra, rb])
        ev.accept()
