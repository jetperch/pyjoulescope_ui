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


import json
import logging
import os
import re
from joulescope_ui import N_, json
from joulescope_ui.sanitize import str_to_filename
from joulescope_ui.pubsub import get_unique_id, get_topic_name
from . import color_file
import pkgutil
import time


_template_replace = re.compile(r'{%\s*([a-zA-Z0-9_\.]+)\s*%}')


def style_settings(name):
    return {
        'name': {
            'dtype': 'str',
            'brief': N_('The name for this widget.'),
            'default': name,
        },
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


class StyleManager:

    def __init__(self, pubsub):
        self._log = logging.getLogger(__name__)
        self.pubsub = pubsub
        # self.pubsub.subscribe('common/paths/styles', self._on_path, ['pub'])  # todo
        # self.pubsub.subscribe('common/profile/settings/active', self._on_profile, ['pub'])  # todo
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
        path = self.pubsub.query('common/paths/styles')
        profile = self.pubsub.query('common/profile/settings/active', default='default')
        view = self.pubsub.query('registry/view/settings/active')
        filename = f'{profile}__{view}'
        return os.path.join(path, str_to_filename(filename))

    def _render_one(self, unique_id, info):
        topic_name = get_topic_name(unique_id)
        target_path = os.path.join(self.path, str_to_filename(unique_id))
        t_start = time.time()
        self._log.info('render %s: start to %s', unique_id, target_path)
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
        children = self.pubsub.query(f'{topic_name}/children', default=[])
        colors = self.pubsub.query(f'{topic_name}/settings/colors', default=None)
        fonts = self.pubsub.query(f'{topic_name}/settings/fonts', default=None)
        style_defines = self.pubsub.query(f'{topic_name}/settings/style_defines', default=None)

        theme_prefix = 'styles/'
        index = _get_data(package, theme_prefix + 'index.json', default=None, encoding='utf-8')
        if index is None:
            theme_prefix += f'{info["theme"]}/'
            index = _get_data(package, theme_prefix + 'index.json', default=None, encoding='utf-8')
            if index is None:
                return  # no style to render
        index = json.loads(index)
        os.makedirs(target_path, exist_ok=True)
        index['render'] = {
            'src_package': package,
            'src_theme_prefix': theme_prefix,
            'target_path': target_path,
        }

        if colors is None:
            if instance_of_topic is not None:
                # get class override colors
                colors = self.pubsub.query(f'{instance_of_topic}/settings/colors', default=None)
            if colors is None:
                # get class default colors
                colors = _get_data(package, f'styles/color_scheme_{info["color_scheme"]}.txt', default='', encoding='utf-8')
                colors = color_file.parse_str(colors)
        qss_colors = {}
        for key, value in colors.items():
            r, g, b, a = int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), int(value[7:9], 16)
            qss_colors[key] = f'rgba({r},{g},{b},{a})'

        #if fonts is None:
        #    fonts = _get_data(package, f'styles/font_scheme_{font_scheme}.txt', default={}, encoding='utf-8')
        #if style_defines is None:
        #    style_defines = _get_data(package, 'styles/style_defines.txt', default={}, encoding='utf-8')

        sub_vars = {**info['sub_vars'], **qss_colors}  # todo {**qss_colors, **fonts, **style_defines}
        info['sub_vars'] = sub_vars
        self._render_templates(index, sub_vars)
        self._render_images(index, sub_vars)
        self._publish(index, unique_id)
        self._log.info('render %s: done in %.3f seconds', unique_id, time.time() - t_start)
        for child in children:
            self._render_one(child, info)
        info['sub_vars'] = sub_vars
        return info

    def _render_view(self, unique_id):
        topic_name = get_topic_name(unique_id)
        # Get the view information
        info = {
            'theme': self.pubsub.query(f'{topic_name}/settings/theme', default='js1'),
            'color_scheme': self.pubsub.query(f'{topic_name}/settings/color_scheme', default='dark'),
            'font_scheme': self.pubsub.query(f'{topic_name}/settings/font_scheme', default='js1'),
            'sub_vars': {},
        }
        info = self._render_one(unique_id, info)
        view = self.pubsub.query(f'{topic_name}/instance')
        for unique_id in view.fixed_widgets:
            topic_name = get_topic_name(unique_id)
            obj = self.pubsub.query(f'{topic_name}/instance')
            self._render_one(unique_id, info)
        return None  # cannot undo directly, must undo settings

    def on_action_render(self, value):
        unique_id = get_unique_id(value)
        while not unique_id.startswith('view:'):
            topic_name = get_topic_name(unique_id)
            unique_id = self.pubsub.query(f'{topic_name}/parent')
        return self._render_view(unique_id)

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
            return sub_vars[varname]

        for template in index['templates']:
            self._log.info('render template %s:%s', package, template)
            data = pkgutil.get_data(package, theme_prefix + template).decode('utf-8')
            if data is None:
                self._log.warning('template not found: %s', template)
                return
            s = _template_replace.sub(replace, data)
            path = os.path.join(target_path, template)
            templates[template] = path
            with open(path, 'w', encoding='utf-8') as f:
                f.write(s)

    def _render_images(self, index, sub_vars):
        package = index['render']['src_package']
        theme_prefix = index['render']['src_theme_prefix']
        target_path = index['render']['target_path'].replace('\\', '/')

        for name, image_set in index['images'].items():
            self._log.info('generate images for %s:%s', package, name)
            for source in image_set['sources']:
                svg = pkgutil.get_data(package, theme_prefix + source).decode('utf-8')
                basename, ext = os.path.splitext(source)
                for filename, subs in image_set['targets']:
                    svg_out = svg
                    filename = filename.format(basename=basename, ext=ext)
                    for substr, replace in subs.items():
                        svg_out = svg_out.replace(substr, sub_vars[replace])
                    path = os.path.join(target_path, filename)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(svg_out)


def styled_widget(translated_name):
    """Construct a widget that supports styles.

    :param translated_name: The translated name for this widget.

    This decorator is a mixin that monkey patches the widget
    to add style SETTINGS and methods to fully support styles.
    """

    def on_setting_stylesheet(self, value):
        self.setStyleSheet(value)

    # todo colors, fonts, style_defines

    def inner(cls):
        if not hasattr(cls, 'SETTINGS'):
            cls.SETTINGS = {}
        for key, value in style_settings(translated_name).items():
            cls.SETTINGS.setdefault(key, value)
        cls._colors = None
        cls._fonts = None
        cls._stylesheet = None
        cls.on_setting_stylesheet = on_setting_stylesheet
        return cls
    return inner
