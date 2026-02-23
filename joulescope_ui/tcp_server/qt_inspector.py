# Copyright 2026 Jetperch LLC
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

"""Qt widget inspector for test automation.

Provides widget tree traversal, property inspection, synthetic event
injection, and screenshot capture.  All Qt operations are dispatched
to the main thread via PubSub.
"""

import concurrent.futures
import logging

from PySide6 import QtCore, QtGui, QtWidgets

from joulescope_ui.tcp_server.protocol import (
    MSG_QT_INSPECT, MSG_QT_INSPECT_RESPONSE,
    MSG_QT_ACTION, MSG_QT_SCREENSHOT, MSG_QT_SCREENSHOT_RESPONSE,
    MSG_ERROR,
)

_log = logging.getLogger(__name__)

# Property types that can be safely serialized to JSON
_SERIALIZABLE_TYPES = (bool, int, float, str, type(None))


def _safe_property_value(value):
    """Convert a QObject property value to a JSON-safe type."""
    if isinstance(value, _SERIALIZABLE_TYPES):
        return value
    if isinstance(value, (QtCore.QSize, QtCore.QSizeF)):
        return [value.width(), value.height()]
    if isinstance(value, (QtCore.QPoint, QtCore.QPointF)):
        return [value.x(), value.y()]
    if isinstance(value, (QtCore.QRect, QtCore.QRectF)):
        return [value.x(), value.y(), value.width(), value.height()]
    if isinstance(value, QtGui.QColor):
        return value.name(QtGui.QColor.HexArgb)
    if isinstance(value, QtCore.QUrl):
        return value.toString()
    return str(value)


def _widget_info(widget, depth=0, max_depth=50):
    """Recursively build a widget tree dict.

    :param widget: The root QObject.
    :param depth: Current recursion depth.
    :param max_depth: Maximum tree depth.
    :return: dict describing the widget and its children.
    """
    info = {
        'class': type(widget).__name__,
        'objectName': widget.objectName(),
        'visible': widget.isVisible() if isinstance(widget, QtWidgets.QWidget) else True,
        'enabled': widget.isEnabled() if isinstance(widget, QtWidgets.QWidget) else True,
    }
    if isinstance(widget, QtWidgets.QWidget):
        geo = widget.geometry()
        info['geometry'] = [geo.x(), geo.y(), geo.width(), geo.height()]

    # Gather properties
    props = {}
    meta = widget.metaObject()
    for i in range(meta.propertyCount()):
        prop = meta.property(i)
        name = prop.name()
        try:
            val = widget.property(name)
            val = _safe_property_value(val)
            if isinstance(val, _SERIALIZABLE_TYPES):
                props[name] = val
        except Exception:
            pass
    if props:
        info['properties'] = props

    # Recurse children
    if depth < max_depth:
        children = []
        for child in widget.children():
            if isinstance(child, QtWidgets.QWidget):
                children.append(_widget_info(child, depth + 1, max_depth))
        if children:
            info['children'] = children

    return info


def _find_widget(root, path):
    """Find a widget by path.

    Path syntax: ``objectName/objectName/ClassName:index``

    Each segment matches by objectName first.  If no match, tries
    ``ClassName:index`` where index is 0-based among same-class siblings.

    :param root: The root widget to search from.
    :param path: Forward-slash-separated widget path.
    :return: The matched QWidget.
    :raises ValueError: If the widget is not found.
    """
    if not path:
        return root
    parts = path.split('/')
    current = root
    for part in parts:
        found = None
        # Try objectName match first
        for child in current.children():
            if isinstance(child, QtWidgets.QWidget) and child.objectName() == part:
                found = child
                break
        # Try ClassName:index
        if found is None and ':' in part:
            class_name, idx_str = part.rsplit(':', 1)
            try:
                idx = int(idx_str)
            except ValueError:
                raise ValueError(f'Invalid path segment: {part}')
            count = 0
            for child in current.children():
                if isinstance(child, QtWidgets.QWidget) and type(child).__name__ == class_name:
                    if count == idx:
                        found = child
                        break
                    count += 1
        if found is None:
            raise ValueError(f'Widget not found at path segment: {part}')
        current = found
    return current


