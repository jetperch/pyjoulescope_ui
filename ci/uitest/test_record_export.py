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

Requires a connected device.  The dual-marker *export* leg of the plan still
goes through an interactive save dialog (ExporterDialog) and needs a
non-interactive UI entry point before it can be automated; see the plan doc.
"""

import os

import pytest

from uitest import verify

_RECORD_SECONDS = 2.0


@pytest.mark.device
def test_record_and_reopen(ui_session, device, tmp_capture):
    path = str(tmp_capture / 'recA.jls')

    # Ensure the device is streaming, then record just this device.
    ui_session.publish(f'registry/{device.unique_id}/settings/auto_open', True)
    ui_session.wait_for_statistics(device.unique_id)   # confirms data is flowing
    record_id = ui_session.record_start(path, source_ids=[device.unique_id])
    ui_session.wait(_RECORD_SECONDS)
    ui_session.record_stop(record_id)

    # File is closed now -> safe to read with pyjls.
    assert os.path.isfile(path) and os.path.getsize(path) > 0, 'no recording written'
    assert verify.jls_version(path) == 2
    summary = verify.assert_recording(
        path, signal_names=['current', 'voltage', 'power'],
        min_duration_s=_RECORD_SECONDS * 0.5)   # allow startup latency
    assert summary['sources'], 'recording has no source metadata'

    # Reopen recording A in the UI.
    source_id = ui_session.open_file(path)
    assert source_id in ui_session.buffer_sources()
    assert ui_session.query(f'registry/{source_id}/settings/path') == path
