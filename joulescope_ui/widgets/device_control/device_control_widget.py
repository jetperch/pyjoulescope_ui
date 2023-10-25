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

from PySide6 import QtWidgets, QtGui, QtCore
from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name, tooltip_format
from .js220_ctrl_widget import Js220CtrlWidget
from joulescope_ui.widget_tools import settings_action_create
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.units import unit_prefix, three_sig_figs
from joulescope_ui.ui_util import comboBoxConfig
import datetime
import numpy as np
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
        self._device_widgets = {}

        self._subscribers = [
            [f'registry_manager/capabilities/{CAPABILITIES.DEVICE_OBJECT}/list', self._on_devices],
        ]

    def on_pubsub_register(self):
        self._log.info('register')
        for topic, fn in self._subscribers:
            pubsub_singleton.subscribe(topic, fn, ['pub', 'retain'])

    def on_pubsub_unregister(self):
        self._log.info('unregister')
        for topic, fn in self._subscribers:
            pubsub_singleton.unsubscribe(topic, fn)
        while len(self._device_widgets):
            self._device_remove(next(iter(self._device_widgets)))

    def _on_devices(self, value):
        for unique_id in list(self._device_widgets.keys()):
            if unique_id not in value:
                self._device_remove(unique_id)
        for unique_id in value:
            if unique_id not in self._device_widgets:
                self._device_add(unique_id)

    def _device_remove(self, unique_id):
        self._log.info('remove %s', unique_id)
        if '-UPDATER' in unique_id:
            return  # todo
        w = self._device_widgets.pop(unique_id)
        self._layout.removeWidget(w)
        w.close()
        w.deleteLater()

    def _device_add(self, unique_id):
        self._log.info('add %s', unique_id)
        if '-UPDATER' in unique_id:
            return  # todo
        w = Js220CtrlWidget(self, unique_id)
        w.expanded = True
        self._device_widgets[unique_id] = w
        self._layout.insertWidget(self._layout.count() - 1, w)
        if hasattr(w, 'on_parent_style_change'):
            w.on_parent_style_change(self.style_obj)

    def on_style_change(self):
        for w in self._device_widgets.values():
            if hasattr(w, 'on_parent_style_change'):
                try:
                    w.on_parent_style_change(self.style_obj)
                except Exception:
                    pass
