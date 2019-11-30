# Copyright 2019 Jetperch LLC
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


from PySide2 import QtWidgets, QtCore
from joulescope_ui.preferences_ui import widget_factory
from joulescope.units import unit_prefix, three_sig_figs
from joulescope_ui.ui_util import comboBoxConfig
import logging


log = logging.getLogger(__name__)


class ParametersWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._main_layout = QtWidgets.QVBoxLayout(self)
        self._parameters_widget = QtWidgets.QWidget(self)
        self._parameters_layout = QtWidgets.QFormLayout(self._parameters_widget)
        self._spacer = QtWidgets.QSpacerItem(20, 461, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._main_layout.addWidget(self._parameters_widget)
        self._main_layout.addItem(self._spacer)

        self._parameters = {}
        self._source = None
        self._parameters_populate()
        cmdp.subscribe('Device/#state/source', self._on_device_state_source, update_now=True)

    def _parameters_clean(self):
        for key, widget in self._parameters.items():
            widget.unpopulate(self._parameters_widget)
        self._parameters = {}
        while self._parameters_layout.rowCount():
            self._parameters_layout.removeRow(0)

    def _on_device_state_source(self, topic, value):
        if self._source == value:
            return
        return
        self._source = value
        if value in ['None', 'File']:
            self._parameters_clean()
        else:
            self._parameters_populate()

    def _parameters_populate(self):
        self._parameters_clean()
        for topic, value in self._cmdp.preferences.flatten().items():
            if not topic.startswith('Device/parameter/') or topic[-1] == '/':
                continue
            widget = widget_factory(self._cmdp, topic)
            if widget is not None:
                widget.populate(self._parameters_widget)
                self._parameters[topic] = widget
        self._parameters_layout.activate()


def widget_register(cmdp):
    return {
        'name': 'Parameters',
        'brief': 'Device parameters control for development.',
        'class': ParametersWidget,
        'location': QtCore.Qt.LeftDockWidgetArea,
        'singleton': True,
        'permissions': ['developer'],
    }
