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

"""Spectrum widget plots: the FFT pane and the waterfall pane.

Both panes draw through the owning SpectrumWidget, which holds the
shared state (frequency viewport, traces, style, and margins) so that
their frequency columns align.
"""

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import N_
from joulescope_ui.spectrum_engine import column_reduce
from joulescope_ui.units import unit_prefix
from joulescope_ui.widgets.waveform import axis_ticks
from joulescope_ui.widgets.waveform.line_segments import PointsF
import numpy as np


_DRAG_PIXELS = 5     # marker grab distance
_ZOOM_STEP = 0.8     # viewport scale per wheel step
_COLORBAR_WIDTH = 12
_MINOR_GRID_PIXELS = 6

_COLORMAP_POLY = {
    # 6th-order polynomial fits by Matt Zucker (CC0), t in [0, 1]
    'viridis': [
        [0.2777273272234177, 0.005407344544966578, 0.3340998053353061],
        [0.1050930431085774, 1.404613529898575, 1.384590162594685],
        [-0.3308618287255563, 0.214847559468213, 0.09509516302823659],
        [-4.634230498983486, -5.799100973351585, -19.33244095627987],
        [6.228269936347081, 14.17993336680509, 56.69055260068105],
        [4.776384997670288, -13.74514537774601, -65.35303263337234],
        [-5.435455855934631, 4.645852612178535, 26.3124352495832],
    ],
    'inferno': [
        [0.0002189403691192265, 0.001651004631001012, -0.01948089843709184],
        [0.1065134194856116, 0.5639564367884091, 3.932712388889277],
        [11.60249308247187, -3.972853965665698, -15.9423941062914],
        [-41.70399613139459, 17.43639888205313, 44.35414519872813],
        [77.162935699427, -33.40235894210092, -81.80730925738993],
        [-71.31942824499214, 32.62606426397723, 73.20951985803202],
        [25.13112622477341, -12.24266895238567, -23.07032500287172],
    ],
}

COLORMAPS = [
    ['inferno', N_('Inferno')],
    ['viridis', N_('Viridis')],
    ['grayscale', N_('Grayscale')],
]


def colormap_rgb(name, count=255):
    """Get the colormap.

    :param name: The colormap name from COLORMAPS.
    :param count: The number of colors.
    :return: The uint8 array with shape (count, 3), dark to bright.
    """
    t = np.linspace(0.0, 1.0, count)
    if name == 'grayscale':
        rgb = np.repeat(t[:, np.newaxis], 3, axis=1)
    else:
        coef = np.array(_COLORMAP_POLY[name])
        rgb = np.zeros((count, 3))
        for c in coef[::-1]:
            rgb = rgb * t[:, np.newaxis] + c
    return np.round(np.clip(rgb, 0.0, 1.0) * 255).astype(np.uint8)


def color_table(name, background):
    """Get the Indexed8 color table.

    :param name: The colormap name.
    :param background: The QColor for index 0, used for missing data.
    :return: The list of 256 QRgb values.
    """
    table = [background.rgba()]
    for r, g, b in colormap_rgb(name, 255):
        table.append(QtGui.qRgb(int(r), int(g), int(b)))
    return table


def value_to_index(values, lo, hi):
    """Map dB values to color table indices 1..255, with NaN to 0."""
    k = 254.0 / max(hi - lo, 1e-9)
    with np.errstate(invalid='ignore'):
        idx = np.clip((values - lo) * k, 0.0, 254.0) + 1.0
    idx = np.nan_to_num(idx, nan=0.0)
    return idx.astype(np.uint8)


