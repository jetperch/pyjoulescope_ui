# Copyright 2020-2022 Jetperch LLC
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

"""Manage styles for the user interface application."""


import logging
import os
import re
from joulescope_ui import N_, pubsub_singleton, get_unique_id, get_topic_name, get_instance, is_pubsub_registered
from joulescope_ui import json_plus as json
from joulescope_ui.sanitize import str_to_filename
from . import color_file, parameter_file
from .color_scheme import COLOR_SCHEMES
from .font_scheme import FONT_SCHEMES
import copy
import pkgutil
import time


_template_replace = re.compile(r'{%\s*([a-zA-Z0-9_\.]+)\s*%}')
RENDER_TOPIC = f'registry/style/actions/!render'
_ENABLE_TEMPLATE_DEBUG = False
_log = logging.getLogger(__name__)


def name_setting(name):
    """Generate the name setting metadata.

    :param name: The translated name.
    :return: The name setting metadata.
    """
    return {
        'dtype': 'str',
        'brief': N_('The name for this widget.'),
        'default': name,
    }


def style_settings(name):
    """Generate the style settings.

    :param name: The translated name.
    :return: The settings dict.

    The settings colors, fonts, and style_defines contain the
    values that have been changed by the user from the defaults,
    both for classes and objects.  They do not
    contain any values inherited from parents.

    The setting style_cls contains the class values loaded from the
    style definitions from the file system.

    For both classes and objects, style contains the
    hierarchically rendered result that is used to populate
    the stylesheet.  It may also be used directly by the
    widget paintEvent method.
    """
    return {
        'name': name_setting(name),
        'colors': {
            'dtype': 'obj',  # map[color_scheme, map[color name str, color value str]]
            'brief': 'The override colors for each color theme',
            'default': None,
            'flags': ['hide'],
        },
        'fonts': {
            'dtype': 'obj',  # map[font_scheme, [font name str, font value str]]
            'brief': 'The override fonts for each font theme',
            'default': None,
            'flags': ['hide'],
        },
        'style_defines': {
            'dtype': 'obj',  # map[property_name, value]
            'brief': 'The style defines',
            'default': None,
            'flags': ['hide'],
        },
        'style_obj': {
            'dtype': 'obj',
                # vars: map[name str, value str] - combined colors, fonts, style_defines
                # templates: map[name_str, template_str] - rendered templates
                # path: The rendered output path (for images)
            'brief': 'The rendered style',
            'default': None,
            'flags': ['hide', 'tmp', 'noinit'],
        },
    }


def _get_data(package, resource, default=None, encoding=None):
    if isinstance(package, type):
        # get package for type
        package = '.'.join(package.__module__.split('.')[:-1])
    try:
        data = pkgutil.get_data(package, resource)
        # _log.info('get_data load %s:%s | %s', package, resource, data)
    except FileNotFoundError:
        # _log.info('get_data could not load %s:%s | %s', package, resource, default)
        data = None
    if data is None:
        # _log.info('get_data load default %s:%s | %s', package, resource, default)
        data = default
    if isinstance(data, bytes) and encoding is not None:
        data = data.decode(encoding)
    return data


def _load_cls_colors(cls):
    colors = {}
    for color_scheme in COLOR_SCHEMES.keys():
        c = _get_data(cls, f'styles/color_scheme_{color_scheme}.txt', default='', encoding='utf-8')
        c = color_file.parse_str(c)
        colors[color_scheme] = c
    return colors


def _load_cls_fonts(cls):
    entries = {}
    for scheme in FONT_SCHEMES.keys():
        e = _get_data(cls, f'styles/font_scheme_{scheme}.txt', default='', encoding='utf-8')
        e = parameter_file.parse_str(e)
        entries[scheme] = e
    return entries


def _load_cls_style_defines(cls):
    entries = _get_data(cls, f'styles/style_defines.txt', default='', encoding='utf-8')
    return parameter_file.parse_str(entries)


def _load_style_for_class(cls, theme):
    package = '.'.join(cls.__module__.split('.')[:-1])
    theme_prefix = 'styles/'
    index = _get_data(package, theme_prefix + 'index.json', default=None, encoding='utf-8')
    if index is None:
        theme_prefix += f'{theme}/'
        index = _get_data(package, theme_prefix + 'index.json', default=None, encoding='utf-8')

    templates = {}
    if index is not None:
        index = json.loads(index)
        for template in index['templates']:
            path = theme_prefix + template
            data = pkgutil.get_data(package, theme_prefix + template)
            if data is None:
                _log.warning('template not found: %s', path)
                return
            data = data.replace(b'\r\n', b'\n').decode('utf-8')
            templates[template] = data

    cls._style_cls = {
        'index': index,
        'render': {
            'package': package,
            'theme': theme,
            'theme_prefix': theme_prefix,
        },
        'load': {
            'templates': templates,
            'colors': _load_cls_colors(cls),
            'fonts': _load_cls_fonts(cls),
            'style_defines': _load_cls_style_defines(cls),
        },
        'vars': {},
    }


