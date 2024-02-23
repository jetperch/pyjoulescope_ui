# Copyright 2019 Jetperch LLC
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

from joulescope_ui import N_, time64, register, pubsub_singleton, get_topic_name
from joulescope_ui.range_tool import RangeToolBase, rsp_as_f32
import logging
import numpy as np
from PySide6 import QtCore, QtWidgets


@register
class MaxWindowRangeTool(RangeToolBase):
    NAME = N_('Max window')
    BRIEF = N_('Find the maximum value window')
    DESCRIPTION = N_("""\
        Search the range for the window that has the maximum value.
        This is an exhaustive search made by sliding the window 
        duration across the entire range.
        
        When complete, this tool will add dual markers to the
        waveform.""")

    def __init__(self, value):
        super().__init__(value)

    def _run(self):
        origin = self.value.get('origin')
        kwargs = self.kwargs
        utc_width = kwargs['width']  # in float seconds
        signal = kwargs['signal']
        d = self.request(signal, 'utc', *self.x_range, 1)
        fs = d['info']['time_map']['counter_rate']
        t_start = d['info']['time_range_utc']['start']
        t_end = d['info']['time_range_utc']['end']
        t_width = t_end - t_start
        s_now = d['info']['time_range_samples']['start']
        s_end = d['info']['time_range_samples']['end'] + 1
        length = s_end - s_now
        if length > 250_000_000:
            self.error('window size too big')
            return
        width = int(np.rint(utc_width * fs))
        if width > length:
            self.error('width > region')
            return
        rsp = self.request(signal, 'samples', s_now, 0, s_end - s_now)
        data = rsp_as_f32(rsp)
        i0 = 0
        i1 = width
        m = np.sum(data[i0:i1])
        max_v = m
        max_i = 0
        progress_counter = 0
        while i1 < length:
            m += data[i1] - data[i0]
            if m > max_v:
                m = max_v
                max_i = i0
            i0 += 1
            i1 += 1
            progress_counter += 1
            if progress_counter >= 10_000:
                self.progress(i0 / length)
                progress_counter = 0

        pos0 = max_i / (length - 1) * t_width + t_start
        pos1 = (max_i + width) / (length - 1) * t_width + t_start
        if origin is not None and 'Waveform' in origin:
            action = ['add_dual', pos0, pos1]
            pubsub_singleton.publish(f'{get_topic_name(origin)}/actions/!x_markers', action)
        else:
            self._log.info('Found range: %r', [pos0, pos1])

    @staticmethod
    def on_cls_action_run(value):
        MaxWindowDialog(value)


class MaxWindowDialog(QtWidgets.QDialog):

    def __init__(self, value):
        self._value = value
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self._log = logging.getLogger(f'{__name__}.dialog')
        self.setWindowTitle(N_('Max Window configuration'))
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.resize(368, 123)

        x0, x1 = value['x_range']
        xd = (x1 - x0) / time64.SECOND

        self._layout = QtWidgets.QVBoxLayout(self)
        self._form = QtWidgets.QFormLayout()
        self._width_label = QtWidgets.QLabel(N_('Width of window (in seconds)'), self)
        self._form.setWidget(0, QtWidgets.QFormLayout.LabelRole, self._width_label)
        self._width = QtWidgets.QDoubleSpinBox(self)
        self._width.setObjectName(u"time_len")
        self._width.setDecimals(5)
        self._width.setMinimum(10e-6)
        xd = min(100., xd)
        starting_value = 10 ** np.round(np.log10(xd / 1000))
        self._width.setValue(max(10e-6, starting_value))
        self._width.setMaximum(xd)
        self._width.setSingleStep(min(0.1, xd / 100))
        self._width.setStepType(QtWidgets.QAbstractSpinBox.AdaptiveDecimalStepType)
        self._form.setWidget(0, QtWidgets.QFormLayout.FieldRole, self._width)

        self._signal_label = QtWidgets.QLabel(N_('Signal'), self)
        self._form.setWidget(1, QtWidgets.QFormLayout.LabelRole, self._signal_label)

        self._signal = QtWidgets.QComboBox(self)
        self._form.setWidget(1, QtWidgets.QFormLayout.FieldRole, self._signal)
        for signal_id in value['signals']:
            signal_name = '.'.join(signal_id.split('.')[-2:])
            self._signal.addItem(signal_name)

        self._layout.addLayout(self._form)

        self._layout.addLayout(self._form)
        self._buttons = QtWidgets.QDialogButtonBox(self)
        self._buttons.setOrientation(QtCore.Qt.Horizontal)
        self._buttons.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        self._layout.addWidget(self._buttons)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self.finished.connect(self._on_finished)
        self._log.info('open')
        self.open()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        self._log.info('finished: %d', value)

        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._log.info('finished: accept - start max window')
            self._value['kwargs'] = {
                'width': float(self._width.value()),
                'signal': self._value['signals'][self._signal.currentIndex()],
            }
            w = MaxWindowRangeTool(self._value)
            pubsub_singleton.register(w)
        else:
            self._log.info('finished: reject - abort')  # no action required
        self.close()
