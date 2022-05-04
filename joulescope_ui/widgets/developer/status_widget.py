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


from PySide6 import QtWidgets, QtCore
from joulescope_ui.preferences_ui import widget_factory
from joulescope.units import unit_prefix, three_sig_figs
from joulescope_ui.ui_util import comboBoxConfig
import logging


log = logging.getLogger(__name__)


class StatusWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._main_layout = QtWidgets.QVBoxLayout(self)

        self._device_status_widget = QtWidgets.QWidget(self)
        self._device_status_layout = QtWidgets.QGridLayout(self._device_status_widget)

        self._spacer = QtWidgets.QSpacerItem(20, 461, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._main_layout.addWidget(self._device_status_widget)
        self._main_layout.addItem(self._spacer)

        self._status = {}
        self._status_row = 0
        self._source = None
        cmdp.subscribe('Device/#state/status', self._on_device_state_status, update_now=True)
        cmdp.subscribe('Device/#state/source', self._on_device_state_source, update_now=True)

    def _status_clean(self):
        for key, widgets in self._status.items():
            for widget in widgets:
                self._device_status_layout.removeWidget(widget)
                widget.setParent(None)
        self._status = {}
        self._status_row = 0

    def _on_device_state_source(self, topic, value):
        if self._source == value:
            return
        self._source = value
        if value in ['None', 'File']:
            self._status_clean()

    def _on_device_state_status(self, topic, status):
        for root_key, root_value in status.items():
            if root_key == 'endpoints':
                root_value = root_value.get('2', {})
            for key, value in root_value.items():
                # print(f'{root_key}.{key} = {value}')
                s = self._status.get(key)
                if s is None:  # create
                    # print(f'Create {key} : {self._status_row}')
                    label_name = QtWidgets.QLabel(self._device_status_widget)
                    label_value = QtWidgets.QLabel(self._device_status_widget)
                    label_units = QtWidgets.QLabel(self._device_status_widget)
                    self._device_status_layout.addWidget(label_name, self._status_row, 0, 1, 1)
                    self._device_status_layout.addWidget(label_value, self._status_row, 1, 1, 1)
                    self._device_status_layout.addWidget(label_units, self._status_row, 2, 1, 1)
                    label_name.setText(key)
                    min_height = label_name.sizeHint().height() + 5
                    label_name.setMinimumHeight(min_height)
                    self._device_status_layout.setRowMinimumHeight(self._status_row, min_height)
                    self._status_row += 1
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
        'name': 'Status',
        'brief': 'Device status for development.',
        'class': StatusWidget,
        'location': QtCore.Qt.LeftDockWidgetArea,
        'singleton': True,
        'permissions': ['developer'],
    }
