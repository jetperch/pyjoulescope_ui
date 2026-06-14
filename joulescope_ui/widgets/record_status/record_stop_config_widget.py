# Copyright 2026 Jetperch LLC
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

"""Dialog to schedule when an in-progress recording should automatically stop."""

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_, pubsub_singleton, time64
from joulescope_ui.units import elapsed_time_formatter
from joulescope_ui.widgets.waveform.interval_widget import IntervalWidget
import logging
import time


_DURATION_SO_FAR = N_('Duration so far')
_STOP_WHEN = N_('Stop recording')
_MODE_NONE = N_('When manually stopped')
_MODE_DURATION = N_('After a duration')
_MODE_TIME = N_('At a specific time')
_DURATION = N_('Duration')
_TIME = N_('Time')
_TITLE = N_('Configure recording stop')
_PAST_ERROR = N_('The selected stop time is in the past.')

_MODE_NONE_IDX = 0
_MODE_DURATION_IDX = 1
_MODE_TIME_IDX = 2


class RecordStopConfigDialog(QtWidgets.QDialog):
    """Configure the scheduled stop for an in-progress recording.

    :param source_unique_id: The record class unique_id, either 'SignalRecord'
        or 'StatisticsRecord'.
    :param start_walltime: The wall-clock time (python timestamp) when the
        recording started.  The duration is anchored to this value.
    :param stop_utc: The currently scheduled stop time (time64) or None.
    :param parent: The optional parent widget.
    """

    def __init__(self, source_unique_id, start_walltime, stop_utc=None, parent=None):
        self._log = logging.getLogger(f'{__name__}.dialog')
        self._source_unique_id = source_unique_id
        self._start_walltime = start_walltime
        if parent is None:
            parent = pubsub_singleton.query('registry/ui/instance', default=None)
        super().__init__(parent=parent)
        self.setObjectName('record_stop_config_dialog')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(_TITLE)

        self._layout = QtWidgets.QFormLayout(self)

        self._duration_so_far = QtWidgets.QLabel(self)
        self._layout.addRow(_DURATION_SO_FAR, self._duration_so_far)

        self._mode = QtWidgets.QComboBox(self)
        self._mode.addItem(_MODE_NONE)
        self._mode.addItem(_MODE_DURATION)
        self._mode.addItem(_MODE_TIME)
        self._mode.currentIndexChanged.connect(self._on_mode)
        self._layout.addRow(_STOP_WHEN, self._mode)

        self._duration = IntervalWidget(self, interval_seconds=60.0)
        self._layout.addRow(_DURATION, self._duration)

        self._time = QtWidgets.QDateTimeEdit(self)
        self._time.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
        self._time.setDateTime(QtCore.QDateTime.currentDateTime().addSecs(3600))
        self._layout.addRow(_TIME, self._time)

        self._buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self._on_ok)
        self._buttons.rejected.connect(self.reject)
        self._layout.addRow(self._buttons)

        if stop_utc:
            # Prefill both modes sensibly; default to duration (from start).
            remaining = (time64.as_timestamp(stop_utc) - start_walltime)
            if remaining > 0:
                self._duration.value = remaining
            self._time.setDateTime(QtCore.QDateTime.fromSecsSinceEpoch(
                int(round(time64.as_timestamp(stop_utc)))))
            self._mode.setCurrentIndex(_MODE_DURATION_IDX)
        else:
            self._mode.setCurrentIndex(_MODE_NONE_IDX)
        self._on_mode(self._mode.currentIndex())

        self._update_timer = QtCore.QTimer(self)
        self._update_timer.timeout.connect(self._update_duration_so_far)
        self._update_timer.start(500)
        self._update_duration_so_far()

        self.open()

    @QtCore.Slot()
    def _update_duration_so_far(self):
        duration = max(0.0, time.time() - self._start_walltime)
        s, u = elapsed_time_formatter(duration, precision=1, trim_trailing_zeros=True)
        self._duration_so_far.setText(f'{s} {u}' if u else s)

    @QtCore.Slot(int)
    def _on_mode(self, index):
        self._layout.setRowVisible(self._duration, index == _MODE_DURATION_IDX)
        self._layout.setRowVisible(self._time, index == _MODE_TIME_IDX)
        self.adjustSize()

    def _utc_stop(self):
        index = self._mode.currentIndex()
        if index == _MODE_DURATION_IDX:
            return time64.as_time64(self._start_walltime + self._duration.value)
        elif index == _MODE_TIME_IDX:
            epoch = self._time.dateTime().toMSecsSinceEpoch() / 1000.0
            return time64.as_time64(epoch)
        return None

    @QtCore.Slot()
    def _on_ok(self):
        utc_stop = self._utc_stop()
        if utc_stop is not None and utc_stop <= time64.now():
            pubsub_singleton.publish('registry/ui/actions/!error_msg', _PAST_ERROR)
            return  # keep the dialog open so the user can fix the value
        topic = f'registry/{self._source_unique_id}/actions/!stop_set'
        self._log.info('stop_set %s -> %s', self._source_unique_id, utc_stop)
        pubsub_singleton.publish(topic, utc_stop)
        self.accept()