def _render_images(obj, path):
    if isinstance(obj, type):
        _log.warning('Render images for objects, not classes')
        return
    cls = obj.__class__
    if not hasattr(cls, 'unique_id'):
        return
    style_cls = cls._style_cls
    index = style_cls['index']
    if index is None:
        return
    theme_prefix = style_cls['render']['theme_prefix']
    style_vars = obj.style_obj['vars']
    images = index.get('images')
    if images is None:
        return

    for name, image_set in images.items():
        _log.info('generate images for %s:%s', obj.unique_id, name)
        for source in image_set['sources']:
            svg = _get_data(cls, theme_prefix + source)
            svg = svg.replace(b'\r\n', b'\n').decode('utf-8')
            basename, ext = os.path.splitext(source)
            for filename, subs in image_set['targets']:
                svg_out = svg
                filename = filename.format(basename=basename, ext=ext)
                for substr, replace in subs.items():
                    v = style_vars[replace]
                    if v.startswith('#') and len(v) == 9:
                        v = v[:7]
                    svg_out = svg_out.replace(substr, v)
                img_path = os.path.join(path, filename)
                with open(img_path, 'w', encoding='utf-8') as f:
                    f.write(svg_out)


def _render_templates(obj, path):
    if isinstance(obj, type):
        _log.warning('Render images for objects, not classes')
        return
    cls = obj.__class__
    if not hasattr(cls, 'unique_id'):
        return
    style_cls = cls._style_cls
    style_vars = obj.style_obj['vars']
    path = path.replace('\\', '/')

    def replace(matchobj):
        varname = matchobj.group(1)
        if varname == 'path':
            return path
        v = style_vars[varname]
        if v.startswith('#') and len(v) == 9:
            r, g, b, a = int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16), int(v[7:9], 16)
            a = a / 255.0
            v = f'rgba({r},{g},{b},{a})'
        return v

    for name, template in style_cls['load']['templates'].items():
        s = _template_replace.sub(replace, template)
        obj.style_obj['templates'][name] = s
        if _ENABLE_TEMPLATE_DEBUG:
            template_path = os.path.join(path, name)
            with open(template_path, 'wt') as f:
                f.write(s)


def _update_vars(v, d, subkey=None):
    if d is None:
        return
    try:
        if subkey is not None:
            d = d[subkey]
        for name, value in d.items():
            v[name] = value
    except (TypeError, KeyError, AttributeError):
        return


def _render_cls(cls, theme, color_scheme, font_scheme):
    v = {}
    if getattr(cls, '_style_cls', None) is None:
        _load_style_for_class(cls, theme)
    style_cls = cls._style_cls
    _update_vars(v, style_cls['load']['colors'], color_scheme)
    _update_vars(v, style_cls['load']['fonts'], font_scheme)
    _update_vars(v, style_cls['load']['style_defines'])
    _update_vars(v, pubsub_singleton.query(f'{get_topic_name(cls)}/settings/colors'), color_scheme)
    _update_vars(v, pubsub_singleton.query(f'{get_topic_name(cls)}/settings/fonts'), font_scheme)
    _update_vars(v, pubsub_singleton.query(f'{get_topic_name(cls)}/settings/style_defines'))
    style_cls['vars'] = v


def _render_obj(obj, path, theme, color_scheme, font_scheme):
    obj = get_instance(obj)
    if not hasattr(obj, 'style_obj'):
        return False
    if get_unique_id(obj) == 'ui':
        cls_mirror = True
        cls = pubsub_singleton.query('registry/view/instance')
    else:
        cls_mirror = False
        cls = obj.__class__
    path = os.path.join(path, str_to_filename(obj.unique_id))
    if hasattr(cls, 'unique_id'):
        _render_cls(cls, theme, color_scheme, font_scheme)
        style_cls = cls._style_cls
        if cls_mirror:
            obj.__class__._style_cls = style_cls
        style_vars = style_cls['vars']
    else:
        style_vars = {}
    parent = pubsub_singleton.query(f'{get_topic_name(obj)}/parent', default=None)
    if parent is None or not len(parent):
        v = {}
    else:
        parent = get_instance(parent)
        v = copy.deepcopy(parent.style_obj['vars'])
    for key, value in style_vars.items():
        v[key] = value
    _update_vars(v, getattr(obj, 'colors'), color_scheme)
    _update_vars(v, getattr(obj, 'fonts'), font_scheme)
    _update_vars(v, getattr(obj, 'style_defines'))

    obj.style_obj = {
        'vars': v,
        'templates': {},
        'path': path,
    }
    os.makedirs(path, exist_ok=True)
    _render_images(obj, path)
    _render_templates(obj, path)
    return True


