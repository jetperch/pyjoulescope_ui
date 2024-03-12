# Copyright 2022-2024 Jetperch LLC
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

from joulescope_ui import json_plus as json
from joulescope_ui import versioned_file
from joulescope_ui.pubsub_proxy import PubSubProxy
from joulescope_ui.pubsub_callable import PubSubCallable
from joulescope_ui.metadata import Metadata
import copy
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
CLS_ACTION_PREFIX = 'on_cls_action_'
CLS_CALLBACK_PREFIX = 'on_cls_callback_'
CLS_EVENT_PREFIX = 'on_cls_event_'
CLS_SETTING_PREFIX = 'on_cls_setting_'
ACTION_PREFIX = 'on_action_'
CALLBACK_PREFIX = 'on_callback_'
SETTING_PREFIX = 'on_setting_'
EVENT_PREFIX = 'on_event_'
_PUBSUB_CLS_ATTR = '__pubsub_cls__'
_PUBSUB_OBJ_ATTR = '__pubsub_obj__'


class PUBSUB_TOPICS:  # todo support profiles
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


def _pubsub_attr_name(x):
    return _PUBSUB_CLS_ATTR if isinstance(x, type) else _PUBSUB_OBJ_ATTR


def pubsub_attr(x):
    return getattr(x, _pubsub_attr_name(x))


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
            if n[0] == '!' or n in ['instance']:
                continue
            children.append(child.to_obj())
        return {
            'topic': self.subtopic_name,
            'value': self.value,
            #'meta': self.meta.to_map(),
            'children': children,
        }

    def from_obj(self, obj):
        self._value = obj['value']
        #self.meta = Metadata(**obj['meta'])
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

    def __init__(self, topic, value, is_core=False):
        self.topic = topic
        self.value = value
        self.is_core = bool(is_core)
        self.undo = None  # list of [topic, value] entries
        self.redo = None  # list of [topic, value] entries

    def __str__(self):
        return f'_Command({repr(self.topic)}, {self.value})'

    def __repr__(self):
        return f'_Command({repr(self.topic)}, {repr(self.value)})'


class _Setting:
    """A data descriptor that patches attributes.

    Patching must handle the following scenarios:
    * property (on class)
    * class attribute
    * instance attribute
    * on_setting_{name} function

    This relies upon the class already having the _PUBSUB_CLS_ATTR
    attribute initialized with 'setting_cls' dict.

    This data descriptor intentionally using __init__ rather
    than using __set_name__ to more easily support monkey patching.

    See https://docs.python.org/3/howto/descriptor.html
    """
    def __init__(self, pubsub, cls, name):
        self.pubsub = pubsub
        self.name = name
        self.attr_name = subtopic_to_name(name)
        self.item = None
        self._log = logging.getLogger(f'{__name__}.Setting.{self.attr_name}')
        if hasattr(cls, name):
            self.item = cls.__dict__[name]
        cls.__dict__[_PUBSUB_CLS_ATTR]['setting_cls'][self.name] = self
        setattr(cls, name, self)

    # def __set_name__(self, owner, name):

    def __get__(self, obj, objtype=None):
        if obj is None:
            raise AttributeError(f'{self.name}')
        attr = obj.__class__.__dict__[_PUBSUB_CLS_ATTR]['setting_cls']
        if self.name in attr:
            item = attr[self.name]
            if isinstance(item, property) and item.fget is not None:
                return item.fget(obj)
            elif not self.name in obj.__dict__:
                obj.__dict__[self.attr_name] = item
        return obj.__dict__[self.attr_name]

    def __set__(self, obj, value):
        self._set(obj, value)
        try:
            unique_id = obj.__dict__[_PUBSUB_OBJ_ATTR]['unique_id']
        except KeyError:
            return
        self.pubsub.publish(f'registry/{unique_id}/settings/{self.name}', value)

    def _set(self, obj, value):
        cls = obj.__class__
        if _PUBSUB_CLS_ATTR in cls.__dict__:
            attr = cls.__dict__[_PUBSUB_CLS_ATTR]
            if 'setting_cls' in attr:
                attr = attr['setting_cls']
                if self.name in attr:
                    item = attr[self.name].item
                    if isinstance(item, property) and item.fset is not None:
                        item.fset(obj, value)
        obj.__dict__[self.attr_name] = value

    def on_publish_factory(self, obj):
        def fn(pubsub, topic: str, value):
            return self.on_publish(obj, pubsub, topic, value)
        return fn

    def on_publish(self, obj, pubsub, topic: str, value):
        self._set(obj, value)
        if _PUBSUB_OBJ_ATTR not in obj.__dict__:
            self._log.warning('on_publish but no __pubsub__ attr')
            return
        attr = obj.__dict__[_PUBSUB_OBJ_ATTR]
        if 'setting' not in attr:
            self._log.warning('on_publish but no setting attr')
            return
        attr = attr['setting']
        fn_name = f'{SETTING_PREFIX}{subtopic_to_name(self.name)}'
        if fn_name not in attr:
            fn = getattr(obj, fn_name, None)
            if fn is not None:
                fn = PubSubCallable(fn)
            attr[fn_name] = fn
        fn = attr[fn_name]
        if callable(fn):
            fn(pubsub, topic, value)


