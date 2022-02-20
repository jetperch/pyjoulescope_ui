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

from PySide2 import QtWidgets, QtGui, QtCore
import pyqtgraph as pg
import weakref
from .signal import Signal
from .signal_statistics import si_format, html_format
from joulescope.units import three_sig_figs
import logging


class MarkerArea(pg.GraphicsObject):
    """The bounding area for markers and their text.
    :param x_axis: The x-axis :class:`pg.AxisItem` instance.
    """

    def __init__(self, x_axis: pg.AxisItem):
        pg.GraphicsObject.__init__(self)
        self._x_axis = weakref.ref(x_axis)
        self.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape)

    def add_to_scene(self):
        x_axis = self._x_axis()
        self.setParentItem(x_axis.parentItem())

    def __str__(self):
        return f'WaveformArea()'

    def boundingRect(self):
        axis = self._x_axis()
        vb = axis.linkedView()
        if vb is None:
            vb = axis
        top = axis.geometry().top()
        vb_bounds = vb.geometry()
        height = vb_bounds.bottom() - top
        clip = QtCore.QRectF(vb_bounds.left(), top, vb_bounds.width(), height)
        return clip

    def paint(self, p, opt, widget):
        path = QtGui.QPainterPath()
        path.addRect(self.boundingRect())
        p.setClipPath(path)