class QtInspector:
    """Handles Qt inspection requests.

    :param pubsub: The PubSub singleton, used to dispatch work to the Qt thread.
    """

    TOPIC = 'common/actions/!qt_inspect'

    def __init__(self, pubsub):
        self._pubsub = pubsub
        self._registered = False

    def _ensure_registered(self):
        if not self._registered:
            try:
                self._pubsub.topic_add(self.TOPIC, dtype='obj', brief='Qt inspection command', exists_ok=True)
                self._pubsub.subscribe(self.TOPIC, self._on_command, ['command'])
            except Exception:
                self._pubsub.subscribe(self.TOPIC, self._on_command, ['pub'])
            self._registered = True

    def dispatch(self, msg_type, header, payload, future):
        """Dispatch a Qt inspection request to the Qt main thread.

        :param msg_type: The message type (MSG_QT_INSPECT, MSG_QT_ACTION, MSG_QT_SCREENSHOT).
        :param header: The decoded message header dict.
        :param payload: The binary payload (unused for most Qt commands).
        :param future: A concurrent.futures.Future to set with the result tuple
            (response_msg_type, response_header, response_payload).
        """
        self._ensure_registered()
        request = {
            'msg_type': msg_type,
            'header': header,
            'payload': payload,
            'future': future,
        }
        self._pubsub.publish(self.TOPIC, request)

    def _on_command(self, topic, value):
        """Handle Qt inspection on the Qt/PubSub thread."""
        future = value.get('future')
        if future is None:
            return
        try:
            msg_type = value['msg_type']
            header = value['header']
            payload = value.get('payload', b'')

            if msg_type == MSG_QT_INSPECT:
                result = self._inspect(header)
                future.set_result((MSG_QT_INSPECT_RESPONSE, result, None))
            elif msg_type == MSG_QT_ACTION:
                result = self._action(header)
                future.set_result((MSG_QT_INSPECT_RESPONSE, result, None))
            elif msg_type == MSG_QT_SCREENSHOT:
                result_header, result_payload = self._screenshot(header)
                future.set_result((MSG_QT_SCREENSHOT_RESPONSE, result_header, result_payload))
            else:
                future.set_result((MSG_ERROR, {'message': f'Unknown Qt message type: {msg_type}'}, None))
        except Exception as ex:
            _log.exception('Qt inspection error')
            future.set_result((MSG_ERROR, {'message': str(ex)}, None))

    def _get_root(self):
        app = QtWidgets.QApplication.instance()
        if app is None:
            raise RuntimeError('No QApplication instance')
        window = app.activeWindow()
        if window is None:
            # Fall back to first top-level widget
            for w in app.topLevelWidgets():
                if isinstance(w, QtWidgets.QMainWindow):
                    return w
            widgets = app.topLevelWidgets()
            if widgets:
                return widgets[0]
            raise RuntimeError('No top-level window found')
        return window

    def _inspect(self, header):
        path = header.get('path', '')
        max_depth = header.get('max_depth', 50)
        root = self._get_root()
        if path:
            root = _find_widget(root, path)
        return _widget_info(root, max_depth=max_depth)

    def _action(self, header):
        action = header.get('action', '')
        path = header.get('path', '')
        root = self._get_root()
        widget = _find_widget(root, path) if path else root

        if action == 'click':
            pos = header.get('pos')
            button = getattr(QtCore.Qt, header.get('button', 'LeftButton'), QtCore.Qt.LeftButton)
            if pos is None:
                pos = widget.rect().center()
            else:
                pos = QtCore.QPoint(pos[0], pos[1])
            # Press
            press = QtGui.QMouseEvent(
                QtCore.QEvent.Type.MouseButtonPress,
                QtCore.QPointF(pos),
                button, button, QtCore.Qt.NoModifier,
            )
            QtWidgets.QApplication.sendEvent(widget, press)
            # Release
            release = QtGui.QMouseEvent(
                QtCore.QEvent.Type.MouseButtonRelease,
                QtCore.QPointF(pos),
                button, button, QtCore.Qt.NoModifier,
            )
            QtWidgets.QApplication.sendEvent(widget, release)
            return {'ok': True, 'action': 'click'}

        elif action == 'key':
            key = header.get('key', '')
            text = header.get('text', '')
            modifiers = QtCore.Qt.NoModifier
            mod_names = header.get('modifiers', [])
            for m in mod_names:
                mod = getattr(QtCore.Qt, m, None)
                if mod is not None:
                    modifiers |= mod
            key_val = getattr(QtCore.Qt, f'Key_{key}', None) if key else 0
            if key_val is None:
                key_val = 0
            press = QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyPress,
                key_val, modifiers, text,
            )
            QtWidgets.QApplication.sendEvent(widget, press)
            release = QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyRelease,
                key_val, modifiers, text,
            )
            QtWidgets.QApplication.sendEvent(widget, release)
            return {'ok': True, 'action': 'key'}

        elif action == 'set_property':
            prop_name = header.get('property', '')
            prop_value = header.get('value')
            widget.setProperty(prop_name, prop_value)
            return {'ok': True, 'action': 'set_property'}

        elif action == 'get_property':
            prop_name = header.get('property', '')
            val = widget.property(prop_name)
            return {'ok': True, 'action': 'get_property',
                    'property': prop_name, 'value': _safe_property_value(val)}

        else:
            raise ValueError(f'Unknown action: {action}')

    def _screenshot(self, header):
        path = header.get('path', '')
        root = self._get_root()
        widget = _find_widget(root, path) if path else root
        pixmap = widget.grab()
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, 'PNG')
        png_bytes = bytes(buffer.data())
        buffer.close()
        result_header = {
            'path': path,
            'width': pixmap.width(),
            'height': pixmap.height(),
            'format': 'png',
        }
        return result_header, png_bytes