class PubSub:
    """A publish-subscribe implementation combined with the command pattern.

    :param app: The application name.  None uses the default.
    :param skip_core_undo: When True, only support undo/redo for top-level
        publish, which best supports registered objects.  This mode
        skip undo/redo for all core operations
        including topic add, topic remove, subscribe, unsubscribe,
        register and unregister.
    """
    def __init__(self, app=None, skip_core_undo=None):
        self._skip_core_undo = bool(skip_core_undo)
        self._process_level = 0
        self._process_count = 0  # for top-level queue
        self._app = _APP_DEFAULT if app is None else str(app)
        self._log = logging.getLogger(__name__)
        self._notify_fn = None
        self.notify_fn = None
        self._thread_id = threading.get_native_id()
        meta = Metadata(dtype='node', brief='root topic')
        self._root = _Topic(None, '', meta)
        self._topic_by_name: dict[str, _Topic] = {'': self._root}
        self._lock = threading.RLock()
        self._queue: list[_Command] = []
        self.undos: list[_Command] = []
        self.redos: list[_Command] = []

        self._add_cmd(SUBSCRIBE_TOPIC, self._cmd_subscribe)                 # subscribe must be first
        self._add_cmd(UNSUBSCRIBE_TOPIC, self._cmd_unsubscribe)
        self._add_cmd(UNSUBSCRIBE_ALL_TOPIC, self._cmd_unsubscribe_all)
        self._add_cmd(TOPIC_ADD_TOPIC, self._cmd_topic_add)
        self._add_cmd(TOPIC_REMOVE_TOPIC, self._cmd_topic_remove)
        self._add_cmd(UNDO_TOPIC, self._cmd_undo)
        self._add_cmd(REDO_TOPIC, self._cmd_redo)

        self.config_filename = None
        self._paths_init()

    def __str__(self):
        return f'PubSub(app={self._app})'

    def __contains__(self, topic):
        return topic in self._topic_by_name

    def __iter__(self):
        thread_id = threading.get_native_id()
        if thread_id != self._thread_id:
            raise RuntimeError('can only iterate on pubsub thread')
        return self._topic_by_name.keys().__iter__()

    @property
    def process_count(self):
        return self._process_count

    @property
    def notify_fn(self):
        """The notification function when a publish is ready to process.

        Systems can use this notification function to resynchronize
        process() calls to a single thread.

        This function is guaranteed to be called within a lock, so only
        one call will be active at a time.
        """
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
            user_path = os.path.join(user_path, self._app)
            appdata_path = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
            app_path = os.path.join(appdata_path, self._app)
        elif 'darwin' in sys.platform:
            user_path = os.path.join(os.path.expanduser('~'), 'Documents', self._app)
            app_path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', self._app)
        elif 'linux' in sys.platform:
            user_path = os.path.join(os.path.expanduser('~'), 'Documents', self._app)
            app_path = os.path.join(os.path.expanduser('~'), '.' + self._app)
        else:
            raise RuntimeError('unsupported platform')

        os.makedirs(user_path, exist_ok=True)
        self.topic_add('common/actions/profile', 'node', 'Profile actions')
        self.topic_add('common/settings/profile', 'node', 'Profile settings')

        self.topic_add('common/settings/paths', 'node', 'Common directory and file paths')
        self.topic_add('common/settings/paths/app', 'str', 'Base application directory', default=app_path)
        self.topic_add('common/settings/paths/config', 'str', 'Config directory', default=os.path.join(app_path, 'config'))
        self.topic_add('common/settings/paths/log', 'str', 'Log directory', default=os.path.join(app_path, 'log'))
        self.topic_add('common/settings/paths/reporter', 'str', 'Reporter directory', default=os.path.join(app_path, 'reporter'))
        self.topic_add('common/settings/paths/styles', 'str', 'Rendered styles', default=os.path.join(app_path, 'styles'))
        self.topic_add('common/settings/paths/update', 'str', 'Downloads for application updates', default=os.path.join(app_path, 'update'))
        self.topic_add('common/settings/paths/data', 'str', 'Data recordings', default=user_path)

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
        if value == 'clear':
            self._log.info('undo clear')
            self.undos.clear()
            return None
        value = 1 if value is None else int(value)
        for count in range(value):
            if not len(self.undos):
                return
            cmd = self.undos.pop()
            self._log.info('undo %s: %s', cmd, cmd.undo)
            self.redos.insert(0, cmd)
            for topic, value in cmd.undo:
                self._process_inner(_Command(topic, value))
        return None

    def _cmd_redo(self, value):
        if value == 'clear':
            self._log.info('redo clear')
            self.redos.clear()
            return None
        value = 1 if value is None else int(value)
        for count in range(value):
            if not len(self.redos):
                return
            cmd = self.redos.pop(0)
            self.undos.append(cmd)
            self._log.info('redo %s: %s', cmd, cmd.redo)
            for topic, value in cmd.redo:
                self._process_inner(_Command(topic, value))
        return None

    def undo(self, count=None):
        self.publish(UNDO_TOPIC, count)

    def redo(self, count=None):
        self.publish(REDO_TOPIC, count)

    def _send(self, cmd: _Command, defer=None):
        thread_id = threading.get_native_id()
        if thread_id == self._thread_id:
            if defer is None:
                return self._process(cmd)
            else:
                with self._lock:
                    if defer == 0:
                        self._queue.insert(0, cmd)
                    else:
                        self._queue.append(cmd)
                    self._notify_fn()
        else:
            with self._lock:
                self._queue.append(cmd)
                self._notify_fn()

    def topic_add(self, topic: str, *args, **kwargs):
        """Define and create a new topic.

        topic_add(topic, meta: Metadata)
        topic_add(topic, meta: json_str)
        topic_add(topic, *args, **kwargs) -> topic_add(topic, Metadata(*args, **kwargs))

        :param topic: The fully-qualified topic name.
        :param args: The metadata either as:
            * Metadata object
            * json-formatted string
            * positional arguments for Metadata constructor.
        :param kwargs: The keyword arguments for the Metadata constructor.
        :param exists_ok: True to skip add if already exists.
            False (default) will log the exception on duplicate add.
        :return: None.
        """
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
        cmd = _Command(TOPIC_ADD_TOPIC, {'topic': topic, 'meta': meta, 'exists_ok': exists_ok}, is_core=True)
        return self._send(cmd)

    def topic_remove(self, topic: str, defer=None):
        """Remove a topic and all subtopics.

        :param topic: The fully-qualified topic name to remove.
        :param defer: Optionally defer the remove, even when called on the
            pubsub thread.
        :return: None.
        """
        cmd = _Command(TOPIC_REMOVE_TOPIC, {'topic': topic}, is_core=True)
        return self._send(cmd, defer=defer)

    def publish(self, topic: str, value, defer=None):
        """Publish a value to a topic.

        :param topic: The topic string.
        :param value: The value, which must pass validation for the topic.
        :param defer: Optionally defer the publish, even when called on the
            pubsub thread.
        :return: None.

        When called from outside the pubsub thread, the publish will be
        queued to the publish thread and performed at a later time.

        You can get this same behavior on the publish thread by
        setting "defer" to True.  This will also add a potential undo/redo
        entry for this publish.

        Publish calls initiating from the pubsub thread are processed
        immediately, but only the top-level publish gets undo/redo support.
        Top-level publish calls must handle their undo state.
        """
        cmd = _Command(topic, value)
        return self._send(cmd, defer=defer)

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
        try:
            t = self._topic_get(topic)
        except KeyError:
            return []
        if bool(traverse):
            lead_count = 0 if bool(absolute) else len(t.topic_name) + 1
            return self._enumerate_recurse(t, lead_count)
        names = t.children.keys()
        if bool(absolute):
            names = [f'{topic}/{n}' for n in names]
        else:
            names = list(names)
        return names

    def subscribe(self, topic: str, update_fn: callable, flags=None):
        """Subscribe to receive topic updates.

        :param self: The driver instance.
        :param topic: Subscribe to this topic string.
        :param update_fn: The function to call on each publish.
            The function can be one of:
            * update_fn(value)
            * update_fn(topic: str, value)
            * update_fn(pubsub: PubSub, topic: str, value)

            For normal subscriptions, the return value is ignored.

            For a command subscriber, a return value of None means that
            no undo / redo support is available.  Otherwise, the return value
            must be [undo, redo].  Both undo and redo should be a [topic, value]
            entry.  "redo" may also be None, and the entry will be the same as the
            publish command.

            The pubsub instance decomposes bound methods.  It stores a weakref
            to the instance so that subscribing does not keep the subscriber
            alive.  If the instance is no longer valid on a publish attempt,
            then the pubsub instance skips that subscription and automatically
            unsubscribes.

            For normal functions and lambdas, this instance will store
            a normal reference.  Any objects in the lambda scope will
            be prevented from being garbage collected by this reference.

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
        :raise RuntimeError: on error.
        """
        if not isinstance(update_fn, PubSubCallable):
            update_fn = PubSubCallable(update_fn, topic)
        value = {
            'topic': topic,
            'update_fn': update_fn,
            'flags': flags
        }
        cmd = _Command(SUBSCRIBE_TOPIC, value, is_core=True)
        self._send(cmd)
        return update_fn

    def unsubscribe(self, topic, update_fn: callable = None, flags=None):
        """Unsubscribe from a topic.

        :param topic: The topic name string.
        :param update_fn: The function previously provided to :func:`subscribe`.
        :param flags: The flags to unsubscribe.  None (default) unsubscribes
            from all.
        :raise: On error.
        """
        if isinstance(topic, PubSubCallable):
            if update_fn is not None:
                self._log.warning('Ignoring update_fn when topic is unsub object')
            topic, update_fn = topic.topic, topic
        value = {
            'topic': topic,
            'update_fn': update_fn,
            'flags': flags
        }
        cmd = _Command(UNSUBSCRIBE_TOPIC, value, is_core=True)
        return self._send(cmd)

    def unsubscribe_all(self, update_fn: callable):
        """Completely unsubscribe a callback from all topics.

        :param update_fn: The function previously provided to :func:`subscribe`.
        :raise: On error.
        """
        value = {'update_fn': update_fn}
        cmd = _Command(UNSUBSCRIBE_ALL_TOPIC, value, is_core=True)
        return self._send(cmd)

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
                # self._log.debug('topic add %s - exists', topic_name)
                return
            raise ValueError(f'topic {topic_name} already exists')
        # self._log.debug('topic add %s', topic_name)
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
            self._log.debug('topic remove %s', topic)
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
        update_fn = value['update_fn']
        if not isinstance(update_fn, PubSubCallable):
            update_fn = PubSubCallable(update_fn)
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
        if not isinstance(update_fn, PubSubCallable):
            update_fn = PubSubCallable(update_fn)
        flags = value['flags']
        if flags is None:
            flags = _SUBSCRIBER_TYPES
        try:
            t = self._topic_get(topic)
        except KeyError:
            self._log.warning('Unsubscribe to unknown topic %s', topic)
            return
        for flag in flags:
            t.update_fn[flag] = [fn for fn in t.update_fn[flag] if fn != update_fn]
        return [SUBSCRIBE_TOPIC, value]

    def _unsubscribe_all_recurse(self, t, update_fn, undo_list):
        flags = []
        for flag, update_fns in t.update_fn.items():
            updated = [fn for fn in update_fns if fn != update_fn]
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
        if not isinstance(update_fn, PubSubCallable):
            update_fn = PubSubCallable(update_fn)
        undo_list = []
        self._unsubscribe_all_recurse(self._root, update_fn, undo_list)
        return undo_list if len(undo_list) else None

    def _publish_value(self, t, flag, topic_name, value):
        while t is not None:
            for fn in t.update_fn[flag]:
                fn(self, topic_name, value)
            t = t.parent

    def _process_inner(self, cmd: _Command):
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
            if t.meta is None:
                self._log.info('Missing metadata for %s', t.topic_name)
            else:
                if t.meta.dtype == 'bool' and value in ['!', '~', '__toggle__']:
                    value = not t.value
                else:
                    value = t.meta.validate(value)

            if t.meta is not None and 'skip_undo' in t.meta.flags:
                capture_undo = False
            elif self._skip_core_undo and cmd.is_core:
                capture_undo = False
            else:
                capture_undo = True

            if t.subtopic_name.startswith('!'):
                cmds_update_fn = t.update_fn['command']
                if len(cmds_update_fn):
                    return_value = cmds_update_fn[0](self, topic, value)
                    if capture_undo and return_value is not None:
                        if isinstance(return_value[0], str):
                            return_value = [[return_value], None]
                        undo, redo = return_value
                        if redo is None:
                            redo = [(cmd.topic, value)]
                        if isinstance(undo[0], str):
                            undo = [undo]
                        if isinstance(redo[0], str):
                            redo = [redo]
                        cmd.undo = undo
                        cmd.redo = redo
            elif t.value == value and t.meta is not None and t.meta.dtype != 'none':
                # self._log.debug('dedup %s: %s == %s', topic_name, t.value, value)
                return None
            else:
                if capture_undo:
                    if len(self.undos) and self.undos[-1].topic == cmd.topic:
                        self.undos[-1].value = value  # coalesce
                    else:
                        cmd.redo = [(cmd.topic, value)]
                        cmd.undo = [(cmd.topic, t.value)]
                t.value = value
        self._publish_value(t, flag, topic_name, value)

    def _process(self, cmd: _Command):
        self._process_level += 1
        try:
            self._process_inner(cmd)
            if self._process_level == 1 and cmd.undo:
                self.undos.append(cmd)
        finally:
            self._process_count += 1
            self._process_level -= 1
            if self._process_level < 0:
                self._log.warning('Invalid process level')
                self._process_level = 0

    def process(self):
        """Process all pending actions."""
        count = 0
        while True:
            with self._lock:
                try:
                    cmd = self._queue.pop(0)
                except IndexError:
                    break
            try:
                self._process(cmd)
            except Exception:
                self._log.exception('process %s', cmd)
            count += 1
        return count

    def _rebuild_topic_by_name(self, t):
        self._topic_by_name[t.topic_name] = t
        for child in t.children.values():
            self._rebuild_topic_by_name(child)

    def _registry_add(self, unique_id: str):
        self.publish(REGISTRY_MANAGER_TOPICS.ACTIONS + '/registry/!add', unique_id)

    def _registry_remove(self, unique_id: str):
        self.publish(REGISTRY_MANAGER_TOPICS.ACTIONS + '/registry/!remove', unique_id)

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
        self.topic_add('registry', dtype='node', brief='')

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
        return None

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
        return None

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

    def _reg_topic(self, topic, meta):
        self._cmd_topic_add({'topic': topic, 'meta': meta, 'exists_ok': True})

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
        pubsub_attr = _pubsub_attr_name(obj)
        if pubsub_attr in obj.__dict__ and len(obj.__dict__[pubsub_attr]):
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
        setattr(obj, pubsub_attr, {
            'is_registered': False,
            'unique_id': unique_id,
            'topic_name': get_topic_name(unique_id),
            'functions': {},    # topic: callable
            'setting_cls': {},  # topic: object, for existing class attribute
            'setting': {},
        })
        if not isinstance(obj, type):
            cls = obj.__class__
            if _PUBSUB_CLS_ATTR not in cls.__dict__ or not len(cls.__dict__[_PUBSUB_CLS_ATTR]):
                self.register(cls, cls.__name__ + '.class')
        self._log.info('register(unique_id=%s, obj=%s) start', unique_id, obj)
        doc = obj.__doc__
        if doc is None:
            doc = obj.__init__.__doc__
        doc = _parse_docstr(doc, unique_id)
        meta = Metadata(dtype='node', brief=doc)
        topic_name = get_topic_name(unique_id)
        self._reg_topic(topic_name, meta)
        self._reg_topic(f'{topic_name}/instance', Metadata(dtype='obj', brief='class', flags=['ro']))
        self._topic_by_name[f'{topic_name}/instance'].value = obj
        self._reg_topic(f'{topic_name}/actions', Metadata(dtype='node', brief='actions'))
        self._reg_topic(f'{topic_name}/callbacks', Metadata(dtype='node', brief='callbacks'))
        self._reg_topic(f'{topic_name}/events', Metadata(dtype='node', brief='events'))
        self._reg_topic(f'{topic_name}/settings', Metadata(dtype='node', brief='settings'))
        if isinstance(obj, type):
            self._reg_topic(f'{topic_name}/instances',
                            Metadata(dtype='obj', brief='instances', default=[],
                                     flags=['hide', 'skip_undo']))
        else:
            cls_unique_id = getattr(obj.__class__, 'unique_id', None)
            if cls_unique_id is not None:
                self._reg_topic(f'{topic_name}/instance_of',
                                Metadata(dtype='str', brief='instance of', default=cls_unique_id,
                                         flags=['hide', 'ro', 'skip_undo']))
                instances_topic = get_topic_name(cls_unique_id) + '/instances'
                instances = self.query(instances_topic)
                if unique_id not in instances:
                    self.publish(instances_topic, instances + [unique_id])
            self._reg_topic(f'{topic_name}/parent',
                            Metadata(dtype='str', brief='unique id for the parent', default='',
                                     flags=['hide', 'skip_undo']))
            self._reg_topic(f'{topic_name}/children',
                            Metadata(dtype='obj', brief='list of unique ids for children', default=[],
                                     flags=['hide', 'skip_undo']))

        self._register_events(obj, unique_id)
        self._register_functions(obj, unique_id)  # on_action and on_callback, but not on_setting
        self._register_settings_create(obj, unique_id)
        obj.pubsub = PubSubProxy(self)
        obj.unique_id = unique_id
        obj.topic = topic_name
        self._register_settings_connect(obj, unique_id)
        if parent is not None:
            self._parent_add(obj, parent)
        try:
            register_abort = False
            self._register_invoke_callback(obj, unique_id)
        except Exception:
            register_abort = True
            self._log.exception('register(unique_id=%s) callback failed', unique_id)
        self._register_capabilities(obj, unique_id)
        self._log.info('register(unique_id=%s) done %s', unique_id, 'ABORT' if register_abort else '')
        if register_abort:
            self.unregister(obj, delete=True)
        else:
            getattr(obj, pubsub_attr)['is_registered'] = True
            self._registry_add(unique_id)

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
        if parent not in [None, '']:
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
        pubsub_attr = _pubsub_attr_name(obj)
        functions = obj.__dict__[pubsub_attr]['functions']
        topic_name = get_topic_name(unique_id)
        if isinstance(obj, type):
            while obj != object:
                for name, attr in obj.__dict__.items():
                    if isinstance(attr, staticmethod):
                        if name.startswith(CLS_ACTION_PREFIX):
                            fn_name = name[len(CLS_ACTION_PREFIX):]
                            fn_topic = _fn_name_to_topic(fn_name)
                            topic = f'{topic_name}/actions/{fn_topic}'
                            if topic not in functions:
                                functions[topic] = self.register_command(topic, attr)
                        elif name.startswith(CLS_CALLBACK_PREFIX):
                            fn_name = name[len(CLS_CALLBACK_PREFIX):]
                            fn_topic = _fn_name_to_topic(fn_name)
                            topic = f'{topic_name}/callbacks/{fn_topic}'
                            if topic not in functions:
                                functions[topic] = self.register_command(topic, attr)
                    elif isinstance(attr, classmethod):
                        if name.startswith(CLS_ACTION_PREFIX) or name.startswith(CLS_CALLBACK_PREFIX):
                            raise ValueError(f'class methods not supported: {unique_id} {name}')
                obj = obj.__base__
        else:
            cls = obj.__class__
            while cls != object:
                for name in cls.__dict__.keys():
                    if name.startswith(ACTION_PREFIX):
                        fn_name = name[len(ACTION_PREFIX):]
                        fn_topic = _fn_name_to_topic(fn_name)
                        topic = f'{topic_name}/actions/{fn_topic}'
                        if topic not in functions:
                            functions[topic] = self.register_command(topic, getattr(obj, name))
                    elif name.startswith(CALLBACK_PREFIX):
                        fn_name = name[len(CALLBACK_PREFIX):]
                        fn_topic = _fn_name_to_topic(fn_name)
                        topic = f'{topic_name}/callbacks/{fn_topic}'
                        if topic not in functions:
                            functions[topic] = self.register_command(topic, getattr(obj, name))
                cls = cls.__base__

    def _unregister_functions(self, obj, unique_id: str = None):
        functions = obj.__dict__[_pubsub_attr_name(obj)].pop('functions')
        settings_topic = f'{obj.topic}/settings/'
        while len(functions):
            topic, fn = functions.popitem()
            if topic.startswith(settings_topic):
                self.unsubscribe(topic, fn, flags=['pub'])
            else:
                self.unsubscribe(topic, fn, flags=['command'])

    def _register_settings_create(self, obj, unique_id: str):
        topic_base_name = get_topic_name(unique_id)
        settings = getattr(obj, 'SETTINGS', {})
        if not isinstance(obj, type):
            obj._pubsub_setting_to_topic = {}
        for setting_name, meta in settings.items():
            topic_name = f'{topic_base_name}/settings/{setting_name}'
            if topic_name not in self:
                meta = Metadata(meta)
                if not isinstance(obj, type) and 'noinit' not in meta.flags:
                    # attempt to set instance default value from class
                    cls_unique_id = obj.__class__.__dict__[_PUBSUB_CLS_ATTR]['unique_id']
                    cls_topic = get_topic_name(cls_unique_id)
                    if cls_topic in self:
                        try:
                            meta.default = self.query(f'{cls_topic}/settings/{setting_name}')
                        except KeyError:
                            pass  # use meta default
                self.topic_add(topic_name, meta=meta)
            elif not isinstance(obj, type):
                topic = self._topic_by_name[topic_name]
                if topic.meta is None:
                    topic.meta = Metadata(meta)

    def _register_settings_connect(self, obj, unique_id: str):
        topic_base_name = get_topic_name(unique_id)
        settings = getattr(obj, 'SETTINGS', {})
        for setting_name, meta in settings.items():
            topic_name = f'{topic_base_name}/settings/{setting_name}'
            if isinstance(obj, type):
                self._setting_cls_connect(obj, topic_name, setting_name)
            else:
                self._setting_connect(obj, topic_name, setting_name)

    def _setting_cls_connect(self, cls, topic_name, setting_name):
        functions = cls.__dict__[_PUBSUB_CLS_ATTR]['functions']
        cls_fn_name = f'{CLS_SETTING_PREFIX}{subtopic_to_name(setting_name)}'
        if hasattr(cls, cls_fn_name):
            fn = getattr(cls, cls_fn_name)
            self.subscribe(topic_name, fn, flags=['pub', 'retain'])
            functions[topic_name] = fn

    def _setting_connect(self, obj, topic_name, setting_name):
        functions = obj.__dict__[_PUBSUB_OBJ_ATTR]['functions']
        cls = obj.__class__
        cls_attr = cls.__dict__[_PUBSUB_CLS_ATTR]
        if setting_name not in cls_attr['setting_cls']:
            _Setting(self, cls, setting_name)
        setting = cls_attr['setting_cls'][setting_name]
        fn = setting.on_publish_factory(obj)
        self.subscribe(topic_name, fn, flags=['pub', 'retain'])
        functions[topic_name] = fn

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
        if args and code.co_varnames[0] == 'self':
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
            return fn()

    def _unregister_invoke_callback(self, obj, unique_id):
        if isinstance(obj, type):
            method_name = 'on_cls_pubsub_unregister'
        else:
            method_name = 'on_pubsub_unregister'
        fn = self._invoke_callback(obj, method_name)
        if callable(fn):
            fn()

    def _delete_invoke_callback(self, obj):
        if isinstance(obj, type):
            method_name = 'on_cls_pubsub_delete'
        else:
            method_name = 'on_pubsub_delete'
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
        obj.pubsub.unsubscribe_all()
        self._unregister_capabilities(obj, unique_id)
        self._unregister_invoke_callback(obj, unique_id)
        if bool(delete):
            self._parent_remove(unique_id)
            self._delete_invoke_callback(obj)
        # settings unsubscribe handled by _unregister_functions
        self._unregister_functions(obj, unique_id)
        self._cmd_topic_remove({'topic': instance_topic_name})  # skip undo, do not want instance in undo list
        if isinstance(obj, type):
            self._unregister_class_settings(obj)
        delattr(obj, _pubsub_attr_name(obj))
        del obj.unique_id
        del obj.topic
        del obj.pubsub
        if bool(delete):
            self._unregister_delete(obj, unique_id)
        self._registry_remove(unique_id)

    def _unregister_class_settings(self, cls):
        attr = cls.__dict__[_PUBSUB_CLS_ATTR]
        for setting, v in attr['setting_cls'].items():
            if v.item is not None:
                setattr(cls, setting, v.item)

    def capabilities_append(self, spec, capabilities):
        """Dynamically add new capabilities to a registered instance.

        :param spec: The target instance, topic name or unique id.
        :param capabilities: The list of capabilities to add.
        """
        obj = get_instance(spec)
        unique_id = get_unique_id(obj)
        obj_caps = getattr(obj, 'CAPABILITIES', [])
        capabilities = [str(c) for c in capabilities]
        existing_capabilities = self.enumerate(REGISTRY_MANAGER_TOPICS.CAPABILITIES)
        for capability in capabilities:
            if capability in obj_caps:
                continue
            if capability not in existing_capabilities:
                self._log.warning(f'unregistered capability: {capability} in {obj}: SKIP')
                continue
            capability_topic = REGISTRY_MANAGER_TOPICS.CAPABILITIES + f'/{capability}'
            self.publish(f'{capability_topic}/!add', unique_id)
            obj_caps.append(capability)
        setattr(obj, 'CAPABILITIES', copy.deepcopy(obj_caps))

    def capabilities_remove(self, spec, capabilities):
        """Dynamically remove capabilities from a registered instance.

        :param spec: The target instance, topic name or unique id.
        :param capabilities: The list of capabilities to remove.
        """
        obj = get_instance(spec)
        unique_id = get_unique_id(obj)
        obj_caps = getattr(obj, 'CAPABILITIES', [])
        capabilities = [str(c) for c in capabilities]
        for capability in capabilities:
            if capability not in obj_caps:
                continue
            capability_topic = REGISTRY_MANAGER_TOPICS.CAPABILITIES + f'/{capability}'
            self.publish(f'{capability_topic}/!remove', unique_id)
            obj_caps.remove(capability)
        setattr(obj, 'CAPABILITIES', copy.deepcopy(obj_caps))

    def _unregister_delete(self, obj, unique_id):
        if not isinstance(obj, type):
            instance_of = self.query(f'{get_topic_name(unique_id)}/instance_of')
            cls_instance = get_instance(instance_of, default=None)
            if cls_instance:
                instances_topic = f'{get_topic_name(cls_instance)}/instances'
                instances = self.query(instances_topic)
                if unique_id in instances:
                    instances = [k for k in instances if k != unique_id]
                    self.publish(instances_topic, instances)
        self.topic_remove(get_topic_name(unique_id))

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

    def _to_obj(self, topic: str):
        t: _Topic = self._topic_by_name[topic]
        result = {
            'value': t.value
        }
        if len(t.children):
            c = {}
            result['children'] = c
            for n, child in t.children.items():
                if n[0] == '!' or n in ['instance', 'actions', 'callbacks', 'events']:
                    continue
                if child.meta is not None and 'tmp' in child.meta.flags:
                    continue
                key, value = self._to_obj(child.topic_name)
                c[key] = value
        return t.subtopic_name, result

    @property
    def config_file_path(self):
        fname = 'joulescope_ui_config.json'
        if self.config_filename is not None:
            fname = self.config_filename
        config_path = self.query('common/settings/paths/config')
        return os.path.join(config_path, fname)

    def save(self, fh=None):
        if fh is None:
            fh = self.config_file_path

        self._log.info('save %r', fh)
        do_close = False
        obj = {
            'type': 'joulescope_ui_config',
            'version': 1,
            'common/settings': self._to_obj('common/settings')[1],
            'registry': self._to_obj('registry')[1],
            REGISTRY_MANAGER_TOPICS.NEXT_UNIQUE_ID: self._topic_get(REGISTRY_MANAGER_TOPICS.NEXT_UNIQUE_ID).value,
        }
        if isinstance(fh, str):
            os.makedirs(os.path.dirname(fh), exist_ok=True)
            fh = versioned_file.open(fh, 'wt')
            do_close = True
        try:
            json.dump(obj, fh)
        finally:
            if do_close:
                fh.close()

    def _from_obj(self, topic: str, obj):
        t: _Topic = self._topic_by_name[topic]
        t.value = obj['value']
        for ckey, cval in obj.get('children', {}).items():
            child_topic = f'{topic}/{ckey}'
            if child_topic not in self._topic_by_name:
                c_t = _Topic(t, child_topic, None)
                t.children[ckey] = c_t
                self._topic_by_name[child_topic] = c_t
            self._from_obj(child_topic, cval)

    def _update_meta_inner(self, src, dst):
        # self._log.debug('%s <= %s', dst.topic_name, src.topic_name')
        if src.meta is not None:
            dst.meta = Metadata(src.meta)
        for key, value in src.children.items():
            if key in dst.children:
                self._update_meta_inner(value, dst.children[key])

    def _update_meta(self, topic_cls, topic_obj):
        t_cls = self._topic_by_name[topic_cls]
        t_obj = self._topic_by_name[topic_obj]
        src = t_cls.children['settings']
        dst = t_obj.children['settings']
        self._update_meta_inner(src, dst)

    def load(self, fh=None):
        if fh is None:
            if not os.path.isfile(self.config_file_path):
                return False
            return self.load(self.config_file_path)

        do_close = False
        if isinstance(fh, str):
            self._log.info('load %s', fh)
            fh = versioned_file.open(fh, 'rt')
            do_close = True
        else:
            self._log.info('load filehandle')
        try:
            obj = json.load(fh)
        finally:
            if do_close:
                fh.close()
        file_type = obj.get('type')
        file_version = obj.get('version')
        if file_type != 'joulescope_ui_config':
            self._log.warning('load type mismatch: %s != joulescope_ui_config', file_type)
            return False
        elif file_version != 1:
            self._log.warning('load version mismatch: %s != %s', file_version, 1)
            return False
        if REGISTRY_MANAGER_TOPICS.NEXT_UNIQUE_ID in obj:
            self._topic_get(REGISTRY_MANAGER_TOPICS.NEXT_UNIQUE_ID).value = obj[REGISTRY_MANAGER_TOPICS.NEXT_UNIQUE_ID]
        self._from_obj('common/settings', obj['common/settings'])
        self._from_obj('registry', obj['registry'])
        t = self._topic_by_name['registry']
        keys_to_remove = []
        for key, value in t.children.items():
            if 'instance_of' in value.children:
                instance_of = value.children['instance_of'].value
                if value is None:
                    continue
                try:
                    self._update_meta(f'registry/{instance_of}', value.topic_name)
                except:
                    self._log.warning('Could not instantiate %s, removing', key)
                    keys_to_remove.append(key)
        for key in keys_to_remove:
            self.topic_remove(f'registry/{key}')
        return True

    def config_clear(self):
        if os.path.isfile(self.config_file_path):
            with versioned_file.open(self.config_file_path, 'wt') as fh:
                fh.write('')
            os.remove(self.config_file_path)


def is_pubsub_registered(obj):
    """Query if the object is registered to a pubsub instance.

    :param obj: The instance, string unique_id, or string topic.
    :return: True if registered, False otherwise.
    """
    try:
        if isinstance(obj, str):
            obj = get_instance(obj)
        return getattr(obj, _pubsub_attr_name(obj))['is_registered']
    except Exception:
        return False
