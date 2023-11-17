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


from PySide6 import QtCore, QtGui
from joulescope_ui import N_, CAPABILITIES, pubsub_singleton


_SOURCE_DEF = {
    'statistics_stream': [
        'registry/app/settings/defaults/statistics_stream_source',
        f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list'
    ],
    'signal_stream': [
        'registry/app/settings/defaults/signal_stream_source',
        f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_STREAM_SOURCE}/list'
    ],
    'signal_buffer': [
        'registry/app/settings/defaults/signal_buffer_source',
        f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_BUFFER_SOURCE}/list'
    ],
}


class SourceSelector(QtCore.QObject):

    source_changed = QtCore.Signal(object)    # includes "default", None if not present, for UI elements
    sources_changed = QtCore.Signal(object)   # includes "default"

    resolved_changed = QtCore.Signal(object)  # excludes "default", None if not present, for processing
    list_changed = QtCore.Signal(object)      # excludes "default", duplicates capabilities list

    def __init__(self, parent, source_type: str, settings_topic=None, pubsub=None):
        """Manage the source selection with default and removal persistence.

        :param parent: The parent object.
        :param source_type: The source type string which is on of:
            [statistics_stream, signal_stream, signal_buffer]
        :param settings_topic: The settings topic for source changes.
        :param pubsub: The PubSub instance or None to use the singleton.
        """
        self._is_registered = False
        self._pubsub = pubsub_singleton if pubsub is None else pubsub
        self._default = None
        self.value = None     # includes "default", mirrors settings_topic
        self.sources = ['default']  # includes default and nonpresent but selected source
        self._list = []             # actual sources list
        source_def = _SOURCE_DEF[source_type]
        super().__init__(parent)
        self._subscribers = [
            (source_def[0], self._on_default),
            (source_def[1], self._on_list),
            (settings_topic, self.source_set),
        ]

    @property
    def settings_topic(self):
        return self._subscribers[-1][0]

    @settings_topic.setter
    def settings_topic(self, value):
        t, fn = self._subscribers[-1]
        if t is not None and self._is_registered:
            self._pubsub.unsubscribe(t, fn)
        self._subscribers.append((value, fn))
        if self._is_registered:
            self._pubsub.subscribe(value, fn, ['pub', 'retain'])

    def on_pubsub_register(self):
        self._is_registered = True
        for topic, fn in self._subscribers:
            self._pubsub.subscribe(topic, fn, ['pub', 'retain'])
        topic = self._subscribers[-1][0]
        self.source_set(self._pubsub.query(topic))

    def on_pubsub_unregister(self):
        for topic, fn in self._subscribers:
            self._pubsub.unsubscribe(topic, fn)
        self._is_registered = False

    def resolved(self):
        """Resolve "default" to get the true active source."""
        source = self.value
        if source in [None, 'default']:
            source = self._default
        if source not in self._list:
            return None
        return source

    @QtCore.Slot(object)
    def source_set(self, value):
        """Set the source

        :param value: The source, which can be "default"
        """
        resolved_prev = self.resolved()
        if value is None:
            value = 'default'
        if value == self.value:
            return
        self.value = value
        self._on_list(self._list)
        self.source_changed.emit(self.value)
        if self._is_registered:
            self._pubsub.publish(self.settings_topic, value)
        resolved_new = self.resolved()
        if resolved_new != resolved_prev:
            if resolved_new not in self._list:
                resolved_new = None
            self.resolved_changed.emit(resolved_new)

    def _on_default(self, value):
        value_prev = self.value
        resolved_prev = self.resolved()
        self._default = value
        value_new = self.value
        resolved_new = self.resolved()
        if value_new != value_prev:
            self.source_changed.emit(value_new)
        if resolved_new != resolved_prev:
            self.resolved_changed.emit(resolved_new)

    def _on_list(self, value):
        resolved_prev = self.resolved()
        sources = ['default'] + value
        list_prev, self._list = self._list, list(value)
        sources_prev, self.sources = self.sources, sources
        self.list_changed.emit(self._list)

        v = self.value
        if v is not None and v not in sources:
            sources.append(v)
        if sources != sources_prev:
            self.sources_changed.emit(sources)

        resolved_new = self.resolved()
        if resolved_new != resolved_prev:
            self.resolved_changed.emit(resolved_new)
        elif resolved_new in self._list and resolved_new not in list_prev:
            self.resolved_changed.emit(resolved_new)
        elif resolved_new not in self._list and resolved_new in list_prev:
            self.resolved_new.emit(None)

    def _construct_source_action(self, source):
        def fn():
            self.source_set(source)
        return fn

    def submenu_factory(self, menu):
        source_menu = menu.addMenu(N_('Source'))
        source_group = QtGui.QActionGroup(source_menu)
        source_group.setExclusive(True)
        source_menu_items = [source_group]
        for device in ['default'] + self._list:
            a = QtGui.QAction(device, source_group, checkable=True)
            a.setChecked(device == self.value)
            a.triggered.connect(self._construct_source_action(device))
            source_menu.addAction(a)
            source_menu_items.append(a)
        return source_menu, source_menu_items
