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

"""
Provide centralized application state management include:

* Preferences (topic-value pairs) including:
  * Publish / Subscribe pattern for loose coupling by topic name only.
  * Save and restore.
  * Profiles with application defaults.
* Commands pattern with undo/redo support.
* Hierarchical topic naming and subscriptions.
* API to support automatic preferences widget population.

Alternatives and references include:

* [QSettings](https://doc.qt.io/qt-5/qsettings.html) -
  [PySide](https://doc.qt.io/qtforpython/PySide2/QtCore/QSettings.html)
* [Implementing a preferences dialog window in PyQt](https://stackoverflow.com/questions/39023584/implementing-a-preferences-dialog-window-in-pyqt)
* [PyQtConfig](https://www.mfitzp.com/article/pyqtconfig/)

"""

from PySide2 import QtCore
import logging
import weakref
import threading
from joulescope_ui.preferences import Preferences, BASE_PROFILE, \
    TOPIC_HIDDEN_CHAR, TOPIC_TEMPORARY_CHAR
from joulescope_ui.units import convert_units, FIELD_UNITS_SI


log = logging.getLogger(__name__)
TOPIC_COMMAND_CHAR = '!'


class _ExampleClass:
    def method(self):
        return True


_method_type = type(_ExampleClass().method)
_function_type = type(lambda: True)
_weakref_type = type(weakref.ref(log))


def _is_command(topic):
    return topic[0] == TOPIC_COMMAND_CHAR or topic[-1] == TOPIC_COMMAND_CHAR


def _is_lambda_or_local(fn):
    if isinstance(fn, _weakref_type):
        fn = fn()
    if fn is None:
        return False
    if isinstance(fn, _function_type):
        if '<lambda>' in fn.__qualname__:
            return True
        elif '<locals>' in fn.__qualname__:
            return True
    return False


def _weakref_factory(x):
    if x is None:
        return None
    elif isinstance(x, _weakref_type):
        return x  # not recommended, but allowed
    elif isinstance(x, _method_type):
        return weakref.WeakMethod(x)
    else:
        return weakref.ref(x)


