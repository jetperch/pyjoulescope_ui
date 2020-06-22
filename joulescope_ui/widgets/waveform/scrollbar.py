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
WHEEL_TICK = 120.0


def _wheel_to_x_gain(delta):
    return 0.7 ** (delta / WHEEL_TICK)


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

    def __init__(self, parent, cmdp):
        pg.ViewBox.__init__(self, parent=parent, enableMenu=False, enableMouse=False)
        self._cmdp = cmdp
        self._region = CustomLinearRegionItem(self, self.regionChange.emit)
        self._region.setZValue(-10)
        self.addItem(self._region)
        self._label = pg.TextItem(html='<div><span style="color: #FFF;">Time (seconds)</span></div>', anchor=(0.5, 0.5))
        self.addItem(self._label, ignoreBounds=True)
        self._cmdp.subscribe('Device/#state/sampling_frequency',
                             self._on_device_state_sampling_frequency,
                             update_now=True)
        cmdp.register('!Widgets/Waveform/x-axis/zoom', self._cmd_waveform_xaxis_zoom,
                      brief='Zoom the x-axis around the center.',
                      detail='value is x-axis zoom in steps.')
        cmdp.register('!Widgets/Waveform/x-axis/pan', self._cmd_waveform_xaxis_pan,
                      brief='Pan the x-axis in relative steps.',
                      detail='1 pans to the right, -1 to the left.')
        cmdp.register('!Widgets/Waveform/x-axis/range', self._cmd_waveform_xaxis_range,
                      brief='Set the x-axis to the specified range.',
                      detail='The value is (x1, x2).')
        cmdp.register('!Widgets/Waveform/x-axis/zoom_all', self._cmd_waveform_xaxis_zoom_all,
                      brief='Zoom to the full extents.')

    def set_xview(self, x_min, x_max):
        self._region.setRegion([x_min, x_max])

    def get_xview(self):
        return self._region.getRegion()

    def set_xlimits(self, x_min, x_max):
        self.setXRange(x_min, x_max, padding=0)
        self._region.setBounds([x_min, x_max])
        self.resizeEvent(None)

    def set_display_mode(self, mode):
        return self._region.set_display_mode(mode)

    def _on_device_state_sampling_frequency(self, topic, data):
        self._region.set_sampling_frequency(data)

    @QtCore.Slot(float, float)
    def on_wheelZoomX(self, x: float, delta: float):
        self._region.on_wheelZoomX(x, delta)

    def _cmd_waveform_xaxis_zoom(self, topic, value):
        previous = self._region.getRegion()
        x1, x2 = self.get_xview()
        xc = (x1 + x2) / 2
        self.on_wheelZoomX(xc, value * WHEEL_TICK)
        return (topic, value), ('!Widgets/Waveform/x-axis/range', previous)

    def _cmd_waveform_xaxis_pan(self, topic, value):
        previous = self._region.getRegion()
        x1, x2 = self.get_xview()
        k = (x2 - x1) * 0.25 * value
        self._region.setRegion((x1 + k, x2 + k))
        return (topic, value), ('!Widgets/Waveform/x-axis/range', previous)

    def _cmd_waveform_xaxis_range(self, topic, value):
        previous = self._region.getRegion()
        if self._region.mode == 'realtime':
            value = min(value), previous[-1]
        self._region.setRegion(value)
        return (topic, value), ('!Widgets/Waveform/x-axis/range', previous)

    def _cmd_waveform_xaxis_zoom_all(self, topic, value):
        self._region.on_zoom_all()

    def wheelEvent(self, ev, axis=None):
        self._region.wheelEvent(ev)

    @QtCore.Slot(object, float)
    def on_panX(self, command: str, x: float):
        self._region.on_panX(command, x)

    def mouseDragEvent(self, ev):
        # delegate to the RegionItem
        ev.currentItem = self._region
        self._region.mouseDragEvent(ev)

    def mouseClickEvent(self, ev, axis=None):
        self._region.mouseClickEvent(ev)

    def request_x_change(self):
        self._region.on_regionChange()

    def resizeEvent(self, ev):
        if ev is not None:
            super().resizeEvent(ev)
        try:
            c = self.geometry().center()
            c = self.mapToView(c)
            self._label.setPos(c.x(), c.y())
        except Exception:
            pass

    def zoom_to_point(self, x):
        self._region.zoom_to_point(x)

    def zoom_to_range(self, x1, x2):
        self._region.zoom_to_range(x1, x2)


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
        self._x_pan = None
        self._x_range_start = None
        self._sampling_frequency = None
        self._callback = callback
        self.sigRegionChanged.connect(self.on_regionChange)

    @property
    def minimum_width(self):
        if self._sampling_frequency is not None and self._sampling_frequency > 0:
            return 10.0 / self._sampling_frequency
        else:
            return 0.001

    def set_sampling_frequency(self, freq):
        self._sampling_frequency = freq
        self.on_regionChange(None)

    def mouseDragEvent(self, ev):
        if not self.movable or int(ev.button() & QtCore.Qt.LeftButton) == 0:
            return
        ev.accept()
        x_pos = ev.pos().x()
        if ev.isFinish():
            x_down, self._x_down = self._x_down, None
            self.on_panX('finish', x_pos - x_down)
        elif ev.isStart():
            self._x_down = ev.buttonDownPos().x()
            self.on_panX('start', x_pos - self._x_down)
        else:
            self.on_panX('drag', x_pos - self._x_down)

    def mouseClickEvent(self, ev, axis=None):
        ev.accept()
        if ev.button() & QtCore.Qt.RightButton:
            if self._x_down:
                self._x_down = None
                self.sigPanXEvent.emit('abort', 0.0)

    @QtCore.Slot(object, float, float)
    def on_panX(self, command: str, x: float):
        log.info('pan(%s, %s)', command, x)
        if command == 'finish':
            if self._x_pan is not None:
                pass
            self._x_pan = None
            self._x_range_start = None
            self.sigRegionChangeFinished.emit(self)
            return
        elif command == 'start':
            self._x_pan = x
            self._x_range_start = [l.pos().x() for l in self.lines]

        if self._x_pan is None:
            return

        x_min, x_max = self.get_bounds()
        delta = x - self._x_pan
        if self.mode == 'realtime':
            r = self._x_range_start[0] + delta
            self.setRegion([r, x_max])
        else:
            ra = self._x_range_start[0] + delta
            rb = self._x_range_start[1] + delta
            self.setRegion([ra, rb])

    def get_bounds(self):
        x_min, x_max = self.lines[0].bounds()
        return x_min, x_max

    def set_display_mode(self, mode):
        if self.mode == mode:
            return False
        log.info('set_display_mode(%s)', mode)
        self.mode = mode
        if self.mode == 'realtime':
            self.lines[1].setMovable(False)
            self.setRegion()
        elif self.mode in ['normal', 'buffer', None]:
            self.lines[1].setMovable(True)
        else:
            raise RuntimeError('invalid mode')
        return True

    def _wheel_to_gain(self, delta):
        gain = 0.7 ** (delta / 120.0)
        self.setRegion(gain=gain)

    @QtCore.Slot(float, float)
    def on_wheelZoomX(self, x, delta):
        ra, rb = self.getRegion()
        gain = _wheel_to_x_gain(delta)
        if self.mode == 'realtime':
            self.setRegion(gain=gain)
        else:
            if x < ra:
                x = ra
            elif x > rb:
                x = rb
            pa = x + gain * (ra - x)
            pb = x + gain * (rb - x)
            self.setRegion(rgn=[pa, pb])

    def wheelEvent(self, ev):
        gain = _wheel_to_x_gain(ev.delta())
        log.info('wheelEvent(delta=%s) gain=>%s', ev.delta(), gain)
        self.setRegion(gain=gain)
        ev.accept()

    def on_zoom_all(self):
        x_min, x_max = self.lines[0].bounds()
        self._region_update(x_min, x_max)

    def zoom_to_point(self, x):
        x_min, x_max = self.lines[0].bounds()  # allowed range
        if self.mode == 'realtime':
            if x > x_max or x < x_min:
                return
            a = x - (x_max - x)
            a = max(a, x_min)
            self._region_update(a, x_max)
        else:
            ra, rb = self.getRegion()
            d = (rb - ra) / 2
            self._region_update(x - d, x + d)

    def zoom_to_range(self, x1, x2):
        if x2 < x1:
            x1, x2 = x2, x1
        if self.mode == 'realtime':
            self.zoom_to_point((x1 + x2) / 2)
        else:
            m = (x2 - x1) * 0.1
            self._region_update(x1 - m, x2 + m)

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
        log.info('on_regionChange(%s, %s) pixels=%s', x_min, x_max, w)
        x_count = int(w) + 1

        if self._sampling_frequency is not None and self._sampling_frequency > 0:
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
