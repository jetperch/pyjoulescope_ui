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

"""Waveform widget basics.

Maps to the test plan's "Waveform displays" and "add/move markers" rows.
Hardware-free -- driven from a generated recording.

NOTE: the live *view-state* rows (scroll/pan, y-axis range manual/auto, scale
linear/logarithmic) are not automated.  Those mutate the waveform's continuously
re-derived render state; the queryable ``state`` setting is a load/save snapshot,
and the auto-range/repaint loop reverts external changes non-deterministically,
so socket-driven assertions on them are flaky.  Verifying them reliably needs a
"render-settled" signal or a value the renderer exposes -- see
docs/plans/ui_release_test_automation.md.
"""

import os

import numpy as np
import pyjls

from uitest import verify
from uitest.jls_fixtures import write_fsr_v2


def _open(ui_session, tmp_capture, name='wave.jls', n=20000):
    path = str(tmp_capture / name)
    write_fsr_v2(path, sample_rate=1000,
                 data=(0.5 + 0.2 * np.sin(np.arange(n) / 40.0)).astype(np.float32))
    source_id = ui_session.open_file(path)
    ui_session.wait(1.0)
    wf = ui_session.waveform()
    assert wf is not None, 'opening a file did not create a waveform'
    return wf, source_id, path


def test_waveform_displays(ui_session, tmp_capture):
    """Opening a recording yields a waveform spanning the data, and it renders."""
    wf, _, _ = _open(ui_session, tmp_capture)
    x_range = ui_session.query(f'registry/{wf}/settings/x_range')
    assert x_range[1] > x_range[0], f'waveform x_range does not span data: {x_range}'

    png = ui_session.qt_screenshot()
    assert png[:4] == b'\x89PNG'
    assert len(png) > 2000, 'window screenshot looks blank (no rendered content)'


def test_add_remove_signals(ui_session, tmp_capture):
    """Add & remove signals: the per-trace toggle buttons enable/disable signals.

    The waveform's trace controls are real ``QPushButton``s (``trace_1..N``), so
    this drives the actual UI via mouse clicks and verifies the checked state.
    """
    _open(ui_session, tmp_capture)

    def checked(name):
        return ui_session.qt_action('get_property', path=name, property='checked')['value']

    start = checked('trace_2')
    ui_session.qt_action('click', path='trace_2')
    ui_session.wait(0.4)
    assert checked('trace_2') != start, 'clicking the trace button did not toggle the signal'
    ui_session.qt_action('click', path='trace_2')
    ui_session.wait(0.4)
    assert checked('trace_2') == start, 'clicking again did not restore the signal'


def test_markers_single_and_dual_export(ui_session, tmp_capture):
    """Add a single and a dual marker, export, and confirm they round-trip.

    The waveform keeps markers as internal state with no live readback, so they
    are verified through the exported ``.anno`` sidecar (single -> 1 VMARKER,
    dual -> 2 VMARKERs => 3 total).
    """
    wf, source_id, _ = _open(ui_session, tmp_capture)
    signals = ui_session.buffer_signals(source_id)
    x0, x1 = ui_session.query(f'registry/{wf}/settings/x_range')
    span = x1 - x0
    ui_session.publish(f'registry/{wf}/actions/!x_markers',
                       ['add_single', int(x0 + 0.5 * span)])
    ui_session.wait(0.3)
    ui_session.add_dual_markers(wf, x0 + 0.35 * span, x0 + 0.65 * span)

    out = str(tmp_capture / 'wave_export.jls')
    ui_session.export_range(wf, out, x_range=[int(x0 + 0.2 * span), int(x0 + 0.8 * span)],
                            signals=signals)
    anno = ui_session.annotation_path(out)
    assert os.path.isfile(anno), 'export did not write the .anno sidecar'
    markers = verify.count_annotations(anno, annotation_type=pyjls.AnnotationType.VMARKER)
    assert markers == 3, f'expected 3 vertical markers (1 single + 1 dual pair), found {markers}'
