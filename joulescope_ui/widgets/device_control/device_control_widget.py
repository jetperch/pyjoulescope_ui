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

from PySide6 import QtWidgets
from joulescope_ui import CAPABILITIES, register,  N_
from .js220_ctrl_widget import Js220CtrlWidget
from joulescope_ui.styles import styled_widget
import logging


@register
@styled_widget(N_('Device Control'))
class DeviceControlWidget(QtWidgets.QWidget):
    """Display and modified device settings."""

    CAPABILITIES = ['widget@']

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        super().__init__(parent=parent)
        self.setObjectName('device_ctrl')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

    def on_pubsub_register(self):
        self._log.info('register')
        self.pubsub.subscribe(f'registry_manager/capabilities/{CAPABILITIES.DEVICE_OBJECT}/list',
                              self._on_devices, ['pub', 'retain'])

    def _on_devices(self, value):
        devices = [obj.unique_id for obj in self.children() if hasattr(obj, 'unique_id')]
        for unique_id in devices:
            if unique_id not in value:
                self._device_remove(unique_id)
        for unique_id in value:
            if unique_id not in devices:
                self._device_add(unique_id)

    def _device_remove(self, unique_id):
        self._log.info('remove %s', unique_id)
        if '-UPDATER' in unique_id:
            return  # todo
        for w in self.children():
            if getattr(w, 'unique_id', None) == unique_id:
                self._layout.removeWidget(w)
                w.close()
                w.deleteLater()

    def _device_add(self, unique_id):
        self._log.info('add %s', unique_id)
        if '-UPDATER' in unique_id:
            return  # todo
        w = Js220CtrlWidget(self, unique_id, self.pubsub)
        w.expanded = True
        self._layout.insertWidget(self._layout.count() - 1, w)
        if hasattr(w, 'on_parent_style_change'):
            w.on_parent_style_change(self.style_obj)

    def on_style_change(self):
        for w in self.children():
            if hasattr(w, 'on_parent_style_change'):
                try:
                    w.on_parent_style_change(self.style_obj)
                except Exception:
                    pass
