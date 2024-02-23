# Copyright 2024 Jetperch LLC
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
from joulescope_ui import N_, Metadata
from joulescope_ui.styles import styled_widget
from joulescope_ui.pubsub import TOPIC_ADD_TOPIC, TOPIC_REMOVE_TOPIC
import json


class TopicFilterWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._label = QtWidgets.QLabel(N_('Filter: '), self)
        self._layout.addWidget(self._label)
        self._filter = QtWidgets.QLineEdit(self)
        self._layout.addWidget(self._filter)
        self._filter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)


class TopicDetailWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        self._row = 0
        self._widgets = {}
        self._meta: Metadata = None
        super().__init__(parent)
        self._layout = QtWidgets.QGridLayout(self)
        self._add_row('Topic')
        self._auto = ['dtype', 'brief', 'detail']
        for field in self._auto:
            self._add_row(field)
        self._add_row('value')

        self._publish_button = QtWidgets.QPushButton('Publish', self)
        self._publish_button.pressed.connect(self._on_publish_button);
        self._publish_value = QtWidgets.QLineEdit(self)
        self._publish_value.setToolTip('Contents must be string or JSON format')
        self._layout.addWidget(self._publish_button, self._row, 0, 1, 1)
        self._layout.addWidget(self._publish_value, self._row, 1, 1, 1)
        self._row += 1

    @property
    def pubsub(self):
        return self.parent().pubsub

    def _on_publish_button(self):
        value = self._publish_value.text()
        if self._meta.dtype == 'str' and value[0] != '"':
            pass
        else:
            value = json.loads(self._publish_value.text())
        self.pubsub.publish(self.topic, value)

    def _add_row(self, name):
        label = QtWidgets.QLabel(name, self)
        value = QtWidgets.QLabel(self)
        self._layout.addWidget(label, self._row, 0, 1, 1)
        self._layout.addWidget(value, self._row, 1, 1, 1)
        self._widgets[name] = [value, label]
        self._row += 1

    @property
    def topic(self):
        return self._widgets['Topic'][0].text()

    @topic.setter
    def topic(self, value):
        topic = value
        self._widgets['Topic'][0].setText(topic)
        self._meta: Metadata = self.pubsub.metadata(topic)
        for field in self._auto:
            self._widgets[field][0].setText(getattr(self._meta, field, ''))
        self._widgets['value'][0].setText('')

    def value(self, value):
        self._widgets['value'][0].setText(str(value))


@styled_widget(N_('PubSub Explorer'))
class PubSubExplorerWidget(QtWidgets.QWidget):
    """A developer widget to explore the publish-subscribe system and topics."""

    CAPABILITIES = ['widget@']

    def __init__(self, parent=None):
        self._items = {}
        super().__init__(parent=parent)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._filter = TopicFilterWidget(self)
        self._layout.addWidget(self._filter)

        self._model = QtGui.QStandardItemModel(self)
        self._view = QtWidgets.QTreeView(self)
        self._view.setObjectName('pubsub_explorer_view')
        self._layout.addWidget(self._view)

        self._view.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
        self._view.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self._view.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._view.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self._model = QtGui.QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels(['Name'])
        self._view.setModel(self._model)

        self._view.setModel(self._model)
        self._view.setHeaderHidden(True)

        self._detail = TopicDetailWidget(self)
        self._layout.addWidget(self._detail)
        self._view.selectionModel().currentChanged.connect(self._on_changed)

    def _on_changed(self, model_index, model_index_old):
        topic = self._model.data(model_index, QtCore.Qt.UserRole + 1)
        self._detail.topic = topic
        self.pubsub.unsubscribe_all(self._on_value)
        self.pubsub.subscribe(topic, self._on_value, ['pub', 'retain'])

    def _on_value(self, topic, value):
        self._detail.value(value)

    def _populate(self):
        for topic in sorted(self.pubsub):
            self._on_topic_add(topic)

    def _on_topic_add(self, value):
        parent = self._model.invisibleRootItem()
        topic = value if isinstance(value, str) else value['topic']
        if topic is None or not len(topic):
            return
        topic_parts = topic.split('/')
        create_parts = []
        while len(topic_parts):
            topic_full = '/'.join(topic_parts)
            if topic_full in self._items:
                parent = self._items[topic_full]
                break
            else:
                create_parts.insert(0, topic_parts.pop())

        for topic_part in create_parts:
            topic_parts.append(topic_part)
            topic_full = '/'.join(topic_parts)
            item = QtGui.QStandardItem(topic_part)
            item.setData(topic_full, QtCore.Qt.UserRole + 1)
            parent.appendRow(item)
            parent.sortChildren(0)
            parent = item
            self._items[topic_full] = item

    def _on_topic_remove(self, value):
        topic = value if isinstance(value, str) else value['topic']
        if topic is None or not len(topic):
            return
        item = self._items.pop(topic, None)
        if item is None:
            return
        item.parent().takeRow(item.row())
        del item

    def on_pubsub_register(self):
        self._populate()
        self.pubsub.subscribe(TOPIC_ADD_TOPIC, self._on_topic_add, ['pub'])
        self.pubsub.subscribe(TOPIC_REMOVE_TOPIC, self._on_topic_remove, ['pub'])
