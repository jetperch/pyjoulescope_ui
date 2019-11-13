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
from .developer_widget_ui import Ui_DeveloperWidget
from joulescope.units import unit_prefix, three_sig_figs
import logging


log = logging.getLogger(__name__)


class DeveloperWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._ui = Ui_DeveloperWidget()
        self._ui.setupUi(self)
        self._status = {}
        self._status_row = 0
        cmdp.subscribe('Device/#state/status', self._on_device_state_status)

    def __del__(self):
        self._cmdp.unsubscribe('Device/#state/status', self._on_device_state_status)

    def _status_clean(self):
        for key, (w1, w2, w3) in self._status.items():
            w1.setParent(None)
            w2.setParent(None)
            w3.setParent(None)
        self._status = {}

    def _on_device_state_status(self, topic, status):
        for root_key, root_value in status.items():
            if root_key == 'endpoints':
                root_value = root_value.get('2', {})
            for key, value in root_value.items():
                # print(f'{root_key}.{key} = {value}')
                s = self._status.get(key)
                if s is None:  # create
                    label_name = QtWidgets.QLabel(self._ui.status_groupbox)
                    label_value = QtWidgets.QLabel(self._ui.status_groupbox)
                    label_units = QtWidgets.QLabel(self._ui.status_groupbox)
                    self._ui.status_layout.addWidget(label_name, self._status_row, 0, 1, 1)
                    self._ui.status_layout.addWidget(label_value, self._status_row, 1, 1, 1)
                    self._ui.status_layout.addWidget(label_units, self._status_row, 2, 1, 1)
                    self._status_row += 1
                    label_name.setText(key)
                    s = [label_name, label_value, label_units]
                    self._status[key] = s
                fmt = value.get('format', None)
                v = value['value']
                c = ''
                if fmt is None:
                    v, c, _ = unit_prefix(v)
                    k = three_sig_figs(v)
                else:
                    k = fmt.format(v)
                units = str(c + value['units'])
                s[1].setText(k)
                s[2].setText(units)


def widget_register(cmdp):
    return {
        'name': 'Developer',
        'brief': 'Developer information and controls.',
        'class': DeveloperWidget,
        'location': QtCore.Qt.LeftDockWidgetArea,
        'singleton': True,
    }
