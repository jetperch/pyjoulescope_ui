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

    def set_fill(self, x, y_min, y_max):
        k = len(x)
        nsegs = k * 2
        assert(k == len(y_min))
        assert(k == len(y_max))
        segs, memory = self._get(nsegs)

        memory[:k, 0] = x
        memory[:k, 1] = y_min
        memory[k:nsegs, 0] = x[::-1]
        memory[k:nsegs, 1] = y_max[::-1]
        return segs[:nsegs]

    def set_line(self, x, y):
        k = len(x)
        assert(k == len(y))
        segs, memory = self._get(k)

        memory[:k, 0] = x
        memory[:k, 1] = y
        return segs[:k]
