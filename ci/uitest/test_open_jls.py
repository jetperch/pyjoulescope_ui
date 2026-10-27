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

"""Open recordings and verify they load.

Maps to the test plan's "Open JLS v1 recording" and the open/verify legs of the
record/export rows.  Hardware-free (the v1 zoom/pan/export test needs a display):

* the **v1** fixture is the canonical ``js110_evk1_10s_0_7_0.jls`` (fetched on
  demand), opened through the UI's v1 parser;
* the **v2** fixture is generated deterministically with pyjls, opened through
  the UI, and independently verified with :mod:`pyjls` (``verify``).
"""

import numpy as np
import pyjls
import pytest

from uitest import assets, verify
from uitest.jls_fixtures import write_fsr_v2


def test_open_jls_v1(ui_session):
    """The canonical JLS v1 recording opens and registers a buffer source."""
    path = assets.get_asset(assets.JLS_V1_EVK1)
    assert verify.jls_version(path) == 1
    source_id = ui_session.open_file(path)
    assert source_id in ui_session.buffer_sources()
    assert ui_session.query(f'registry/{source_id}/settings/path') == path


def test_open_jls_v2(ui_session, tmp_capture):
    """A generated JLS v2 recording opens, and its contents verify with pyjls."""
    path = str(tmp_capture / 'gen_v2.jls')
    data = (0.5 + 0.1 * np.sin(np.arange(10000) / 100.0)).astype(np.float32)
    write_fsr_v2(path, signal_name='current', sample_rate=1000, data=data, markers=2)

    # Independent file-level verification (the "verify correct" check).
    verify.assert_recording(path, signal_names=['current'], min_duration_s=9.0,
                            value_range=(0.0, 1.0))
    verify.assert_has_markers(path, 2)

    # And the UI opens it.
    source_id = ui_session.open_file(path)
    assert source_id in ui_session.buffer_sources()
    assert ui_session.query(f'registry/{source_id}/settings/path') == path


def _v1_path():
    return assets.get_asset(assets.JLS_V1_EVK1)


@pytest.mark.waveform_path(factory=_v1_path)
def test_jls_v1_zoom_pan_export(rendered_waveform, tmp_capture):
    """JLS v1: zoom in/out, pan, add dual markers, export A, reopen A, verify."""
    session, wf, source_id = rendered_waveform
    topic = f'registry/{wf}/settings/x_range'
    ext = session.query(topic)
    span = ext[1] - ext[0]
    zoom = [int(ext[0] + 0.4 * span), int(ext[0] + 0.6 * span)]
    session.publish(f'registry/{wf}/actions/!x_range', zoom)
    zoomed = session.wait_for(topic, lambda v: v[1] - v[0] < 0.5 * span, timeout=5.0)

    w, h = session.plot_geometry(wf)[2:]
    session.qt_action('drag', path=session.plot_path(wf),
                      start=[int(w * 0.6), h // 2], end=[int(w * 0.35), h // 2])
    session.wait_for(topic, lambda v: v != zoomed, timeout=5.0)

    session.publish(f'registry/{wf}/actions/!x_range', list(ext))
    session.wait_for(topic, lambda v: v[1] - v[0] > 0.9 * span, timeout=5.0)

    x0, x1 = session.source_utc_range(source_id)
    s = x1 - x0
    session.add_dual_markers(wf, x0 + 0.45 * s, x0 + 0.55 * s)
    path_a = str(tmp_capture / 'A.jls')
    session.export_range(wf, path_a, x_range=[int(x0 + 0.4 * s), int(x0 + 0.6 * s)],
                         signals=session.buffer_signals(source_id), timeout=120.0)
    verify.assert_recording(path_a, signal_names=['current', 'voltage', 'power'])
    for name in ['current', 'voltage', 'power']:
        verify.compare_subrange(_v1_path(), path_a, name)
    assert verify.count_annotations(session.annotation_path(path_a),
                                    annotation_type=pyjls.AnnotationType.VMARKER) == 2
    source_a = session.open_file(path_a)
    assert source_a in session.buffer_sources()
