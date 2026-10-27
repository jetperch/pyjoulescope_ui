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

"""Live record and export, following the test plan's steps.

Maps to the "Live view record and export from waveform" sections, at full rate
and 10 kHz:

1. View -> Oscilloscope, set the signal frequency.
2. Record A for 10 s, stop.
3. In the live view, add dual markers, export B.
4. View -> File, open A, verify.
5. Open B, verify it matches A.
6. Add dual markers to the opened file's waveform, export C, verify C matches A.

Requires a connected device.
"""

import pyjls
import pytest

from uitest import discover, verify

_RECORD_SECONDS = 10.0
_LIVE_BUFFER = 'JsdrvStreamBuffer:001'
_SIGNALS = ['current', 'voltage', 'power']
_EXPORT_TIMEOUT = 120.0     # seconds; a 1 MHz export writes tens of MB
# Allowed UTC disagreement between a recording and a live-buffer export of the
# same samples.  JS110 recordings and its stream buffer differ by about 2 ms
# (see docs/plans/completed/expand_test_coverage_202610.md, Stage 1 findings).
_UTC_TOLERANCE_S = {'JS110': 0.005, 'JS220': 0.0, 'JS320': 0.0}


def _rate(device, rate):
    return discover.FULL_RATE[device.model] if rate == 'full' else rate


def _inner(t0, t1, lo, hi):
    """Return ``[t0 + lo * span, t0 + hi * span]`` as int time64."""
    span = t1 - t0
    return [int(t0 + lo * span), int(t0 + hi * span)]


def _export_and_verify(ui_session, wf, path, x_range, signals, reference, max_shift=4):
    """Add dual markers inside ``x_range``, export, and compare with ``reference``."""
    ui_session.add_dual_markers(wf, *_inner(*x_range, 0.25, 0.75))
    ui_session.export_range(wf, path, x_range=x_range, signals=signals,
                            timeout=_EXPORT_TIMEOUT)
    verify.assert_recording(path, signal_names=_SIGNALS)
    for name in _SIGNALS:
        verify.compare_subrange(reference, path, name, max_shift=max_shift)
    markers = verify.count_annotations(ui_session.annotation_path(path),
                                       annotation_type=pyjls.AnnotationType.VMARKER)
    assert markers == 2, f'{path}: expected 2 vertical markers, found {markers}'
    source_id = ui_session.open_file(path)
    assert source_id in ui_session.buffer_sources()


@pytest.mark.device
@pytest.mark.parametrize('rate', ['full', 10_000], ids=['full_rate', '10khz'])
def test_record_export(ui_session, device, tmp_capture, rate):
    freq = _rate(device, rate)
    path_a, path_b, path_c = [str(tmp_capture / f'{n}.jls') for n in 'ABC']

    # 1. View -> Oscilloscope at the requested signal frequency.
    ui_session.set_view('oscilloscope')
    live_wf = ui_session.waveform()
    ui_session.set_signal_frequency(device.unique_id, freq)
    ui_session.wait_for_statistics(device.unique_id)   # data is flowing

    # 2. Record A, stop.
    record_id = ui_session.record_start(path_a, source_ids=[device.unique_id])
    ui_session.wait(_RECORD_SECONDS)
    ui_session.record_stop(record_id)
    summary = verify.assert_recording(path_a, signal_names=_SIGNALS,
                                      min_duration_s=_RECORD_SECONDS * 0.8)
    rates = {s['sample_rate'] for s in summary['signals'].values()}
    assert rates == {float(freq)}, f'expected {freq} Hz, recording has {rates}'

    # 3. Pause the live view (the buffer keeps its data), export B from it.
    ui_session.publish('registry/app/settings/signal_stream_enable', False)
    ui_session.publish('registry/app/settings/statistics_stream_enable', False)
    ui_session.wait(0.5)
    a_range = verify.utc_range(path_a, 'current')
    live_signals = [s for s in ui_session.buffer_signals(_LIVE_BUFFER)
                    if s.startswith(f'{_LIVE_BUFFER}.{device.unique_id}.')
                    and s.split('.')[-1] in ('i', 'v', 'p')]
    assert len(live_signals) == 3, f'live buffer signals: {live_signals}'
    max_shift = max(4, int(_UTC_TOLERANCE_S[device.model] * freq))
    _export_and_verify(ui_session, live_wf, path_b, _inner(*a_range, 0.3, 0.7),
                       live_signals, path_a, max_shift=max_shift)

    # 4. View -> File, open A.
    ui_session.set_view('file')
    source_a = ui_session.open_file(path_a)
    assert ui_session.query(f'registry/{source_a}/settings/path') == path_a
    ui_session.wait(1.0)
    file_wf = ui_session.waveform()
    assert file_wf != live_wf, 'opening A did not create a file waveform'

    # 6. Markers on the opened file's waveform, export C.
    x0, x1 = ui_session.source_utc_range(source_a)
    _export_and_verify(ui_session, file_wf, path_c, _inner(x0, x1, 0.2, 0.6),
                       ui_session.buffer_signals(source_a), path_a)
