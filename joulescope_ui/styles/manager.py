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


import json
import logging
import os
import re
from joulescope_ui import N_, json, pubsub_singleton, get_unique_id, get_topic_name, get_instance
from joulescope_ui.sanitize import str_to_filename
from . import color_file, parameter_file
from .color_scheme import COLOR_SCHEMES
from .font_scheme import FONT_SCHEMES
import copy
import pkgutil
import time


_template_replace = re.compile(r'{%\s*([a-zA-Z0-9_\.]+)\s*%}')
RENDER_TOPIC = f'registry/StyleManager:0/actions/!render'


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
    """
    return {
        'name': name_setting(name),
        'colors': {
            'dtype': 'obj',  # map[color name str, color value str]
            'brief': N_('The active colors'),
            'default': None,
        },
        'fonts': {
            'dtype': 'obj',  # map[font name str, font value str]
            'brief': N_('The active fonts'),
            'default': None,
        },
        'style_defines': {
            'dtype': 'obj',  # map[property_name, value]
            'brief': N_('The style defines'),
            'default': None,
        },
        'stylesheet': {
            'dtype': 'str',
            'brief': N_('The currently rendered stylesheet'),
            'default': '',
        },
    }


def _get_data(package, resource, default=None, encoding=None):
    try:
        data = pkgutil.get_data(package, resource)
    except FileNotFoundError:
        data = None
    if data is None:
        data = default
    if isinstance(data, bytes) and encoding is not None:
        data = data.decode(encoding)
    return data


def load_colors(obj, color_scheme=None, pubsub=None):
    if pubsub is None:
        pubsub = pubsub_singleton
    obj = get_instance(obj, pubsub=pubsub)
    try:
        topic_name = get_topic_name(obj)
    except ValueError:
        if isinstance(obj, type):
            return {'dark': {}, 'light': {}}
        else:
            return {}
    colors = pubsub.query(f'{topic_name}/settings/colors', default=None)
    if colors is not None:
        return colors
    if isinstance(obj, type):  # object is a class
        cls = obj
        # get class override colors
        instance_of_topic = get_topic_name(cls)
        colors = pubsub.query(f'{instance_of_topic}/settings/colors', default=None)
        if colors is not None:
            return colors

        # get class default colors
        package = '.'.join(cls.__module__.split('.')[:-1])
        colors = {}
        for color_scheme in COLOR_SCHEMES.keys():
            c = _get_data(package, f'styles/color_scheme_{color_scheme}.txt', default='', encoding='utf-8')
            c = color_file.parse_str(c)
            colors[color_scheme] = c
        return colors
    else:
        if color_scheme is None:
            color_scheme = obj.style_manager_info['color_scheme']
        colors = load_colors(obj.__class__, pubsub=pubsub)
        return colors[color_scheme]


def load_fonts(obj, font_scheme=None, pubsub=None):
    if pubsub is None:
        pubsub = pubsub_singleton
    obj = get_instance(obj, pubsub=pubsub)
    try:
        topic_name = get_topic_name(obj)
    except ValueError:
        if isinstance(obj, type):
            return {'js1': {}}
        else:
            return {}
    entries = pubsub.query(f'{topic_name}/settings/fonts', default=None)
    if entries is not None:
        return entries
    if isinstance(obj, type):  # object is a class
        cls = obj
        # get class override entries
        instance_of_topic = get_topic_name(cls)
        entries = pubsub.query(f'{instance_of_topic}/settings/fonts', default=None)
        if entries is not None:
            return entries

        # get class default entries
        package = '.'.join(cls.__module__.split('.')[:-1])
        entries = {}
        for scheme in FONT_SCHEMES.keys():
            e = _get_data(package, f'styles/font_scheme_{scheme}.txt', default='', encoding='utf-8')
            e = parameter_file.parse_str(e)
            entries[scheme] = e
        return entries
    else:
        if font_scheme is None:
            font_scheme = obj.style_manager_info['font_scheme']
        entries = load_fonts(obj.__class__, pubsub=pubsub)
        return entries[font_scheme]


def load_style_defines(obj, pubsub=None):
    if pubsub is None:
        pubsub = pubsub_singleton
    obj = get_instance(obj, pubsub=pubsub)
    try:
        topic_name = get_topic_name(obj)
    except ValueError:
        return {}
    entries = pubsub.query(f'{topic_name}/settings/style_defines', default=None)
    if entries is not None:
        return entries
    if isinstance(obj, type):  # object is a class
        cls = obj
        # get class override entries
        instance_of_topic = get_topic_name(cls)
        entries = pubsub.query(f'{instance_of_topic}/settings/style_defines', default=None)
        if entries is not None:
            return entries

        # get class default entries
        package = '.'.join(cls.__module__.split('.')[:-1])
        entries = _get_data(package, f'styles/style_defines.txt', default='', encoding='utf-8')
        return parameter_file.parse_str(entries)
    else:
        return load_style_defines(obj.__class__, pubsub=pubsub)


class StyleManager:

    def __init__(self, pubsub):
        self._log = logging.getLogger(__name__)
        self.pubsub = pubsub
        self._dialog = None
        # self.pubsub.subscribe('common/settings/paths/styles', self._on_path, ['pub'])  # todo
        # self.pubsub.subscribe('common/settings/profile/active', self._on_profile, ['pub'])  # todo
        # self.pubsub.subscribe('registry/ui/settings/theme', self._on_theme, ['pub'])
        # ui_color_scheme_topic = 'registry/ui/settings/color_scheme'
        # self.pubsub.subscribe(ui_color_scheme_topic, self._on_color_scheme, ['pub'])

        # if self.pubsub.query(ui_color_scheme_topic, default=None) is None:
        #     color_scheme_name = self.pubsub.query('registry/ui/settings/color_scheme_name', default='dark')
        #     color_scheme = self._color_scheme_load(color_scheme_name)
        #     self.pubsub.publish(ui_color_scheme_topic, color_scheme)
        # if not os.path.isdir(path):
        #     self.render()

    @property
    def path(self):
        path = self.pubsub.query('common/settings/paths/styles')
        profile = self.pubsub.query('common/settings/profile/active', default='default')
        view = self.pubsub.query('registry/view/settings/active')
        filename = f'{profile}__{view}'
        return os.path.join(path, str_to_filename(filename))

    def _render_one(self, unique_id, info):
        obj = get_instance(unique_id, pubsub=self.pubsub)
        topic_name = get_topic_name(unique_id)
        target_path = os.path.join(self.path, str_to_filename(unique_id))
        t_start = time.time()
        self._log.info('_render_one(%s): start to %s', unique_id, target_path)
        instance = self.pubsub.query(f'{topic_name}/instance', default=None)
        if instance is None:
            return  # nothing to update
        if isinstance(instance, type):
            cls = instance
        else:
            cls = instance.__class__
        package = '.'.join(cls.__module__.split('.')[:-1])
        instance_of_unique_id = self.pubsub.query(f'{topic_name}/instance_of', default=None)
        if instance_of_unique_id is None:
            instance_of_topic = None
        else:
            instance_of_topic = get_topic_name(instance_of_unique_id)

        theme_prefix = 'styles/'
        index = _get_data(package, theme_prefix + 'index.json', default=None, encoding='utf-8')
        if index is None:
            theme_prefix += f'{info["theme"]}/'
            index = _get_data(package, theme_prefix + 'index.json', default=None, encoding='utf-8')
        if index is not None:
            index = json.loads(index)
            os.makedirs(target_path, exist_ok=True)
            index['render'] = {
                'src_package': package,
                'src_theme_prefix': theme_prefix,
                'target_path': target_path,
            }

            fonts = self.pubsub.query(f'{topic_name}/settings/fonts', default=None)
            style_defines = self.pubsub.query(f'{topic_name}/settings/style_defines', default=None)

            colors = load_colors(obj, color_scheme=info['color_scheme'], pubsub=self.pubsub)
            qss_colors = {}
            for key, value in colors.items():
                r, g, b, a = int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), int(value[7:9], 16)
                qss_colors[key] = f'#{r:02x}{g:02x}{b:02x}{a:02x}'

            fonts = load_fonts(obj, font_scheme=info['font_scheme'], pubsub=self.pubsub)
            style_defines = load_style_defines(obj, pubsub=self.pubsub)

            sub_vars = {**info['sub_vars'], **style_defines, **fonts, **qss_colors}
            info['sub_vars'] = sub_vars
            self._render_templates(index, sub_vars)
            self._render_images(index, sub_vars)
            self._publish(index, unique_id)
        obj.style_manager_info = info  # record style manager info for future renderings
        children = self.pubsub.query(f'{topic_name}/children', default=[])
        self._log.info('render %s: done in %.3f seconds', unique_id, time.time() - t_start)
        for child in children:
            self._render_one(child, info)
        if not isinstance(obj, type) and hasattr(obj, 'on_style_change'):
            obj.on_style_change()
        return info

    def _render_view(self, unique_id=None):
        if unique_id is None:
            unique_id = self.pubsub.query(f'registry/view/settings/active')
        topic_name = get_topic_name(unique_id)
        # Get the view information
        info = {
            'theme': self.pubsub.query(f'{topic_name}/settings/theme', default='js1'),
            'color_scheme': self.pubsub.query(f'{topic_name}/settings/color_scheme', default='dark'),
            'font_scheme': self.pubsub.query(f'{topic_name}/settings/font_scheme', default='js1'),
            'sub_vars': {},
        }
        info = self._render_one(unique_id, info)
        obj = get_instance('ui')
        obj.style_manager_info = info
        self._render_one('ui', info)
        return None  # cannot undo directly, must undo settings

    def on_action_render(self, value):
        if value is None:
            self._render_view()
            return None
        try:
            unique_id = get_unique_id(value)
        except ValueError:
            # self._log.debug('render None - likely still being registered, will get called later.')
            return None
        self._log.info('on_action_render(%s)', value)
        obj = get_instance(unique_id)
        active_view_unique_id = self.pubsub.query(f'registry/view/settings/active')
        if isinstance(obj, type):
            # Only need to render active widgets of this type
            # but go ahead and render the entire active view
            unique_id = active_view_unique_id
            obj = get_instance(unique_id)
        if unique_id.startswith('view:'):
            return self._render_view(unique_id)
        if hasattr(obj, 'style_manager_info'):
            self._render_one(unique_id, obj.style_manager_info)
            return None
        while True:
            if unique_id.startswith('view:'):
                return self._render_view(unique_id)
            topic_name = get_topic_name(unique_id)
            self._log.info('find parent for %s', topic_name)
            next_unique_id = self.pubsub.query(f'{topic_name}/parent')
            if next_unique_id in [None, '']:
                next_unique_id = active_view_unique_id
            next_topic_name = get_topic_name(next_unique_id)
            next_obj = self.pubsub.query(f'{next_topic_name}/instance')
            if hasattr(next_obj, 'style_manager_info'):
                self._render_one(unique_id, copy.deepcopy(next_obj.style_manager_info))
                return None
            unique_id = next_unique_id

    def _publish(self, index, unique_id):
        style_path = index['render']['templates'].get('style.qss')
        if style_path is None:
            self._log.info('render %s does not contain style.qss', unique_id)
            return
        topic = get_topic_name(unique_id)
        with open(style_path, 'rt') as f:
            stylesheet = f.read()
        self.pubsub.publish(f'{topic}/settings/stylesheet', stylesheet)

    def _render_templates(self, index, sub_vars):
        package = index['render']['src_package']
        theme_prefix = index['render']['src_theme_prefix']
        target_path = index['render']['target_path'].replace('\\', '/')
        templates = {}
        index['render']['templates'] = templates

        def replace(matchobj):
            varname = matchobj.group(1)
            if varname == 'path':
                return target_path
            v = sub_vars[varname]
            if v.startswith('#') and len(v) == 9:
                r, g, b, a = int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16), int(v[7:9], 16)
                a = a / 255.0
                v = f'rgba({r},{g},{b},{a})'
            return v

        for template in index['templates']:
            self._log.info('render template %s:%s', package, template)
            data = pkgutil.get_data(package, theme_prefix + template)
            if data is None:
                self._log.warning('template not found: %s', template)
                return
            data = data.replace(b'\r\n', b'\n').decode('utf-8')
            s = _template_replace.sub(replace, data)
            path = os.path.join(target_path, template)
            templates[template] = path
            with open(path, 'wt', encoding='utf-8') as f:
                f.write(s)

    def _render_images(self, index, sub_vars):
        package = index['render']['src_package']
        theme_prefix = index['render']['src_theme_prefix']
        target_path = index['render']['target_path'].replace('\\', '/')

        for name, image_set in index['images'].items():
            self._log.info('generate images for %s:%s', package, name)
            for source in image_set['sources']:
                svg = pkgutil.get_data(package, theme_prefix + source)
                svg = svg.replace(b'\r\n', b'\n').decode('utf-8')
                basename, ext = os.path.splitext(source)
                for filename, subs in image_set['targets']:
                    svg_out = svg
                    filename = filename.format(basename=basename, ext=ext)
                    for substr, replace in subs.items():
                        v = sub_vars[replace]
                        if v.startswith('#') and len(v) == 9:
                            v = v[:7]
                        svg_out = svg_out.replace(substr, v)
                    path = os.path.join(target_path, filename)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(svg_out)


def styled_widget(translated_name):
    """Construct a widget that supports styles.

    :param translated_name: The translated name for this widget.

    This decorator is a mixin that monkey patches the widget
    to add style SETTINGS and methods to fully support styles
    and adds methods to handle the settings updates.
    """

    def on_setting_stylesheet(self, value):
        self.setStyleSheet(value)

    def render(self, value):
        pubsub_singleton.publish(RENDER_TOPIC, self)

    def inner(cls):
        def cls_render(value):
            if RENDER_TOPIC in pubsub_singleton:
                pubsub_singleton.publish(RENDER_TOPIC, cls)

        if not hasattr(cls, 'SETTINGS'):
            cls.SETTINGS = {}
        for key, value in style_settings(translated_name).items():
            cls.SETTINGS.setdefault(key, value)
        cls._colors = None
        cls._fonts = None
        cls._stylesheet = None
        cls.on_cls_setting_colors = cls_render
        cls.on_cls_setting_fonts = cls_render
        cls.on_cls_setting_style_defines = cls_render
        cls.on_setting_stylesheet = on_setting_stylesheet
        cls.on_setting_colors = render
        cls.on_setting_fonts = render
        cls.on_setting_style_defines = render
        return cls
    return inner
