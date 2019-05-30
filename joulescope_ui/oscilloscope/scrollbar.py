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

from PySide2 import QtCore
import pyqtgraph as pg
import weakref
from typing import Callable
import logging


log = logging.getLogger(__name__)


class ScrollBar(pg.ViewBox):
    """ScrollBar for x-axis range control.

    :param parent: The parent widget.
    """

    regionChange = QtCore.Signal(float, float, int)  # x_min, x_max, x_count
    """The signal when the x-axis region changes.
    
    :param x_min: The minimum x-axis range value in seconds.
    :param x_max: The maximum x-axis range value in seconds.
    :parma x_count: The number of samples to provide between 
        x_min and x_max, inclusive.
    """

    def __init__(self, parent=None):
        pg.ViewBox.__init__(self, parent=parent, enableMenu=False, enableMouse=False)
        self._region = CustomLinearRegionItem(self, self.regionChange.emit)
        self._region.setZValue(-10)
        self.addItem(self._region)

    def wheelEvent(self, ev, axis=None):
        ev.accept()

    def set_xview(self, x_min, x_max):
        self._region.setRegion([x_min, x_max])

    def set_xlimits(self, x_min, x_max):
        self.setXRange(x_min, x_max, padding=0)
        self._region.setBounds([x_min, x_max])

    def set_display_mode(self, mode):
        self._region.set_display_mode(mode)

    def set_sampling_frequency(self, freq):
        self._region.set_sampling_frequency(freq)

    def wheelEvent(self, ev, axis=None):
        self._region.wheelEvent(ev)

    def mouseDragEvent(self, ev):
        # delegate to the RegionItem
        ev.currentItem = self._region
        self._region.mouseDragEvent(ev)


class CustomLinearRegionItem(pg.LinearRegionItem):
    """Custom linear region that enforces x-axis zoom constraints

    :param parent: The parent :class:1ScrollBar1.
    :param callback: The function(x_min, x_max, x_count) called on
        view updates.
    """

    def __init__(self, parent: ScrollBar, callback: Callable[[float, float, int], None]):
        pg.LinearRegionItem.__init__(self, orientation='vertical', swapMode='block')
        self._parent = weakref.ref(parent)
        self.mode = 'normal'
        self._x_down = None
        self._x_range_start = None
        self._sampling_frequency = None
        self._callback = callback
        self.sigRegionChanged.connect(self.on_regionChange)

    @property
    def minimum_width(self):
        if self._sampling_frequency is not None:
            return 10.0 / self._sampling_frequency
        else:
            return 0.001

    def set_sampling_frequency(self, freq):
        self._sampling_frequency = freq

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

        x_min, x_max = self.get_bounds()
        delta = x_pos - self._x_down
        if self.mode == 'realtime':
            r = self._x_range_start[0] + delta
            self.setRegion([r, x_max])
        else:
            ra = self._x_range_start[0] + delta
            rb = self._x_range_start[1] + delta
            self.setRegion([ra, rb])

        if ev.isFinish():
            self.moving = False
            self.sigRegionChangeFinished.emit(self)

    def mouseDragEvent(self, ev):
        self.on_mouse_drag_event(ev)

    def get_bounds(self):
        x_min, x_max = self.lines[0].bounds()
        return x_min, x_max

    def set_display_mode(self, mode):
        if self.mode == mode:
            return
        log.info('set_display_mode(%s)', mode)
        self.mode = mode
        if self.mode == 'realtime':
            self.lines[1].setMovable(False)
            self.setRegion()
        elif self.mode in ['normal', None]:
            self.lines[1].setMovable(True)
        else:
            raise RuntimeError('invalid mode')

    def wheelEvent(self, ev):
        gain = 0.7 ** (ev.delta() / 120)
        log.info('wheelEvent(delta=%s) gain=>%s', ev.delta(), gain)
        self.setRegion(gain=gain)
        ev.accept()

    def _region_update(self, ra, rb, skip_line_update=None):
        """Update the currently selected region.

        :param ra: The left-most x-axis time.
        :param rb: The right-most x-axis time.
        :param skip_line_update: When true, do not update the lines to allow
            for continuous dragging.  This function reserves the right to
            ignore this option when required to enforce bounds.
        """
        x_min, x_max = self.lines[0].bounds()  # allowed range

        # enforce minimum width requirement
        min_width = self.minimum_width
        rdelta = rb - ra
        if rdelta < min_width:
            rdelta = min_width
            skip_line_update = False  # force update since changing

        # Compute new locations
        if self.mode == 'realtime':
            ra = x_max - rdelta
            if ra < x_min:
                ra = x_min
                skip_line_update = False
            rb = x_max
        else:
            rc = (ra + rb) / 2
            ra = rc - rdelta / 2
            rb = rc + rdelta / 2
            if rb > x_max:
                skip_line_update = False
                ra = max(ra - (rb - x_max), x_min)
                rb = x_max
            elif ra < x_min:
                skip_line_update = False
                rb = min(rb + (x_min - ra), x_max)
                ra = x_min
        if not bool(skip_line_update):
            self.blockLineSignal = True
            self.lines[0].setValue(ra)
            self.lines[1].setValue(rb)
            self.blockLineSignal = False
        self.prepareGeometryChange()
        self.sigRegionChanged.emit(self)

    def setRegion(self, rgn=None, gain=None, skip_line_update=None):
        if rgn is None:
            ra, rb = self.getRegion()
        else:
            ra, rb = rgn
        if ra > rb:
            ra, rb = rb, ra
        if gain is not None:
            rc = (rb + ra) / 2
            rd = (rb - ra) * gain / 2
            ra = rc - rd
            rb = rc + rd

        if self.lines[0].value() == ra and self.lines[1].value() == rb:
            return
        self._region_update(ra, rb)

    def lineMoved(self, i):
        if self.blockLineSignal:
            return
        ra = self.lines[0].value()
        rb = self.lines[1].value()
        if ra > rb:
            self._region_update(ra, rb)
        else:
            self._region_update(ra, rb, skip_line_update=True)

    @QtCore.Slot(object)
    def on_regionChange(self, obj=None):
        x_min, x_max = self.getRegion()
        w = self._parent().geometry().width()
        x_count = int(w) + 1

        if self._sampling_frequency is not None:
            # adjust to ease processing
            x_range_orig = x_max - x_min
            samples = x_range_orig * self._sampling_frequency
            if samples < 10:
                samples = 10
            if samples < x_count:
                samples_per_pixel = 1 / int(x_count / samples)
            else:
                samples_per_pixel = int(samples / x_count)
            pixel_freq = self._sampling_frequency / samples_per_pixel
            x_count = int(x_range_orig * pixel_freq)

        if self._callback:
            self._callback(x_min, x_max, x_count)

    def viewTransformChanged(self):
        self.on_regionChange()
