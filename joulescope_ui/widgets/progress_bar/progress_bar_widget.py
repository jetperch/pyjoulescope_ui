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
from joulescope_ui import pubsub_singleton, register_decorator, N_, tooltip_format
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
    _instances = {}

    def __init__(self):
        self._brief = ''
        self._description = ''
        self.cancel_topic = None
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setObjectName('progress_bar_widget')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._log = logging.getLogger(__name__)
        self._log.info(f'start')
        self._layout = QtWidgets.QVBoxLayout(self)

        self._label = QtWidgets.QLabel('', self)
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

        self.setWindowTitle(N_('Progress'))
        self._log.info('open')
        self.open()

    def name(self, value):
        self._label.setText(value)

    def _update_tooltip(self):
        tooltip = tooltip_format(self._brief, self._description)
        self._label.setToolTip(tooltip)
        self._progress.setToolTip(tooltip)

    def brief(self, *args):
        if len(args):
            self._brief = args[0]
            self._update_tooltip()
        return self._brief

    def description(self, *args):
        if len(args):
            self._description = args[0]
            self._update_tooltip()
        return self._description

    def on_pubsub_register(self):
        self._log.info(f'register {self.unique_id}')

    @QtCore.Slot(int)
    def _on_finished(self, value):
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._log.info('complete')
        else:
            self._log.info('cancel')
            if self.cancel_topic is not None:
                pubsub_singleton.publish(self.cancel_topic, None)
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

    @staticmethod
    def on_cls_action_update(value):
        """Create, update, and/or close a progress bar.

        :param value: The update dict which contains:
            * id: The identifier for this progress.  You can often use the
              unique_id of the originator.  If this id is not yet known,
              this call will create a new progress bar.
            * progress: The fractional progress from 0 to 1.0.  If 1.0,
              then the progress bar will close automatically.
            * cancel_topic: The topic to publish with value None on cancel.
            * name: The localized, user-meaningful name for this progress bar.
              Will be cached whenever provided.
            * brief: The localized brief description for this progress bar.
              Will be cached whenever provided.
            * description: The localized, detailed description for the progress bar.
              Will be cached whenever provided.

        Normally, the originator provides cancel_topic, name, brief, and
        description at the initial call with progress 0.0.  It then only provides
        id and progress for subsequent calls.  The originator must call with
        progress 1.0 to close the progress bar.
        """
        my_id = value['id']
        progress = value['progress']
        if progress >= 1.0:
            if my_id not in ProgressBarWidget._instances:
                return
            instance = ProgressBarWidget._instances.pop(my_id)
            instance.accept()  # causes close
            return
        elif my_id not in ProgressBarWidget._instances:
            instance = ProgressBarWidget()
            pubsub_singleton.register(instance)
            ProgressBarWidget._instances[my_id] = instance
        instance = ProgressBarWidget._instances[my_id]
        instance.progress = progress
        if 'cancel_topic' in value:
            instance.cancel_topic = value['cancel_topic']
        if 'name' in value:
            instance.name(value['name'])
        if 'brief' in value:
            instance.brief(value['brief'])
        if 'description' in value:
            instance.description(value['description'])
