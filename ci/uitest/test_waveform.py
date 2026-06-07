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

Maps to the test plan's "Waveform displays & scrolls" row.  Opening a recording
creates a waveform whose x-range spans the data, and the window renders content.

NOTE: the remaining waveform rows (y-axis range/scale, add/remove signals,
add/move markers) and the analysis tools (USB Inrush / Histogram / CDF /
Frequency) are not yet automated.  They drive the range-tool ``!run`` protocol,
which needs the waveform's *effective* signal-id list (what ``_signals_get()``
feeds the tool); that list is computed internally and is not currently exposed
as a queryable topic, and the export/analysis result paths use interactive
dialogs.  Automating them needs a non-interactive UI entry point -- see
docs/plans/ui_release_test_automation.md.
"""

import numpy as np

from uitest.jls_fixtures import write_fsr_v2


def test_waveform_displays(ui_session, tmp_capture):
    """Opening a recording yields a waveform spanning the data, and it renders."""
    path = str(tmp_capture / 'wave.jls')
    write_fsr_v2(path, sample_rate=1000,
                 data=np.linspace(0.0, 1.0, 12000, dtype=np.float32))
    ui_session.open_file(path)
    ui_session.wait(1.0)

    waveforms = [i for i in ui_session.enumerate('registry')
                 if i.startswith('WaveformWidget:')]
    assert waveforms, 'opening a file did not create a waveform widget'
    x_range = ui_session.query(f'registry/{waveforms[-1]}/settings/x_range')
    assert x_range[1] > x_range[0], f'waveform x_range does not span data: {x_range}'

    png = ui_session.qt_screenshot()
    assert png[:4] == b'\x89PNG'
    assert len(png) > 2000, 'window screenshot looks blank (no rendered content)'
