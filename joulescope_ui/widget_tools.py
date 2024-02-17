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


from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import pubsub_singleton, N_
import types


class CallableAction(QtGui.QAction):
    """An action that calls a python callable.

    :param parent: The parent for this action.  If parent is a QMenu instance,
        or QActionGroup who has a QMenu instance parent,
        then automatically call parent.addAction(self).
    :param text: The text to display for the action.
    :param fn: The callable that is called with each trigger.
    :param checkable: True to allow checkable.
    :param checked: Set the checked state, if checkable.

    As of Feb 2024, connecting a callable to a signal increments
    the callable's reference count.  Unfortunately, this reference
    count is not decremented when the object is deleted.

    This class provides a Python-side wrapper for a QAction that
    connects to a Python callable.  You can safely provide a lambda
    which will be dereferenced and deleted along with the QAction.

    For a discussion on PySide6 memory management, see
    https://forum.qt.io/topic/154590/pyside6-memory-model-and-qobject-lifetime-management/11
    """

    def __init__(self, parent: QtCore.QObject, text: str, fn: callable, checkable=False, checked=False):
        self._fn = fn
        super().__init__(text, parent=parent)
        if bool(checkable):
            self.setCheckable(True)
            self.setChecked(bool(checked))
        self.triggered.connect(self._on_triggered)
        while isinstance(parent, QtGui.QActionGroup):
            parent = parent.parent()
        if isinstance(parent, QtWidgets.QMenu):
            parent.addAction(self)

    def _on_triggered(self, checked=False):
        code = self._fn.__code__
        args = code.co_argcount
        if args and isinstance(self._fn, types.MethodType):
            args -= 1
        if args == 0:
            self._fn()
        elif args == 1:
            self._fn(checked)


class CallableSlotAdapter(QtCore.QObject):
    """A QObject that calls a python callable whenever its slot is called.

    :param parent: The required parent QObject that manages this
        instance lifecycle through the Qt parent-child relationship.
    :param fn: The Python callable to call.

    Connect the desired signal to self.slot.
    """

    def __init__(self, parent, fn):
        self._fn = fn
        super().__init__(parent)

    def slot(self, *args):
        code = self._fn.__code__
        co_argcount = code.co_argcount
        if args and isinstance(self._fn, types.MethodType):
            args -= 1
        self._fn(*args[:co_argcount])


def settings_action_create(obj, menu):
    def on_action(checked=False):
        pubsub_singleton.publish('registry/settings/actions/!edit', obj)
    return CallableAction(menu, N_('Settings'), on_action)


def context_menu_show(menu: QtWidgets.QMenu, event, parent=None):
    if parent is not None:
        menu.setParent = parent
    menu.aboutToHide.connect(menu.deleteLater)
    menu.popup(event.globalPosition().toPoint())
    return menu
