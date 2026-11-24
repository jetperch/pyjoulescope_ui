# Copyright 2026 Jetperch LLC
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

"""The Efficiency widget readout pane."""

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import N_
from joulescope_ui.units import unit_prefix
import math


_PAD = 8
_GAP = 24


def value_str(x, units):
    """Format x with an SI prefix and 4 significant figures."""
    if x is None or not math.isfinite(x):
        return '---'
    v, prefix, _ = unit_prefix(x)
    z = abs(v)
    fmt = '%.1f' if z >= 100 else ('%.2f' if z >= 10 else '%.3f')
    return f'{fmt % v} {prefix}{units}'


def efficiency_str(x):
    if x is None or not math.isfinite(x):
        return '--- %'
    return f'{x * 100:.2f} %'


class EfficiencyReadout(QtWidgets.QWidget):
    """Paint the efficiency readout from the owner's state.

    :param owner: The EfficiencyWidget, which provides plot_style() and
        readout().
    """

    def __init__(self, owner, parent=None):
        self._owner = owner
        super().__init__(parent)
        self.setObjectName('efficiency_readout')
        policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def _rows(self):
        r = self._owner.readout()
        w = r['window'] or {}
        rows = [
            (N_('Input power'), value_str(w.get('p_in'), 'W')),
            (N_('Output power'), value_str(w.get('p_out'), 'W')),
            (N_('Power loss'), value_str(w.get('p_loss'), 'W')),
            (N_('Cumulative efficiency'), efficiency_str(r['efficiency_cumulative'])),
        ]
        if r['show_vi']:
            rows += [
                (N_('Input voltage'), value_str(w.get('v_in'), 'V')),
                (N_('Input current'), value_str(w.get('i_in'), 'A')),
                (N_('Output voltage'), value_str(w.get('v_out'), 'V')),
                (N_('Output current'), value_str(w.get('i_out'), 'A')),
            ]
        return r, rows

    def _layout(self, style, rows, width):
        """Get (main_rect, table_origin, label_width, value_width, size).

        The table is right of the main value when width allows, else below.
        """
        main_fm, stats_fm = style['main_metrics'], style['stats_metrics']
        main_w = main_fm.horizontalAdvance('100.00 %')
        main_h = main_fm.height() + style['title_metrics'].height()
        label_w = max(stats_fm.horizontalAdvance(label) for label, _ in rows)
        value_w = max(stats_fm.horizontalAdvance('-888.8 mW'),
                      max(stats_fm.horizontalAdvance(v) for _, v in rows))
        table_w = label_w + _GAP // 2 + value_w
        table_h = len(rows) * stats_fm.height()
        main = QtCore.QRectF(_PAD, _PAD, main_w, main_h)
        if _PAD + main_w + _GAP + table_w + _PAD <= width:
            origin = QtCore.QPointF(_PAD + main_w + _GAP, _PAD)
            size = QtCore.QSize(int(_PAD * 2 + main_w + _GAP + table_w), int(_PAD * 2 + max(main_h, table_h)))
        else:  # narrow: table below
            origin = QtCore.QPointF(_PAD, _PAD + main_h + _PAD)
            size = QtCore.QSize(int(_PAD * 2 + max(main_w, table_w)), int(_PAD * 3 + main_h + table_h))
        return main, origin, label_w, value_w, size

    def _size(self, width):
        _, rows = self._rows()
        return self._layout(self._owner.plot_style(), rows, width)[-1]

    def sizeHint(self):
        return self._size(1 << 16)  # wide

    def minimumSizeHint(self):
        return QtCore.QSize(self._size(0).width(), self.sizeHint().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._size(width).height()

    def paintEvent(self, event):
        style = self._owner.plot_style()
        r, rows = self._rows()
        main, origin, label_w, value_w, _ = self._layout(style, rows, self.width())
        p = QtGui.QPainter(self)
        p.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)  # QPainter follows the app, not the widget
        try:
            p.fillRect(self.rect(), style['background_brush'])
            valid = r['valid']
            color = style['main_color'] if valid else style['invalid_color']
            w = r['window'] or {}
            p.setFont(style['main_font'])
            p.setPen(color)
            main_fm = style['main_metrics']
            p.drawText(QtCore.QPointF(main.left(), main.top() + main_fm.ascent()),
                       efficiency_str(w.get('efficiency')))
            p.setFont(style['title_font'])
            p.setPen(style['title_color'])
            p.drawText(QtCore.QPointF(main.left(), main.top() + main_fm.height() + style['title_metrics'].ascent()),
                       N_('Efficiency'))
            stats_fm = style['stats_metrics']
            p.setFont(style['stats_font'])
            for idx, (label, value) in enumerate(rows):
                y = origin.y() + idx * stats_fm.height() + stats_fm.ascent()
                p.setPen(style['title_color'])
                p.drawText(QtCore.QPointF(origin.x(), y), label)
                p.setPen(style['stats_color'] if valid else style['invalid_color'])
                x = origin.x() + label_w + _GAP // 2 + value_w - stats_fm.horizontalAdvance(value)
                p.drawText(QtCore.QPointF(x, y), value)
        finally:
            p.end()
