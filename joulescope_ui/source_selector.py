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
from joulescope_ui import N_, CAPABILITIES, pubsub_singleton, get_topic_name


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
        self._source_type = source_type
        self._signal_buffer_sources = {}  # the top-level sources mapped to subsources
        source_def = _SOURCE_DEF[source_type]
        super().__init__(parent)
        self._subscribers = [
            [settings_topic, self.source_set, ('pub', 'retain')],
            [source_def[0], self._on_default, ('pub', 'retain')],
            [source_def[1], self._on_list, ('pub', 'retain')],
        ]

    def _subscribe(self, topic, fn, flags):
        self._subscribers.append((topic, fn, flags))
        if self._is_registered and topic is not None:
            self._pubsub.subscribe(topic, fn, flags)

    def _unsubscribe(self, topic):
        if topic is None:
            return
        for idx, entry in enumerate(self._subscribers):
            if topic == entry[0]:
                self._pubsub.unsubscribe(*entry)
                self._subscribers.pop(idx)
                return

    @property
    def settings_topic(self):
        return self._subscribers[0][0]

    @settings_topic.setter
    def settings_topic(self, value):
        t, fn, flags = self._subscribers[0]
        if t is not None and self._is_registered:
            self._pubsub.unsubscribe(t, fn)
        self._subscribers[0][0] = value
        if self._is_registered:
            self._pubsub.subscribe(value, fn, flags)

    def on_pubsub_register(self):
        self._is_registered = True
        for topic, fn, flags in self._subscribers:
            if topic is not None:
                self._pubsub.subscribe(topic, fn, flags)
        topic = self._subscribers[0][0]
        if topic is not None:
            value_prev = self._pubsub.query(topic)
            self.source_set(value_prev)

    def on_pubsub_unregister(self):
        for topic, fn, flags in self._subscribers:
            if topic is not None:
                self._pubsub.unsubscribe(topic, fn, flags)
        self._is_registered = False

    def resolved(self):
        """Resolve "default" to get the true active source."""
        source = self.value
        if source in [None, 'default']:
            source = self._default
        if source == 'off':
            return None
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
        self._on_list_inner(self._list)
        self.source_changed.emit(self.value)
        if self._is_registered and self.settings_topic is not None:
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

    def _buffer_signal_update(self):
        sources = {}
        for source, signals in self._signal_buffer_sources.items():
            for signal in signals:
                source_id, quantity = signal.split('.')
                sources[f'{source}.{source_id}'] = 1
        sources = list(sources.keys())
        self._on_list_inner(sources)

    def _buffer_signal_add(self, topic, value):
        source = topic.split('/')[1]
        signal = value
        if source not in self._signal_buffer_sources:
            self._signal_buffer_sources[source] = []
        signals = self._signal_buffer_sources[source]
        if signal not in signals:
            signals.append(signal)

    def _buffer_signal_remove(self, topic, value):
        source = topic.split('/')[1]
        signal = value
        if source in self._signal_buffer_sources:
            signals = self._signal_buffer_sources[source]
            if signal in signals:
                signals.remove(signal)

    def _buffer_signal_add_update(self, topic, value):
        self._buffer_signal_add(topic, value)
        self._buffer_signal_update()

    def _buffer_signal_remove_update(self, topic, value):
        self._buffer_signal_remove(topic, value)
        self._buffer_signal_update()

    def _buffer_add(self, unique_id):
        topic = get_topic_name(unique_id)
        try:
            self._pubsub.query(f'{topic}/events/signals/!add')
            self._subscribe(f'{topic}/events/signals/!add', self._buffer_signal_add_update, ['pub'])
            self._subscribe(f'{topic}/events/signals/!remove', self._buffer_signal_remove_update, ['pub'])
        except KeyError:
            pass
        signals = self._pubsub.enumerate(f'{topic}/settings/signals')
        for signal in signals:
            self._buffer_signal_add(topic, signal)
        self._buffer_signal_update()

    def _buffer_remove(self, unique_id):
        topic = get_topic_name(unique_id)
        try:
            self._pubsub.query(f'{topic}/events/signals/!add')
            self._unsubscribe(f'{topic}/events/signals/!add')
            self._unsubscribe(f'{topic}/events/signals/!remove')
        except KeyError:
            pass
        self._buffer_signal_update()

    def _on_list_signal_buffer(self, value):
        for v in value:
            if v not in self._signal_buffer_sources:
                self._buffer_add(v)
        for v in self._signal_buffer_sources.keys():
            if v not in value:
                self._buffer_remove(v)

    def _on_list_inner(self, value):
        resolved_prev = self.resolved()
        sources = ['default'] + value
        list_prev, self._list = self._list, list(value)
        sources_prev, self.sources = self.sources, sources
        self.list_changed.emit(self._list)

        v = self.value
        if v is not None and v not in sources and v != 'off':
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

    def _on_list(self, value):
        if self._source_type == 'signal_buffer':
            return self._on_list_signal_buffer(value)
        else:
            self._on_list_inner(value)

    def _construct_source_action(self, source):
        def fn(checked=False):
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
