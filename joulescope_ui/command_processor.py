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
Implement the "Command" pattern for the Joulescope UI.

The "command" pattern (also called "action" or "transaction" pattern) allows
for all UI actions to funnel through a central location.  This allows
consistent state management and support for undo/redo.

The Joulescope UI intentionally does not use the Qt Undo framework, because
we can provide much greater flexibility in Python.
"""

from PySide2 import QtCore
import logging


log = logging.getLogger(__name__)


class CommandProcessor(QtCore.QObject):
    invokeSignal = QtCore.Signal(str, object)

    def __init__(self, parent=None, synchronous=None):
        QtCore.QObject.__init__(self, parent)
        self._commands = {}
        self._undos = []  # tuples of (do, undo), each tuples (command, data)
        self._redos = []  # tuples of (do, undo), each tuples (command, data)
        self.register('undo', self._undo)
        self.register('redo', self._redo)
        connect_type = QtCore.Qt.QueuedConnection
        if bool(synchronous):
            connect_type = QtCore.Qt.AutoConnection
        self.invokeSignal.connect(self._on_invoke, type=connect_type)

    def __str__(self):
        return "CommandProcessor: %d commands, %d undos, %d redos" % (
            len(self._commands), len(self._undos), len(self._redos))

    @property
    def undos(self):
        return [do_cmd[0] for do_cmd, _ in self._undos]

    @property
    def redos(self):
        return [do_cmd[0] for do_cmd, _ in self._redos]

    def _undo(self, command, data):
        if len(self._undos):
            do_cmd, undo_cmd = self._undos.pop()
            undo_command, undo_data = undo_cmd
            self._commands[undo_command](undo_command, undo_data)
            self._redos.append((do_cmd, undo_cmd))
        return None

    def _redo(self, command, data):
        if len(self._redos):
            do_cmd, undo_cmd = self._redos.pop()
            do_command, do_data = do_cmd
            self._commands[do_command](do_command, do_data)
            self._undos.append((do_cmd, undo_cmd))
        return None

    @QtCore.Slot(str, object)
    def _on_invoke(self, command, data):
        rv = self._commands[command](command, data)
        if rv is None or rv[0] is None:
            return
        self._undos.append(((command, data), rv))

    def invoke(self, command, data=None):
        """Invoke a new command.

        :param command: The command name.
        :param data: The optional associated data.

        The commands "redo" and "undo" are registered automatically,
        and neither take data.
        """
        if command not in self._commands:
            raise KeyError(f'unknown command {command}')
        self.invokeSignal.emit(command, data)

    def register(self, command, execute_fn):
        """Register a new command.

        :param command: The name for the command which must be unique.
            The convention is to use "/" to create a hierarchical
            name, such as ui/oscilloscope/waveform/grid_x.
        :param execute_fn: The callable(command, data) -> (command, data) that executes
            the command and returns the undo command and data.  If the callable returns
            None or (None, object), then no undo operation will be registered.
        :raises ValueError: If command is not a string of execute_fn is not callable.
        :raises KeyError: If command is already registered.
        """
        if not isinstance(command, str):
            raise ValueError('commands must be strings')
        if command in self._commands:
            raise KeyError(f'command already exists: {command}')
        if not callable(execute_fn):
            raise ValueError('execute_fn is not callable')
        log.info('register command %s', command)
        self._commands[command] = execute_fn

    def unregister(self, command):
        """Unregister a command.

        :param command: The command to unregister.
        """
        if command not in self._commands:
            log.warning('unregister command %s, but not registered', command)
            return
        del self._commands[command]

