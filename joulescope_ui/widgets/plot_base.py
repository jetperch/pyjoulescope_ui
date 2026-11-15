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

"""Shared QPainter plot helpers for the Spectrum and Efficiency widgets.

Each widget defines its own style variables with a common set of names
under its prefix, such as ``spectrum.grid_major``.  See :func:`style_build`.
"""

from PySide6 import QtCore, QtGui
from joulescope_ui.styles import color_as_qcolor, font_as_qfont
from joulescope_ui.styles.manager import _load_cls_colors, _load_cls_fonts
import numpy as np


MINOR_GRID_PIXELS = 6


def style_vars(widget):
    """Get the style variables for a styled widget.

    :param widget: The styled widget instance.
    :return: The style variables dict.  Widgets not rendered by the style
        manager, such as in unit tests, get the dark colors and js1 fonts.
    """
    style_obj = getattr(widget, 'style_obj', None)
    if style_obj is not None:
        return style_obj['vars']
    cls = type(widget)
    return {**_load_cls_colors(cls)['dark'], **_load_cls_fonts(cls)['js1']}


def style_build(v, prefix):
    """Build the common plot style.

    :param v: The style variables from :func:`style_vars`.
    :param prefix: The style variable prefix, such as 'spectrum'.
    :return: The style dict with the common pens, brushes, and font.
        Requires the variables {prefix}.background, text_foreground,
        text_background, grid_major, grid_minor, plot_border, hover,
        status_warning, and axis_font.
    """
    font = font_as_qfont(v[f'{prefix}.axis_font'])
    fm = QtGui.QFontMetrics(font)

    def color(name):
        return color_as_qcolor(v[f'{prefix}.{name}'])

    return {
        'background': color('background'),
        'background_brush': QtGui.QBrush(color('background')),
        'text_pen': QtGui.QPen(color('text_foreground')),
        'text_bg_brush': QtGui.QBrush(color('text_background')),
        'grid_major_pen': QtGui.QPen(color('grid_major')),
        'grid_minor_pen': QtGui.QPen(color('grid_minor')),
        'border_pen': QtGui.QPen(color('plot_border')),
        'hover_pen': QtGui.QPen(color('hover')),
        'warning_pen': QtGui.QPen(color('status_warning')),
        'font': font,
        'font_metrics': fm,
        'font_height': fm.height(),
        'font_ascent': fm.ascent(),
    }


def autoscale_hysteresis(current, lo, hi, step):
    """Autoscale an axis range without jitter.

    :param current: The current [y0, y1] range, or None.
    :param lo: The data minimum.
    :param hi: The data maximum.
    :param step: The range granularity.  The range snaps to multiples of
        step with at least half a step of margin, and only changes when
        the data leaves it or falls well inside it.
    :return: The new [y0, y1] range.
    """
    target_hi = np.ceil((hi + 0.5 * step) / step) * step
    target_lo = np.floor((lo - 0.5 * step) / step) * step
    if current is None:
        return [target_lo, target_hi]
    y0, y1 = current
    if hi > y1 or hi < y1 - 3 * step:
        y1 = target_hi
    if lo < y0 or lo > y0 + 4 * step:
        y0 = target_lo
    if y1 - y0 < 2 * step:
        y0 = y1 - 2 * step
    return [y0, y1]


def minor_visible(v):
    """True if minor grid lines at pixels v are far enough apart to draw."""
    return v is not None and len(v) > 1 and np.min(np.abs(np.diff(v))) >= MINOR_GRID_PIXELS


def v_lines(x, rect):
    """Vertical grid lines at x within rect, for QPainter.drawLines."""
    if x is None:
        return []
    t, b = rect.top(), rect.bottom()
    return [QtCore.QLineF(v, t, v, b) for v in x if rect.left() <= v <= rect.right()]


def h_lines(y, rect):
    """Horizontal grid lines at y within rect, for QPainter.drawLines."""
    left, right = rect.left(), rect.right()
    return [QtCore.QLineF(left, v, right, v) for v in y if rect.top() <= v <= rect.bottom()]


def draw_x_axis(p, rect, style, ticks, x_to_pixel):
    """Draw the x grid and the major tick labels below rect.

    :param ticks: The ticks from :mod:`axis_ticks`, or None.
    :param x_to_pixel: The callable(values) -> pixel array.
    :return: The baseline y for the tick labels.
    """
    y_text = rect.bottom() + style['font_height']
    if ticks is None:
        return y_text
    fm = style['font_metrics']
    minor = x_to_pixel(np.asarray(ticks['minor']))
    if minor_visible(minor):
        p.setPen(style['grid_minor_pen'])
        p.drawLines(v_lines(minor, rect))
    major = x_to_pixel(np.asarray(ticks['major']))
    p.setPen(style['grid_major_pen'])
    p.drawLines(v_lines(major, rect))
    p.setPen(style['text_pen'])
    right_edge = rect.left()
    for x, label in zip(major, ticks['labels']):
        w = fm.horizontalAdvance(label)
        x_text = min(max(x - w / 2, rect.left()), rect.right() - w)
        if x_text >= right_edge:
            p.drawText(QtCore.QPointF(x_text, y_text), label)
            right_edge = x_text + w + 8
    return y_text


def draw_y_axis(p, rect, style, ticks, y_to_pixel):
    """Draw the y grid and the major tick labels left of rect.

    :param ticks: The ticks from :mod:`axis_ticks`, or None.
    :param y_to_pixel: The callable(values) -> pixel array.
    :return: The ticks unit prefix, or '' when no ticks.
    """
    if ticks is None:
        return ''
    fm = style['font_metrics']
    minor = y_to_pixel(ticks['minor'])
    if minor_visible(minor):
        p.setPen(style['grid_minor_pen'])
        p.drawLines(h_lines(minor, rect))
    major = y_to_pixel(ticks['major'])
    p.setPen(style['grid_major_pen'])
    p.drawLines(h_lines(major, rect))
    p.setPen(style['text_pen'])
    for y, label in zip(major, ticks['labels']):
        if not (rect.top() <= y <= rect.bottom()):
            continue
        p.drawText(QtCore.QPointF(rect.left() - 4 - fm.horizontalAdvance(label), y + style['font_ascent'] / 2), label)
    return ticks['unit_prefix']


def draw_v_line(p, rect, pen, x):
    """Draw a vertical line across rect at x."""
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))


def draw_text_box(p, style, lines, x, y, align_right):
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


def draw_border(p, rect, style):
    """Draw the plot border around rect."""
    p.setPen(style['border_pen'])
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawRect(rect)
