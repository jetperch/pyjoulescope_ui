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
import os
import sys


_APP_DEFAULT = 'joulescope'
_SUBSCRIBER_TYPES = ['command', 'pub', 'retain', 'metadata', 'remove', 'completion']
_SUFFIX_CHAR = {
    '$': 'metadata',
    '~': 'remove',
    '#': 'completion'
}
COMMON_ACTIONS_TOPIC = 'common/actions'
UNDO_TOPIC = COMMON_ACTIONS_TOPIC + '/!undo'
REDO_TOPIC = COMMON_ACTIONS_TOPIC + '/!redo'
SUBSCRIBE_TOPIC = COMMON_ACTIONS_TOPIC + '/!subscribe'
UNSUBSCRIBE_TOPIC = COMMON_ACTIONS_TOPIC + '/!unsubscribe'
UNSUBSCRIBE_ALL_TOPIC = COMMON_ACTIONS_TOPIC + '/!unsubscribe_all'
TOPIC_ADD_TOPIC = COMMON_ACTIONS_TOPIC + '/!topic_add'
TOPIC_REMOVE_TOPIC = COMMON_ACTIONS_TOPIC + '/!topic_remove'
REGISTER_COMPLETION = COMMON_ACTIONS_TOPIC + '/!register_completion'
CLS_ACTION_PREFIX = 'on_cls_action_'
CLS_CALLBACK_PREFIX = 'on_cls_cbk_'
CLS_EVENT_PREFIX = 'on_cls_event_'
ACTION_PREFIX = 'on_action_'
CALLBACK_PREFIX = 'on_cbk_'
EVENT_PREFIX = 'on_event_'


class PUBSUB_TOPICS:  # todo
    PUBSUB_APP_NAME = 'common/settings/name'
    PUBSUB_PROFILE_ACTION_ADD = 'common/actions/profile/!add'
    PUBSUB_PROFILE_ACTION_REMOVE = 'common/actions/profile/!remove'
    PUBSUB_PROFILE_ACTION_SAVE = 'common/actions/profile/!save'
    PUBSUB_PROFILE_ACTION_LOAD = 'common/actions/profile/!load'


class REGISTRY_MANAGER_TOPICS:
    BASE = 'registry_manager'
    ACTIONS = 'registry_manager/actions'
    CAPABILITY_ADD = 'registry_manager/actions/capability/!add'
    CAPABILITY_REMOVE = 'registry_manager/actions/capability/!remove'
    REGISTRY_ADD = 'registry_manager/actions/registry/!add'
    REGISTRY_REMOVE = 'registry_manager/actions/registry/!remove'
    CAPABILITIES = f'registry_manager/capabilities'
    NEXT_UNIQUE_ID = f'registry_manager/next_unique_id'


def get_unique_id(obj):
    """Get the unique_id.

    :param obj: The source for the unique id, which can be any of:
        * The topic name string
        * The unique id string (simply returned)
        * A registered class or object
    :return: The unique id string.
    :raise ValueError: If cannot find the unique id.
    """
    if isinstance(obj, str):
        if obj.startswith('registry/'):
            return obj.split('/')[1]
        elif '/' not in obj:
            return obj  # presume that this is the unique id
        else:
            raise ValueError(f'Invalid unique_id string {obj}')
    if 'unique_id' in obj.__dict__:
        return obj.unique_id
    else:
        raise ValueError(f'Could not find unique_id for {obj}')


def get_topic_name(obj):
    """Get the topic name.

    :param obj: The source for the topic name, which can be any of:
        * The topic name string (simply returned)
        * The unique id string
        * A registered class or object
    :return: The topic name string.
    :raise ValueError: If cannot find the topic name.
    """
    unique_id = get_unique_id(obj)
    return f'registry/{unique_id}'


def get_instance(obj, pubsub=None, **kwargs):
    """Get the instance.

    :param obj: The source for the topic name, which can be any of:
        * The topic name string (simply returned)
        * The unique id string
        * A registered class or object
    :param pubsub: The pubsub instance or None.
        None uses the Joulescope UI singleton instance.
    :param default: When specified, return this value if the
        instance cannot be found.
    :return: The instance.
    :raise TypeError: If invalid arguments names are provided.
    :raise KeyError: If cannot find the instance.
    """
    if not isinstance(obj, str):
        return obj
    has_default = 'default' in kwargs
    default = kwargs.pop('default', None)
    if len(kwargs):
        raise TypeError(f'Unsupported kwargs {kwargs}')
    if pubsub is None:
        from joulescope_ui import pubsub_singleton
        pubsub = pubsub_singleton
    topic = get_topic_name(obj)
    if has_default:
        return pubsub.query(f'{topic}/instance', default=default)
    else:
        return pubsub.query(f'{topic}/instance')


