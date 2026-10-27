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

"""Long-term tests with every connected Joulescope streaming at once.

Maps to the test plan's "Long-term testing" rows: about 1 h captures at full
rate and 10 kHz, and a 10 h run of the waveform widget.  Marked ``slow``, so
the release gate (``-m "not slow"``) excludes them; the HIL farm runs them on
demand as the ``ui_longterm`` suite.  The durations come from
``JS_UITEST_CAPTURE_S`` (default 3600) and ``JS_UITEST_RUN_S`` (default
36000), so a check run can shorten them.

A 1 h full-rate capture needs about 45 GB free per JS220/JS320.
"""

import os
import shutil
import time

import psutil
import pytest

from uitest import discover, verify

pytestmark = [pytest.mark.device, pytest.mark.slow]

_CAPTURE_S = float(os.environ.get('JS_UITEST_CAPTURE_S', '3600'))
_RUN_S = float(os.environ.get('JS_UITEST_RUN_S', '36000'))
_CHECK_INTERVAL_S = 60.0
_SIGNALS = ['current', 'voltage', 'power']
_BYTES_PER_SAMPLE = 16      # measured about 12.5 for a JS320 recording
_RSS_GROWTH_MAX = 1 << 30   # bytes the UI may grow over the run


def _stream(ui_session, devices, rate):
    """Show the live waveform with every device streaming at ``rate``.

    :param rate: 'full' for each model's full rate, else the rate in Hz.
    :return: ``{unique_id: rate}``.
    """
    ui_session.set_view('oscilloscope')
    if not ui_session.offscreen:
        ui_session.resize_window_settled(1600, 900)
    rates = {}
    for d in devices:
        rates[d.unique_id] = discover.FULL_RATE[d.model] if rate == 'full' else rate
        ui_session.set_signal_frequency(d.unique_id, rates[d.unique_id])
    ui_session.publish('registry/app/settings/signal_stream_enable', True)
    for d in devices:
        ui_session.wait_for_statistics(d.unique_id)
    return rates


def _watch(ui_session, devices, duration, check=None):
    """Wait ``duration`` seconds, checking each minute that every device's
    statistics arrive.

    :param check: Optional callable run at each check.
    """
    deadline = time.monotonic() + duration
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        ui_session.wait(min(_CHECK_INTERVAL_S, remaining))
        for d in devices:
            ui_session.wait_for_statistics(d.unique_id)  # raises if stalled
        if check is not None:
            check()


@pytest.mark.parametrize('rate', ['full', 10_000], ids=['full_rate', '10khz'])
def test_long_capture(ui_session, all_devices, tmp_capture, rate):
    """Capture every device for ~1 hour, then verify the recording and open it."""
    rates = _stream(ui_session, all_devices, rate)
    need = sum(rates.values()) * _CAPTURE_S * _BYTES_PER_SAMPLE
    free = shutil.disk_usage(tmp_capture).free
    assert free > 1.2 * need, \
        f'a {_CAPTURE_S:g} s capture at {rates} Hz needs {need / 1e9:.1f} GB, ' \
        f'{free / 1e9:.1f} GB free'

    path = str(tmp_capture / 'long.jls')
    record_id = ui_session.record_start(path, source_ids=list(rates))
    sizes = [0]

    def growing():
        size = os.path.getsize(path)
        assert size > sizes[-1], f'recording stopped growing at {size} bytes'
        sizes.append(size)

    try:
        _watch(ui_session, all_devices, _CAPTURE_S, growing)
    finally:
        ui_session.record_stop(record_id)
    try:
        verify.assert_recording(path, signal_names=_SIGNALS, min_duration_s=0.99 * _CAPTURE_S)
        counts = verify.assert_no_gaps(path, _SIGNALS)
        assert counts['current'] == len(all_devices), \
            f'recorded {counts["current"]} of {len(all_devices)} devices'
        ui_session.publish('registry/app/settings/signal_stream_enable', False)
        source_id = ui_session.open_file(path, timeout=120.0)
        assert source_id in ui_session.buffer_sources()
    finally:
        os.remove(path)


def test_long_run(ui_session, all_devices, record_property):
    """Run the waveform widget for ~10 hours with every device streaming.

    Statistics keep arriving from every device, the waveform keeps repainting
    (on a display), and UI memory stays bounded.
    """
    _stream(ui_session, all_devices, 'full')
    wf = ui_session.waveform()
    ui_session.wait(min(_CHECK_INTERVAL_S, _RUN_S))  # the stream buffer fills first
    process = psutil.Process(ui_session.pid)
    rss0 = process.memory_info().rss
    paints = [ui_session.plot_render_info(wf).get('paint_count', 0)]

    def repainting():
        if ui_session.offscreen:
            return  # offscreen does not paint the GL plot
        count = ui_session.plot_render_info(wf).get('paint_count', 0)
        assert count > paints[-1], f'waveform stopped repainting at {count} paints'
        paints.append(count)

    _watch(ui_session, all_devices, _RUN_S, repainting)
    growth = process.memory_info().rss - rss0
    record_property('rss_growth_mb', round(growth / (1 << 20)))
    record_property('devices', ','.join(d.unique_id for d in all_devices))
    assert growth < _RSS_GROWTH_MAX, f'UI memory grew {growth / (1 << 20):.0f} MB over the run'
