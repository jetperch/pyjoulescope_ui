#!/usr/bin/env python3
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

"""Regenerate every application icon asset from joulescope_ui/resources/icon.svg.

Outputs (all under joulescope_ui/resources/):
    icon.iconset/icon_{16,32,64,128,256,512}.png
    icon.iconset/icon_{16,32,64,128,256,512}@2.png
    icon.ico            multi-resolution Windows icon (PyInstaller, Inno Setup)
    icon_64x64.ico      single 64x64 icon embedded in resources.rcc at runtime
    icon.icns           macOS app bundle icon

After running, also re-run setup.py convert_qt_ui to refresh resources.rcc.

Usage:
    python ci/icon_generate.py

Dependencies (already project deps): PySide6, Pillow.
"""

import io
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image
from PySide6 import QtCore, QtGui
from PySide6.QtSvg import QSvgRenderer


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RES = os.path.join(REPO, 'joulescope_ui', 'resources')
SVG_PATH = os.path.join(RES, 'icon.svg')
ICONSET = os.path.join(RES, 'icon.iconset')


ICONSET_SIZES = [16, 32, 64, 128, 256, 512]
ICO_SIZES = [16, 32, 48, 64, 128, 256]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def _ensure_app():
    app = QtGui.QGuiApplication.instance()
    if app is None:
        app = QtGui.QGuiApplication(sys.argv[:1])
    return app


def render_png(svg_data: bytes, size: int) -> bytes:
    renderer = QSvgRenderer(QtCore.QByteArray(svg_data))
    image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)
    image.save(buf, 'PNG')
    return bytes(buf.data())


def main():
    _ensure_app()
    with open(SVG_PATH, 'rb') as f:
        svg_data = f.read()
    os.makedirs(ICONSET, exist_ok=True)

    cache: dict = {}

    def get_image(px: int) -> Image.Image:
        img = cache.get(px)
        if img is None:
            png = render_png(svg_data, px)
            img = Image.open(io.BytesIO(png)).convert('RGBA')
            cache[px] = img
        return img

    for size in ICONSET_SIZES:
        for tag, px in ((f'{size}x{size}', size), (f'{size}x{size}@2', size * 2)):
            target = os.path.join(ICONSET, f'icon_{tag}.png')
            get_image(px).save(target, 'PNG')
            print(f'wrote {target}')

    ico_target = os.path.join(RES, 'icon.ico')
    get_image(max(ICO_SIZES)).save(
        ico_target, format='ICO', sizes=[(s, s) for s in ICO_SIZES])
    print(f'wrote {ico_target}')

    ico64_target = os.path.join(RES, 'icon_64x64.ico')
    get_image(64).save(ico64_target, format='ICO', sizes=[(64, 64)])
    print(f'wrote {ico64_target}')

    icns_target = os.path.join(RES, 'icon.icns')
    get_image(max(ICNS_SIZES)).save(
        icns_target, format='ICNS', sizes=[(s, s) for s in ICNS_SIZES])
    print(f'wrote {icns_target}')


if __name__ == '__main__':
    main()
