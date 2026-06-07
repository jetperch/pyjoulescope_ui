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

"""Live record from a device, then reopen and verify.

Maps to the test plan's "Live view record ... Press record, wait, stop ... Open
recording A, verify correct" legs.  Records a short window from the device under
test, stops (which finalizes/closes the JLS), verifies the file with pyjls, and
reopens it in the UI.

Requires a connected device.
"""

import os

import pyjls
import pytest

from uitest import verify

_RECORD_SECONDS = 2.0


def _record(ui_session, device, path):
    """Record a short window from ``device`` to ``path`` and finalize it."""
    ui_session.publish(f'registry/{device.unique_id}/settings/auto_open', True)
    ui_session.wait_for_statistics(device.unique_id)   # confirms data is flowing
    record_id = ui_session.record_start(path, source_ids=[device.unique_id])
    ui_session.wait(_RECORD_SECONDS)
    ui_session.record_stop(record_id)
    assert os.path.isfile(path) and os.path.getsize(path) > 0, 'no recording written'


@pytest.mark.device
def test_record_and_reopen(ui_session, device, tmp_capture):
    path = str(tmp_capture / 'recA.jls')
    _record(ui_session, device, path)

    # File is closed now -> safe to read with pyjls.
    assert verify.jls_version(path) == 2
    summary = verify.assert_recording(
        path, signal_names=['current', 'voltage', 'power'],
        min_duration_s=_RECORD_SECONDS * 0.5)   # allow startup latency
    assert summary['sources'], 'recording has no source metadata'

    # Reopen recording A in the UI.
    source_id = ui_session.open_file(path)
    assert source_id in ui_session.buffer_sources()
    assert ui_session.query(f'registry/{source_id}/settings/path') == path


@pytest.mark.device
def test_record_markers_export(ui_session, device, tmp_capture):
    """Record A, add dual markers, export to B, verify B's data and markers.

    Mirrors the plan's "record A ... add dual markers, export to B ... open
    export B, verify correct" leg.  The exporter writes data to B.jls and the
    markers to the B.anno.jls sidecar.
    """
    path_a = str(tmp_capture / 'recA.jls')
    path_b = str(tmp_capture / 'exportB.jls')
    _record(ui_session, device, path_a)

    source_id = ui_session.open_file(path_a)
    ui_session.wait(1.0)
    wf = ui_session.waveform()
    signals = ui_session.buffer_signals(source_id)
    assert signals, 'opened recording exposed no signals'

    x0, x1 = ui_session.query(f'registry/{wf}/settings/x_range')
    span = x1 - x0
    # Dual markers strictly inside the export sub-range.
    ui_session.add_dual_markers(wf, x0 + 0.45 * span, x0 + 0.55 * span)
    ui_session.export_range(
        wf, path_b, x_range=[int(x0 + 0.3 * span), int(x0 + 0.7 * span)],
        signals=signals)

    # B.jls carries the data; B.anno.jls carries the markers.
    verify.assert_recording(path_b, signal_names=['current', 'voltage', 'power'])
    anno = ui_session.annotation_path(path_b)
    assert os.path.isfile(anno), 'export did not write the .anno sidecar'
    markers = verify.count_annotations(anno, annotation_type=pyjls.AnnotationType.VMARKER)
    assert markers == 2, f'expected 2 vertical markers in export, found {markers}'

    # Open export B and confirm it loads.
    b_source = ui_session.open_file(path_b)
    assert b_source in ui_session.buffer_sources()