def _recurse(unique_id):
    rv = []
    for child in pubsub_singleton.query(f'{get_topic_name(unique_id)}/children'):
        rv.append(child)
        rv.extend(_recurse(child))
    return rv


def _objs_in_view(view=None):
    if view is None:
        view = pubsub_singleton.query('registry/view/settings/active')
    return _recurse(view)


class StyleManager:

    SETTINGS = {
        'enable': {
            'dtype': 'bool',
            'brief': 'Enable style management',
            'default': False,
            'flags': ['hide', 'tmp', 'noinit'],
        },
    }

    def __init__(self):
        pass

    @property
    def path(self):
        path = self.pubsub.query('common/settings/paths/styles')
        profile = self.pubsub.query('common/settings/profile/active', default='default')
        view = self.pubsub.query('registry/view/settings/active')
        filename = f'{profile}__{view}'
        return os.path.normpath(os.path.join(path, str_to_filename(filename)))

    def _render(self, value):
        t_start = time.time()
        try:
            obj = get_instance(value)
        except KeyError:
            return
        if isinstance(obj, type):
            objs = _objs_in_view()
            for child in pubsub_singleton.query(f'{get_topic_name(obj)}/children'):
                if child in objs:
                    self.on_action_render(child)
            return
        active_view = self.pubsub.query('registry/view/settings/active', default=None)
        if active_view is None:
            _log.warning('render requested - ignored, no active view')
            return
        active_view_topic = get_topic_name(active_view)
        theme = self.pubsub.query(f'{active_view_topic}/settings/theme', default='js1')
        color_scheme = self.pubsub.query(f'{active_view_topic}/settings/color_scheme', default='dark')
        font_scheme = self.pubsub.query(f'{active_view_topic}/settings/font_scheme', default='js1')
        is_styled = _render_obj(obj, self.path, theme, color_scheme, font_scheme)
        children = self.pubsub.query(f'{get_topic_name(obj)}/children', default=[])
        _log.info('rendered %s [theme=%s, color_scheme=%s, font_scheme=%s], in %.3f',
                  value, theme, color_scheme, font_scheme, time.time() - t_start)
        for child in children:
            self._render(child)
        if is_styled:
            stylesheet = obj.style_obj['templates'].get('style.qss')
            if obj.unique_id.startswith('view:'):
                obj = self.pubsub.query('registry/ui/instance')
            if stylesheet is not None and stylesheet != obj.styleSheet():
                obj.setStyleSheet(stylesheet)
                obj.style().unpolish(obj)
                obj.style().polish(obj)
            if not isinstance(obj, type) and hasattr(obj, 'on_style_change'):
                obj.on_style_change()

    def on_action_render(self, value):
        if not self.enable:
            return
        _log.info('render start %s', value)
        t_start = time.time()
        if value is None:
            self._render('ui')
            self._render(pubsub_singleton.query('registry/view/settings/active'))
        else:
            self._render(value)
        duration = time.time() - t_start
        _log.info('render complete in %.3f seconds for %s', duration, value)


def styled_widget(translated_name):
    """Construct a widget that supports styles.

    :param translated_name: The translated name for this widget.

    This decorator is a mixin that monkey patches the widget
    to add style SETTINGS and methods to fully support styles
    and adds methods to handle the settings updates.
    """

    def render(self, value):
        if is_pubsub_registered(self):
            pubsub_singleton.publish(RENDER_TOPIC, self)

    def inner(cls):
        def cls_render(value):
            if is_pubsub_registered(cls):
                if RENDER_TOPIC in pubsub_singleton:
                    pubsub_singleton.publish(RENDER_TOPIC, cls)

        if not hasattr(cls, 'SETTINGS'):
            cls.SETTINGS = {}
        for key, value in style_settings(translated_name).items():
            cls.SETTINGS.setdefault(key, value)
        cls.on_cls_setting_colors = cls_render
        cls.on_cls_setting_fonts = cls_render
        cls.on_cls_setting_style_defines = cls_render
        cls.on_setting_colors = render
        cls.on_setting_fonts = render
        cls.on_setting_style_defines = render
        return cls
    return inner
