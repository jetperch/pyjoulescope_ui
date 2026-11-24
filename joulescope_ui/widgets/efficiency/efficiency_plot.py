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

"""The Efficiency widget plots."""

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import N_, time64
from joulescope_ui.spectrum_engine import column_map, column_reduce
from joulescope_ui.widgets import plot_base
from joulescope_ui.widgets.waveform import axis_ticks
from joulescope_ui.widgets.waveform.line_segments import PointsF
from .efficiency_readout import efficiency_str, value_str
import math
import numpy as np


_ZOOM_STEP = 0.8            # x span scale per wheel step
_MIN_SPAN_PERCENT = 0.02    # minimum autoscale y span, in percent
_MIN_DURATION = 1.0         # minimum zoomed x span, in seconds


def finite_runs(y):
    """Get the [start, end) index ranges of consecutive finite values."""
    finite = np.isfinite(y)
    if not len(finite):
        return []
    d = np.diff(np.concatenate([[False], finite, [False]]).astype(np.int8))
    starts = np.nonzero(d == 1)[0]
    ends = np.nonzero(d == -1)[0]
    return list(zip(starts, ends))


def reduce_to_columns(x, y, x0, x1, width):
    """Reduce points to a min/max pair per pixel column.

    :param x: The increasing x values.
    :param y: The y values, NaN for gaps.
    :param x0: The x value at the left edge.
    :param x1: The x value at the right edge.
    :param width: The number of pixel columns.
    :return: (x, y) with points interleaved min, max per column at the
        column centers.  Columns containing NaN are NaN.  When there are
        fewer than two points per column, returns the inputs.
    """
    if width < 1 or len(x) < 2 * width:
        return x, y
    edges = np.linspace(x0, x1, width + 1)
    cmap = column_map(x, edges)
    y_min = column_reduce(y, cmap, np.minimum)
    y_max = column_reduce(y, cmap, np.maximum)
    xc = 0.5 * (edges[:-1] + edges[1:])
    keep = ~cmap['empty']
    xc, y_min, y_max = xc[keep], y_min[keep], y_max[keep]
    return np.repeat(xc, 2), np.column_stack([y_min, y_max]).ravel()


class _PlotBase(QtWidgets.QWidget):
    """Common layout, percent y autoscale, hover, and context menu.

    :param owner: The EfficiencyWidget, which provides plot_style() and
        context_menu(event).
    """

    def __init__(self, owner, name, parent=None):
        self._owner = owner
        self._points = PointsF()
        self._hover = None      # QPointF
        self._y_auto = None     # [y0, y1] percent
        super().__init__(parent)
        # Plots and readings stay left to right, also in right-to-left languages.
        self.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.setObjectName(name)
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMinimumHeight(60)

    def plot_rect(self):
        style = self._owner.plot_style()
        left = style['font_metrics'].horizontalAdvance('100.000') + 8
        right = 12
        bottom = 2 * style['font_height'] + 4
        return QtCore.QRectF(left, 4, max(1, self.width() - left - right), max(1, self.height() - 4 - bottom))

    def clear(self):
        self._y_auto = None
        self.update()

    def y_view(self, y):
        """Update and get the autoscaled y range in percent."""
        y = np.asarray(y, dtype=np.float64)
        finite = y[np.isfinite(y)]
        if not len(finite):
            return self._y_auto or [0.0, 100.0]
        lo, hi = float(np.min(finite)), float(np.max(finite))
        span = max(hi - lo, _MIN_SPAN_PERCENT)
        step = 10 ** np.floor(np.log10(span)) / 2
        if self._y_auto is not None and (self._y_auto[1] - self._y_auto[0]) > 20 * span:
            self._y_auto = None  # zoom in after a large excursion leaves the view
        self._y_auto = plot_base.autoscale_hysteresis(self._y_auto, lo, hi, step)
        return self._y_auto

    def _y_axis(self, p, rect, style, y0, y1):
        """Draw the percent y axis and get y_to_pixel."""
        def y_to_pixel(v):
            return rect.bottom() - (np.asarray(v) - y0) * (rect.height() / (y1 - y0))

        fh = style['font_height']
        y_ticks = axis_ticks.ticks(y0, y1, major_max=max(2, int(rect.height() / (2.5 * fh))))
        plot_base.draw_y_axis(p, rect, style, y_ticks, y_to_pixel)
        p.setPen(style['text_pen'])
        p.drawText(QtCore.QPointF(rect.left() + 4, rect.top() + style['font_ascent'] + 2), '%')
        return y_to_pixel

    def _x_units(self, p, rect, style, y_text, units):
        fm = style['font_metrics']
        p.setPen(style['text_pen'])
        p.drawText(QtCore.QPointF(rect.right() - fm.horizontalAdvance(units), y_text + style['font_height']), units)

    def mouseMoveEvent(self, event):
        self._hover = event.position()
        self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            event.accept()
            self._owner.context_menu(event)
        else:
            super().mousePressEvent(event)


