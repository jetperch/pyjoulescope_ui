# This code originates from pyqtgraph
# Significant edits made!

# Copyright (c) 2012  University of North Carolina at Chapel Hill
# Luke Campagnola    ('luke.campagnola@%s.com' % 'gmail')
#
# The MIT License
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# See https://github.com/pyqtgraph/pyqtgraph
# pyqtgraph/Qt/__init__.py
# pyqtgraph/graphicsItems/PlotCurveItem.py

from PySide6 import QtCore
import shiboken6
import itertools
import numpy as np


_OVERSIZE_FRACT = 1.10


def clip_y(x, y, y_min, y_max):
    """Clip a polyline to [y_min, y_max] without moving its in-range part.

    :param x: The x-axis values.
    :param y: The y-axis values.
    :param y_min: The minimum y-axis value.
    :param y_max: The maximum y-axis value.
    :return: The clipped (x, y) as np.float64 arrays.

    Each run of consecutive points beyond the same limit becomes two points
    on that limit, at the x where the original segments into and out of the
    run cross it.  Qt drops paths that exceed +/-32767 pixels  #352.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    side = (y > y_max).astype(np.int8) - (y < y_min).astype(np.int8)
    out = side != 0
    if not np.any(out):
        return x, y
    n = len(y)
    change = side[1:] != side[:-1]
    start = out.copy()
    start[1:] &= change
    end = out.copy()
    end[:-1] &= change
    limit = np.where(side > 0, y_max, y_min)
    counts = np.where(out, start.astype(np.int64) + end, 1)
    pos = np.cumsum(counts) - counts
    x_out = np.empty(pos[-1] + counts[-1], dtype=np.float64)
    y_out = np.empty_like(x_out)
    keep = ~out
    x_out[pos[keep]] = x[keep]
    y_out[pos[keep]] = y[keep]

    # run start crosses from the previous point, run end crosses to the next point
    for idx, step in [(np.nonzero(start)[0], -1), (np.nonzero(end)[0], 1)]:
        x_lim = x[idx]  # first/last point: no neighbor, keep x
        has_neighbor = (idx > 0) if step < 0 else (idx < n - 1)
        i = idx[has_neighbor]
        j = i + step
        x_lim[has_neighbor] = x[j] + (limit[i] - y[j]) * (x[i] - x[j]) / (y[i] - y[j])
        dst = pos[idx] + (start[idx] if step > 0 else 0)  # a one-point run emits start, end
        x_out[dst] = x_lim
        y_out[dst] = limit[idx]
    return x_out, y_out


class PrimitiveArray:

    def __init__(self, Klass, nfields):
        self._Klass = Klass
        self._nfields = nfields
        self._ndarray = None

    def __len__(self):
        if self._ndarray is None:
            return 0
        return len(self._ndarray)

    def resize(self, size):
        if self._ndarray is not None:
            sz = len(self._ndarray)
            if size <= sz:
                return
            # print(f'resize {sz} -> {size}')

        # size = int(size * _OVERSIZE_FRACT)
        array = np.empty((size, self._nfields), dtype=np.float64)
        self._objs = list(map(shiboken6.wrapInstance,
            itertools.count(array.ctypes.data, array.strides[0]),
            itertools.repeat(self._Klass, array.shape[0])))

        self._ndarray = array

    def ndarray(self):
        return self._ndarray

    def instances(self):
        return self._objs


class PointsF:

    def __init__(self):
        self.array = PrimitiveArray(QtCore.QPointF, 2)

    def _get(self, size):
        self.array.resize(size)
        return self.array.instances(), self.array.ndarray()

    def set_fill(self, x, y_min, y_max, y_limits=None):
        k = len(x)
        assert(k == len(y_min))
        assert(k == len(y_max))
        if y_limits is None:
            x_min, x_max = x, x
        else:
            x_min, y_min = clip_y(x, y_min, *y_limits)
            x_max, y_max = clip_y(x, y_max, *y_limits)
        k = len(x_min)
        nsegs = k + len(x_max)
        segs, memory = self._get(nsegs)

        memory[:k, 0] = x_min
        memory[:k, 1] = y_min
        memory[k:nsegs, 0] = x_max[::-1]
        memory[k:nsegs, 1] = y_max[::-1]
        return segs[:nsegs]

    def set_line(self, x, y, y_limits=None):
        k = len(x)
        assert(k == len(y))
        if y_limits is not None:
            x, y = clip_y(x, y, *y_limits)
            k = len(x)
        segs, memory = self._get(k)

        memory[:k, 0] = x
        memory[:k, 1] = y
        return segs[:k]
