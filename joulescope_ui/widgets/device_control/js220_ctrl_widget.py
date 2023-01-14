# 2023 Jetperch LLC
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

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui.expanding_widget import ExpandingWidget
import logging
from joulescope_ui import N_, register, tooltip_format, pubsub_singleton, get_topic_name
from joulescope_ui.devices.jsdrv.js220 import SETTINGS
from joulescope_ui.ui_util import comboBoxConfig
from joulescope_ui.styles import styled_widget


class Js220CtrlWidget(QtWidgets.QWidget):

    def __init__(self, parent, unique_id):
        self._parent = parent
        self._unique_id = unique_id
        self._widgets = []
        self._unsub = []  # (topic, fn)
        self._row = 0
        self._log = logging.getLogger(f'{__name__}.{unique_id}')
        super().__init__(parent)

        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._expanding = ExpandingWidget(self)
        self._expanding.title = unique_id

        self._body = QtWidgets.QWidget(self)
        self._body_layout = QtWidgets.QGridLayout(self)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(1)
        self._body.setLayout(self._body_layout)
        self._expanding.body_widget = self._body

        self._layout.addWidget(self._expanding)
        self.setLayout(self._layout)

        for name, value in SETTINGS.items():
            if name.startswith('out/') or name.startswith('enable/'):
                continue
            self._add(name, value)

    def _subscribe(self, topic, update_fn):
        pubsub_singleton.subscribe(topic, update_fn, ['pub', 'retain'])
        self._unsub.append((topic, update_fn))

    def _add_combobox(self, name, value):
        w = QtWidgets.QComboBox(self)

        options = value['options']
        option_values = [o[0] for o in options]
        option_strs = [o[1] for o in options]
        comboBoxConfig(w, option_strs)
        topic = f'{get_topic_name(self._unique_id)}/settings/{name}'
        w.currentIndexChanged.connect(lambda idx: pubsub_singleton.publish(topic, options[idx][0]))

        def lookup(v):
            try:
                idx = option_values.index(v)
            except ValueError:
                self._log.warning('Invalid value: %s not in %s', v, option_values)
                return
            block_state = w.blockSignals(True)
            w.setCurrentIndex(idx)
            w.blockSignals(block_state)

        self._subscribe(topic, lookup)
        return w

    def _add(self, name, value):
        lbl = QtWidgets.QLabel(value['brief'], self)
        self._body_layout.addWidget(lbl, self._row, 0, 1, 1)
        self._widgets.append(lbl)

        w = None
        if 'options' in value:
            w = self._add_combobox(name, value)
        else:
            pass

        if w is not None:
            self._body_layout.addWidget(w, self._row, 1, 1, 1)
            self._widgets.append(w)
        self._row += 1

    def clear(self):
        for topic, fn in self._unsub:
            pubsub_singleton.unsubscribe(topic, fn)
        while len(self._widgets):
            w = self._widgets.pop()
            self._grid.removeWidget(w)
            w.deleteLater()
