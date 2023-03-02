# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtWidgets, QtCore
from joulescope_ui import pubsub_singleton, register_decorator, N_
import logging


@register_decorator('progress')
class ProgressBarWidget(QtWidgets.QDialog):
    CAPABILITIES = []
    SETTINGS = {
        'progress': {
            'dtype': 'float',
            'brief': 'The fractional progress (0=begin, 1=done)',
            'default': 0.0,
        },
    }

    def __init__(self, description, cancel_action_topic=None):
        self._cancel_action_topic = cancel_action_topic
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setObjectName('progress_bar_widget')
        self._log = logging.getLogger(__name__)
        self._log.info(f'start')
        self._layout = QtWidgets.QVBoxLayout()

        self._layout = QtWidgets.QVBoxLayout()
        self.setLayout(self._layout)

        self._label = QtWidgets.QLabel(description, self)
        self._layout.addWidget(self._label)

        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._layout.addWidget(self._progress)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

        self.finished.connect(self._on_finished)

        #self.resize(600, 400)
        self.setWindowTitle(N_('Progress'))
        self._log.info('open')
        self.open()

    def on_pubsub_register(self):
        self._log.info(f'register {self.unique_id}')

    @QtCore.Slot(int)
    def _on_finished(self, value):
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._log.info('complete')
        else:
            self._log.info('cancel')
            if self._cancel_action_topic is not None:
                pubsub_singleton.publish(self._cancel_action_topic, None)
        self.close()

    def close(self):
        self._log.info('close')
        pubsub_singleton.unregister(self, delete=True)
        super().close()

    def on_setting_progress(self, value):
        if self._progress is None:
            return
        v = int(value * 1000)
        self._progress.setValue(v)
        if value >= 1.0:
            self.accept()
