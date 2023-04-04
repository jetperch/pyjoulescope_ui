# Copyright 2023 Jetperch LLC
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

"""Manage fonts.

The Joulescope UI often looks better with tabular fonts or
monospaced fonts.
"""


from PySide6 import QtGui


_font_weight_map = {
    QtGui.QFont.Weight.Thin: ['100', 'thin'],
    QtGui.QFont.Weight.ExtraLight: ['200', 'extralight'],
    QtGui.QFont.Weight.Light: ['300', 'light'],
    QtGui.QFont.Weight.Normal: ['400', 'normal'],
    QtGui.QFont.Weight.Medium: ['500', 'medium'],
    QtGui.QFont.Weight.DemiBold: ['600', 'demibold'],
    QtGui.QFont.Weight.Bold: ['700', 'bold'],
    QtGui.QFont.Weight.ExtraBold: ['800', 'extrabold'],
    QtGui.QFont.Weight.Black: ['900', 'black'],
}
_font_weight_map_reverse = {}


def _font_weight_map_reverse_construct():
    for key, values in _font_weight_map.items():
        for v in values:
            _font_weight_map_reverse[v] = key


_font_weight_map_reverse_construct()


def font_as_qfont(s) -> QtGui.QFont:
    if isinstance(s, QtGui.QFont):
        return QtGui.QFont(s)
    elif not isinstance(s, str):
        raise ValueError(f'Unsupported font type for {s}')
    font = QtGui.QFont()
    parts = s.split()
    while len(parts):
        p = parts.pop(0)
        if p[0] == '"':
            fontname = ' '.join([p] + parts)[1:-1]
            font.setFamily(fontname)
            parts.clear()
        elif p in _font_weight_map_reverse:
            font.setWeight(_font_weight_map_reverse[p])
        elif p == 'normal':
            font.setItalic(False)
        elif p == 'italic':
            font.setItalic(True)
        elif p[0] in '0123456789':
            if p.endswith('pt'):
                sz = float(p[:-2])
                font.setPointSizeF(sz)
            elif p.endswith('px'):
                sz = int(p[:-2])
                font.setPixelSize(sz)
            else:
                raise ValueError(f'unsupported font size: {p}')
        else:
            raise ValueError(f'unsupported font specification: {s}')
    return font


def font_as_qss(font) -> str:
    """Convert font to QSS font specification.

    :param font: The font specification as QFont or qss string.
    :return: The qss font string specification.
        Example: bold italic 12pt "Times New Roman"
    """
    if isinstance(font, str):
        font = font_as_qfont(font)
    elif not isinstance(font, QtGui.QFont):
        raise ValueError(f'Unsupported font type for {font}')

    # https://doc.qt.io/qt-6/qfont.html
    # https://doc.qt.io/qt-6/stylesheet-reference.html
    weight = font.weight()
    weight_str = _font_weight_map.get(weight, None)
    weight_str = '' if weight_str is None else weight_str[0] + ' '
    italic = 'italic ' if font.italic() else ''
    size = f'{font.pointSize()}pt '
    return f'{weight_str}{italic}{size}"{font.family()}"'
