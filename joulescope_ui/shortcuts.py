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

from joulescope_ui import pubsub_singleton
from PySide6 import QtCore, QtGui


class Shortcuts:

    def __init__(self, parent):
        self._shortcuts = []
        self._parent = parent

    def add(self, key, topic, value=None):
        if isinstance(key, QtCore.Qt.Key):
            key = QtGui.QKeySequence(key)
        shortcut = QtGui.QShortcut(key, self._parent)
        fn = lambda: pubsub_singleton.publish(topic, value)
        shortcut.activated.connect(fn)
        self._shortcuts.append((shortcut, fn))

    def clear(self):
        for shortcut, fn in self._shortcuts:
            shortcut.activated.disconnect(fn)
        self._shortcuts.clear()
        self._parent = None
