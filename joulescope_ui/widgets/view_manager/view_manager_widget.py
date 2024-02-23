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

from PySide6 import QtWidgets, QtCore
from joulescope_ui import N_, get_topic_name, register
from joulescope_ui.styles import styled_widget
from joulescope_ui.widgets import DraggableListWidget
from joulescope_ui.styles.manager import RENDER_TOPIC
from joulescope_ui.view import View


_VIEW_LIST_TOPIC = 'registry/view/instances'
_SPECIAL_VIEWS = ['view:multimeter', 'view:oscilloscope', 'view:file']


class _ViewItem(QtWidgets.QWidget):

    def __init__(self, parent, unique_id, pubsub):
        self.unique_id = unique_id
        self.pubsub = pubsub
        super().__init__(parent)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 6, 0, 6)

        self._move_start = QtWidgets.QLabel(self)
        self._move_start.setObjectName('move')
        self._move_start.setFixedSize(20, 20)
        is_special = unique_id in _SPECIAL_VIEWS
        if is_special:
            self._name = QtWidgets.QLabel(parent=self)
        else:
            self._name = QtWidgets.QLineEdit(parent=self)
            self._name.textEdited.connect(self._on_name_changed)
        self._action = QtWidgets.QPushButton(self)
        self._action.setFixedSize(20, 20)

        self._layout.addWidget(self._move_start)
        self._layout.addWidget(self._name)
        self._spacer = QtWidgets.QSpacerItem(1, 1, QtWidgets.QSizePolicy.Expanding,
                                             QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer)
        self._layout.addWidget(self._action)

        if is_special:
            self._action.setObjectName('view_reset')
            self._action.clicked.connect(self._on_view_reset)
        else:
            self._action.setObjectName('view_delete')
            self._action.clicked.connect(self._on_view_delete)

        self.pubsub.subscribe(f'{get_topic_name(self.unique_id)}/settings/name',
                              self._on_pubsub_name, ['pub', 'retain'])

    def _on_pubsub_name(self, value):
        if value != self._name.text():
            self._name.setText(value)

    def _on_name_changed(self, name):
        self.pubsub.publish(f'{get_topic_name(self.unique_id)}/settings/name', name)

    @property
    def is_active_view(self):
        active_view = self.pubsub.query('registry/view/settings/active')
        return active_view == self.unique_id

    def _on_view_reset(self, checked):
        active_view = self.pubsub.query('registry/view/settings/active')
        self.pubsub.publish('registry/view/settings/active', self.unique_id)
        for child in self.pubsub.query(f'registry/{self.unique_id}/children'):
            self.pubsub.publish('registry/view/actions/!widget_close', child)

        if self.unique_id == 'view:multimeter':
            self.pubsub.publish('registry/view/actions/!widget_open', 'MultimeterWidget')
        elif self.unique_id == 'view:oscilloscope':
            self.pubsub.publish('registry/view/actions/!widget_open', {
                'value': 'WaveformWidget',
                'kwargs': {'source_filter': 'JsdrvStreamBuffer:001'},
            })
        self.pubsub.publish('registry/view/settings/active', active_view)

    def _on_view_delete(self, checked):
        if self.is_active_view:
            items = self.pubsub.query(_VIEW_LIST_TOPIC)
            next_view = items[0] if items[0] != self.unique_id else items[1]
            self.pubsub.publish('registry/view/settings/active', next_view)
        self.pubsub.publish('registry/view/actions/!remove', self.unique_id)
        self.parentWidget().item_remove(self)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._move_start.underMouse():
            # Start the drag operation
            pos = event.position().toPoint()
            self.parentWidget().drag_start(self, pos)


@register
@styled_widget(N_('sidebar'))
class ViewManagerWidget(QtWidgets.QWidget):
    """Manage the views."""

    def __init__(self, parent):
        super().__init__(parent=parent)
        self._menu = None
        self._layout = QtWidgets.QVBoxLayout(self)

        self._view_list = DraggableListWidget(self)
        self._layout.addWidget(self._view_list)
        self._view_list.order_changed.connect(self._on_order_changed)

        self._bottom = QtWidgets.QWidget(self)
        self._layout.addWidget(self._bottom)
        self._bottom_layout = QtWidgets.QHBoxLayout(self._bottom)

        self._add_button = QtWidgets.QPushButton()
        self._add_button.setObjectName('view_add')
        self._add_button.setFixedSize(20, 20)
        self._add_button.clicked.connect(self._on_add)

        self._bottom_layout.addWidget(self._add_button)

        self._spacer = QtWidgets.QSpacerItem(1, 1, QtWidgets.QSizePolicy.Expanding,
                                             QtWidgets.QSizePolicy.Minimum)
        self._bottom_layout.addItem(self._spacer)

        self.ok_button = QtWidgets.QPushButton('OK')
        self._bottom_layout.addWidget(self.ok_button)

    def on_pubsub_register(self):
        views = self.pubsub.query(_VIEW_LIST_TOPIC)
        for unique_id in views:
            item = _ViewItem(self, unique_id, self.pubsub)
            self._view_list.item_add(item)

    def _on_add(self, checked):
        name = N_('New View')
        view = View()
        self.pubsub.register(view)
        self.pubsub.publish(f'{get_topic_name(view)}/settings/name', name)
        item = _ViewItem(self, view.unique_id, self.pubsub)
        self._view_list.item_add(item)

    def _on_order_changed(self, items):
        unique_ids = [item.unique_id for item in items]
        self.pubsub.publish(_VIEW_LIST_TOPIC, unique_ids)


class ViewManagerDialog(QtWidgets.QDialog):

    def __init__(self, parent, pubsub):
        self.pubsub = pubsub
        super().__init__(parent=parent)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._widget = ViewManagerWidget(self)
        self._layout.addWidget(self._widget)
        self.pubsub.register(self._widget, parent='ui')
        self.pubsub.publish(RENDER_TOPIC, self._widget)

        self._widget.ok_button.pressed.connect(self.accept)
        self.finished.connect(self._on_finish)

        self.setWindowTitle(N_('View Manager'))
        self.open()

    @QtCore.Slot()
    def _on_finish(self):
        w, self._widget = self._widget, None
        if w is not None:
            self.pubsub.unregister(w, delete=True)
        self.close()
