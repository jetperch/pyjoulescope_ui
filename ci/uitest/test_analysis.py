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

"""Waveform analysis range tools.

Maps to the test plan's "analysis Histogram / CDF / Frequency" rows.  Opens a
recording, then runs each range tool over a sub-range via the non-interactive
``WaveformWidget`` ``!range_tool`` action (added to the UI for automation),
accepts the tool's config dialog, and asserts a result widget is created.

Hardware-free.  Notes:
* **USB Inrush** requires the external USBET library and is not registered in a
  default install, so it is not covered here.
* **MaxWindow** does not create a persistent result widget the same way, so it
  is exercised for "does not error" rather than widget creation.
"""

import numpy as np
import pytest

from uitest.jls_fixtures import write_fsr_v2

_WIDGET_TOOLS = ['HistogramRangeTool', 'CdfRangeTool', 'FrequencyRangeTool']


def _open_signal_file(ui_session, tmp_capture):
    path = str(tmp_capture / 'analysis.jls')
    data = (0.5 + 0.2 * np.sin(np.arange(40000) / 40.0)).astype(np.float32)
    write_fsr_v2(path, sample_rate=1000, data=data)
    source_id = ui_session.open_file(path)
    ui_session.wait(1.0)
    wf = ui_session.waveform()
    assert wf is not None, 'opening a file did not create a waveform'
    signals = ui_session.buffer_signals(source_id)
    assert signals, 'no analysis signals available from the opened file'
    return wf, signals


@pytest.mark.parametrize('tool', _WIDGET_TOOLS)
def test_analysis_tool_creates_result(ui_session, tmp_capture, tool):
    wf, signals = _open_signal_file(ui_session, tmp_capture)
    x_range = ui_session.subrange(wf)
    result = ui_session.run_analysis(wf, tool, signals=signals, x_range=x_range)
    assert result, f'{tool} produced no result widget'


def test_max_window_runs(ui_session, tmp_capture):
    """MaxWindow runs without error (it reports a value rather than a widget)."""
    wf, signals = _open_signal_file(ui_session, tmp_capture)
    x_range = ui_session.subrange(wf)
    # Should not raise; result-widget detection is best-effort for this tool.
    ui_session.run_analysis(wf, 'MaxWindowRangeTool', signals=signals,
                            x_range=x_range, timeout=4.0)
