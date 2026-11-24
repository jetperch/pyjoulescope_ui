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

"""Helpers for navigating the Qt widget tree returned by ``qt_inspect``.

The tree is the plain JSON structure produced by
:func:`joulescope_ui.tcp_server.qt_inspector._widget_info`: each node is a dict
with ``class``, ``objectName``, optional ``properties`` (a name->value map), and
optional ``children`` (a list of nodes).  These pure functions let tests assert
on that structure without touching Qt, so they are unit-testable headlessly.
"""


def iter_widgets(node):
    """Depth-first iterate over every widget node in the tree."""
    if not node:
        return
    yield node
    for child in node.get('children', []) or []:
        yield from iter_widgets(child)


def find_widgets(tree, *, cls=None, object_name=None, text_contains=None):
    """Return all nodes matching the given criteria (AND-combined).

    :param cls: Match ``node['class']`` exactly.
    :param object_name: Match ``node['objectName']`` exactly.
    :param text_contains: Match nodes any of whose string properties contain
        this substring.
    """
    out = []
    for node in iter_widgets(tree):
        if cls is not None and node.get('class') != cls:
            continue
        if object_name is not None and node.get('objectName') != object_name:
            continue
        if text_contains is not None and not _node_text_contains(node, text_contains):
            continue
        out.append(node)
    return out


def find_widget(tree, *, cls=None, object_name=None, text_contains=None):
    """Return the first matching node, or None."""
    found = find_widgets(tree, cls=cls, object_name=object_name,
                         text_contains=text_contains)
    return found[0] if found else None


def any_text_contains(tree, text):
    """True if any widget in the tree has a string property containing ``text``."""
    return any(_node_text_contains(node, text) for node in iter_widgets(tree))


def all_texts_present(tree, texts):
    """Return the subset of ``texts`` that are NOT found anywhere in the tree.

    An empty result means every requested string is present.
    """
    return [t for t in texts if not any_text_contains(tree, t)]


def _node_text_contains(node, text):
    props = node.get('properties', {}) or {}
    for value in props.values():
        if isinstance(value, str) and text in value:
            return True
    return False


def find_truncation(tree, tolerance=1):
    """Find visible text that does not fit its widget.

    Uses the ``fit`` records from the inspector (see
    docs/plans/translation_display_audit.md).

    :param tree: The ``qt_inspect`` tree.
    :param tolerance: Allowed overflow in pixels, for rounding.
    :return: List of dicts with ``path``, ``class``, ``text``, ``need``,
        and ``have``, in tree order.
    """
    out = []

    def walk(node, path):
        path = f'{path}/{node.get("class")}'
        if node.get('objectName'):
            path += f'[{node["objectName"]}]'
        if not node.get('visible', True):
            return
        fit = node.get('fit')
        if fit:
            for item in fit.get('items', [fit]):
                if item['have'] > 0 and item['need'] > item['have'] + tolerance:
                    out.append({'path': path, 'class': node.get('class'), 'text': item['text'],
                                'need': item['need'], 'have': item['have']})
        for child in node.get('children', []) or []:
            walk(child, path)

    if tree:
        walk(tree, '')
    return out


_TEXT_PROPERTIES = ('text', 'title', 'windowTitle', 'placeholderText', 'toolTip')


def iter_texts(tree):
    """Yield the user-visible text in the tree.

    Includes text properties, tab and header items, and menu actions.
    Menus are included even while closed, since their text shows when
    opened.  Other hidden widgets are skipped.

    :param tree: The ``qt_inspect`` tree.
    :return: Iterator of ``(class, kind, text)`` tuples.
    """
    def walk(node):
        cls = node.get('class')
        is_menu = cls in ('QMenu', 'QMenuBar')
        if not node.get('visible', True) and not is_menu:
            return
        props = node.get('properties') or {}
        for name in _TEXT_PROPERTIES:
            value = props.get(name)
            if isinstance(value, str) and value.strip():
                yield cls, name, value
        fit = node.get('fit') or {}
        for item in fit.get('items', []):
            yield cls, 'item', item['text']
        for action in node.get('actions', []) or []:
            yield cls, 'action', action
        for child in node.get('children', []) or []:
            yield from walk(child)

    if tree:
        yield from walk(tree)


def find_blank_buttons(tree):
    """Find visible dialog buttons without text.

    Standard dialog buttons (OK, Cancel) always have text, so a blank one
    means a broken translation lookup.

    :return: List of button paths.
    """
    out = []

    def walk(node, path, parent_cls):
        cls = node.get('class')
        path = f'{path}/{cls}'
        if not node.get('visible', True):
            return
        text = (node.get('properties') or {}).get('text')
        if cls == 'QPushButton' and parent_cls == 'QDialogButtonBox' and not (text or '').strip():
            out.append(path)
        for child in node.get('children', []) or []:
            walk(child, path, cls)

    if tree:
        walk(tree, '', None)
    return out
