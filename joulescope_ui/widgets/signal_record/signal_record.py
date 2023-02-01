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


from joulescope_ui import pubsub_singleton, register, CAPABILITIES
from .signal_record_config_widget import SignalRecordConfigDialog
import logging


@register
class SignalRecord:
    CAPABILITIES = []
    _singleton = None  # not strictly singleton, but target of class actions.
    _instances = []
    _log = logging.getLogger(f'{__name__}.cls')

    def __init__(self):
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self._log = logging.getLogger(f'{__name__}.obj')
        self.CAPABILITIES = [CAPABILITIES.SIGNAL_STREAM_SINK]

    @staticmethod
    def on_cls_action_start_request(pubsub, topic, value):
        SignalRecord._log.info('on_cls_action_start_request')
        SignalRecordConfigDialog()

    @staticmethod
    def on_cls_action_start(pubsub, topic, value):
        SignalRecord._log.info('on_cls_action_start')
        pass

    @staticmethod
    def on_cls_action_stop(pubsub, topic, value):
        SignalRecord._log.info('on_cls_action_stop')
        pass