class TimePlot(_PlotBase):
    """Efficiency vs time, newest at the right edge.

    :param owner: The EfficiencyWidget, which provides plot_style(),
        history, time_plot_duration, and context_menu(event).
    """

    def __init__(self, owner, parent=None):
        self._span = None       # zoomed x span in seconds, None for the duration setting
        super().__init__(owner, 'efficiency_time_plot', parent)

    def span(self):
        """The displayed x span in seconds."""
        duration = float(self._owner.time_plot_duration)
        return duration if self._span is None else min(self._span, duration)

    def data(self):
        """Get the visible (x, y) with x in seconds relative to the newest, y in percent."""
        t, y = self._owner.history.newest()
        if not len(t):
            return np.zeros(0), np.zeros(0)
        x = (t - t[-1]) / time64.SECOND
        k = np.searchsorted(x, -self.span(), 'left')
        k = max(0, k - 1)  # include the point just left of the edge
        return x[k:], y[k:] * 100.0

    def paintEvent(self, event):
        style = self._owner.plot_style()
        p = QtGui.QPainter(self)
        try:
            p.fillRect(self.rect(), style['background_brush'])
            p.setFont(style['font'])
            rect = self.plot_rect()
            x, y = self.data()
            span = self.span()
            y0, y1 = self.y_view(y)

            def x_to_pixel(v):
                return rect.left() + (np.asarray(v) + span) * (rect.width() / span)

            fh = style['font_height']
            x_ticks = axis_ticks.ticks(-span, 0.0, major_max=max(2, int(rect.width() / 80)))
            y_text = plot_base.draw_x_axis(p, rect, style, x_ticks, x_to_pixel)
            self._x_units(p, rect, style, y_text, f'{x_ticks["unit_prefix"] if x_ticks else ""}s')
            y_to_pixel = self._y_axis(p, rect, style, y0, y1)

            p.setClipRect(rect)
            xr, yr = reduce_to_columns(x, y, -span, 0.0, int(rect.width()))
            px, py = x_to_pixel(xr), y_to_pixel(yr)
            p.setPen(style['trace_pen'])
            for k0, k1 in finite_runs(py):
                if k1 - k0 == 1:
                    p.drawPoint(QtCore.QPointF(px[k0], py[k0]))
                else:
                    p.drawPolyline(self._points.set_line(px[k0:k1], py[k0:k1]))
            hover_x, lines = self._hover_at(rect, x, y, x_to_pixel)
            if hover_x is not None:
                plot_base.draw_v_line(p, rect, style['hover_pen'], hover_x)
            p.setClipping(False)
            plot_base.draw_text_box(p, style, lines, rect.left() + 4, rect.top() + fh + 4, align_right=False)
            plot_base.draw_border(p, rect, style)
        finally:
            p.end()

    def _hover_at(self, rect, x, y, x_to_pixel):
        """Get the hover (pixel x, text lines) snapped to the nearest window."""
        if self._hover is None or not len(x) or not rect.contains(self._hover):
            return None, []
        px = x_to_pixel(x)
        k = int(np.argmin(np.abs(px - self._hover.x())))
        eta = efficiency_str(y[k] / 100.0) if np.isfinite(y[k]) else N_('invalid')
        return float(px[k]), [f'{x[k]:.3f} s', eta]

    # ---- mouse ----

    def wheelEvent(self, event):
        event.accept()
        steps = event.angleDelta().y() / 120.0
        if steps:
            duration = float(self._owner.time_plot_duration)
            span = self.span() * _ZOOM_STEP ** steps
            self._span = None if span >= duration else max(_MIN_DURATION, span)
            self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
            self._span = None
            self.update()


