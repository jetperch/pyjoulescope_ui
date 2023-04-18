# Copyright 2023 Jetperch LLC
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

"""
Allow the user to configure the source devices displayed on the waveform.

WARNING: this widget and feature is still under development.
"""

from joulescope_ui.ui_util import comboBoxConfig
from PySide6 import QtWidgets
import logging

log = logging.getLogger(__name__)


class SingleSourceWidget(QtWidgets.QWidget):

    def __init__(self, parent, index):
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setObjectName("WaveformSingleSourceWidget")

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformSingleSourceLayout")
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)

        self.color = QtWidgets.QLabel(self)
        self.color.setObjectName(f'WaveformSingleSourceColor_{index}')
        self.color.setFixedSize(20, 20)
        self._layout.addWidget(self.color)

        self.name = QtWidgets.QLabel(self)
        self.name.setObjectName(f'WaveformSingleSourceName_{index}')
        self.name.setText('off')  # todo combo box?
        self._layout.addWidget(self.name)


class WaveformSourceWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.setObjectName("WaveformSourceWidget")
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformSourceLayout")
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(10)

        self._spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding,
                                             QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer)

        self._source_widgets = []
        for i in range(4):
            w = SingleSourceWidget(self, i)
            self._layout.addWidget(w)
            self._source_widgets.append(w)

        self._spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding,
                                             QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer)
