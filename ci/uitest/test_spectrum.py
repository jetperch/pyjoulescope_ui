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

import pytest

from uitest import spectrum


@pytest.mark.device
def test_spectrum_widget_live(ui_session, device):
    """The Spectrum widget analyzes the device's current stream."""
    ui_session.publish_and_wait('registry/app/settings/signal_stream_enable', True)
    fs = ui_session.query(f'{device.topic}/settings/signal_frequency')
    widget = spectrum.open_widget(ui_session, device)
    info = spectrum.wait_info(ui_session, widget, lambda i: i.get('count', 0) > 10)
    assert info['source'] == device.unique_id, info
    assert info['signal'] == 'i', info
    assert info['fs'] == fs, info
    assert info['n'] == 4096, info
    assert info['rbw'] == pytest.approx(1.5 * fs / 4096, rel=0.01), info   # Hann
    assert info['overruns'] == 0, info
    assert info['waterfall_rows'] > 0, info
    # Startup may toggle streaming (sample rate apply), a real gap, so check
    # gaps after this reconfiguration, which resets them.

    spectrum.configure(ui_session, widget, fft_length=1024, decimate=4)
    info = spectrum.wait_info(ui_session, widget, lambda i: i.get('n') == 1024 and i.get('count', 0) > 10)
    assert info['fs'] == fs / 4, info
    assert info['overruns'] == 0, info
    assert info['gaps'] == 0, info

    ui_session.publish_and_wait(f'registry/{widget}/settings/hold', True)
    count = spectrum.info(ui_session, widget)['count']
    ui_session.wait(1.0)
    assert spectrum.info(ui_session, widget)['count'] == count
    spectrum.close_widget(ui_session, widget)
