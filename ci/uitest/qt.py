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