class WaterfallHistory:
    """Hold waterfall rows at full bin resolution in a ring buffer."""

    def __init__(self):
        self.version = 0
        self.reset(1, 1)

    def reset(self, capacity, bins):
        self.capacity = max(1, int(capacity))
        self.bins = int(bins)
        self._data = np.full((self.capacity, self.bins), np.nan, dtype=np.float32)
        self._ids = np.zeros(self.capacity, dtype=np.int64)
        self._head = 0       # next row to write
        self.count = 0       # valid rows
        self.pending = 0     # rows added since the last image update
        self.version += 1

    def append(self, rows):
        """Append engine rows, inserting an empty row at each gap."""
        for row in rows:
            if len(row['db']) != self.bins:
                continue
            if row['gap'] and self.count:
                self._add(None, row['sample_id'])
            self._add(row['db'], row['sample_id'])

    def _add(self, db, sample_id):
        if db is None:
            self._data[self._head, :] = np.nan
        else:
            self._data[self._head, :] = db
        self._ids[self._head] = sample_id
        self._head = (self._head + 1) % self.capacity
        self.count = min(self.count + 1, self.capacity)
        self.pending = min(self.pending + 1, self.capacity)

    def newest(self, count=None):
        """Get rows, newest first.

        :param count: The number of rows, None for all valid rows.
        :return: (data, sample_ids)
        """
        count = self.count if count is None else min(count, self.count)
        idx = (self._head - 1 - np.arange(count)) % self.capacity
        return self._data[idx], self._ids[idx]

    @property
    def newest_sample_id(self):
        if not self.count:
            return None
        return int(self._ids[(self._head - 1) % self.capacity])


class WaterfallImage:
    """Map waterfall history to an Indexed8 image, newest row at top."""

    def __init__(self):
        self.image = None
        self._key = None
        self._array = None

    def update(self, history, cmap, width, lo, hi, table, cmap_key):
        """Update the image.

        :param history: The WaterfallHistory.
        :param cmap: The column map from spectrum_engine.column_map.
        :param width: The image width in pixels.
        :param lo: The dB value for the first color.
        :param hi: The dB value for the last color.
        :param table: The color table.
        :param cmap_key: The hashable identity for cmap.
        :return: The QImage or None.
        """
        key = (history.version, history.capacity, width, lo, hi, cmap_key, id(table))
        if width <= 0:
            return None
        if key != self._key:
            self._key = key
            stride = (width + 3) & ~3
            self._array = np.zeros((history.capacity, stride), dtype=np.uint8)
            data, _ = history.newest()
            if len(data):
                self._array[:len(data), :width] = value_to_index(column_reduce(data, cmap), lo, hi)
            history.pending = 0
            self.image = QtGui.QImage(self._array.data, width, history.capacity, stride,
                                      QtGui.QImage.Format.Format_Indexed8)
            self.image.setColorTable(table)
        elif history.pending:
            k = history.pending
            history.pending = 0
            a = self._array
            if k < len(a):
                a[k:] = a[:-k].copy()
            data, _ = history.newest(k)
            a[:len(data), :width] = value_to_index(column_reduce(data, cmap), lo, hi)
        return self.image


def _minor_visible(v):
    """True if minor grid lines at pixels v are far enough apart to draw."""
    return v is not None and len(v) > 1 and np.min(np.abs(np.diff(v))) >= _MINOR_GRID_PIXELS


def _v_lines(x, rect):
    """Vertical grid lines at x within rect, for QPainter.drawLines."""
    if x is None:
        return []
    t, b = rect.top(), rect.bottom()
    return [QtCore.QLineF(v, t, v, b) for v in x if rect.left() <= v <= rect.right()]


def _h_lines(y, rect):
    """Horizontal grid lines at y within rect, for QPainter.drawLines."""
    left, right = rect.left(), rect.right()
    return [QtCore.QLineF(left, v, right, v) for v in y if rect.top() <= v <= rect.bottom()]


def f_str(f):
    """Format a frequency."""
    if f is None or not np.isfinite(f):
        return ''
    adjusted, prefix, _ = unit_prefix(f)
    return f'{adjusted:.6g} {prefix}Hz'


