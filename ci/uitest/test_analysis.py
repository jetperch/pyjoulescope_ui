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

import time

import numpy as np
import pytest

from uitest import verify
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


# --- Analysis over a live device recording, checking the computed results ---

_ANALYSIS_RATE = 10_000
_ANALYSIS_SECONDS = 3.0
_OFFSETS = range(-2, 3)  # the tool's UTC->sample conversion may differ by a sample


def _record(ui_session, device, path):
    ui_session.publish(f'registry/{device.unique_id}/settings/auto_open', True)
    ui_session.set_signal_frequency(device.unique_id, _ANALYSIS_RATE)
    ui_session.publish('registry/app/settings/signal_stream_enable', False)
    ui_session.wait(0.5)
    ui_session.wait_for_statistics(device.unique_id)
    record_id = ui_session.record_start(path, source_ids=[device.unique_id])
    ui_session.wait(_ANALYSIS_SECONDS)
    ui_session.record_stop(record_id)
    ui_session.publish('registry/app/settings/signal_stream_enable', False)
    ui_session.publish('registry/app/settings/statistics_stream_enable', False)
    ui_session.wait(0.5)


def _sample_id(path, utc):
    with verify.open_reader(path) as r:
        sig = verify.signal_by_name(r, 'current')
        return int(r.timestamp_to_sample_id(sig.signal_id, int(utc)))


def _reference(path, x_range):
    """Return ``(data, fs)`` of the recorded current over ``x_range``, padded
    by ``max(_OFFSETS)`` samples on each side."""
    pad = max(_OFFSETS)
    s0, s1 = [_sample_id(path, t) for t in x_range]
    with verify.open_reader(path) as r:
        sig = verify.signal_by_name(r, 'current')
        data = verify.read_fsr(r, sig.signal_id, s0 - pad, s1 - s0 + 1 + 2 * pad)
        return data.astype(np.float64), sig.sample_rate


def _hist(x, bins):
    # The tools bin over the range's own min/max (from a summary request).
    return np.histogram(x, bins=bins, range=(x.min(), x.max()))[0] / len(x)


def _candidates(ref, n):
    """The reference windows of ``n`` samples for each candidate offset."""
    pad = max(_OFFSETS)
    for k in _OFFSETS:
        yield ref[pad + k:pad + k + n]


def _welch(x, fs, nfft, overlap):
    """Reference one-sided PSD: hamming window, averaged.  The callers
    compare bins 1..N-2, so DC and Nyquist are left doubled here."""
    w = np.hamming(nfft)
    step = nfft - int(overlap * nfft)
    segments = np.lib.stride_tricks.sliding_window_view(x, nfft)[::step]
    z = np.fft.rfft(segments * w, axis=1)
    return np.mean(np.abs(z) ** 2, axis=0) * 2.0 / (fs * np.sum(w * w))


@pytest.mark.device
def test_analysis_on_recording(ui_session, device, tmp_capture):
    """Histogram, CDF, Frequency and Max window match numpy on the same samples."""
    path = str(tmp_capture / 'analysis.jls')
    _record(ui_session, device, path)
    source_id = ui_session.open_file(path)
    ui_session.wait(1.0)
    wf = ui_session.waveform()
    signal = [s for s in ui_session.buffer_signals(source_id) if s.endswith('.i')]
    assert signal, f'no current signal in {ui_session.buffer_signals(source_id)}'
    x0, x1 = ui_session.source_utc_range(source_id)
    x_range = [int(x0 + 0.3 * (x1 - x0)), int(x0 + 0.7 * (x1 - x0))]
    ref, fs = _reference(path, x_range)

    def result(tool):
        prefix = f'{tool}Widget:'
        before = {i for i in ui_session.enumerate('registry') if i.startswith(prefix)}
        ui_session.run_analysis(wf, tool, signals=signal, x_range=x_range)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            new = {i for i in ui_session.enumerate('registry') if i.startswith(prefix)} - before
            if new:
                return ui_session.query(f'registry/{sorted(new)[0]}/settings/data')
            ui_session.wait(0.2)
        pytest.fail(f'{tool} produced no result widget')

    # Histogram (default: discrete probability distribution).
    hist = np.asarray(result('HistogramRangeTool')['hist'])
    n = len(ref) - 2 * max(_OFFSETS)
    assert any(np.allclose(_hist(x, len(hist)), hist, atol=3.0 / n)
               for x in _candidates(ref, n)), f'{device.model}: histogram differs from numpy'

    # CDF (default: not complementary).
    y = np.asarray(result('CdfRangeTool')['y'])
    assert any(np.allclose(np.cumsum(_hist(x, len(y))), y, atol=3.0 / n)
               for x in _candidates(ref, n)), f'{device.model}: CDF differs from numpy'

    # Frequency (defaults: hamming, 25% overlap): the PSD in dB.
    d = result('FrequencyRangeTool')
    psd = 10.0 ** (np.asarray(d['y']) / 10.0)
    nfft = 2 * (len(psd) - 1)
    assert any(np.allclose(_welch(x, fs, nfft, 0.25)[1:-1], psd[1:-1], rtol=1e-3)
               for x in _candidates(ref, n)), f'{device.model}: PSD differs from numpy'

    # Max window: adds dual markers around the maximum-sum window.
    before = {m['id'] for m in ui_session.x_markers_info(wf)}
    ui_session.run_analysis(wf, 'MaxWindowRangeTool', signals=signal, x_range=x_range, timeout=4.0)
    ui_session.wait(1.0)
    added = [m for m in ui_session.x_markers_info(wf) if m['id'] not in before]
    assert added, f'{device.model}: Max window added no markers'
    m = added[0]
    s0 = _sample_id(path, x_range[0])
    start = _sample_id(path, m['pos1']) - s0
    width = _sample_id(path, m['pos2']) - s0 - start
    sums = np.lib.stride_tricks.sliding_window_view(ref, width).sum(axis=1)
    expect = int(np.argmax(sums)) - max(_OFFSETS)
    assert abs(start - expect) <= 2, \
        f'{device.model}: Max window starts at sample {start}, numpy maximum at {expect}'
