# Copyright 2022 Jetperch LLC
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
from joulescope_ui import pubsub_singleton, N_, register, get_instance, get_unique_id, get_topic_name


def settings_action_create(obj, menu):
    def on_action(checked=False):
        pubsub_singleton.publish('registry/settings/actions/!edit', obj)

    action = QtGui.QAction(menu)
    action.setText(N_('Settings'))
    action.triggered.connect(on_action)
    menu.addAction(action)
    return action
