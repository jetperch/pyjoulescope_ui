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

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope.units import unit_prefix, three_sig_figs
from joulescope.stream_buffer import single_stat_to_api
from joulescope_ui.ui_util import rgba_to_css, font_to_css
from joulescope_ui.units import FIELD_UNITS_INTEGRAL
import numpy as np
import math
import pyqtgraph as pg


STYLE_DEFAULT = 'color: #FFF'


def _si_format(names, values, units):
    results = []
    if units is None:
        units = ''
    if len(values):
        values = np.array(values)
        max_value = float(np.max(np.abs(values)))
        _, prefix, scale = unit_prefix(max_value)
        scale = 1.0 / scale
        if not len(prefix):
            prefix = '&nbsp;'
        units_suffix = f'{prefix}{units}'
        for lbl, v in zip(names, values):
            v *= scale
            if abs(v) < 0.000005:  # minimum display resolution
                v = 0
            v_str = ('%+6f' % v)[:8]
            results.append('%s=%s %s' % (lbl, v_str, units_suffix))
    return results


def si_format(labels):
    results = []
    if not len(labels):
        return results
    units = None
    values = []
    names = []
    for name, d in labels.items():
        value = float(d['value'])
        if name == 'σ2':
            name = 'σ'
            value = math.sqrt(value)
        if d['units'] != units:
            results.extend(_si_format(names, values, units))
            units = d['units']
            values = [value]
            names = [name]
        else:
            values.append(value)
            names.append(name)
    results.extend(_si_format(names, values, units))
    return results


def convert(field, labels, cmdp):
    for name, d in labels.items():
        if name == '∫':
            field = FIELD_UNITS_INTEGRAL.get(field, field)
        v = cmdp.convert_units(field, d)
        d['value'], d['units'] = v['value'], v['units']
    return labels


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

    def __init__(self, parent=None, field=None, units=None, cmdp=None):
        pg.GraphicsWidget.__init__(self, parent=parent)
        self._field = field
        self._units = units
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._label = QtWidgets.QGraphicsTextItem(self)
        self._label.setVisible(True)
        self._label.document().setUseDesignMetrics(True)
        self._value_cache = None
        self._cmdp = cmdp
        labels = single_stat_to_api(-0.000000001, 0.000001, -0.001, 0.001, self._units)
        self.data_update(labels)
        self._resize()
        self.data_clear()
        cmdp.subscribe('Appearance/__index__', self._on_font_color, update_now=True)
        pg.GraphicsWidget.show(self)

    def preferred_height(self):
        return self._label.boundingRect().height()

    def setFont(self, font):
        # 'Widgets/Waveform/Statistics/font',
        self._label.setFont(font)
        self._label.adjustSize()
        b = self._label.boundingRect()
        self.setMinimumWidth(b.width())

    def _resize(self):
        self._label.adjustSize()
        b = self._label.boundingRect()
        self.setMinimumWidth(b.width())
        self.adjustSize()

    def _on_font_color(self, topic, value):
        if self._value_cache is not None:
            self._data_update(*self._value_cache)

    def close(self):
        self.scene().removeItem(self._label)
        self._label = None
        self._value_cache = None

    def data_clear(self):
        self._value_cache = None
        self._label.setHtml(f'<html><body></body></html>')

    def _data_update(self, labels, x):
        font_color = self._cmdp['Appearance/__index__']['colors']['waveform_font_color']
        style = f'color: {font_color};'
        txt_result = si_format(convert(self._field, labels, self._cmdp))
        html = html_format(txt_result, x=x, style=style)
        self._label.setHtml(html)

    def data_update(self, labels, x=None):
        self._value_cache = (labels, x)
        self._data_update(labels, x)


class SignalMarkerStatistics(pg.TextItem):

    def __init__(self, field, cmdp):
        pg.TextItem.__init__(self)
        self._field = field
        self._cmdp = cmdp
        self._value_cache = None
        cmdp.subscribe('Widgets/Waveform/Statistics/font', self._on_font, update_now=True)
        cmdp.subscribe('Appearance/__index__', self._on_font_color, update_now=True)

    def preferred_height(self):
        return self.textItem.boundingRect().height()

    def height(self):
        return self.getViewBox().height() * 0.85

    def _on_font(self, topic, value):
        font = QtGui.QFont()
        font.fromString(value)
        self.textItem.setFont(font)
        self.updateTextPos()

    def _on_font_color(self, topic, value):
        if self._value_cache is not None:
            self.data_update(None, *self._value_cache)

    def computing(self):
        self.setHtml(f'<html><body></body></html>')

    def move(self, vb, xv=None):
        if vb is not None:
            if xv is None:
                xv = self.pos().x()
            ys = vb.geometry().top()
            yv = vb.mapSceneToView(pg.Point(0.0, ys)).y()
            self.setPos(pg.Point(xv, yv))

    def data_update(self, vb, xv, labels):
        if labels is None or not len(labels):
            html = '<p>No data</p>'
            self._value_cache = None
        else:
            font_color = self._cmdp['Appearance/__index__']['colors']['waveform_font_color']
            style = f'color: {font_color};'
            self._value_cache = (xv, labels)
            txt_result = si_format(convert(self._field, labels, self._cmdp))
            html = html_format(txt_result, x=xv, style=style)
        self.setHtml(html)