class _PlotBase(QtWidgets.QWidget):
    """Common mouse handling for both panes."""

    def __init__(self, owner, parent=None):
        self._owner = owner
        self._drag = None   # (kind, start_x, start_value)
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMinimumHeight(40)

    def plot_rect(self):
        raise NotImplementedError()

    def _marker_at(self, x):
        o = self._owner
        rect = self.plot_rect()
        for idx, f in enumerate(o.marker_freqs):
            fx = o.f_to_x(f, rect)
            if fx is not None and abs(fx - x) <= _DRAG_PIXELS:
                return idx
        return None

    def mousePressEvent(self, event):
        o = self._owner
        pos = event.position()
        rect = self.plot_rect()
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
            marker = self._marker_at(pos.x())
            if marker is not None:
                self._drag = ('marker', marker)
            elif rect.contains(pos):
                self._drag = ('pan', pos.x(), o.viewport())
        elif event.button() == QtCore.Qt.RightButton:
            event.accept()
            o.context_menu(self, event, o.x_to_f(pos.x(), rect), self._marker_at(pos.x()))
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        o = self._owner
        pos = event.position()
        rect = self.plot_rect()
        if self._drag is not None and self._drag[0] == 'marker':
            f = o.x_to_f(min(max(pos.x(), rect.left()), rect.right()), rect)
            o.marker_move(self._drag[1], f, publish=False)
        elif self._drag is not None and self._drag[0] == 'pan':
            o.viewport_pan(self._drag[2], pos.x() - self._drag[1], rect.width())
        o.hover_set(self, pos if rect.contains(pos) else None)
        if self._marker_at(pos.x()) is not None or (self._drag and self._drag[0] == 'marker'):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            if self._drag[0] == 'marker':
                self._owner.marker_move(self._drag[1], None, publish=True)
            elif self._drag[0] == 'pan':
                self._owner.viewport_publish()
            self._drag = None
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
            self._owner.viewport_reset()

    def leaveEvent(self, event):
        self._owner.hover_set(self, None)
        super().leaveEvent(event)

    def wheelEvent(self, event):
        o = self._owner
        event.accept()
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return
        pos = event.position()
        rect = self.plot_rect()
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            self._wheel_shift(pos, rect, steps)
        else:
            o.viewport_zoom(o.x_to_f(pos.x(), rect), _ZOOM_STEP ** steps)

    def _wheel_shift(self, pos, rect, steps):
        pass

    def _draw_markers(self, p, rect, style, labels):
        o = self._owner
        if not o.marker_freqs:
            return
        p.setPen(style['marker_pen'])
        for idx, f in enumerate(o.marker_freqs):
            x = o.f_to_x(f, rect)
            if x is None or x < rect.left() or x > rect.right():
                continue
            p.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            if labels:
                p.drawText(QtCore.QPointF(x + 3, rect.bottom() - 3), f'M{idx + 1}')

    def _draw_text_box(self, p, style, lines, x, y, align_right):
        """Draw lines of text with a background box at (x, y) top corner."""
        if not lines:
            return
        fm = style['font_metrics']
        w = max(fm.horizontalAdvance(s) for s in lines) + 8
        h = len(lines) * style['font_height'] + 4
        x0 = x - w if align_right else x
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(style['text_bg_brush'])
        p.drawRect(QtCore.QRectF(x0, y, w, h))
        p.setPen(style['text_pen'])
        for idx, s in enumerate(lines):
            p.drawText(QtCore.QPointF(x0 + 4, y + 2 + style['font_ascent'] + idx * style['font_height']), s)


