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

"""Rendered-waveform mouse interactions (scroll/pan, y-axis range/scale).

Maps to the test-plan rows: "waveform displays & scrolls", "y-axis right-click
range manual/auto", "y-axis right-click scale linear/logarithmic".

These drive the waveform like a user -- a horizontal drag to pan, a right-click
on the y-axis to open its context menu, and the menu's Range/Scale actions.
They require a real display that renders the GL plot (the ``rendered_waveform``
fixture skips otherwise), since the waveform's mouse hit-testing needs the
painted geometry.
"""

import os
import time

import numpy as np
import pytest


def _midy(session, wf):
    geo = session.plot_geometry(wf)
    return geo[2], geo[3], geo[3] // 2  # width, height, mid-y


def _add_centered_marker(session, wf, dual=False):
    """Zoom in and add an x-marker at the view centre; return its info.

    A dual marker spans 40% to 60% of the zoomed view.
    """
    ext = session.query(f'registry/{wf}/settings/x_range')
    span = ext[1] - ext[0]
    session.publish(f'registry/{wf}/actions/!x_range',
                    [int(ext[0] + 0.3 * span), int(ext[0] + 0.7 * span)])
    session.wait(1.0)
    x0, x1 = session.query(f'registry/{wf}/settings/x_range')
    if dual:
        session.add_dual_markers(wf, x0 + 0.4 * (x1 - x0), x0 + 0.6 * (x1 - x0))
    else:
        session.publish(f'registry/{wf}/actions/!x_markers',
                        ['add_single', int((x0 + x1) // 2)])
    session.wait(0.6)
    info = session.x_markers_info(wf)
    assert info, 'marker was not added'
    return info[0]


def test_pan(rendered_waveform):
    """Scroll/pan: a horizontal drag moves the (zoomed-in) view."""
    session, wf, _ = rendered_waveform
    w, h, midy = _midy(session, wf)

    # Zoom in so there is room to pan (a fresh file view is at the extents).
    ext = session.query(f'registry/{wf}/settings/x_range')
    span = ext[1] - ext[0]
    session.publish(f'registry/{wf}/actions/!x_range',
                    [int(ext[0] + 0.35 * span), int(ext[0] + 0.65 * span)])
    session.wait(1.0)

    x0 = session.query(f'registry/{wf}/settings/x_range')
    session.qt_action('drag', path=session.plot_path(wf),
                      start=[int(w * 0.6), midy], end=[int(w * 0.35), midy])
    session.wait(0.8)
    x1 = session.query(f'registry/{wf}/settings/x_range')
    assert x1 != x0, 'horizontal drag did not pan the view'


def _check_y_axis_range_menu(session, wf):
    _w, _h, midy = _midy(session, wf)
    session.right_click(wf, 25, midy)
    items = session.menu_items()
    assert any('Range/Manual' in i for i in items), f'no Range menu: {items}'
    assert session.menu_invoke('Manual')['ok']
    session.wait(0.4)
    session.right_click(wf, 25, midy)
    assert session.menu_invoke('Auto')['ok']


def _check_y_axis_scale_menu(session, wf):
    """Verified through the menu itself: the 'Logarithmic zero' submenu only
    appears while the scale is logarithmic."""
    _w, _h, midy = _midy(session, wf)
    session.right_click(wf, 25, midy)
    items = session.menu_items()
    assert any('Scale/Logarithmic' in i for i in items), f'no Scale menu: {items}'
    assert session.menu_invoke('Logarithmic')['ok']
    session.wait(0.5)

    session.right_click(wf, 25, midy)
    after = session.menu_items()
    assert any('Logarithmic zero' in i for i in after), \
        'scale did not switch to logarithmic (no Logarithmic-zero submenu)'
    assert session.menu_invoke('Linear')['ok']
    session.wait(0.5)

    session.right_click(wf, 25, midy)
    restored = session.menu_items()
    assert not any('Logarithmic zero' in i for i in restored), \
        'scale did not switch back to linear'
    session.qt_action('key', key='Escape')


def test_y_axis_range_menu(rendered_waveform):
    """y-axis right-click Range -> Manual / Auto works."""
    session, wf, _ = rendered_waveform
    _check_y_axis_range_menu(session, wf)


def test_y_axis_scale_menu(rendered_waveform):
    """y-axis right-click Scale -> Logarithmic / Linear works."""
    session, wf, _ = rendered_waveform
    _check_y_axis_scale_menu(session, wf)


def _pause_live(session, wf):
    """Pause streaming and unpin the view so it stops following live data."""
    session.publish('registry/app/settings/signal_stream_enable', False)
    session.publish(f'registry/{wf}/settings/pin_left', False)
    session.publish(f'registry/{wf}/settings/pin_right', False)
    session.wait(0.5)


@pytest.mark.device
def test_live_display_and_scroll(rendered_live_waveform):
    """The live waveform advances while streaming, then pans when paused."""
    session, wf, _device = rendered_live_waveform
    topic = f'registry/{wf}/settings/x_range'
    x0 = session.wait_for(topic, lambda v: v is not None and v[1] > v[0], timeout=10.0)
    session.wait_for(topic, lambda v: v[1] > x0[1], timeout=5.0)

    _pause_live(session, wf)
    ext = session.query(topic)
    span = ext[1] - ext[0]
    session.publish(f'registry/{wf}/actions/!x_range',
                    [int(ext[0] + 0.35 * span), int(ext[0] + 0.65 * span)])
    session.wait(1.0)
    w, _h, midy = _midy(session, wf)
    before = session.query(topic)
    session.qt_action('drag', path=session.plot_path(wf),
                      start=[int(w * 0.6), midy], end=[int(w * 0.35), midy])
    session.wait(0.8)
    assert session.query(topic) != before, 'horizontal drag did not pan the live view'


@pytest.mark.device
def test_live_y_axis_menus(rendered_live_waveform):
    """y-axis Range and Scale menus on the live waveform."""
    session, wf, _device = rendered_live_waveform
    _pause_live(session, wf)
    _check_y_axis_range_menu(session, wf)
    _check_y_axis_scale_menu(session, wf)


def test_marker_move(rendered_waveform):
    """Move a marker by dragging its painted line to a new position."""
    session, wf, _ = rendered_waveform
    _w, _h, midy = _midy(session, wf)
    marker = _add_centered_marker(session, wf)
    pixel, pos0 = marker['pixel1'], marker['pos1']

    session.qt_action('drag', path=session.plot_path(wf),
                      start=[pixel, midy], end=[pixel - 200, midy])
    session.wait(0.6)
    info = session.x_markers_info(wf)
    assert info, 'marker disappeared after drag'
    assert info[0]['pos1'] != pos0, 'dragging the marker did not move it'


def test_marker_remove(rendered_waveform):
    """Remove a marker via its right-click context menu -> Remove."""
    session, wf, _ = rendered_waveform
    _w, _h, midy = _midy(session, wf)
    marker = _add_centered_marker(session, wf)

    items = session.right_click_marker(wf, marker['pixel1'], midy)
    assert 'Remove' in items, f'right-click did not open the marker menu: {items[:5]}'
    assert session.menu_invoke('Remove')['ok']
    session.wait(0.5)
    assert session.x_markers_info(wf) == [], 'marker was not removed'


def test_dual_marker_move(rendered_waveform):
    """Move each line of a dual marker by dragging it."""
    session, wf, _ = rendered_waveform
    _w, _h, midy = _midy(session, wf)
    marker = _add_centered_marker(session, wf, dual=True)
    assert marker['dtype'] == 'dual'

    session.qt_action('drag', path=session.plot_path(wf),
                      start=[marker['pixel2'], midy], end=[marker['pixel2'] + 100, midy])
    session.wait(0.6)
    moved = session.x_markers_info(wf)[0]
    assert moved['pos2'] != marker['pos2'], 'dragging line 2 did not move it'
    assert moved['pos1'] == marker['pos1'], 'dragging line 2 moved line 1'

    session.qt_action('drag', path=session.plot_path(wf),
                      start=[moved['pixel1'], midy], end=[moved['pixel1'] - 100, midy])
    session.wait(0.6)
    final = session.x_markers_info(wf)[0]
    assert final['pos1'] != moved['pos1'], 'dragging line 1 did not move it'
    assert final['pos2'] == moved['pos2'], 'dragging line 1 moved line 2'


def test_dual_marker_remove(rendered_waveform):
    """Remove a dual marker (both lines) via its right-click menu -> Remove."""
    session, wf, _ = rendered_waveform
    _w, _h, midy = _midy(session, wf)
    marker = _add_centered_marker(session, wf, dual=True)

    items = session.right_click_marker(wf, marker['pixel2'], midy)
    assert 'Remove' in items, f'right-click did not open the marker menu: {items[:5]}'
    assert session.menu_invoke('Remove')['ok']
    session.wait(0.5)
    assert session.x_markers_info(wf) == [], 'dual marker was not removed'


def _spike_data():
    """Min/max band 0.3..0.5 with one sample far above it."""
    data = np.full(40000, 0.3, dtype=np.float32)
    data[1::2] = 0.5
    data[20000] = 1000.0
    return data


def _trace_pixels(path, size=None):
    """Count the image pixels in the (yellow) trace color family.

    :param size: The optional (width, height) logical size to scale to first.
    """
    from PySide6 import QtGui
    img = QtGui.QImage(str(path))
    if size is not None:
        img = img.scaled(*size)
    img = img.convertToFormat(QtGui.QImage.Format.Format_RGB32)
    a = np.frombuffer(img.constBits(), dtype=np.uint8)
    a = a.reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width(), :3].astype(int)
    b, g, r = a[..., 0], a[..., 1], a[..., 2]
    return int(np.count_nonzero(((r - b) > 40) & ((g - b) > 40)))


@pytest.mark.waveform_data(factory=_spike_data)
def test_fill_with_offscreen_spike(rendered_waveform, tmp_path):
    """The min/max fill renders when a spike extends far past the Y range  #352.

    The OpenGL plot must match the raster image export, which never had the bug.
    Grabs return the last GL frame, and an occluded Wayland window may not
    repaint, so resize to force a fresh frame, then grab the main window.
    Change the width: Windows gives extra height to another dock and does not
    repaint a GL widget whose size is unchanged.
    """
    session, wf, _ = rendered_waveform
    session.publish(f'registry/{wf}/settings/show_min_max', 2)  # fill 1
    session.publish(f'registry/{wf}/actions/!plot_config',
                    [{'index': 0, 'changes': {'range_mode': 'manual', 'range': [0.0, 0.8]}}])
    session.wait_for(f'registry/{wf}/settings/state',
                     lambda s: s['plots'][0]['range'] == [0.0, 0.8])
    width, height = session.qt_inspect(path='', max_depth=0)['geometry'][2:]
    window_size = (width - 1, height)
    paint_count = session.plot_render_info(wf)['paint_count']
    session.resize_window(*window_size)
    assert session.wait_for_paint(wf, paint_count), 'plot did not repaint'
    session.wait(0.5)
    gl_path = tmp_path / 'gl.png'
    session.screenshot(str(gl_path))
    raster_path = tmp_path / 'raster.png'
    session.publish(f'registry/{wf}/actions/!save_image', str(raster_path))
    deadline = time.monotonic() + 10.0
    while not os.path.isfile(raster_path) and time.monotonic() < deadline:
        session.wait(0.2)
    assert os.path.isfile(raster_path), 'image export did not complete'

    gl, raster = _trace_pixels(gl_path, window_size), _trace_pixels(raster_path)
    plot_w, plot_h = session.plot_geometry(wf)[2:]
    assert raster > 0.05 * plot_w * plot_h, f'raster export has no min/max fill ({raster})'
    assert gl > 0.8 * raster, f'OpenGL fill missing: gl={gl}, raster={raster}'
