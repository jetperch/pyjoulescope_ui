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
from joulescope_ui import N_, get_topic_name, pubsub_singleton, register, tooltip_format
from joulescope_ui.styles import styled_widget
from joulescope_ui.units import elapsed_time_formatter
import os
import time


_PATH = N_('Path: ')
_FILENAME = N_('Filename: ')


_UNIQUE_IDS = {
    'SignalRecord': N_('Signal recording in progress'),
    'StatisticsRecord': N_('Statistics recording in progress'),
}


@register
@styled_widget(N_('Record Status'))
class RecordStatusWidget(QtWidgets.QWidget):

    # Note: does NOT implement widget CAPABILITY, since not instantiable by user or available as a dock widget.

    def __init__(self, parent, source_unique_id):
        self._parent = parent
        self._time = None
        self._source_unique_id = source_unique_id
        self._brief = _UNIQUE_IDS[source_unique_id]
        super().__init__(parent=parent)
        self.setVisible(False)

        self._layout = QtWidgets.QHBoxLayout()
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._icon = QtWidgets.QLabel(self)
        self._icon.setFixedSize(20, 20)
        self._icon.setObjectName(source_unique_id)
        self._layout.addWidget(self._icon)

        self._text = QtWidgets.QLabel(self)
        self._layout.addWidget(self._text)

        self.setLayout(self._layout)

        topic = get_topic_name(source_unique_id)
        pubsub_singleton.subscribe(f'{topic}/actions/!start', self._on_start, ['pub'])
        pubsub_singleton.subscribe(f'{topic}/events/!stop', self._on_stop, ['pub'])
        pubsub_singleton.subscribe('registry/ui/events/blink_fast', self._on_tick, ['pub'])

    def _on_start(self, value):
        sources = value['sources']
        try:
            path = sources['path']
            filename = os.path.basename(path)
            path = os.path.dirname(path)
            detail = f'{_PATH}{path}\n\n{_FILENAME}{filename}'
        except TypeError:
            path = os.path.dirname(sources[0][-1])
            filenames = [os.path.basename(x[-1]) for x in sources]
            filenames_str = '\n'.join(filenames)
            detail = f'{_PATH}{path}\n\n{filenames_str}'

        self._time = time.time()
        self.setToolTip(tooltip_format(self._brief, detail))
        self.setVisible(True)

    def _on_stop(self):
        self._time = None
        self._text.setText('')
        self.setToolTip('')
        self.setVisible(False)

    def _on_tick(self):
        if self._time is not None:
            duration = time.time() - self._time
            s, u = elapsed_time_formatter(duration, precision=1, trim_trailing_zeros=True)
            if u:
                s = f'{s} {u}'
            self._text.setText(s)