class FftPlot(_PlotBase):
    """The FFT spectrum pane."""

    def __init__(self, owner, parent=None):
        self._points = PointsF()
        super().__init__(owner, parent)
        self.setObjectName('spectrum_fft')

    def plot_rect(self):
        o = self._owner
        left, right = o.margins()
        style = o.plot_style()
        bottom = 2 * style['font_height'] + 4
        return QtCore.QRectF(left, 4, max(1, self.width() - left - right), max(1, self.height() - 4 - bottom))

    def _wheel_shift(self, pos, rect, steps):
        o = self._owner
        o.y_zoom(o.y_from_pixel(pos.y(), rect), _ZOOM_STEP ** steps)

    def paintEvent(self, event):
        o = self._owner
        style = o.plot_style()
        p = QtGui.QPainter(self)
        try:
            p.fillRect(self.rect(), style['background_brush'])
            p.setFont(style['font'])
            rect = self.plot_rect()
            self._draw_x_axis(p, rect, style)
            self._draw_y_axis(p, rect, style)
            p.setClipRect(rect)
            self._draw_traces(p, rect, style)
            self._draw_markers(p, rect, style, labels=True)
            self._draw_peaks(p, rect, style)
            self._draw_hover(p, rect, style)
            p.setClipping(False)
            self._draw_annotations(p, rect, style)
            p.setPen(style['border_pen'])
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(rect)
        finally:
            p.end()

    def _draw_x_axis(self, p, rect, style):
        o = self._owner
        ticks = o.x_ticks(rect.width())
        if ticks is None:
            return
        y_text = rect.bottom() + style['font_height']
        fm = style['font_metrics']
        minor = o.f_to_x(np.asarray(ticks['minor']), rect)
        if _minor_visible(minor):
            p.setPen(style['grid_minor_pen'])
            p.drawLines(_v_lines(minor, rect))
        p.setPen(style['grid_major_pen'])
        p.drawLines(_v_lines(o.f_to_x(np.asarray(ticks['major']), rect), rect))
        p.setPen(style['text_pen'])
        right_edge = rect.left()
        for f, label in zip(ticks['major'], ticks['labels']):
            x = o.f_to_x(f, rect)
            w = fm.horizontalAdvance(label)
            x_text = min(max(x - w / 2, rect.left()), rect.right() - w)
            if x_text >= right_edge:
                p.drawText(QtCore.QPointF(x_text, y_text), label)
                right_edge = x_text + w + 8
        units = f'{ticks["unit_prefix"]}Hz'
        p.setPen(style['text_pen'])
        p.drawText(QtCore.QPointF(rect.right() - fm.horizontalAdvance(units), y_text + style['font_height']), units)
        p.setPen(style['warning_pen'] if o.status_warning else style['text_pen'])
        p.drawText(QtCore.QPointF(rect.left(), y_text + style['font_height']), o.status)

    def _draw_y_axis(self, p, rect, style):
        o = self._owner
        y0, y1 = o.y_view()
        ticks = axis_ticks.ticks(y0, y1, major_max=max(2, int(rect.height() / (2.5 * style['font_height']))))
        if ticks is None:
            return
        fm = style['font_metrics']
        minor = o.y_to_pixel(ticks['minor'], rect)
        if _minor_visible(minor):
            p.setPen(style['grid_minor_pen'])
            p.drawLines(_h_lines(minor, rect))
        p.setPen(style['grid_major_pen'])
        p.drawLines(_h_lines(o.y_to_pixel(ticks['major'], rect), rect))
        p.setPen(style['text_pen'])
        for v, label in zip(ticks['major'], ticks['labels']):
            y = o.y_to_pixel(v, rect)
            if not (rect.top() <= y <= rect.bottom()):
                continue
            p.drawText(QtCore.QPointF(rect.left() - 4 - fm.horizontalAdvance(label), y + style['font_ascent'] / 2), label)
        o.y_prefix = ticks['unit_prefix']

    def _draw_traces(self, p, rect, style):
        o = self._owner
        width = int(rect.width())
        cmap = o.column_map(width)
        if cmap is None:
            return
        x = rect.left() + np.arange(width, dtype=np.float64) + 0.5
        y_limits = (rect.top() - 1, rect.bottom() + 1)
        for name in ['min', 'max', 'average', 'live']:
            y = o.trace(name)
            if y is None:
                continue
            op = np.minimum if name == 'min' else np.maximum
            yc = o.y_to_pixel(column_reduce(y, cmap, op), rect)
            segs = self._points.set_line(x, yc, y_limits)
            p.setPen(style[f'trace_{name}_pen'])
            p.drawPolyline(segs)

    def _draw_peaks(self, p, rect, style):
        o = self._owner
        p.setPen(style['peak_pen'])
        p.setBrush(style['peak_brush'])
        fm = style['font_metrics']
        for idx, (f, db) in enumerate(o.peaks):
            x = o.f_to_x(f, rect)
            y = o.y_to_pixel(o.db_to_display(db), rect)
            if x is None:
                continue
            tri = QtGui.QPolygonF([QtCore.QPointF(x, y - 2), QtCore.QPointF(x - 4, y - 9), QtCore.QPointF(x + 4, y - 9)])
            p.drawPolygon(tri)
            s = str(idx + 1)
            p.drawText(QtCore.QPointF(x - fm.horizontalAdvance(s) / 2, y - 11), s)

    def _draw_hover(self, p, rect, style):
        o = self._owner
        hover = o.hover(self)
        if hover is None:
            return
        p.setPen(style['hover_pen'])
        p.drawLine(QtCore.QPointF(hover.x(), rect.top()), QtCore.QPointF(hover.x(), rect.bottom()))

    def _draw_annotations(self, p, rect, style):
        o = self._owner
        p.setPen(style['text_pen'])
        p.drawText(QtCore.QPointF(rect.left() + 4, rect.top() + style['font_ascent'] + 2), o.y_label())
        lines = o.marker_lines()
        hover = o.hover(self)
        if hover is not None:
            lines = o.hover_lines(o.x_to_f(hover.x(), rect)) + lines
        y = rect.top() + style['font_height'] + 4
        self._draw_text_box(p, style, lines, rect.left() + 4, y, align_right=False)
        self._draw_text_box(p, style, o.peak_lines(), rect.right() - 4, rect.top() + 4, align_right=True)


