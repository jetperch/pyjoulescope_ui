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

from PySide6 import QtWidgets
from joulescope_ui import N_, register, CAPABILITIES
from joulescope_ui.ui_util import comboBoxConfig
from joulescope_ui.styles import styled_widget


SETTINGS = {
    'source': {
        'dtype': 'str',
        'brief': N_('The JLS data stream source.'),
        'default': None,
    },
}

@register
@styled_widget(N_('JLS Info'))
class JlsInfoWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@', CAPABILITIES.SIGNAL_BUFFER_SINK]
    SETTINGS = SETTINGS

    def __init__(self, parent=None):
        self._sources = []
        self._source = None
        super().__init__(parent=parent)
        self.setObjectName('jls_info_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._source_widget = QtWidgets.QWidget(self)
        self._source_layout = QtWidgets.QHBoxLayout(self._source_widget)
        self._source_label = QtWidgets.QLabel(N_('Source'), self._source_widget)
        self._source_combobox = QtWidgets.QComboBox(self._source_widget)
        self._source_combobox.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._source_layout.addWidget(self._source_label)
        self._source_layout.addWidget(self._source_combobox)
        self._source_spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._source_layout.addItem(self._source_spacer)
        self._layout.addWidget(self._source_widget)

        self._text = QtWidgets.QPlainTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._layout.addWidget(self._text)

    def _on_signal_buffer_source_list(self, sources):
        self._sources = [s for s in sources if s.startswith('JlsSource:')]
        self._source_names = [self.pubsub.query(f'registry/{s}/settings/name') for s in self._sources]
        active_source = self.active_source
        comboBoxConfig(self._source_combobox, self._source_names, active_source)
        prefix = f'registry/{active_source}'
        notes = self.pubsub.query(f'{prefix}/settings/notes', default=None)
        txt = []

        if notes:
            txt.append(notes)
            txt.append('------')

        sources = {}
        for source_idx in self.pubsub.enumerate(f'{prefix}/settings/sources'):
            sources[source_idx] = {
                'source_idx': source_idx,
                'name': self.pubsub.query(f'{prefix}/settings/sources/{source_idx}/name', default=None),
                'info': self.pubsub.query(f'{prefix}/settings/sources/{source_idx}/info', default=None),
                'signals': [],
            }
        for signal_idx in self.pubsub.enumerate(f'{prefix}/settings/signals'):
            meta = self.pubsub.query(f'{prefix}/settings/signals/{signal_idx}/meta', default=None)
            source_idx = meta['source']
            signal = {
                'signal_idx': signal_idx,
                'name': self.pubsub.query(f'{prefix}/settings/signals/{signal_idx}/name', default=None),
                'meta': meta,
                'range': self.pubsub.query(f'{prefix}/settings/signals/{signal_idx}/range', default=None),
            }
            sources[source_idx]['signals'].append(signal)
        for source_idx, source in sources.items():
            txt.append(f'{source_idx}) {source["name"]} : {source["info"]["version"]}')
            for signal in source['signals']:
                length = signal['range']['samples']['length']
                sample_rate = signal['range']['sample_rate']
                txt.append(f'    {signal["name"]} : {length} samples @ {sample_rate} Hz')
        self._text.setPlainText('\n'.join(txt))

    @property
    def active_source(self):
        if not len(self._sources):
            return None
        if self.source is not None and self.source in self._sources:
            return self.source
        else:
            return self._sources[0]

    def on_pubsub_register(self):
        self.pubsub.subscribe(f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_BUFFER_SOURCE}/list',
                              self._on_signal_buffer_source_list, ['pub', 'retain'])
