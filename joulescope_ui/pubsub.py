# Copyright 2022 Jetperch LLC
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

"""
Communication method used to connect the Joulescope UI components.
"""

from . import json
from .metadata import Metadata
import threading
import logging


_SUBSCRIBER_TYPES = ['command', 'pub', 'retain', 'metadata', 'remove', 'completion']
_SUFFIX_CHAR = {
    '$': 'metadata',
    '~': 'remove',
    '#': 'completion'
}
APP_COMMON_ACTIONS_TOPIC = 'app_common/actions'
UNDO_TOPIC = APP_COMMON_ACTIONS_TOPIC + '/!undo'
REDO_TOPIC = APP_COMMON_ACTIONS_TOPIC + '/!redo'
SUBSCRIBE_TOPIC = APP_COMMON_ACTIONS_TOPIC + '/!subscribe'
UNSUBSCRIBE_TOPIC = APP_COMMON_ACTIONS_TOPIC + '/!unsubscribe'
UNSUBSCRIBE_ALL_TOPIC = APP_COMMON_ACTIONS_TOPIC + '/!unsubscribe_all'
TOPIC_ADD_TOPIC = APP_COMMON_ACTIONS_TOPIC + '/!topic_add'
TOPIC_REMOVE_TOPIC = APP_COMMON_ACTIONS_TOPIC + '/!topic_remove'


class _Topic:

    def __init__(self, parent, topic, meta, value=None):
        """Hold a single MyTopic entry for :class:`PubSub`.

        :param parent: The parent :class:`MyTopic` instance.
        :param topic: The fully-qualified topic string.
        :param meta: The metadata for this topic.
        :param value: The optional initial value.
        """
        self.update_fn = {}   # Mapping[str, list]
        for stype in _SUBSCRIBER_TYPES:
            self.update_fn[stype] = []
        self.parent = parent
        self.topic_name = topic
        self.subtopic_name = topic.split('/')[-1]
        self._value = None          # for retained values
        self.children = {}      # Mapping[str, MyTopic]
        self.meta = meta
        default = None if meta is None else meta.default
        self.value = value if value is not None else default

    def to_obj(self):
        children = []
        for n, child in self.children.items():
            if n[0] == '!':
                continue
            children.append(child.to_obj())
        return {
            'topic': self.subtopic_name,
            'value': self.value,
            'meta': self.meta.to_map(),
            'children': children,
        }

    def from_obj(self, obj):
        self._value = obj['value']
        self.meta = Metadata(**obj['meta'])
        for child_obj in obj['children']:
            child_name = child_obj['topic']
            if child_name in self.children:
                child = self.children[child_name]
            else:
                if self.topic_name == '':
                    topic_name = child_name
                else:
                    topic_name = f'{self.topic_name}/{child_name}'
                child = _Topic(self, topic_name, None)
                self.children[child_name] = child
            child.from_obj(child_obj)

    def __str__(self):
        return f'_Topic({self.topic_name}, value={self.value})'

    @property
    def name(self):
        return self.topic_name

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, x):
        if self.meta is not None:
            x = self.meta.validate(x)
        if not self.subtopic_name.startswith('!'):
            self._value = x


class _Command:

    def __init__(self, topic, value):
        self.topic = topic
        self.value = value

    def __str__(self):
        return f'_Command({repr(self.topic)}, {self.value})'

    def __repr__(self):
        return f'_Command({repr(self.topic)}, {repr(self.value)})'


class _Undo:

    def __init__(self, topic, undos=None, redos=None):
        self.topic = topic
        self.undos = [] if undos is None else undos  # list of _Command
        self.redos = [] if redos is None else redos  # list of _Command

    def __str__(self):
        return self.topic

    def __repr__(self):
        return f'_Undo({repr(self.topic)}, {repr(self.undos)}, {repr(self.redos)})'

    def __len__(self):
        return len(self.undos)

    def pub_add(self, topic: str, old_value, new_value):
        """Add an undo/redo for a publish.

        :param topic: The publish topic name.
        :param old_value: The original retained topic value.
        :param new_value: The new topic value being published.
        """
        self.undos.append(_Command(topic, old_value))
        self.redos.append(_Command(topic, new_value))

    def cmd_add(self, topic: str, value, rv):
        """Add an undo/redo for a command.

        :param topic: The command topic name.
        :param value: The value for the command.
        :param rv: The return value from the command processing function,
            which is one of:
            * None: No undo/redo support
            * [undo_topic, undo_value]
        """
        if rv is None:
            return
        if isinstance(rv[0], str) and len(rv) == 2:
            self.undos.append(_Command(*rv))
        else:
            for topic, value in rv:
                self.undos.append(_Command(topic, value))
        self.redos.append(_Command(topic, value))


