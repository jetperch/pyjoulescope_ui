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


def _midy(session, wf):
    geo = session.plot_geometry(wf)
    return geo[2], geo[3], geo[3] // 2  # width, height, mid-y


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


def test_y_axis_range_menu(rendered_waveform):
    """y-axis right-click Range -> Manual / Auto works."""
    session, wf, _ = rendered_waveform
    _w, _h, midy = _midy(session, wf)

    session.right_click(wf, 25, midy)
    items = session.menu_items()
    assert any('Range/Manual' in i for i in items), f'no Range menu: {items}'
    assert session.menu_invoke('Manual')['ok']
    session.wait(0.4)
    session.right_click(wf, 25, midy)
    assert session.menu_invoke('Auto')['ok']


def test_y_axis_scale_menu(rendered_waveform):
    """y-axis right-click Scale -> Logarithmic / Linear works.

    Verified through the menu itself: the 'Logarithmic zero' submenu only appears
    while the scale is logarithmic.
    """
    session, wf, _ = rendered_waveform
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
