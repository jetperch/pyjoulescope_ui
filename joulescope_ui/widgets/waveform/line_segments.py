# This code is taken from pyqtgraph
# Edits have been made to simply for PySide6 only

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

from PySide6 import QtCore, QtGui, QtWidgets
import shiboken6
import numpy as np
import ctypes
import itertools
import numpy as np


def have_native_drawlines_array():
    size = 10
    line = QtCore.QLineF(0, 0, size, size)
    qimg = QtGui.QImage(size, size, QtGui.QImage.Format.Format_RGB32)
    qimg.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(qimg)
    painter.setPen(QtCore.Qt.GlobalColor.white)

    try:
        painter.drawLines(line, 1)
    except TypeError:
        success = False
    else:
        success = True
    finally:
        painter.end()

    return success


_have_native_drawlines_array = False  # have_native_drawlines_array()


class PrimitiveArray:
    # Note: This class is an internal implementation detail and is not part
    #       of the public API.
    #
    # QPainter has a C++ native API that takes an array of objects:
    #   drawPrimitives(const Primitive *array, int count, ...)
    # where "Primitive" is one of QPointF, QLineF, QRectF, PixmapFragment
    #
    # PySide (with the exception of drawPixmapFragments) and older PyQt
    # require a Python list of "Primitive" instances to be provided to
    # the respective "drawPrimitives" method.
    #
    # This is inefficient because:
    # 1) constructing the Python list involves calling wrapinstance multiple times.
    #    - this is mitigated here by reusing the instance pointers
    # 2) The binding will anyway have to repack the instances into a contiguous array,
    #    in order to call the underlying C++ native API.
    #
    # Newer PyQt provides sip.array, which is more efficient.
    #
    # PySide's drawPixmapFragments() takes an instance to the first item of a
    # C array of PixmapFragment(s) _and_ the length of the array.
    # There is no overload that takes a Python list of PixmapFragment(s).

    def __init__(self, Klass, nfields, *, use_array=None):
        self._Klass = Klass
        self._nfields = nfields
        self._ndarray = None
        if use_array is None:
            use_array = Klass in [QtGui.QPainter.PixmapFragment]
        self.use_ptr_to_array = use_array
        self.resize(0)

    def resize(self, size):
        if self._ndarray is not None and len(self._ndarray) == size:
            return

        if self.use_ptr_to_array:
            array = np.empty((size, self._nfields), dtype=np.float64)
            self._objs = shiboken6.wrapInstance(array.ctypes.data, self._Klass)
        else:
            array = np.empty((size, self._nfields), dtype=np.float64)
            self._objs = list(map(shiboken6.wrapInstance,
                itertools.count(array.ctypes.data, array.strides[0]),
                itertools.repeat(self._Klass, array.shape[0])))

        self._ndarray = array

    def __len__(self):
        return len(self._ndarray)

    def ndarray(self):
        return self._ndarray

    def instances(self):
        return self._objs


class PointsF:

    def __init__(self):
        self.use_native_drawlines = _have_native_drawlines_array
        self.array = PrimitiveArray(QtCore.QPointF, 2, use_array=self.use_native_drawlines)

    def _get(self, size):
        self.array.resize(size)
        return self.array.instances(), self.array.ndarray()

    def set_fill(self, x, y_min, y_max):
        k = len(x)
        nsegs = k * 2
        assert(k == len(y_min))
        assert(k == len(y_max))
        segs, memory = self._get(nsegs)
        memory[:k, 0] = x
        memory[:k, 1] = y_min
        memory[k:, 0] = x[::-1]
        memory[k:, 1] = y_max[::-1]
        return segs, nsegs

    def set_line(self, x, y):
        nsegs = len(x)
        assert(nsegs == len(y))
        segs, memory = self._get(nsegs)
        memory[:, 0] = x
        memory[:, 1] = y
        return segs, nsegs


class LineSegments:
    def __init__(self):
        # "use_native_drawlines" is pending the following issue and code review
        # https://bugreports.qt.io/projects/PYSIDE/issues/PYSIDE-1924
        # https://codereview.qt-project.org/c/pyside/pyside-setup/+/415702
        self.use_native_drawlines = _have_native_drawlines_array
        self.array = PrimitiveArray(QtCore.QLineF, 4, use_array=self.use_native_drawlines)

    def get(self, size):
        self.array.resize(size)
        return self.array.instances(), self.array.ndarray()

    def arrayToLineSegments(self, x, y, connect, finiteCheck):
        # analogue of arrayToQPath taking the same parameters
        if len(x) < 2:
            return [],

        connect_array = None
        if isinstance(connect, np.ndarray):
            # the last element is not used
            connect_array, connect = np.asarray(connect[:-1], dtype=bool), 'array'

        all_finite = True
        if finiteCheck or connect == 'finite':
            mask = np.isfinite(x) & np.isfinite(y)
            all_finite = np.all(mask)

        if connect == 'all':
            if not all_finite:
                # remove non-finite points, if any
                x = x[mask]
                y = y[mask]

        elif connect == 'finite':
            if all_finite:
                connect = 'all'
            else:
                # each non-finite point affects the segment before and after
                connect_array = mask[:-1] & mask[1:]

        elif connect in ['pairs', 'array']:
            if not all_finite:
                # replicate the behavior of arrayToQPath
                #backfill_idx = fn._compute_backfill_indices(mask)
                #x = x[backfill_idx]
                #y = y[backfill_idx]
                raise RuntimeError('???')

        segs = []
        nsegs = 0

        if connect == 'all':
            nsegs = len(x) - 1
            if nsegs:
                segs, memory = self.get(nsegs)
                memory[:, 0] = x[:-1]
                memory[:, 2] = x[1:]
                memory[:, 1] = y[:-1]
                memory[:, 3] = y[1:]

        elif connect == 'pairs':
            nsegs = len(x) // 2
            if nsegs:
                segs, memory = self.get(nsegs)
                memory = memory.reshape((-1, 2))
                memory[:, 0] = x[:nsegs * 2]
                memory[:, 1] = y[:nsegs * 2]

        elif connect_array is not None:
            # the following are handled here
            # - 'array'
            # - 'finite' with non-finite elements
            nsegs = np.count_nonzero(connect_array)
            if nsegs:
                segs, memory = self.get(nsegs)
                memory[:, 0] = x[:-1][connect_array]
                memory[:, 2] = x[1:][connect_array]
                memory[:, 1] = y[:-1][connect_array]
                memory[:, 3] = y[1:][connect_array]

        if nsegs and self.use_native_drawlines:
            return segs, nsegs
        else:
            return segs,
