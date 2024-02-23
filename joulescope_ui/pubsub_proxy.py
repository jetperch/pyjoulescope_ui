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

from joulescope_ui.pubsub_callable import PubSubCallable


class PubSubProxy:
    """Provide managed pubsub access to registered objects.

    :param parent: The parent PubSub instance.
    """

    def __init__(self, parent):
        self.parent = parent
        self._subscribers = {}

    def __str__(self):
        return 'PubSubProxy()'

    def __iter__(self):
        return self.parent.__iter__()

    def topic_add(self, topic: str, *args, **kwargs):
        return self.parent.topic_add(topic, *args, **kwargs)

    def topic_remove(self, topic: str, defer=None):
        return self.parent.topic_remove(topic, defer)

    def publish(self, topic: str, value, defer=None):
        return self.parent.publish(topic, value, defer)

    def query(self, topic, **kwargs):
        return self.parent.query(topic, **kwargs)

    def metadata(self, topic):
        return self.parent.metadata(topic)

    def enumerate(self, topic, absolute=None, traverse=None):
        return self.parent.enumerate(topic, absolute, traverse)

    def subscribe(self, topic: str, update_fn: callable, flags=None):
        c = self.parent.subscribe(topic, update_fn, flags)
        if topic not in self._subscribers:
            self._subscribers[topic] = [c]
        else:
            self._subscribers[topic].append(c)
        return c

    def unsubscribe(self, topic, update_fn: callable = None):
        if topic is None:
            return
        self.parent.unsubscribe(topic, update_fn)
        if isinstance(topic, PubSubCallable):
            topic, c = topic.topic, topic
        else:
            c = PubSubCallable(update_fn, topic)
        if topic in self._subscribers:
            self._subscribers[topic] = [fn for fn in self._subscribers[topic] if fn != c]

    def unsubscribe_all(self, update_fn: callable = None):
        if update_fn is None:
            for topic, fn_list in self._subscribers.items():
                for fn in fn_list:
                    self.parent.unsubscribe(fn)
            self._subscribers.clear()
            return
        self.parent.unsubscribe_all(update_fn)
        c = update_fn
        if not isinstance(c, PubSubCallable):
            c = PubSubCallable(update_fn)
        for topic, values in self._subscribers.items():
            self._subscribers[topic] = [fn for fn in self._subscribers[topic] if fn != c]

    def register(self, obj, unique_id: str = None, parent=None):
        return self.parent.register(obj, unique_id, parent)

    def unregister(self, spec, delete=None):
        self.parent.unregister(spec, delete)

    def on_pubsub_unregister(self):
        self.unsubscribe_all()

    def capabilities_append(self, spec, capabilities):
        self.parent.capabilities_append(spec, capabilities)

    def capabilities_remove(self, spec, capabilities):
        self.parent.capabilities_remove(spec, capabilities)
