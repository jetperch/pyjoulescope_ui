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
record/export rows.  Hardware-free:

* the **v1** fixture is the canonical ``js110_evk1_10s_0_7_0.jls`` (fetched on
  demand), opened through the UI's v1 parser;
* the **v2** fixture is generated deterministically with pyjls, opened through
  the UI, and independently verified with :mod:`pyjls` (``verify``).
"""

import numpy as np

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