class PubSub:
    def __init__(self, notify_fn=None):
        """A publish-subscribe implementation combined with the command pattern.

        :param notify_fn: The function to call whenever a new item is
            ready for processing.

        """
        self._log = logging.getLogger(__name__)
        if callable(notify_fn):
            self._notify_fn = notify_fn
        elif notify_fn is None:
            self._notify_fn = lambda: None
        else:
            raise ValueError('Invalid notify_fn')
        self._thread_id = threading.get_native_id()
        meta = Metadata(dtype='node', brief='root topic')
        self._root = _Topic(None, '', meta)
        self._topic_by_name = {}
        self._lock = threading.RLock()
        self._queue = []  # entries are _Command
        self._stack = []  # entries are _Command
        self._undo_capture = None
        self.undos = []  # list of _Undo
        self.redos = []  # list of _Undo

        self._add_cmd(SUBSCRIBE_TOPIC, self._cmd_subscribe)                 # subscribe must be first
        self._add_cmd(UNSUBSCRIBE_TOPIC, self._cmd_unsubscribe)
        self._add_cmd(UNSUBSCRIBE_ALL_TOPIC, self._cmd_unsubscribe_all)
        self._add_cmd(TOPIC_ADD_TOPIC, self._cmd_topic_add)
        self._add_cmd(TOPIC_REMOVE_TOPIC, self._cmd_topic_remove)
        self._add_cmd(UNDO_TOPIC, self._cmd_undo)
        self._add_cmd(REDO_TOPIC, self._cmd_redo)

    def _add_cmd(self, topic, update_fn):
        topic_add_value = {
            'topic': topic,
            'meta': Metadata(dtype='obj', brief=topic, flags=['hide']),
        }
        self._cmd_topic_add(TOPIC_ADD_TOPIC, topic_add_value)
        subscribe_value = {
            'topic': topic,
            'update_fn': update_fn,
            'flags': ['command']
        }
        self._cmd_subscribe(SUBSCRIBE_TOPIC, subscribe_value)

    def _cmd_undo(self, topic, value):
        for count in range(value):
            if not len(self.undos):
                return
            undo = self.undos.pop()
            self.redos.insert(0, undo)
            for cmd in undo.undos:
                self._process_one(cmd)
        return None

    def _cmd_redo(self, topic, value):
        for count in range(value):
            if not len(self.redos):
                return
            undo = self.redos.pop()
            for cmd in undo.redos:
                self._process_one(cmd)
        return None

    def undo(self, count=None):
        count = 1 if count is None else int(count)
        self.publish(UNDO_TOPIC, count)

    def redo(self, count=None):
        count = 1 if count is None else int(count)
        self.publish(REDO_TOPIC, count)

    def _send(self, topic, value, timeout=None):
        thread_id = threading.get_native_id()
        if thread_id == self._thread_id:
            if timeout:
                raise BlockingIOError()
            if len(self._stack):
                self._stack[-1].append(_Command(topic, value))
            else:
                with self._lock:
                    was_empty = (len(self._queue) == 0)
                    self._queue.append(_Command(topic, value))
                if was_empty:
                    self.process()
            return None

        if timeout is not None:
            raise NotImplementedError()
        with self._lock:
            self._queue.append(_Command(topic, value))
        self._notify_fn()
        if timeout is not None:
            raise NotImplementedError()

    def topic_add(self, topic: str, *args, **kwargs):
        """Define and create a new topic.

        topic_add(topic, meta: Metadata, timeout=None)
        topic_add(topic, meta: json_str, timeout=None)
        topic_add(topic, *args, **kwargs, timeout=None) -> topic_add(topic, Metadata(*args, **kwargs))

        :param topic: The fully-qualified topic name.
        :param args: The metadata either as:
            * Metadata object
            * json-formatted string
            * positional arguments for Metadata constructor.
        :param kwargs: The keyword arguments for the Metadata constructor.
        :param timeout: If None (default), complete asynchronously.
            If specified, the time in seconds to wait for the completion.
        :return: Completion code if timeout, else None.
        :raise BlockingIOError: If timeout is provided and invoked from the
            Qt event thread.
        """

        timeout = kwargs.pop('timeout', None)
        if len(kwargs):
            meta = Metadata(*args, **kwargs)
        elif len(args) == 1:
            x = args[0]
            if isinstance(x, Metadata):
                meta = x
            elif isinstance(x, str):
                meta = Metadata(**json.loads(x))
            else:
                raise ValueError('positional metadata arg must be Metadata or json string')
        return self._send(TOPIC_ADD_TOPIC, {'topic': topic, 'meta': meta}, timeout)

    def topic_remove(self, topic: str, timeout=None):
        """Remove a topic and all subtopics.

        :param topic: The fully-qualified topic name to remove.
        :param timeout: If None (default), complete asynchronously.
            If specified, the time in seconds to wait for the completion.
        :return: Completion code if timeout, else None.
        :raise BlockingIOError: If timeout is provided and invoked from the
            Qt event thread.
        """
        return self._send(TOPIC_REMOVE_TOPIC, {'topic': topic}, timeout)

    def publish(self, topic: str, value, timeout=None):
        """Publish a value to a topic.

        :param topic: The topic string.
        :param value: The value, which must pass validation for the topic.
        :param timeout: If None (default), complete asynchronously.
            If specified, the time in seconds to wait for the completion.
        :return: Completion code if timeout, else None.
        :raise BlockingIOError: If timeout is provided and invoked from the
            Qt event thread.
        """
        return self._send(topic, value, timeout)

    def _topic_get(self, topic) -> _Topic:
        with self._lock:
            return self._topic_by_name[topic]

    def query(self, topic):
        """Query the retained value for a topic.

        :param topic: The topic string.
        :return: The value for the topic.

        Note that this method returns immediately with the existing retained
        value.  It does not account for any changes that are still queued
        awaiting processing.  To get the resulting values of topics that
        may change, you normally want to subscribe.
        """
        t = self._topic_get(topic)
        return t.value

    def metadata(self, topic):
        """Query the metadata value for a topic.

        :param topic: The topic string.
        :return: The metadict instance for the topic.
        """
        t = self._topic_get(topic)
        return t.meta

    def _enumerate_recurse(self, t, lead_count):
        names = []
        for subtopic in t.children.values():
            names.append(subtopic.topic_name[lead_count:])
            names.extend(self._enumerate_recurse(subtopic, lead_count))
        return names

    def enumerate(self, topic, absolute=None, traverse=None):
        """Enumerate the subtopic names of the specified topic.

        :param topic: The topic string.
        :param absolute: True to return the absolute topic paths, not just
            the relative subtopic path.  False or None (default) only returns
            the immediate subtopic string.
        :param traverse: True to descend into all subtopics.
            False or None (default) only returns the immediate children.
        :return: The list of subtopic strings.
        """
        t = self._topic_get(topic)
        if bool(traverse):
            lead_count = 0 if bool(absolute) else len(t.topic_name) + 1
            return self._enumerate_recurse(t, lead_count)
        names = t.children.keys()
        if bool(absolute):
            names = [f'{topic}/{n}' for n in names]
        else:
            names = list(names)
        return names

    def subscribe(self, topic: str, update_fn: callable, flags=None, timeout=None):
        """Subscribe to receive topic updates.

        :param self: The driver instance.
        :param topic: Subscribe to this topic string.
        :param flags: The list of flags for this subscription.
            None (default) is equivalent to ['pub'].

            The available flags are:

            - pub: Subscribe to normal values.
            - retain: Subscribe to retained values.
            - command: Subscribe as the command handler.
              A topic may only have one command handler.
            - metadata: Subscribe to metadata updates.
              The topic provided to update_fn is topic + '$'.
            - remove: Subscribe to topic.
              The topic provided to update_fn is topic + '~'.
            - completion: Subscribe to completion code.
              The topic provided to update_fn is topic + '#'.

        :param update_fn: The function(topic, value) to call on each publish.
            For normal subscriptions, the return value is ignored.
            For a command subscriber, the return value should be
            [undo, redo].
            Note that this instance stores a weakref to update_fn so that
            subscribing does not keep the subscriber alive.  Therefore,
            update_fn must remain referenced externally.
            Lambdas, local functions, and bound methods all go out of scope.
            To prevent unintentionally having update_fn go out of scope,
            the caller must maintain a local reference, which can also
            be used to unsubscribe.
        :param timeout: If None (default), complete asynchronously.
            If specified, the time in seconds to wait for the completion.
        :raise BlockingIOError: If timeout is provided and invoked from the
            Qt event thread.
        :raise RuntimeError: on error.
        """
        value = {
            'topic': topic,
            'update_fn': update_fn,
            'flags': flags
        }
        return self._send(SUBSCRIBE_TOPIC, value, timeout)

    def unsubscribe(self, topic, update_fn: callable, flags=None, timeout=None):
        """Unsubscribe from a topic.

        :param topic: The topic name string.
        :param update_fn: The function previously provided to :func:`subscribe`.
        :param flags: The flags to unsubscribe.  None (default) unsubscribes
            from all.
        :param timeout: If None (default), complete asynchronously.
            If specified, the time in seconds to wait for the completion.
        :raise BlockingIOError: If timeout is provided and invoked from the
            Qt event thread.
        :raise: On error.
        """
        value = {
            'topic': topic,
            'update_fn': update_fn,
            'flags': flags
        }
        return self._send(UNSUBSCRIBE_TOPIC, value, timeout)

    def unsubscribe_all(self, update_fn: callable, timeout=None):
        """Completely unsubscribe a callback from all topics.

        :param update_fn: The function previously provided to :func:`subscribe`.
        :param timeout: If None (default), complete asynchronously.
            If specified, the time in seconds to wait for the completion.
        :raise BlockingIOError: If timeout is provided and invoked from the
            Qt event thread.
        :raise: On error.
        """
        value = {'update_fn': update_fn}
        return self._send(UNSUBSCRIBE_ALL_TOPIC, value, timeout)

    def _cmd_topic_add(self, topic, value):
        topic_name = value['topic']
        topic_name_parts = topic_name.split('/')
        topic = self._root
        for idx in range(len(topic_name_parts) - 1):
            subtopic_name = topic_name_parts[idx]
            try:
                topic = topic.children[subtopic_name]
            except KeyError:
                topic_name_new = '/'.join(topic_name_parts[:(idx + 1)])
                subtopic = _Topic(topic, topic_name_new, Metadata(dtype='node', brief=subtopic_name))
                topic.children[subtopic_name] = subtopic
                self._topic_by_name[topic_name_new] = subtopic
                topic = subtopic
        if 'instance' in value:
            t = value['instance']
        else:
            t = _Topic(topic, topic_name, value['meta'])
        topic.children[topic_name_parts[-1]] = t
        self._topic_by_name[topic_name] = t
        return [TOPIC_REMOVE_TOPIC, {'topic': value['topic']}]

    def _cmd_topic_remove(self, topic, value):
        topic = value['topic']
        try:
            t = self._topic_get(topic)
        except KeyError:
            self._log.debug('topic remove %s but already removed', topic)
            return None
        t.parent.children.pop(t.subtopic_name)
        self._topic_by_name.pop(topic)
        return [TOPIC_ADD_TOPIC, {'topic': topic, 'instance': t}]

    def _publish_retain(self, t, update_fn):
        if not t.subtopic_name.startswith('!'):
            update_fn(t.topic_name, t.value)
        for child in t.children.values():
            self._publish_retain(child, update_fn)

    def _cmd_subscribe(self, topic, value):
        topic = value['topic']
        update_fn = value['update_fn']
        flags = value['flags']
        if flags is None:
            flags = ['pub']
        try:
            t = self._topic_get(topic)
        except KeyError:
            self._log.warning('Subscribe to unknown topic %s', topic)
            return
        retain = False
        for flag in flags:
            if flag == 'retain':
                retain = True
            else:
                t.update_fn[flag].append(update_fn)
        if retain:
            self._publish_retain(t, update_fn)
        return [UNSUBSCRIBE_TOPIC, value]

    def _cmd_unsubscribe(self, topic, value):
        topic = value['topic']
        update_fn = value['update_fn']
        flags = value['flags']
        if flags is None:
            flags = _SUBSCRIBER_TYPES
        try:
            t = self._topic_get(topic)
        except KeyError:
            self._log.warning('Subscribe to unknown topic %s', topic)
            return
        for flag in flags:
            while True:
                try:
                    t.update_fn[flag].remove(update_fn)
                except ValueError:
                    break
        return [SUBSCRIBE_TOPIC, value]

    def _unsubscribe_all_recurse(self, t, update_fn, undo_list):
        for flag, update_fns in t.update_fn.items():
            flags = []
            while True:
                try:
                    update_fns.remove(update_fn)
                    flags.append(flag)
                except ValueError:
                    break
            if len(flags):
                value = {'topic': t.topic_name, 'update_fn': update_fn, 'flags': flags}
                undo_list.append([SUBSCRIBE_TOPIC, value])
        for subtopic in t.children.values():
            self._unsubscribe_all_recurse(subtopic, update_fn, undo_list)

    def _cmd_unsubscribe_all(self, topic, value):
        update_fn = value['update_fn']
        undo_list = []
        self._unsubscribe_all_recurse(self._root, update_fn, undo_list)
        return undo_list

    def _publish_value(self, t, flag, topic_name, value):
        while t is not None:
            for fn in t.update_fn[flag]:
                fn(topic_name, value)
            t = t.parent

    def _process_one(self, cmd):
        topic, value = cmd.topic, cmd.value
        if topic[-1] in _SUFFIX_CHAR:
            topic_name = topic[:-1]
            flag = _SUFFIX_CHAR[topic[-1]]
        else:
            topic_name = topic
            flag = 'pub'
        try:
            t = self._topic_get(topic)
        except KeyError:
            self._log.warning('Publish to unknown topic %s', topic)
            return
        if flag == 'pub':
            value = t.meta.validate(value)
            if t.subtopic_name.startswith('!'):
                cmds_update_fn = t.update_fn['command']
                if len(cmds_update_fn):
                    rv = cmds_update_fn[0](topic, value)
                    self._undo_capture.cmd_add(topic, value, rv)
                for fn in t.update_fn['pub']:
                    fn(topic, value)
                return
            else:
                self._undo_capture.pub_add(topic_name, t.value, value)
                t.value = value
        self._publish_value(t, flag, topic_name, value)

    def _process(self):
        while len(self._stack):
            cmd = self._stack[-1].pop(0)
            self._process_one(cmd)
            if not len(self._stack[-1]):
                self._stack.pop()

    def process(self):
        """Process all pending actions."""
        count = 0
        while True:
            with self._lock:
                try:
                    cmd = self._queue.pop(0)
                except IndexError:
                    break
            assert(len(self._stack) == 0)
            self._undo_capture = _Undo(cmd.topic)
            self._stack.append([cmd])
            self._process()
            assert (len(self._stack) == 0)
            if len(self._undo_capture):
                self.undos.append(self._undo_capture)
            self._undo_capture = None
            count += 1
        return count

    def save(self, fh):
        do_close = False
        obj = self._root.to_obj()
        if isinstance(fh, str):
            fh = open(fh, 'wb')
        try:
            json.dump(obj, fh)
        finally:
            if do_close:
                fh.close()

    def _rebuild_topic_by_name(self, t):
        self._topic_by_name[t.topic_name] = t
        for child in t.children.values():
            self._rebuild_topic_by_name(child)

    def load(self, fh):
        obj = json.load(fh)
        self._root.from_obj(obj)
        self._topic_by_name.clear()
        self._rebuild_topic_by_name(self._root)
