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

"""Reset settings to their defaults.

An instance of a widget, device or view resets to its class: the defaults
the user edits in the Settings widget.  A class, or an instance with no
editable class, resets to the factory defaults in SETTINGS.
See docs/plans/completed/settings_reset.md.
"""

from joulescope_ui import get_topic_name, get_unique_id
from joulescope_ui.capabilities import CAPABILITIES


RESET_TOPIC = 'registry/settings/actions/!reset'
TABS = ['settings', 'colors', 'fonts', 'style_defines']
_STYLE_TABS = ['colors', 'fonts', 'style_defines']
_SKIP = ['name', 'style_obj'] + _STYLE_TABS
_CLASS_CAPABILITIES = [CAPABILITIES.WIDGET_CLASS, CAPABILITIES.DEVICE_CLASS, CAPABILITIES.VIEW_CLASS]


def _has_capability(pubsub, unique_id, capability):
    unique_ids = pubsub.query(f'registry_manager/capabilities/{capability}/list', default=None)
    return unique_ids is not None and unique_id in unique_ids


def _is_device(pubsub, unique_id):
    return (_has_capability(pubsub, unique_id, CAPABILITIES.DEVICE_OBJECT)
            or _has_capability(pubsub, unique_id, CAPABILITIES.DEVICE_CLASS))


def base_topic(pubsub, target):
    """The class topic that an instance resets to.

    :param pubsub: The pubsub instance.
    :param target: The instance or class unique_id, topic or object.
    :return: The class topic, or None to reset to the factory defaults.
    """
    topic = get_topic_name(target)
    instance_of = pubsub.query(f'{topic}/instance_of', default=None)
    if not instance_of:
        return None  # a class
    if any(_has_capability(pubsub, instance_of, c) for c in _CLASS_CAPABILITIES):
        return get_topic_name(instance_of)
    return None


def _style_remove(value, scheme, names):
    """Remove style overrides, returning the new value or None if empty.

    :param value: The colors, fonts or style_defines override value.
    :param scheme: The scheme for colors and fonts, None for all schemes,
        or False for style_defines, which has no schemes.
    :param names: The override names to remove, or None for all.
    """
    if not isinstance(value, dict):
        return None
    if scheme is False:
        if names is None:
            return None
        return {k: v for k, v in value.items() if k not in names} or None
    rv = {}
    for k, v in value.items():
        if scheme is None or k == scheme:
            v = None if names is None else _style_remove(v, False, names)
        if v:
            rv[k] = v
    return rv or None


def reset_values(pubsub, target, tabs=None, schemes=None, names=None):
    """Compute the settings changes for a reset.

    :param pubsub: The pubsub instance.
    :param target: The instance or class unique_id, topic or object.
    :param tabs: The list of TABS to reset.  None resets all.
    :param schemes: For a one-tab reset, the map of tab name to the
        active scheme, like {'colors': 'dark'}.  Colors and fonts then reset
        only that scheme.  None resets every scheme.
    :param names: The setting, color, font or define names to reset, for a
        one-setting reset.  None resets all.
    :return: The list of [topic, value] changes, skipping unchanged values.
    """
    tabs = TABS if tabs is None else tabs
    schemes = {} if schemes is None else schemes
    topic = get_topic_name(target)
    cls_topic = base_topic(pubsub, topic)
    changes = []

    def add(t, value):
        if pubsub.query(t) != value:
            changes.append([t, value])

    if 'settings' in tabs:
        include_hidden = _is_device(pubsub, get_unique_id(topic))  # device configuration
        settings = pubsub.enumerate(f'{topic}/settings', absolute=False, traverse=True)
        for name in settings:
            if name in _SKIP or (names is not None and name not in names):
                continue
            t = f'{topic}/settings/{name}'
            meta = pubsub.metadata(t)
            if meta is None or meta.dtype == 'node':
                continue
            flags = meta.flags
            if 'ro' in flags or 'tmp' in flags or ('hide' in flags and not include_hidden):
                continue
            if cls_topic is not None and f'{cls_topic}/settings/{name}' in pubsub:
                value = pubsub.query(f'{cls_topic}/settings/{name}')
            else:
                cls_meta = None if cls_topic is None else pubsub.metadata(f'{cls_topic}/settings/{name}')
                value = meta.default if cls_meta is None else cls_meta.default
            add(t, value)

    for tab in _STYLE_TABS:
        t = f'{topic}/settings/{tab}'
        if tab not in tabs or t not in pubsub:
            continue
        scheme = False if tab == 'style_defines' else schemes.get(tab)
        add(t, _style_remove(pubsub.query(t), scheme, names))
    return changes


def modified(pubsub, target, tab, scheme=None):
    """The names that differ from what a reset would give.

    :param pubsub: The pubsub instance.
    :param target: The instance or class unique_id, topic or object.
    :param tab: One of TABS.
    :param scheme: The active scheme for colors and fonts.
    :return: The set of modified setting, color, font or define names.
    """
    topic = get_topic_name(target)
    if tab == 'settings':
        prefix = f'{topic}/settings/'
        return {t[len(prefix):] for t, _ in reset_values(pubsub, topic, ['settings'])}
    value = pubsub.query(f'{topic}/settings/{tab}', default=None)
    if tab != 'style_defines' and isinstance(value, dict):
        value = value.get(scheme)
    return set(value.keys()) if isinstance(value, dict) else set()


def reset(pubsub, value):
    """Reset settings as a single undo step.

    :param pubsub: The pubsub instance.
    :param value: The map with keys target, and optionally tabs, schemes
        and names.  See :func:`reset_values`.
    :return: The undo/redo specification, or None when nothing changed.
    """
    target = value['target']
    topic = get_topic_name(target)
    changes = reset_values(pubsub, topic, value.get('tabs'), value.get('schemes'), value.get('names'))
    if not len(changes):
        return None
    undo = [[t, pubsub.query(t)] for t, _ in changes]
    restore = []
    if _has_capability(pubsub, get_unique_id(topic), CAPABILITIES.DEVICE_OBJECT):
        # Stop streaming and close before changing device settings, as the
        # device control widget always did.
        changed = [t for t, _ in changes]
        for name in pubsub.enumerate(f'{topic}/settings/signals', absolute=False, traverse=True):
            t = f'{topic}/settings/signals/{name}'
            if name.endswith('/enable') and pubsub.query(t):
                pubsub.publish(t, False)
                if t not in changed:
                    restore.append([t, True])  # already at its default
        pubsub.publish(f'{topic}/actions/!state_req', 0)
    for t, v in changes + restore:
        pubsub.publish(t, v)
    return {'undo': undo}