def _parse_docstr(doc: str, default):
    if doc is None:
        return str(default)
    doc = doc.split('\n\n')[0]
    doc = doc.replace('\n', ' ')
    return doc


def _fn_name_to_topic(s):
    parts = s.split('__')
    parts[-1] = '!' + parts[-1]
    return '/'.join(parts)


def subtopic_to_name(s):
    s = s.replace('/', '__')
    s = s.replace('.', '_')
    return s


class _Function:

    def __init__(self, fn, signature_type=None):
        self.fn = fn
        self.signature_type = signature_type
        if signature_type is None:
            fn = getattr(fn, '__func__', fn)
            code = fn.__code__
            args = code.co_argcount
            if code.co_varnames[0] == 'self':
                args -= 1
            if not 0 <= args <= 3:
                raise ValueError(f'invalid function {fn}')
            self.signature_type = args

    def __call__(self, pubsub, topic: str, value):
        if self.signature_type == 0:
            return self.fn()
        elif self.signature_type == 1:
            return self.fn(value)
        elif self.signature_type == 2:
            return self.fn(topic, value)
        elif self.signature_type == 3:
            return self.fn(pubsub, topic, value)
        else:
            raise RuntimeError('invalid')


class _Topic:

    def __init__(self, parent, topic, meta, value=None):
        """Hold a single MyTopic entry for :class:`PubSub`.

        :param parent: The parent :class:`MyTopic` instance.
        :param topic: The fully-qualified topic string.
        :param meta: The metadata for this topic.
        :param value: The optional initial value.
        """
        self.update_fn = {}   # Mapping[str, list of _Function]
        for stype in _SUBSCRIBER_TYPES:
            self.update_fn[stype] = []
        self.parent = parent
        self.topic_name = topic
        self.subtopic_name = topic.split('/')[-1]
        self._value = None          # for retained values
        self.children = {}      # Mapping[str, _Topic]
        self.meta = meta
        default = None if meta is None else meta.default
        if len(self.subtopic_name) and self.subtopic_name[0] != '!':
            self.value = value if value is not None else default

    def __del__(self):
        for value in self.update_fn.values():
            value.clear()
        self.children.clear()
        self.parent = None
        self._value = None

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
    """A publish-subscribe implementation combined with the command pattern.

    :param app: The application name.  None uses the default.
    """
    def __init__(self, app=None):
        self._app = _APP_DEFAULT if app is None else str(app)
        self._log = logging.getLogger(__name__)
        self._notify_fn = None
        self.notify_fn = None
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
        self._add_cmd(REGISTER_COMPLETION, self._cmd_register_completion)

        self._paths_init()

    def __str__(self):
        return f'PubSub(app={self._app})'

    def __contains__(self, topic):
        return topic in self._topic_by_name

    @property
    def notify_fn(self):
        return self._notify_fn

    @notify_fn.setter
    def notify_fn(self, notify_fn):
        if callable(notify_fn):
            self._notify_fn = notify_fn
        elif notify_fn is None:
            self._notify_fn = lambda: None
        else:
            raise ValueError('Invalid notify_fn')

    def _paths_init(self):
        if 'win32' in sys.platform:
            from win32com.shell import shell, shellcon
            user_path = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
            appdata_path = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
            app_path = os.path.join(appdata_path, self._app)
        elif 'darwin' in sys.platform:
            user_path = os.path.join(os.path.expanduser('~'), 'Documents', self._app)
            app_path = os.path.join(user_path, 'Library', 'Application Support', self._app)
        elif 'linux' in sys.platform:
            user_path = os.path.join(os.path.expanduser('~'), 'Documents', self._app)
            app_path = os.path.join(user_path, '.' + self._app)
        else:
            raise RuntimeError('unsupported platform')

        self.topic_add('common/actions/profile', 'node', 'Profile actions')
        self.topic_add('common/settings/profile', 'node', 'Profile settings')

        self.topic_add('common/settings/paths', 'node', 'Common directory and file paths')
        self.topic_add('common/settings/paths/app', 'str', 'Base application directory', default=app_path)
        self.topic_add('common/settings/paths/config', 'str', 'Config directory', default=os.path.join(app_path, 'config'))
        self.topic_add('common/settings/paths/log', 'str', 'Log directory', default=os.path.join(app_path, 'log'))
        self.topic_add('common/settings/paths/styles', 'str', 'Rendered styles', default=os.path.join(app_path, 'styles'))
        self.topic_add('common/settings/paths/update', 'str', 'Downloads for application updates', default=os.path.join(app_path, 'update'))
        self.topic_add('common/settings/paths/data', 'str', 'Data recordings', default=os.path.join(user_path, self._app))

    def _add_cmd(self, topic, update_fn):
        topic_add_value = {
            'topic': topic,
            'meta': Metadata(dtype='obj', brief=topic, flags=['hide']),
        }
        self._cmd_topic_add(topic_add_value)
        subscribe_value = {
            'topic': topic,
            'update_fn': update_fn,
            'flags': ['command']
        }
        self._cmd_subscribe(subscribe_value)

    def _cmd_undo(self, value):
        for count in range(value):
            if not len(self.undos):
                return
            undo = self.undos.pop()
            self.redos.insert(0, undo)
            for cmd in undo.undos:
                self._process_one(cmd)
        return None

    def _cmd_redo(self, value):
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
        :param exists_ok: True to skip add if already exists.
            False (default) will log the exception on duplicate add.
        :param timeout: If None (default), complete asynchronously.
            If specified, the time in seconds to wait for the completion.
        :return: Completion code if timeout, else None.
        :raise BlockingIOError: If timeout is provided and invoked from the
            Qt event thread.
        """

        timeout = kwargs.pop('timeout', None)
        meta = kwargs.pop('meta', None)
        exists_ok = bool(kwargs.pop('exists_ok', False))

        if meta is not None:
            if len(kwargs):
                raise ValueError('invalid arguments')
            elif isinstance(meta, Metadata):
                pass
            elif isinstance(meta, dict):
                meta = Metadata(**meta)
            elif isinstance(meta, str):
                meta = Metadata(**json.loads(meta))
            else:
                raise ValueError('invalid meta argument')
        elif len(kwargs):
            meta = Metadata(*args, **kwargs)
        elif len(args) == 1:
            x = args[0]
            if isinstance(x, Metadata):
                meta = x
            elif isinstance(x, str):
                meta = Metadata(**json.loads(x))
            else:
                raise ValueError(f'topic {topic}: positional metadata arg must be Metadata or json string')
        else:
            meta = Metadata(*args)
        return self._send(TOPIC_ADD_TOPIC, {'topic': topic, 'meta': meta, 'exists_ok': exists_ok}, timeout)

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

    def query(self, topic, **kwargs):
        """Query the retained value for a topic.

        :param topic: The topic string.
        :param default: If provided, the default value to use when the
            topic does not exist.
        :return: The value for the topic.
        :raises KeyError: If topic does not exist

        Note that this method returns immediately with the existing retained
        value.  It does not account for any changes that are still queued
        awaiting processing.  To get the resulting values of topics that
        may change, you normally want to subscribe.
        """
        try:
            t = self._topic_get(topic)
        except KeyError:
            if 'default' in kwargs:
                return kwargs['default']
            raise
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

        :param update_fn: The function to call on each publish.
            The function can be one of:
            * update_fn(value)
            * update_fn(topic: str, value)
            * update_fn(pubsub: PubSub, topic: str, value)
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

    def _topic_by_name_recursive_remove(self, t: _Topic):
        for subtopic in t.children.values():
            self._topic_by_name_recursive_remove(subtopic)
        self._topic_by_name.pop(t.topic_name)

    def _topic_by_name_recursive_add(self, t: _Topic):
        for subtopic in t.children.values():
            self._topic_by_name_recursive_add(subtopic)
        self._topic_by_name[t.topic_name] = t

    def _cmd_topic_add(self, value):
        topic_name = value['topic']
        exists_ok = value.get('exists_ok', False)
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
        subtopic_name = topic_name_parts[-1]
        if subtopic_name in topic.children:
            if exists_ok:
                return
            raise ValueError(f'topic {topic_name} already exists')
        if 'instance' in value:
            t = value['instance']
            t.parent = topic
            self._topic_by_name_recursive_add(t)
        else:
            t = _Topic(topic, topic_name, value['meta'])
        topic.children[subtopic_name] = t
        self._topic_by_name[topic_name] = t
        return [TOPIC_REMOVE_TOPIC, {'topic': value['topic']}]

    def _cmd_topic_remove(self, value):
        topic = value['topic']
        try:
            t = self._topic_get(topic)
        except KeyError:
            self._log.debug('topic remove %s but already removed', topic)
            return None
        t.parent.children.pop(t.subtopic_name)
        t.parent = None
        self._topic_by_name_recursive_remove(t)
        return [TOPIC_ADD_TOPIC, {'topic': topic, 'instance': t}]

    def _publish_retain(self, t, update_fn):
        if not t.subtopic_name.startswith('!'):
            update_fn(self, t.topic_name, t.value)
        for child in t.children.values():
            self._publish_retain(child, update_fn)

    def _cmd_subscribe(self, value):
        topic = value['topic']
        update_fn = _Function(value['update_fn'])
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

    def _cmd_unsubscribe(self, value):
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
            t.update_fn[flag] = [fn for fn in t.update_fn[flag] if fn.fn != update_fn]
        return [SUBSCRIBE_TOPIC, value]

    def _unsubscribe_all_recurse(self, t, update_fn, undo_list):
        flags = []
        for flag, update_fns in t.update_fn.items():
            updated = [fn for fn in update_fns if fn.fn != update_fn]
            if len(updated) != len(update_fns):
                t.update_fn[flag] = updated
                flags.append(flag)
        if len(flags):
            value = {'topic': t.topic_name, 'update_fn': update_fn, 'flags': flags}
            undo_list.append([SUBSCRIBE_TOPIC, value])
        for subtopic in t.children.values():
            self._unsubscribe_all_recurse(subtopic, update_fn, undo_list)

    def _cmd_unsubscribe_all(self, value):
        update_fn = value['update_fn']
        undo_list = []
        self._unsubscribe_all_recurse(self._root, update_fn, undo_list)
        return undo_list if len(undo_list) else None

    def _cmd_register_completion(self, value):
        completion_fn = value['completion_fn']
        completion_fn()
        return None

    def _publish_value(self, t, flag, topic_name, value):
        while t is not None:
            for fn in t.update_fn[flag]:
                fn(self, topic_name, value)
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
            return None
        if flag == 'pub':
            value = t.meta.validate(value)
            if t.subtopic_name.startswith('!'):
                cmds_update_fn = t.update_fn['command']
                if len(cmds_update_fn):
                    rv = cmds_update_fn[0](self, topic, value)
                    self._undo_capture.cmd_add(topic, value, rv)
            elif t.value == value:
                # self._log.debug('dedup %s: %s == %s', topic_name, t.value, value)
                return None
            else:
                if t.meta is None or 'skip_undo' not in t.meta.flags:
                    # print(f'{topic_name}')
                    self._undo_capture.pub_add(topic_name, t.value, value)
                t.value = value
        self._publish_value(t, flag, topic_name, value)

    def _process(self):
        while len(self._stack):
            cmd = self._stack[-1].pop(0)
            try:
                self._process_one(cmd)
            except Exception:
                self._log.exception('while processing %s', cmd)
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
            t = self._process()
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

    def _registry_add(self, unique_id: str, timeout=None):
        self.publish(REGISTRY_MANAGER_TOPICS.ACTIONS + '/registry/!add', unique_id, timeout=timeout)

    def _registry_remove(self, unique_id: str, timeout=None):
        self.publish(REGISTRY_MANAGER_TOPICS.ACTIONS + '/registry/!remove', unique_id, timeout=timeout)

    def registry_initialize(self):
        t = REGISTRY_MANAGER_TOPICS
        self.topic_add(t.BASE, dtype='node', brief='')
        self.topic_add(t.ACTIONS, dtype='node', brief='')
        self.topic_add(t.ACTIONS + '/capability', dtype='node', brief='')
        self.topic_add(t.CAPABILITY_ADD, dtype='obj', brief='')
        self.topic_add(t.CAPABILITY_REMOVE, dtype='obj', brief='')
        self.topic_add(t.ACTIONS + '/registry', dtype='node', brief='')
        self.topic_add(t.REGISTRY_ADD, dtype='obj', brief='')
        self.topic_add(t.REGISTRY_REMOVE, dtype='obj', brief='')
        self.topic_add(t.CAPABILITIES, dtype='node', brief='')
        self.topic_add(t.NEXT_UNIQUE_ID, dtype='int', brief='', default=1)

    def _on_action_capability_add(self, topic, value):
        parts = topic.split('/')
        topic_str = '/'.join(parts[:-1])
        topic_list_str = topic_str + '/list'
        t_list = self._topic_by_name[topic_list_str]
        v = t_list.value + [value]
        t_list.value = v
        topic_update_str = topic_str + '/!update'
        t_update = self._topic_by_name[topic_update_str]
        self._publish_value(t_update, 'pub', topic_update_str, ['+', value, v])
        self._publish_value(t_list, 'pub', topic_list_str, v)

    def _on_action_capability_remove(self, topic, value):
        parts = topic.split('/')
        topic_str = '/'.join(parts[:-1])
        topic_list_str = topic_str + '/list'
        t_list = self._topic_by_name[topic_list_str]
        v = [x for x in t_list.value if x != value]
        t_list.value = v
        topic_remove_str = topic_str + '/!remove'
        t_remove = self._topic_by_name[topic_remove_str]
        self._publish_value(t_remove, 'pub', topic_remove_str, value)
        topic_update_str = topic_str + '/!update'
        t_update = self._topic_by_name[topic_update_str]
        self._publish_value(t_update, 'pub', topic_update_str, ['-', value, v])
        self._publish_value(t_list, 'pub', topic_list_str, v)

    def register_capability(self, name):
        t = f'{REGISTRY_MANAGER_TOPICS.CAPABILITIES}/{name}'
        self.topic_add(t, dtype='node', brief='')
        self.topic_add(t + '/!update', dtype='obj', brief='The ["+" or "-", unique_id, unique_ids]')
        self.register_command(t + '/!add', self._on_action_capability_add)
        self.register_command(t + '/!remove', self._on_action_capability_remove)
        self.topic_add(t + '/list', dtype='obj',
                       brief='The current list of unique_ids with this capability', default=[])
        self.publish(REGISTRY_MANAGER_TOPICS.CAPABILITY_ADD, name)

    def unregister_capability(self, name):
        t = REGISTRY_MANAGER_TOPICS.CAPABILITIES + '/' + name
        self._cmd_topic_remove({'topic': t})
        self.publish(REGISTRY_MANAGER_TOPICS.CAPABILITY_REMOVE, name)

    def register(self, obj, unique_id: str = None, parent=None):
        """Register a class or instance.

        :param obj: The class type or instance to register.
        :param unique_id: The unique_id to use for this class.
            None (default) determines a suitable unique_id.
            For classes, the class name.
            For instances, a randomly generated value.
        :type unique_id: str, optional
        :param parent: The optional parent unique_id, topic, or object.
        """
        if 'unique_id' in obj.__dict__:  # ignore class attributes for objects
            self._log.info('Duplicate registration for %s', obj)
            if parent is not None:
                self._parent_add(obj, parent)
            return
        if unique_id is None:
            if isinstance(obj, type):
                # Use the unqualified class name
                # This keeps the string short & readable, but names must avoid collisions.
                unique_id = obj.__name__
            else:
                cls_unique_id = getattr(obj.__class__, 'unique_id', obj.__class__.__name__)
                t = self._topic_by_name[REGISTRY_MANAGER_TOPICS.NEXT_UNIQUE_ID]
                v = t.value
                t.value += 1
                unique_id = f'{cls_unique_id}:{v:08x}'
        else:
            unique_id = get_unique_id(unique_id)
        self._log.info('register(obj=%s, unique_id=%s) start', obj, unique_id)
        doc = obj.__doc__
        if doc is None:
            doc = obj.__init__.__doc__
        doc = _parse_docstr(doc, unique_id)
        meta = Metadata(dtype='node', brief=doc)
        topic_name = get_topic_name(unique_id)
        self.topic_add(topic_name, meta=meta, exists_ok=True)
        self.topic_add(f'{topic_name}/instance', dtype='obj', brief='class', default=obj, flags=['ro'], exists_ok=True)
        self.topic_add(f'{topic_name}/actions', dtype='node', brief='actions', exists_ok=True)
        self.topic_add(f'{topic_name}/callbacks', dtype='node', brief='callbacks', exists_ok=True)
        self.topic_add(f'{topic_name}/events', dtype='node', brief='events', exists_ok=True)
        self.topic_add(f'{topic_name}/settings', dtype='node', brief='settings', exists_ok=True)
        if isinstance(obj, type):
            self.topic_add(f'{topic_name}/instances', dtype='obj', brief='instances', default=[], exists_ok=True)
        else:
            cls_unique_id = getattr(obj.__class__, 'unique_id', None)
            if cls_unique_id is not None:
                self.topic_add(f'{topic_name}/instance_of', dtype='str', brief='instance of',
                               default=cls_unique_id, flags=['ro'], exists_ok=True)
                instances_topic = get_topic_name(cls_unique_id) + '/instances'
                instances = self.query(instances_topic)
                if unique_id not in instances:
                    self.publish(instances_topic, instances + [unique_id])
            self.topic_add(f'{topic_name}/parent',
                           dtype='str', brief='unique id for the parent', default='', exists_ok=True)
            self.topic_add(f'{topic_name}/children',
                           dtype='obj', brief='list of unique ids for children', default=[], exists_ok=True)

        self._register_events(obj, unique_id)
        self._register_functions(obj, unique_id)
        self._register_settings(obj, unique_id)
        obj.pubsub = self
        obj.unique_id = unique_id
        obj.topic = topic_name
        if parent is not None:
            self._parent_add(obj, parent)
        self._registry_add(unique_id)
        self._register_invoke_callback(obj, unique_id)
        self._register_capabilities(obj, unique_id)
        self._log.info('register(unique_id=%s) done', unique_id)

    def _parent_add(self, obj, parent=None):
        if parent is None:
            self._parent_remove(obj)
            return
        unique_id = get_unique_id(obj)
        self.publish(f'{get_topic_name(obj)}/parent', get_unique_id(parent))
        children_topic = f'{get_topic_name(parent)}/children'
        children = self.query(children_topic)
        if unique_id not in children:
            self.publish(children_topic, children + [unique_id])

    def _parent_remove(self, obj):
        unique_id = get_unique_id(obj)
        topic = f'{get_topic_name(obj)}/parent'
        parent = self.query(topic, default=None)
        if parent is not None:
            children_topic = f'{get_topic_name(parent)}/children'
            children = self.query(children_topic)
            if unique_id in children:
                children = [x for x in children if x != unique_id]
                self.publish(children_topic, children)
            self.publish(topic, None)

    def _register_events(self, obj, unique_id: str):
        topic_name = get_topic_name(unique_id)
        for event, meta in getattr(obj, 'EVENTS', {}).items():
            self.topic_add(f'{topic_name}/events/{event}', meta, exists_ok=True)

    def _register_functions(self, obj, unique_id: str):
        functions = {}
        topic_name = get_topic_name(unique_id)
        if isinstance(obj, type):
            for name, attr in obj.__dict__.items():
                if isinstance(attr, staticmethod):
                    if name.startswith(CLS_ACTION_PREFIX):
                        fn_name = name[len(CLS_ACTION_PREFIX):]
                        fn_topic = _fn_name_to_topic(fn_name)
                        topic = f'{topic_name}/actions/{fn_topic}'
                        functions[topic] = self.register_command(topic, attr)
                    elif name.startswith(CLS_CALLBACK_PREFIX):
                        fn_name = name[len(CLS_CALLBACK_PREFIX):]
                        fn_topic = _fn_name_to_topic(fn_name)
                        topic = f'{topic_name}/callbacks/{fn_topic}'
                        functions[topic] = self.register_command(topic, attr)
                elif isinstance(attr, classmethod):
                    if name.startswith(CLS_ACTION_PREFIX) or name.startswith(CLS_CALLBACK_PREFIX):
                        raise ValueError(f'class methods not supported: {unique_id} {name}')
        else:
            for name in obj.__class__.__dict__.keys():
                if name.startswith(ACTION_PREFIX):
                    fn_name = name[len(ACTION_PREFIX):]
                    fn_topic = _fn_name_to_topic(fn_name)
                    topic = f'{topic_name}/actions/{fn_topic}'
                    functions[topic] = self.register_command(topic, getattr(obj, name))
                elif name.startswith(CALLBACK_PREFIX):
                    fn_name = name[len(CALLBACK_PREFIX):]
                    fn_topic = _fn_name_to_topic(fn_name)
                    topic = f'{topic_name}/callbacks/{fn_topic}'
                    functions[topic] = self.register_command(topic, getattr(obj, name))
        obj._pubsub_functions = functions

    def _unregister_functions(self, obj, unique_id: str = None):
        for topic, fn in obj._pubsub_functions.items():
            self.unregister_command(topic, fn)
        del obj._pubsub_functions

    def _register_settings(self, obj, unique_id: str):
        topic_base_name = get_topic_name(unique_id)
        settings = getattr(obj, 'SETTINGS', {})
        if not isinstance(obj, type):
            obj._pubsub_setting_to_topic = {}
        for setting_name, setting_meta in settings.items():
            topic_name = f'{topic_base_name}/settings/{setting_name}'
            if topic_name not in self:
                self.topic_add(topic_name, meta=setting_meta)
                if not isinstance(obj, type):
                    # attempt to set instance default value from class
                    cls = getattr(obj, '__class__', None)
                    cls_topic_name = getattr(cls, 'topic', '__invalid_topic_name__')
                    if cls_topic_name in self:
                        self.publish(topic_name, self.query(f'{cls_topic_name}/settings/{setting_name}'))
            if isinstance(obj, type):
                self._setting_cls_connect(obj, topic_name, setting_name)
            else:
                self._setting_connect(obj, topic_name, setting_name)

    def _unregister_settings(self, obj, unique_id):
        topic_name = get_topic_name(unique_id)
        settings = getattr(obj, 'SETTINGS', {})
        for setting_name, setting_meta in settings.items():
            setting_topic_name = f'{topic_name}/settings/{setting_name}'
            if isinstance(obj, type):
                self._setting_cls_disconnect(obj, setting_topic_name, setting_name)
            else:
                self._setting_disconnect(obj, setting_topic_name, setting_name)

    def _setting_cls_connect(self, cls, topic_name, setting_name):
        cls_fn_name = f'on_cls_setting_{setting_name}'
        obj_fn_name = f'on_setting_{setting_name}'
        if hasattr(cls, cls_fn_name):
            fn = getattr(cls, cls_fn_name)
            self.subscribe(topic_name, fn, flags=['pub', 'retain'])
        if hasattr(cls, obj_fn_name):
            return
        else:
            # Monkeypatch class to "magically" connect settings attributes to pubsub
            setting_holder = f'_setting_{setting_name}'
            setting_orig_value = None
            if hasattr(cls, setting_name):
                setting_orig_value = getattr(cls, setting_name)
            setattr(cls, setting_holder, setting_orig_value)

            def getter(instance_self):
                return getattr(instance_self, setting_holder)

            def setter(instance_self, value):
                setattr(instance_self, setting_holder, value)
                m = getattr(instance_self, '_pubsub_setting_to_topic', {})
                t, _ = m.get(setting_name, [None, None])
                if t is not None:
                    self.publish(t, value)

            setattr(cls, setting_name, property(getter, setter))

    def _setting_cls_disconnect(self, cls, topic_name, setting_name):
        cls_fn_name = f'on_cls_setting_{setting_name}'
        obj_fn_name = f'on_setting_{setting_name}'
        if hasattr(cls, cls_fn_name):
            fn = getattr(cls, cls_fn_name)
            self.unsubscribe(topic_name, fn, flags=['pub'])
        if hasattr(cls, obj_fn_name):
            return
        setting_holder = f'_setting_{setting_name}'
        setting_orig_value = getattr(cls, setting_holder)
        setattr(cls, setting_name, setting_orig_value)
        delattr(cls, setting_holder)

    def _setting_connect(self, obj, topic_name, setting_name):
        fn_subname = subtopic_to_name(setting_name)

        def setter(value):
            setattr(obj, f'_setting_{fn_subname}', value)

        fn_name = f'on_setting_{fn_subname}'
        if hasattr(obj, fn_name):
            fn = getattr(obj, fn_name)
        else:
            fn = setter
        obj._pubsub_setting_to_topic[setting_name] = [topic_name, fn]
        self.subscribe(topic_name, fn, flags=['pub', 'retain'])

    def _setting_disconnect(self, obj, topic_name, setting_name):
        topic_name, fn = obj._pubsub_setting_to_topic.pop(setting_name)
        self.unsubscribe(topic_name, fn, flags=['pub'])

    def _register_capabilities(self, obj, unique_id):
        topic_name = get_topic_name(unique_id)
        capabilities = getattr(obj, 'CAPABILITIES', [])
        capabilities = [str(c) for c in capabilities]
        self.topic_add(f'{topic_name}/capabilities', dtype='obj', brief='', default=capabilities, flags=['ro'], exists_ok=True)
        existing_capabilities = self.enumerate(REGISTRY_MANAGER_TOPICS.CAPABILITIES)
        suffix = '.class' if isinstance(obj, type) else '.object'
        for capability in capabilities:
            if capability[-1] == '@':
                capability = capability[:-1] + suffix
            if capability not in existing_capabilities:
                self._log.warning(f'unregistered capability: {capability} in {obj}: SKIP')
                continue
            capability_topic = REGISTRY_MANAGER_TOPICS.CAPABILITIES + f'/{capability}'
            self.publish(f'{capability_topic}/!add', unique_id)

    def _unregister_capabilities(self, obj, unique_id):
        capabilities = getattr(obj, 'CAPABILITIES', [])
        capabilities = [c if not hasattr(c, 'value') else c.value for c in capabilities]
        existing_capabilities = self.enumerate(REGISTRY_MANAGER_TOPICS.CAPABILITIES)
        suffix = '.class' if isinstance(obj, type) else '.object'
        for capability in capabilities:
            if capability[-1] == '@':
                capability = capability[:-1] + suffix
            if capability not in existing_capabilities:
                continue
            capability_topic = REGISTRY_MANAGER_TOPICS.CAPABILITIES + f'/{capability}'
            self.publish(f'{capability_topic}/!remove', unique_id)

    def _invoke_callback(self, obj, method_name):
        method = getattr(obj, method_name, None)
        func = getattr(method, '__func__', None)
        if func is None:
            return
        code = func.__code__
        args = code.co_argcount
        if code.co_varnames[0] == 'self':
            args -= 1
        if args == 0:
            return lambda: method()
        elif args == 1:
            return lambda: method(self)

    def _register_invoke_callback(self, obj, unique_id):
        if isinstance(obj, type):
            method_name = 'on_cls_pubsub_register'
        else:
            method_name = 'on_pubsub_register'
        fn = self._invoke_callback(obj, method_name)
        if callable(fn):
            # post so that it completes after pending default settings process
            return self._send(REGISTER_COMPLETION, {'completion_fn': fn}, 0)

    def _unregister_invoke_callback(self, obj, unique_id):
        if isinstance(obj, type):
            method_name = 'on_cls_pubsub_unregister'
        else:
            method_name = 'on_pubsub_unregister'
        fn = self._invoke_callback(obj, method_name)
        if callable(fn):
            fn()

    def unregister(self, spec, delete=None):
        """Unregister a class or instance.

        :param spec: The class type, instance, topic name or unique id to unregister.
        :param delete: When True, delete all information from the pubsub instance.
            When None (default) or false, then the topic and subtopics are not
            removed.  Future instances registered
            to this unique_id will be configured with the same settings.
        """
        try:
            unique_id = get_unique_id(spec)
            topic_name = get_topic_name(unique_id)
        except ValueError:
            self._log.warning('Could not unregister %s - invalid spec', spec)
            return
        instance_topic_name = f'{topic_name}/instance'
        obj = self.query(instance_topic_name, default=None)
        if obj is None:
            self._log.warning('Could not unregister %s - instance not found', spec)
            return
        self._unregister_capabilities(obj, unique_id)
        self._unregister_invoke_callback(obj, unique_id)
        self._registry_remove(unique_id)
        self._unregister_settings(obj, unique_id)
        self._unregister_functions(obj, unique_id)
        self.topic_remove(instance_topic_name)
        del obj.unique_id
        del obj.topic
        if bool(delete):
            self.topic_remove(topic_name)

    def register_command(self, topic: str, fn: callable):
        """Add a new command topic to the pubsub instance.

        :param topic: The topic string for the command.
        :param fn: The callable for the command.  The callable may have
            any of the following signatures:
            * fn(pubsub, topic, value)
            * fn(topic, value)
            * fn(value)
            * fn()
            The return value determines undo/redo behavior.
            See :meth:`PubSub.subscribe` for details.
        :return: fn, to allow storage for future unsub
        """
        doc_default = topic.split('/')[-1][1:]
        doc = _parse_docstr(fn.__doc__, doc_default)
        self.topic_add(topic, dtype='obj', brief=doc, exists_ok=True)
        self.subscribe(topic, fn, flags=['command'])
        return fn

    def unregister_command(self, topic: str, fn: callable):
        """Remove the registered command handler for a topic.

        :param topic: The topic string for the command.
        :param fn: The callable for the command provided to
            :meth:`register_command`, which is used to validate the removal.
        """
        return self.unsubscribe(topic, fn, flags=['command'])

    def load(self, fh):
        obj = json.load(fh)
        self._root.from_obj(obj)
        self._topic_by_name.clear()
        self._rebuild_topic_by_name(self._root)
