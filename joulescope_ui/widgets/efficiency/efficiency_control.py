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

"""The Efficiency widget control bar."""

from PySide6 import QtWidgets
from joulescope_ui import N_, tooltip_format
from joulescope_ui.widgets.control_bar import ControlBar


_TOOLTIPS = {
    'hold': tooltip_format(
        N_('Hold the display'),
        N_('When selected, ignore new data so that the display stays frozen.')),
    'clear': tooltip_format(
        N_('Clear'),
        N_('Clear the cumulative efficiency, history, and efficiency curve.')),
    'input': tooltip_format(
        N_('Input'),
        N_("""The instrument that measures the converter input.  Connect its
        voltage inputs at the converter input pins.""")),
    'output': tooltip_format(
        N_('Output'),
        N_("""The instrument that measures the converter output.  Connect its
        voltage inputs at the converter output pins.""")),
    'swap': tooltip_format(N_('Swap'), N_('Swap the input and output instruments.')),
    'enable': tooltip_format(
        N_('Enable signals'),
        N_('Enable the instrument signals that this widget needs.')),
}


class EfficiencyControlWidget(ControlBar):
    """The control bar.

    :param parent: The EfficiencyWidget.
    """

    def __init__(self, parent):
        super().__init__(parent, 'efficiency', _TOOLTIPS)
        self.toggle_add('hold', N_('Hold'))
        self.button_add('clear', N_('Clear'), parent.on_action_clear)
        self._layout.addWidget(QtWidgets.QLabel(N_('Input'), self))
        self.combo_add('input').activated.connect(self._source_factory('input'))
        self.button_add('swap', '⇄', parent.on_action_swap)
        self._layout.addWidget(QtWidgets.QLabel(N_('Output'), self))
        self.combo_add('output').activated.connect(self._source_factory('output'))
        self.enable = self.button_add('enable', N_('Enable signals'), parent.on_action_enable_signals)
        self.enable.setVisible(False)
        self.status = QtWidgets.QLabel(self)
        self.status.setObjectName('efficiency_status')
        self.status.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self._layout.addWidget(self.status, 1)

    def _source_factory(self, name):
        def fn(index):
            self._parent.source_set(name, self._combos[name].itemData(index))
        return fn

    def status_set(self, text, warning):
        self.status.setText(text)
        self.status.setProperty('warning', bool(warning))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
