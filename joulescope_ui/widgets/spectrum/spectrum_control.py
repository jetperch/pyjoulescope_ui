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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_, tooltip_format


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


class SpectrumControlWidget(QtWidgets.QWidget):
    """The control bar.

    :param parent: The SpectrumWidget.
    :param settings: The SpectrumWidget SETTINGS.
    """

    def __init__(self, parent, settings):
        self._parent = parent
        self._combos = {}
        super().__init__(parent)
        self.setObjectName('spectrum_control')
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self._layout = layout

        self._hold = QtWidgets.QPushButton(N_('Hold'), self)
        self._hold.setObjectName('spectrum_hold')
        self._hold.setCheckable(True)
        self._hold.setToolTip(_TOOLTIPS['hold'])
        self._hold.toggled.connect(lambda checked: parent.setting_publish('hold', bool(checked)))
        layout.addWidget(self._hold)

        self._clear = QtWidgets.QPushButton(N_('Clear'), self)
        self._clear.setObjectName('spectrum_clear')
        self._clear.setToolTip(_TOOLTIPS['clear'])
        self._clear.clicked.connect(lambda checked=False: parent.on_action_clear())
        layout.addWidget(self._clear)

        self._source = self._combo_add('source')
        self._source.activated.connect(self._on_source)
        self._combo_add('signal').activated.connect(self._factory('signal'))

        for name in _COMBO_SETTINGS:
            combo = self._combo_add(name)
            for value, label in settings[name]['options']:
                combo.addItem(label, value)
            combo.activated.connect(self._factory(name))

        layout.addStretch(1)

    def _combo_add(self, name):
        combo = QtWidgets.QComboBox(self)
        combo.setObjectName(f'spectrum_{name}')
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setToolTip(_TOOLTIPS[name])
        self._layout.addWidget(combo)
        self._combos[name] = combo
        return combo

    def _factory(self, name):
        def fn(index):
            self._parent.setting_publish(name, self._combos[name].itemData(index))
        return fn

    def _on_source(self, index):
        self._parent.source_selector.source_set(self._source.itemData(index))

    @staticmethod
    def _select(combo, value):
        idx = combo.findData(value)
        if idx >= 0:
            with QtCore.QSignalBlocker(combo):
                combo.setCurrentIndex(idx)

    def value_set(self, name, value):
        """Update a control to match its setting."""
        if name == 'hold':
            with QtCore.QSignalBlocker(self._hold):
                self._hold.setChecked(bool(value))
        elif name in self._combos:
            self._select(self._combos[name], value)

    def items_set(self, name, items, value):
        """Replace a combobox's items.

        :param name: The combobox name.
        :param items: The list of (value, label).
        :param value: The selected value.
        """
        combo = self._combos[name]
        with QtCore.QSignalBlocker(combo):
            combo.clear()
            for v, label in items:
                combo.addItem(label, v)
        self._select(combo, value)

    def labels_set(self, name, labels):
        """Update the item labels, keeping values.

        :param name: The combobox name.
        :param labels: The map of value to label.
        """
        combo = self._combos[name]
        for idx in range(combo.count()):
            label = labels.get(combo.itemData(idx))
            if label is not None:
                combo.setItemText(idx, label)
        combo.updateGeometry()  # the size hint changed, but the layout does not know
