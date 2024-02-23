# Copyright 2024 Jetperch LLC
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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_, register
from joulescope_ui.styles import styled_widget
from joulescope_ui.widget_tools import settings_action_create, context_menu_show
from datetime import datetime


_TOPIC = f'registry/ui/events/blink_medium'


@register
@styled_widget(N_('Clock'))
class ClockWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']
    SETTINGS = {
        'time_zone': {
            'dtype': 'str',
            'brief': N_('The time zone.'),
            'options': [
                ['local', N_('Local')],
                ['utc', N_('UTC')],
            ],
            'default': 'local',
        },
        'string_format': {
            'dtype': 'str',
            'brief': N_('The format string'),
            'detail': """\
                For syntax, see Python datetime.datetime.strftime""",
            'default': '%Y-%m-%d %H:%M:%S',
        }
    }

    def __init__(self, parent=None):
        self._menu = None
        super().__init__(parent=parent)
        self.setObjectName('clock_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._time_str = QtWidgets.QLabel(self)
        self._layout.addWidget(self._time_str)

    def _on_update(self):
        if self.time_zone == 'utc':
            d = datetime.utcnow()
        else:
            d = datetime.now()
        s = d.strftime(self.string_format)
        self._time_str.setText(s)

    def on_pubsub_register(self):
        self.pubsub.subscribe(_TOPIC, self._on_update, ['pub'])

    def mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton:
            pass
        elif event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            settings_action_create(self, menu)
            context_menu_show(menu, event)
