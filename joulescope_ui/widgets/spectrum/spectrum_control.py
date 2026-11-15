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

"""The Spectrum widget control bar.

Each control publishes its setting.  The widget calls
:meth:`SpectrumControlWidget.value_set` from its on_setting_* handlers,
so the controls always mirror the settings.
"""

from joulescope_ui import N_, tooltip_format
from joulescope_ui.widgets.control_bar import ControlBar


_COMBO_SETTINGS = ['decimate', 'fft_length', 'fft_window', 'scaling', 'average_mode']

_TOOLTIPS = {
    'hold': tooltip_format(
        N_('Hold the display'),
        N_('When selected, ignore new data so that the spectrum and waterfall stay frozen.')),
    'clear': tooltip_format(
        N_('Clear'),
        N_('Clear the average, max hold, min hold, and waterfall history.')),
    'source': tooltip_format(N_('Source'), N_('Select the source device.')),
    'signal': tooltip_format(N_('Signal'), N_('Select the signal to analyze.')),
    'decimate': tooltip_format(
        N_('Span'),
        N_("""The analyzed frequency span.  Spans narrower than the full
        sample rate decimate the signal before the FFT, which improves the
        resolution bandwidth for the same FFT length.""")),
    'fft_length': tooltip_format(
        N_('FFT length'),
        N_("""The number of samples in each FFT.  Longer FFTs give finer
        resolution bandwidth (RBW) but update less often.""")),
    'fft_window': tooltip_format(
        N_('Window'),
        N_("""The FFT window.  Flat top gives the most accurate tone
        amplitude.  Hann is a good general-purpose window.""")),
    'scaling': tooltip_format(
        N_('Scaling'),
        N_("""Amplitude shows the RMS amplitude in each bin, best for tones.
        PSD shows the power spectral density, best for noise.""")),
    'average_mode': tooltip_format(N_('Average'), N_('The averaging mode for the average trace.')),
}


class SpectrumControlWidget(ControlBar):
    """The control bar.

    :param parent: The SpectrumWidget.
    :param settings: The SpectrumWidget SETTINGS.
    """

    def __init__(self, parent, settings):
        super().__init__(parent, 'spectrum', _TOOLTIPS)
        self._hold = self.toggle_add('hold', N_('Hold'))
        self._clear = self.button_add('clear', N_('Clear'), parent.on_action_clear)
        self._source = self.combo_add('source')
        self._source.activated.connect(self._on_source)
        self.combo_add('signal').activated.connect(self._factory('signal'))
        for name in _COMBO_SETTINGS:
            self.combo_add(name, settings[name]['options'])
        self._layout.addStretch(1)

    def _on_source(self, index):
        self._parent.source_selector.source_set(self._source.itemData(index))
