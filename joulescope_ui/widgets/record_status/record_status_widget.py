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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_, get_topic_name, register, time64, tooltip_format
from joulescope_ui.styles import styled_widget
from joulescope_ui.units import elapsed_time_formatter
from joulescope_ui.widget_tools import CallableAction
from .record_stop_config_widget import RecordStopConfigDialog
import os
import time


_PATH = N_('Path: ')
_FILENAME = N_('Filename: ')
_STOP_SET = N_('Set stop duration/time')
_STOP_CLEAR = N_('Clear scheduled stop')
_REMAINING = N_('left')


_UNIQUE_IDS = {
    'SignalRecord': N_('Signal recording in progress'),
    'StatisticsRecord': N_('Statistics recording in progress'),
}

# Map the record source to its app record on/off setting.
_RECORD_SETTINGS = {
    'SignalRecord': 'signal_stream_record',
    'StatisticsRecord': 'statistics_stream_record',
}


@register
@styled_widget(N_('Record Status'))
class RecordStatusWidget(QtWidgets.QWidget):

    # Note: does NOT implement widget CAPABILITY, since not instantiable by user or available as a dock widget.

    def __init__(self, parent, source_unique_id):
        self._time = None
        self._stop_utc = None
        self._source_unique_id = source_unique_id
        self._brief = _UNIQUE_IDS[source_unique_id]
        super().__init__(parent=parent)
        self.setVisible(False)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._icon = QtWidgets.QLabel(self)
        self._icon.setFixedSize(20, 20)
        self._icon.setObjectName(source_unique_id)
        self._layout.addWidget(self._icon)

        self._text = QtWidgets.QLabel(self)
        self._layout.addWidget(self._text)

    def on_pubsub_register(self):
        topic = get_topic_name(self._source_unique_id)
        self.pubsub.subscribe(f'{topic}/actions/!start', self._on_start, ['pub'])
        self.pubsub.subscribe(f'{topic}/events/!stop', self._on_stop, ['pub'])
        self.pubsub.subscribe(f'{topic}/events/!stop_changed', self._on_stop_changed, ['pub'])
        self.pubsub.subscribe('registry/ui/events/blink_fast', self._on_tick, ['pub'])

    def _on_context_menu(self, pos):
        if self._time is None:
            return  # not recording
        menu = QtWidgets.QMenu(self)
        CallableAction(menu, _STOP_SET, self._stop_config_show)
        if self._stop_utc is not None:
            CallableAction(menu, _STOP_CLEAR, self._stop_clear)
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.mapToGlobal(pos))

    def _stop_config_show(self):
        RecordStopConfigDialog(self._source_unique_id, self._time, self._stop_utc)

    def _stop_clear(self):
        self.pubsub.publish(f'registry/{self._source_unique_id}/actions/!stop_set', None)

    def _on_stop_changed(self, value):
        self._stop_utc = value if value else None

    def _on_start(self, value):
        self._stop_utc = None
        if 'path' in value:
            # JLS sample recording from SignalRecordConfigWidget
            path = os.path.dirname(value['path'])
            sources = [value['path']]
        else:  # statistics recording from StatisticsRecordConfigWidget
            sources = [s[-1] for s in value['sources']]
            path = os.path.dirname(sources[0])
        filenames = [os.path.basename(s) for s in sources]
        filenames_str = '\n'.join(filenames)
        detail = f'{_PATH}{path}\n\n{filenames_str}'
        self._time = time.time()
        self.setToolTip(tooltip_format(self._brief, detail))
        self.setVisible(True)

    def _on_stop(self):
        self._time = None
        self._stop_utc = None
        self._text.setText('')
        self.setToolTip('')
        self.setVisible(False)

    def _on_tick(self):
        if self._time is None:
            return
        if self._stop_utc is not None and time64.now() >= self._stop_utc:
            # Scheduled stop reached: drive the normal record toggle-off so the
            # file is closed, the !stop event fires, and the toggle resets.
            self._stop_utc = None
            self.pubsub.publish(f'registry/app/settings/{_RECORD_SETTINGS[self._source_unique_id]}', False)
            return
        duration = time.time() - self._time
        s, u = elapsed_time_formatter(duration, precision=1, trim_trailing_zeros=True)
        text = f'{s} {u}' if u else s
        if self._stop_utc is not None:
            remaining = max(0.0, (self._stop_utc - time64.now()) / time64.SECOND)
            rs, ru = elapsed_time_formatter(remaining, precision=1, trim_trailing_zeros=True)
            rs = f'{rs} {ru}' if ru else rs
            text = f'{text} ({rs} {_REMAINING})'
        self._text.setText(text)