class WaterfallPlot(_PlotBase):
    """The waterfall (spectrogram) history pane, newest row at top."""

    def __init__(self, owner, parent=None):
        self._image = WaterfallImage()
        super().__init__(owner, parent)
        self.setObjectName('spectrum_waterfall')

    def plot_rect(self):
        left, right = self._owner.margins()
        return QtCore.QRectF(left, 4, max(1, self.width() - left - right), max(1, self.height() - 8))

    def paintEvent(self, event):
        o = self._owner
        style = o.plot_style()
        p = QtGui.QPainter(self)
        try:
            p.fillRect(self.rect(), style['background_brush'])
            p.setFont(style['font'])
            rect = self.plot_rect()
            width = int(rect.width())
            image = None
            cmap = o.column_map(width)
            lo, hi = o.intensity_range()
            if cmap is not None:
                image = self._image.update(o.waterfall, cmap, width, lo, hi, o.color_table(), o.column_map_key())
            if image is not None:
                p.drawImage(rect, image, QtCore.QRectF(0, 0, width, image.height()))
            self._draw_time_axis(p, rect, style)
            self._draw_colorbar(p, rect, style, lo, hi)
            p.setClipRect(rect)
            self._draw_markers(p, rect, style, labels=False)
            hover = o.hover(self)
            if hover is not None:
                p.setPen(style['hover_pen'])
                p.drawLine(QtCore.QPointF(hover.x(), rect.top()), QtCore.QPointF(hover.x(), rect.bottom()))
                lines = o.waterfall_hover_lines(o.x_to_f(hover.x(), rect), (hover.y() - rect.top()) / rect.height())
                p.setClipping(False)
                self._draw_text_box(p, style, lines, rect.left() + 4, rect.top() + 4, align_right=False)
            p.setClipping(False)
            p.setPen(style['border_pen'])
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(rect)
        finally:
            p.end()

    def _draw_time_axis(self, p, rect, style):
        o = self._owner
        duration = o.waterfall_time()
        if not duration:
            return
        ticks = axis_ticks.ticks(0, duration, major_max=max(2, int(rect.height() / (2.5 * style['font_height']))))
        if ticks is None:
            return
        fm = style['font_metrics']
        for t, label in zip(ticks['major'], ticks['labels']):
            y = rect.top() + t / duration * rect.height()
            if t:
                label = f'-{label}'
            label = f'{label} {ticks["unit_prefix"]}s'
            p.setPen(style['grid_major_pen'])
            p.drawLine(QtCore.QPointF(rect.left() - 3, y), QtCore.QPointF(rect.left(), y))
            p.setPen(style['text_pen'])
            y_text = min(max(y + style['font_ascent'] / 2, rect.top() + style['font_ascent']), rect.bottom())
            p.drawText(QtCore.QPointF(rect.left() - 5 - fm.horizontalAdvance(label), y_text), label)

    def _draw_colorbar(self, p, rect, style, lo, hi):
        o = self._owner
        bar = QtCore.QRectF(rect.right() + 6, rect.top(), _COLORBAR_WIDTH, rect.height())
        p.drawImage(bar, o.colorbar_image())
        p.setPen(style['border_pen'])
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRect(bar)
        p.setPen(style['text_pen'])
        x = bar.right() + 3
        p.drawText(QtCore.QPointF(x, bar.top() + style['font_ascent']), f'{hi:.0f}')
        p.drawText(QtCore.QPointF(x, bar.bottom()), f'{lo:.0f}')
        p.drawText(QtCore.QPointF(x, bar.center().y() + style['font_ascent'] / 2), 'dB')
