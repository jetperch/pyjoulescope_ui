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

from pyqtgraph.Qt import QtGui, QtCore
from joulescope.units import unit_prefix, three_sig_figs
import numpy as np
import pyqtgraph as pg


STYLE_DEFAULT = 'color: #FFF; font-size: 8pt'


def si_format(labels, units=None):
    if units is None:
        units = ''
    values = np.array([z for z in labels.values()])
    max_value = float(np.max(np.abs(values)))
    _, prefix, scale = unit_prefix(max_value)
    scale = 1.0 / scale
    if not len(prefix):
        prefix = '&nbsp;'
    units_suffix = f'{prefix}{units}'
    results = []
    for lbl, v in labels.items():
        v *= scale
        if abs(v) < 0.000005:  # minimum display resolution
            v = 0
        v_str = ('%+6f' % v)[:8]
        results.append('%s=%s %s' % (lbl, v_str, units_suffix))
    return results


def html_format(results, x=None, style=None):
    if style is None:
        style = STYLE_DEFAULT
    if x is None:
        values = []
    else:
        values = ['t=%.6f' % (x, )]
    values += results

    body = '<br/>'.join(results)
    return f'<div><span style="{style}">{body}</span></div>'


class SignalStatistics(pg.GraphicsWidget):

    def __init__(self, parent=None, units=None):
        pg.GraphicsWidget.__init__(self, parent=parent)
        self._units = units
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        self._label = QtGui.QGraphicsTextItem(self)
        self._label.setVisible(True)
        self.style = 'color: #FFF; font-size: 8pt'

        labels = {'μ': -0.001, 'σ': -0.01, 'min': -0.1, 'max': 0.001, 'p2p': 0.001 + 0.1}
        txt_result = si_format(labels)
        self.data_update(txt_result)
        b = self._label.boundingRect()
        self.setMinimumHeight(b.height())
        self.setMinimumWidth(b.width())
        pg.GraphicsWidget.show(self)

    def close(self):
        self.scene().removeItem(self._label)
        self._label = None

    def data_clear(self):
        self._label.setHtml(f'<html><body></body></html>')

    def data_update(self, results, x=None):
        html = html_format(results, x=x)
        self._label.setHtml(html)


class SignalMarkerStatistics(pg.TextItem):

    def __init__(self):
        pg.TextItem.__init__(self)

    def computing(self):
        self.setHtml(f'<html><body></body></html>')

    def move(self, vb, xv):
        if vb is not None and xv is not None:
            ys = vb.geometry().top()
            yv = vb.mapSceneToView(pg.Point(0.0, ys)).y()
            self.setPos(pg.Point(xv, yv))

    def data_update(self, vb, xv, labels, units):
        if labels is None or not len(labels):
            html = '<p>No data</p>'
        else:
            txt_result = si_format(labels, units=units)
            html = html_format(txt_result, x=xv)
        self.setHtml(html)
