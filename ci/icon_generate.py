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
import struct
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


def _ico_bmp_payload(img: Image.Image) -> bytes:
    # ICO BMP-style entry: BITMAPINFOHEADER + bottom-up BGRA pixels + AND mask.
    # Pillow's plain ICO writer emits PNG-encoded entries for every size and
    # sorts smallest-first, which Windows tools (PyInstaller, Inno Setup,
    # Explorer thumbnails) handle inconsistently for sub-256 sizes. The legacy
    # Vista+ layout expected by those tools uses BMP for small entries.
    #
    # The AND mask must be derived from the alpha channel: legacy/downlevel
    # render paths use it for 1-bit transparency even when the BGRA carries
    # an alpha channel. An all-zero (opaque) mask combined with alpha=0 corner
    # pixels causes corners to render black or get dropped in some contexts.
    img = img.convert('RGBA')
    w, h = img.size
    pixels = img.tobytes('raw', 'BGRA')
    bih = struct.pack(
        '<IiiHHIIiiII',
        40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0,
    )
    rows = [pixels[y * w * 4:(y + 1) * w * 4] for y in range(h - 1, -1, -1)]
    xor_mask = b''.join(rows)

    alpha = img.split()[3].load()
    and_row_bytes = ((w + 31) // 32) * 4
    and_rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray(and_row_bytes)
        for x in range(w):
            if alpha[x, y] < 128:
                row[x // 8] |= 0x80 >> (x % 8)
        and_rows.append(bytes(row))
    and_mask = b''.join(and_rows)
    return bih + xor_mask + and_mask


def _ico_png_payload(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert('RGBA').save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def write_ico(path: str, images_by_size: dict) -> None:
    # Match the legacy Joulescope icon.ico layout: largest entries first, PNG
    # encoding only for 256x256, BMP encoding for everything smaller.
    sizes = sorted(images_by_size.keys(), reverse=True)
    payloads = []
    for s in sizes:
        if s >= 256:
            payloads.append(_ico_png_payload(images_by_size[s]))
        else:
            payloads.append(_ico_bmp_payload(images_by_size[s]))
    n = len(sizes)
    header = struct.pack('<HHH', 0, 1, n)
    offset = 6 + 16 * n
    directory = []
    for s, blob in zip(sizes, payloads):
        b = 0 if s == 256 else s  # 256 is encoded as 0 in the byte field
        directory.append(struct.pack(
            '<BBBBHHII', b, b, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    with open(path, 'wb') as f:
        f.write(header)
        for d in directory:
            f.write(d)
        for blob in payloads:
            f.write(blob)


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
    write_ico(ico_target, {s: get_image(s) for s in ICO_SIZES})
    print(f'wrote {ico_target}')

    ico64_target = os.path.join(RES, 'icon_64x64.ico')
    write_ico(ico64_target, {64: get_image(64)})
    print(f'wrote {ico64_target}')

    icns_target = os.path.join(RES, 'icon.icns')
    get_image(max(ICNS_SIZES)).save(
        icns_target, format='ICNS', sizes=[(s, s) for s in ICNS_SIZES])
    print(f'wrote {icns_target}')


if __name__ == '__main__':
    main()