class CurvePlot(_PlotBase):
    """Efficiency vs output current or power, built up from steady windows.

    :param owner: The EfficiencyWidget, which provides plot_style(),
        curve_bins(), curve_x, curve_x_scale, curve_whiskers,
        curve_min_count, and context_menu(event).
    """

    def __init__(self, owner, parent=None):
        super().__init__(owner, 'efficiency_curve_plot', parent)

    def x_units(self):
        return 'A' if self._owner.curve_x == 'current' else 'W'

    def x_log(self):
        return self._owner.curve_x_scale == 'log'

    def x_view(self, bins):
        """Get the x range covering all bins."""
        lo = min(b['x_min'] for b in bins)
        hi = max(b['x_max'] for b in bins)
        if self.x_log():
            lo, hi = lo / 1.2, hi * 1.2
            if hi < 10 * lo:  # a full decade always has labeled 1, 2, 5 ticks
                center = math.sqrt(lo * hi)
                lo, hi = center / math.sqrt(10), center * math.sqrt(10)
            return lo, hi
        span = max(hi - lo, abs(hi) * 1e-3, 1e-12)
        return max(0.0, lo - 0.05 * span) if lo >= 0 else lo - 0.05 * span, hi + 0.05 * span

    def _x_mapper(self, rect, x0, x1):
        if self.x_log():
            u0, u1 = np.log10(x0), np.log10(x1)

            def fn(v):
                return rect.left() + (np.log10(np.asarray(v)) - u0) * (rect.width() / (u1 - u0))
        else:
            def fn(v):
                return rect.left() + (np.asarray(v) - x0) * (rect.width() / (x1 - x0))
        return fn

    def paintEvent(self, event):
        o = self._owner
        style = o.plot_style()
        p = QtGui.QPainter(self)
        try:
            p.fillRect(self.rect(), style['background_brush'])
            p.setFont(style['font'])
            rect = self.plot_rect()
            bins = o.curve_bins()
            if not bins:
                p.setPen(style['text_pen'])
                p.drawText(rect, QtCore.Qt.AlignCenter, N_('Waiting for steady load'))
                plot_base.draw_border(p, rect, style)
                return
            x0, x1 = self.x_view(bins)
            x_to_pixel = self._x_mapper(rect, x0, x1)
            eta = np.array([b['efficiency'] for b in bins]) * 100.0
            eta_min = np.array([b['efficiency_min'] for b in bins]) * 100.0
            eta_max = np.array([b['efficiency_max'] for b in bins]) * 100.0
            whiskers = bool(o.curve_whiskers)
            y0, y1 = self.y_view(np.concatenate([eta, eta_min, eta_max]) if whiskers else eta)

            if self.x_log():
                x_ticks = axis_ticks.log_ticks(x0, x1)
            else:
                x_ticks = axis_ticks.ticks(x0, x1, major_max=max(2, int(rect.width() / 80)))
            y_text = plot_base.draw_x_axis(p, rect, style, x_ticks, x_to_pixel)
            prefix = x_ticks['unit_prefix'] if x_ticks else ''
            self._x_units(p, rect, style, y_text, f'{prefix}{self.x_units()}')
            y_to_pixel = self._y_axis(p, rect, style, y0, y1)

            p.setClipRect(rect)
            px = x_to_pixel([b['x'] for b in bins])
            py = y_to_pixel(eta)
            ok = np.array([b['count'] >= int(o.curve_min_count) for b in bins])
            if np.count_nonzero(ok) > 1:
                p.setPen(style['curve_pen'])
                p.drawPolyline(self._points.set_line(px[ok], py[ok]))
            if whiskers:
                lo, hi = y_to_pixel(eta_min), y_to_pixel(eta_max)
                for k in range(len(bins)):
                    p.setPen(style['curve_pen'] if ok[k] else style['curve_faded_pen'])
                    p.drawLine(QtCore.QPointF(px[k], lo[k]), QtCore.QPointF(px[k], hi[k]))
            p.setPen(QtCore.Qt.NoPen)
            r = 3.5
            for k in range(len(bins)):
                p.setBrush(style['curve_brush'] if ok[k] else style['curve_faded_brush'])
                p.drawEllipse(QtCore.QPointF(px[k], py[k]), r, r)
            hover = self._hover_bin(rect, px)
            lines = []
            if hover is not None:
                plot_base.draw_v_line(p, rect, style['hover_pen'], px[hover])
                lines = self.hover_lines(bins[hover])
            p.setClipping(False)
            plot_base.draw_text_box(p, style, lines, rect.right() - 4, rect.bottom() - 4 - len(lines)
                                    * style['font_height'] - 4, align_right=True)
            plot_base.draw_border(p, rect, style)
        finally:
            p.end()

    def _hover_bin(self, rect, px):
        if self._hover is None or not rect.contains(self._hover) or not len(px):
            return None
        return int(np.argmin(np.abs(px - self._hover.x())))

    def hover_lines(self, b):
        units = self.x_units()
        return [
            f'{value_str(b["x_min"], units)} – {value_str(b["x_max"], units)}',
            f'{efficiency_str(b["efficiency"])}  ({efficiency_str(b["efficiency_min"])} – '
            f'{efficiency_str(b["efficiency_max"])})',
            N_('{0} windows, {1}').format(b['count'], value_str(b['duration'], 's')),
        ]