class CommandProcessor(QtCore.QObject):
    """Implement the command pattern and shared application state.

    The "command" pattern (also called "action" or "transaction" pattern)
    allows for all UI actions to funnel through a central location.  This class
    consistent state management and support for undo/redo.  The Joulescope UI
    intentionally does not use the Qt Undo framework, because we can provide
    much greater flexibility in Python.

    This class also integrates with Preferences, which are shared application
    state that can be changed.  For example, the Joulescope's current range
    setting may be controlled by multiple widgets within the UI.  This class
    implements a consistent publish/subscribe model to these Preferences.
    Unlike with Qt's signals and slots, a subscriber can automatically
    register itself without any knowledge of the producer.  See
    `The Many Faces of Publish/Subscribe <http://members.unine.ch/pascal.felber/publications/CS-03.pdf>`_.

    This class uses :meth:`register` for command and :meth:`subscribe` for
    preferences.  This distinction may seem arbitrary, but commands must
    only have a single subscriber that processes the command and returns
    the undo.  The command processor for preferences is handled internally
    to this class, and subscribers simply observe the result.  The return
    value for subscriber calls is ignored.  You can subscribe to commands
    to know that they occurred.
    """

    invokeSignal = QtCore.Signal(str, object)

    def __init__(self, parent=None, synchronous=None, app=None):
        QtCore.QObject.__init__(self, parent)
        self.preferences = Preferences(parent=self, app=app)
        self.restore_success = self.preferences.load()
        starting_profile = self.preferences.get('General/starting_profile', profile='default', default=None)
        if starting_profile == 'app defaults':
            # New instance, do not load!
            self.preferences = Preferences(parent=self, app=app)
            self.preferences.set('General/starting_profile', starting_profile)

        self._topic = {}
        self._subscribers = {}
        self._undos = []  # tuples of (do, undo), do is tuple (command, data), undo is list of tuples (command, data)
        self._redos = []  # tuples of (do, undo), do is tuple (command, data), undo is list of tuples (command, data)
        self._thread_id = None
        self._topic_stack = []
        self._stack_undo = None
        self.register('!undo', self._undo)
        self.register('!redo', self._redo)
        self.register('!command_group/start', self._command_group_start)
        self.register('!command_group/end', self._command_group_end)
        self.register('!preferences/profile/add', self._preferences_profile_add)
        self.register('!preferences/profile/remove', self._preferences_profile_remove)
        self.register('!preferences/profile/set', self._preferences_profile_set)
        self.register('!preferences/save', self._preferences_save)
        self.register('!preferences/load', self._preferences_load)
        self.register('!preferences/restore', self._preferences_restore)
        self.register('!preferences/preference/purge', self._preferences_preference_purge)
        self.register('!preferences/preference/set', self._preferences_preference_set)  # name, value, profile
        self.register('!preferences/preference/clear', self._preferences_preference_clear)  # name, profile

        # Push all commands through the Qt event queue by default
        connect_type = QtCore.Qt.QueuedConnection
        if bool(synchronous):
            connect_type = QtCore.Qt.AutoConnection
        self.invokeSignal.connect(self._on_invoke, type=connect_type)

    def __str__(self):
        return "CommandProcessor: %d commands, %d undos, %d redos" % (
            len(self._topic), len(self._undos), len(self._redos))

    def __getitem__(self, key):
        return self.preferences.get(key)

    def __setitem__(self, key, value):
        self.publish(key, value)

    def __delitem__(self, key):
        self.invoke('!preferences/preference/purge', key)

    def __contains__(self, key):
        return self.preferences.__contains__(key)

    def items(self, prefix=None):
        return self.preferences.items(prefix=prefix)

    @property
    def undos(self):
        """The list of currently available undos."""
        return [do_cmd[0] for do_cmd, _ in self._undos]

    @property
    def redos(self):
        """The list of currently available redos."""
        return [do_cmd[0] for do_cmd, _ in self._redos]

    def _undo(self, topic, data):
        if len(self._undos):
            do_cmd, undo_cmds = self._undos.pop()
            for undo_topic, undo_data in undo_cmds[-1::-1]:
                if _is_command(undo_topic):
                    log.debug('undo_exec %s | %s', undo_topic, undo_data)
                    fn = self._topic[undo_topic]['execute_fn']()
                    if fn is not None:
                        fn(undo_topic, undo_data)
                else:
                    log.debug('undo_pref %s | %s', undo_topic, undo_data)
                    self.preferences[undo_topic] = undo_data
            self._redos.append((do_cmd, undo_cmds))
            self._subscriber_update(undo_topic, undo_data)
            if undo_topic == '!command_group/end':
                while len(self._undos):
                    (redo_topic, _), _ = self._undos[-1]
                    self._undo(None, None)
                    if redo_topic == '!command_group/start':
                        break
        return None

    def _redo(self, topic, data):
        if len(self._redos):
            do_cmd, undo_cmds = self._redos.pop()
            do_topic, do_data = do_cmd
            if _is_command(do_topic):
                log.debug('redo_exec %s | %s', do_topic, do_data)
                fn = self._topic[do_topic]['execute_fn']()
                if fn is not None:
                    fn(do_topic, do_data)
            else:
                self.preferences[do_topic] = do_data
            self._undos.append((do_cmd, undo_cmds))
            self._subscriber_update(do_topic, do_data)
            if do_topic == '!command_group/start':
                while len(self._redos):
                    (redo_topic, _), _ = self._redos[-1]
                    self._redo(None, None)
                    if redo_topic == '!command_group/end':
                        break
        return None

    def _command_group_start(self, topic, data):
        return topic, data

    def _command_group_end(self, topic, data):
        return topic, data

    @QtCore.Slot(str, object)
    def _on_invoke(self, topic, data):
        if self._thread_id is None:
            self._thread_id = threading.get_ident()
        self._topic_stack.append(topic)  # re-entrant!
        try:
            redo_undos = None
            if _is_command(topic):
                log.debug('cmd %s | %s', topic, data)
                if bool(self._topic[topic].get('record_undo', False)) and len(self._topic_stack) == 1:
                    self._stack_undo = []
                execute_fn = self._topic[topic]['execute_fn']()
                if execute_fn is not None:
                    rv = execute_fn(topic, data)
                    if rv is not None and rv[0] is not None:
                        if isinstance(rv[0], str):
                            redo_undos = (topic, data), [rv]
                        else:
                            redo, undos = rv
                            if not isinstance(undos[0][0], str):
                                raise ValueError('invalid return value for topic %s', topic)
                            redo_undos = rv
            else:
                if TOPIC_TEMPORARY_CHAR not in topic:
                    try:
                        data_orig = self.preferences.get(topic)
                        if data == data_orig:
                            return  # ignore, no change necessary
                        if len(self._undos) and self._undos[0][0][0] == topic:
                            # coalesce repeated actions to the same topic
                            _, undos = self._undos.pop()
                            if 1 == len(undos):
                                _, data_orig = undos[0]
                        undos = [(topic, data_orig)]
                    except KeyError:
                        undos = [('!preferences/preference/purge', topic)]
                    log.debug('set %s <= %s', topic, data)
                    redo_undos = (topic, data), undos
                self.preferences[topic] = data
        finally:
            self._topic_stack.pop()

        is_dependent_command = len(self._topic_stack)
        if redo_undos is not None:
            if is_dependent_command:
                if self._stack_undo is not None:
                    self._stack_undo.extend(redo_undos[1])
            else:
                if self._stack_undo is not None and len(self._stack_undo):
                    redo, undos = redo_undos
                    redo_undos = (redo, self._stack_undo + undos)
                self._undos.append(redo_undos)
                self._redos.clear()
        if not is_dependent_command:
            self._stack_undo = None
        self._subscriber_update(topic, data)

    def invoke(self, topic, data=None):
        """Invoke a new command.

        :param topic: The command's topic name.
        :param data: The optional associated data.

        The commands "redo" and "undo" are registered automatically,
        and neither take data.
        """
        if not _is_command(topic):
            raise ValueError('invoke commands only, use publish for preferences')
        self.publish(topic, data)

    def publish(self, topic, data):
        """Publish new data to a topic.

        :param topic: The topic name.
        :param data: The new data for the topic.

        """
        if _is_command(topic):
            if topic not in self._topic:
                raise KeyError(f'unknown command {topic}')
            fn = self._topic[topic]['validate_fn']
            if fn is not None:
                fn = fn()  # dereference weakref
            if fn is not None and callable(fn):
                data = fn(data)
        else:
            data = self.preferences.validate(topic, data)
        if self._thread_id == threading.get_ident() and self._stack_undo is not None:
            self._on_invoke(topic, data)
        else:
            self.invokeSignal.emit(topic, data)

    def subscribe(self, topic, update_fn, update_now=False):
        """Subscribe to a topic.

        :param topic: The topic name.  Topic names that end with "/"
            are wildcards that match all subtopics.
        :param update_fn: The callable(topic, data) that will be called
            whenever topic is published.  The return value is ignored.
            Note that this instance stores a weakref to update_fn so that
            subscribing does not keep the subscriber alive.  Since this
            instance creates and stores weakrefs, the update_fn must remain
            referenced externally.  To prevent unintentionally having
            update_fn go out of scope, creating and passing a lambda or
            local function will raise a ValueError.  Write the caller to
            provide a method or module function.
        :param update_now: When True, call update_fn with the current
            value for all matching topics.  Any commands (topics that
            start with "!") will not match since they do not have
            persistent state.
        """
        if _is_lambda_or_local(update_fn):
            raise ValueError(f'Provided update_fn {update_fn.__qualname__} that may have limited lifetime')
        subscribers = self._subscribers.get(topic, [])
        update_fn = _weakref_factory(update_fn)
        subscribers.append(update_fn)
        self._subscribers[topic] = subscribers
        if bool(update_now):
            if _is_command(topic):
                log.warning('commands do not support update_now')
                return
            elif topic[-1] == '/':
                for t, v in self.preferences.items(prefix=topic):
                    self._subscriber_call(update_fn, t, v)
            else:
                try:
                    value = self.preferences[topic]
                    self._subscriber_call(update_fn, topic, value)
                except KeyError:
                    log.info('subscribed to missing topic %s', topic)

    def unsubscribe(self, topic, update_fn):
        """Unsubscribe from a topic.

        :param topic: The topic name provided to :meth:`subscribe`.
        :param update_fn: The callable provided to :meth:`subscribe`.
        """
        subscribers = self._subscribers.get(topic, [])
        if isinstance(update_fn, _weakref_type):
            update_fn = update_fn()
        if update_fn is not None:
            for subscriber in subscribers:
                if subscriber() == update_fn:
                    subscribers.remove(subscriber)
                    return True
        log.info('unsubscribe not found for %s', topic)
        return False

    def _subscriber_call(self, subscriber, topic, value):
        try:
            fn = subscriber()
            if fn is None:
                return False
            fn(topic, value)
        except:
            log.exception('subscriber error for topic=%s, value=%s', topic, value)
        return True

    def _subscribers_call(self, subscribers, topic, value):
        remove_indices = []
        for idx, subscriber in enumerate(subscribers):
            if not self._subscriber_call(subscriber, topic, value):
                remove_indices.append(idx)
        for idx in remove_indices[-1::-1]:
            log.debug('removing expired subscriber from %s', topic)
            subscribers.pop(idx)

    def _subscriber_update(self, topic, value):
        subscribers = self._subscribers.get(topic, [])
        self._subscribers_call(subscribers, topic, value)
        subscriber_parts = topic.split('/')
        while len(subscriber_parts):
            subscriber_parts[-1] = ''
            n = '/'.join(subscriber_parts)
            subscribers = self._subscribers.get(n, [])
            self._subscribers_call(subscribers, topic, value)
            subscriber_parts.pop()

    def _preferences_bulk_update(self, profile_name=None, flat_old=None):
        if flat_old is None:
            flat_old = self.preferences.flatten()
        if profile_name is not None:
            self.preferences.profile = profile_name
        flat_new = self.preferences.flatten()
        for key, value in flat_new.items():
            if TOPIC_TEMPORARY_CHAR in key:
                continue
            if key not in flat_old or flat_new[key] != flat_old[key]:
                self._subscriber_update(key, value)
        return self

    def _preferences_profile_add(self, topic, data):
        # data is either name, or (name, flatten)
        if isinstance(data, str):
            name = data
            self.preferences.profile_add(data)
        else:
            name = data[0]
            self.preferences.profile_add(data[0])
            for t, v in data[1].items():
                self.preferences[t] = v
        return '!preferences/profile/remove', name

    def _preferences_profile_remove(self, topic, data):
        flat_old = self.preferences.flatten()
        self.preferences.profile_remove(data)
        return'!preferences/profile/add', (data, flat_old)

    def _preferences_profile_set(self, topic, data):
        profile = data
        profile_prev = self.preferences.profile
        if profile_prev == data:
            return
        self._preferences_bulk_update(profile_name=profile)
        return '!preferences/profile/set', profile_prev

    def _preferences_save(self, topic, data):
        self.preferences.save()
        return None

    def _preferences_load(self, topic, data):
        state_old = self.preferences.state_export()
        flat_old = self.preferences.flatten()
        self.preferences.load()
        self._preferences_bulk_update(flat_old=flat_old)
        return '!preferences/restore', state_old

    def _preferences_restore(self, topic, data):
        state_old = self.preferences.state_export()
        flat_old = self.preferences.flatten()
        self.preferences.state_restore(data)
        self._preferences_bulk_update(flat_old=flat_old)
        return '!preferences/restore', state_old

    def _preferences_preference_purge(self, topic, data):
        try:
            value = self.preferences[data]
        except KeyError:
            return None
        self.preferences.purge(data)
        return data, value

    def _preferences_preference_clear(self, topic, data):
        topic, profile = data
        try:
            value_orig = self.preferences.get(topic)
            value_profile = self.preferences.get(topic, profile=profile)
            self.preferences.clear(topic, profile=profile)
            value_new = self.preferences.get(topic)
            if value_orig != value_new:
                self._subscriber_update(topic, value_new)
            return '!preferences/preference/set', (topic, value_orig, profile)
        except KeyError:
            return None

    def _preferences_preference_set(self, topic, data):
        topic, value, profile = data
        value_orig = self.preferences.get(topic, default=None)
        try:
            previous_value = self.preferences.get(topic, profile=profile)
            undo = '!preferences/preference/set', (topic, previous_value, profile)
        except KeyError:
            undo = '!preferences/preference/clear', (topic, profile)
        self.preferences.set(topic, value, profile)
        value_new = self.preferences.get(topic, default=None)
        if value_orig != value_new:
            self._subscriber_update(topic, value_new)
        return undo

    def define(self, topic, brief=None, detail=None, dtype=None, options=None, default=None,
               default_profile_only=None):
        """Define a new preference.

        :param topic: The name for the preference which must be unique.  Preferences
            must not contain a "!", but should use "/" to create hierarchical
            names, such as "widget/marker/color".
        :param brief: The brief user-meaningful description for this preference.
        :param detail: The detailed user-meaningful HTML formatted description
            for this preference.
        :param dtype: The data for this preference, which must be one of
            :data:`joulescope_ui.preferences.DTYPES_DEF`.
        :param options: The options when dtype='str', which can be one of:
            * list of allowed value strings
            * dict containing allowed value strings with entry dicts as containing
              any of [brief, detail, aliases], where aliases is a list of
              alternative allowed value string.
        :param default: The default value for this preference.  Providing a default
            value is high recommended.
        :param default_profile_only: True to force this preference to exist
            in the default profile only.  False or None (default), allow
            this preference to exist in all profiles and override the default
            profile.  If '#' is in the topic string, then default_profile_only
            defaults to True.
        """
        if _is_command(topic):
            raise ValueError(f'Invalid topic name "{topic}" for a preference.')
        return self.preferences.define(topic, brief=brief, detail=detail,
                                       dtype=dtype, options=options, default=default,
                                       default_profile_only=default_profile_only)

    def register(self, topic, execute_fn, validate_fn=None, brief=None, detail=None, record_undo=None):
        """Register a new command topic.

        :param topic: The name for the command topic which must be unique.
            Command topics not associated with a preference must start with "!"
            and use "/" to create a hierarchical names, such as
            "!widget/marker/add".  Topics that do not start with "!" are presumed
             to be associated with a preference topic.
        :param execute_fn: The callable(topic, data) -> (undo_topic, undo_data)
            that executes the command and returns the undo command and undo
            data.  If the callable returns None or (None, object), then no undo
            operation will be registered.  The callable can optionally override
            the original command for future redos or have multiple undo operations
            by returning
            ((redo_topic, redo_data), [(undo1_topic, undo1_data), ...]).
            Note that the list of undos will be performed in reverse order!
        :param validate_fn: The optional callable(data) that validates the data.
            Returns the validate data on success, which may be different from the
              input data.  Throw an exception on failure.
        :param brief: The brief user-meaningful description for this command.
        :param detail: The detailed user-meaningful HTML formatted description
            for this command.
        :param record_undo: True to record all publish and invokes that occur during
            the command for future undo as a single group.  False to simply use
            the execute_fn return value for undo.  None (default) is equivalent to
            False.
        :raises ValueError: If command is not a string of execute_fn is not callable.
        :raises KeyError: If command is already registered.
        """
        if not isinstance(topic, str):
            raise ValueError('commands must be strings')
        if not _is_command(topic):
            raise ValueError(f'topic "{topic}" is not a valid command name')
        if topic in self._topic:
            raise KeyError(f'command already exists: {topic}')
        if not callable(execute_fn):
            raise ValueError('execute_fn is not callable')
        if _is_lambda_or_local(execute_fn):
            raise ValueError(f'Provided execute_fn {execute_fn.__qualname__} that may have limited lifetime')
        if _is_lambda_or_local(validate_fn):
            raise ValueError(f'Provided validate_fn {validate_fn.__qualname__} that may have limited lifetime')

        log.info('register command %s', topic)
        self._topic[topic] = {
            'execute_fn': _weakref_factory(execute_fn),
            'validate_fn': _weakref_factory(validate_fn),
            'brief': brief,
            'detail': detail,
            'record_undo': bool(record_undo)
        }

    def unregister(self, topic):
        """Unregister a command.

        :param topic: The command to unregister.
        """
        if topic not in self._topic:
            log.warning('unregister command %s, but not registered', topic)
            return
        del self._topic[topic]

    def convert_units(self, field, value, units=None):
        """Convert a field value into user-configurable preferred units.

        :param field: The field name, such as 'current'.
        :param value: The float value to convert or the dict of
            {'value': value, 'units': units}.
        :param units: The units for when value is a float.  Ignored
            otherwise.
        :return: dict of {'value': value, 'units': units}.
        """
        if value is None:
            value = 0.0
            if units is None:
                units = FIELD_UNITS_SI.get(field)
        if units is None:
            units = value['units']
            value = value['value']
        output_units = self.preferences.get('Units/' + field, default=units)
        return convert_units(value, units, output_units)
