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
from PySide6 import QtGui
from joulescope_ui import N_, json, pubsub_singleton, get_unique_id, get_topic_name, get_instance
from joulescope_ui.sanitize import str_to_filename
from . import color_file
from .style_editor import StyleEditorDialog
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


def load_colors(obj, color_scheme=None, pubsub=None):
    if pubsub is None:
        pubsub = pubsub_singleton
    obj = get_instance(obj, pubsub=pubsub)
    topic_name = get_topic_name(obj)
    colors = pubsub.query(f'{topic_name}/settings/colors', default=None)
    if colors is not None:
        return colors
    if isinstance(obj, type):
        cls = obj
        instance_of_unique_id = pubsub.query(f'{topic_name}/instance_of', default=None)
        if instance_of_unique_id is not None:
            # get class override colors
            instance_of_topic = get_topic_name(instance_of_unique_id)
            colors = pubsub.query(f'{instance_of_topic}/settings/colors', default=None)
            if colors is not None:
                return colors
    else:
        cls = obj.__class__

    # get class default colors
    package = '.'.join(cls.__module__.split('.')[:-1])
    if color_scheme is None:
        color_scheme = obj.style_manager_info['color_scheme']
    colors = _get_data(package, f'styles/color_scheme_{color_scheme}.txt', default='', encoding='utf-8')
    colors = color_file.parse_str(colors)
    return colors


class StyleManager:

    def __init__(self, pubsub):
        self._log = logging.getLogger(__name__)
        self.pubsub = pubsub
        self._dialog = None
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
        obj = get_instance(unique_id, pubsub=self.pubsub)
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

            children = self.pubsub.query(f'{topic_name}/children', default=[])
            fonts = self.pubsub.query(f'{topic_name}/settings/fonts', default=None)
            style_defines = self.pubsub.query(f'{topic_name}/settings/style_defines', default=None)

            colors = load_colors(obj, color_scheme=info['color_scheme'], pubsub=self.pubsub)
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
        obj.style_manager_info = info  # record style manager info for future renderings
        self._log.info('render %s: done in %.3f seconds', unique_id, time.time() - t_start)
        for child in children:
            self._render_one(child, dict(info))
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
            self._render_one(unique_id, info)
        return None  # cannot undo directly, must undo settings

    def on_action_edit(self, value):
        obj = get_instance(value)
        self._dialog = StyleEditorDialog(obj=obj)
        self._dialog.show()
        # todo clear on close

    def on_action_render(self, value):
        try:
            unique_id = get_unique_id(value)
        except ValueError:
            return None  # still being registered, will get called later.
        if unique_id.startswith('view:'):
            return self._render_view(unique_id)
        topic_name = get_topic_name(unique_id)
        obj = self.pubsub.query(f'{topic_name}/instance')
        if hasattr(obj, 'style_manager_info'):
            self._render_one(unique_id, obj.style_manager_info)
            return None
        while True:
            if unique_id.startswith('view:'):
                return self._render_view(unique_id)
            topic_name = get_topic_name(unique_id)
            next_unique_id = self.pubsub.query(f'{topic_name}/parent')
            next_topic_name = get_topic_name(next_unique_id)
            next_obj = self.pubsub.query(f'{next_topic_name}/instance')
            if hasattr(next_obj, 'style_manager_info'):
                self._render_one(unique_id, next_obj.style_manager_info)
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


def style_edit_action_create(obj, menu):
    def on_action():
        pubsub_singleton.publish('registry/StyleManager:0/actions/!edit', obj)

    action = QtGui.QAction(menu)
    action.setText(N_('Style'))
    action.triggered.connect(on_action)
    menu.addAction(action)
    return action


def styled_widget(translated_name):
    """Construct a widget that supports styles.

    :param translated_name: The translated name for this widget.

    This decorator is a mixin that monkey patches the widget
    to add style SETTINGS and methods to fully support styles.
    """

    def on_setting_stylesheet(self, value):
        self.setStyleSheet(value)

    def on_setting_colors(self, value):
        pubsub_singleton.publish(f'registry/StyleManager:0/actions/!render', self)

    def on_setting_fonts(self, value):
        pubsub_singleton.publish(f'registry/StyleManager:0/actions/!render', self)

    def on_setting_style_defines(self, value):
        pubsub_singleton.publish(f'registry/StyleManager:0/actions/!render', self)

    def inner(cls):
        if not hasattr(cls, 'SETTINGS'):
            cls.SETTINGS = {}
        for key, value in style_settings(translated_name).items():
            cls.SETTINGS.setdefault(key, value)
        cls._colors = None
        cls._fonts = None
        cls._stylesheet = None
        cls.on_setting_stylesheet = on_setting_stylesheet
        cls.on_setting_colors = on_setting_colors
        cls.on_setting_fonts = on_setting_fonts
        cls.on_setting_style_defines = on_setting_style_defines
        return cls
    return inner
