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

"""Spectrum widget: live FFT and waterfall from a connected device.

Verifies that the widget computes spectra from the device's live stream at
the device sample rate, without overruns or stream gaps, and that its
settings reconfigure it.  Spectrum accuracy is covered by the unit tests
(joulescope_ui/test/test_spectrum_engine.py).  See docs/plans/spectrum.md.
"""

import time

import pytest


def _spectrum_open(ui_session, device):
    """Open a Spectrum widget on ``device``; return its unique id."""
    before = set(i for i in ui_session.enumerate('registry') if i.startswith('SpectrumWidget:'))
    ui_session.publish('registry/view/actions/!widget_open', 'SpectrumWidget')
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        ids = [i for i in ui_session.enumerate('registry')
               if i.startswith('SpectrumWidget:') and i not in before]
        if ids:
            ui_session.publish(f'registry/{ids[0]}/settings/signal_stream_source', device.unique_id)
            return ids[0]
        ui_session.wait(0.2)
    raise AssertionError('Spectrum widget did not open')


def _info(ui_session, widget):
    rsp = ui_session.qt_action('call', path=widget, method='spectrum_info')
    assert rsp.get('ok'), f'spectrum_info failed: {rsp}'
    return rsp['result']


def _wait_info(ui_session, widget, predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    info = None
    while time.monotonic() < deadline:
        info = _info(ui_session, widget)
        if predicate(info):
            return info
        ui_session.wait(0.25)
    raise AssertionError(f'spectrum condition not met: {info}')


@pytest.mark.device
def test_spectrum_widget_live(ui_session, device):
    """The Spectrum widget analyzes the device's current stream."""
    ui_session.publish('registry/app/settings/signal_stream_enable', True)
    fs = ui_session.query(f'{device.topic}/settings/signal_frequency')
    widget = _spectrum_open(ui_session, device)
    info = _wait_info(ui_session, widget, lambda i: i.get('count', 0) > 10)
    assert info['source'] == device.unique_id, info
    assert info['signal'] == 'i', info
    assert info['fs'] == fs, info
    assert info['n'] == 4096, info
    assert info['rbw'] == pytest.approx(1.5 * fs / 4096, rel=0.01), info   # Hann
    assert info['overruns'] == 0, info
    assert info['waterfall_rows'] > 0, info
    # Startup may toggle streaming (sample rate apply), a real gap, so check
    # gaps after this reconfiguration, which resets them.

    ui_session.publish(f'registry/{widget}/settings/fft_length', 1024)
    ui_session.publish(f'registry/{widget}/settings/decimate', 4)
    info = _wait_info(ui_session, widget, lambda i: i.get('n') == 1024 and i.get('count', 0) > 10)
    assert info['fs'] == fs / 4, info
    assert info['overruns'] == 0, info
    assert info['gaps'] == 0, info

    ui_session.publish(f'registry/{widget}/settings/hold', True)
    ui_session.wait(0.5)
    count = _info(ui_session, widget)['count']
    ui_session.wait(1.0)
    assert _info(ui_session, widget)['count'] == count
    ui_session.publish('registry/view/actions/!widget_close', widget)
