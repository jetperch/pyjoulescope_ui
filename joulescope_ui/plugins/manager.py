# Copyright 2024 Jetperch LLC
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

"""Load and unload plugins for the Joulescope UI.

Note that python only supports the notion of module reload, not unload.
For our implementation, unload means that all classes registered to pubsub
by the module are unregistered.  We then defer reload until needed.

Python packages and imports are complicated.  See:
* https://docs.python.org/3/reference/import.html
* https://docs.python.org/3/library/pkgutil.html
https://docs.python.org/3/library/importlib.html
"""


from joulescope_ui import is_release, get_topic_name, get_instance
from joulescope_ui.pubsub import REGISTRY_MANAGER_TOPICS
from PySide6 import QtCore, QtWidgets
import importlib
import json
import logging
import pkgutil
import os
import sys
from watchdog.observers import Observer


_VIEW = 'registry/view/settings/active'


class PluginManager(QtCore.QObject):
    SETTINGS = {
        'active': {
            'dtype': 'obj',
            'brief': 'The list of active plugins',
            'default': [],
            'flags': ['ro', 'hide', 'skip_undo'],
        },
        'available': {
            'dtype': 'obj',
            'brief': 'The map of available plugin name to detailed info',
            'default': {},
            'flags': ['ro', 'tmp', 'hide', 'skip_undo'],
        },
        'monitor': {
            'dtype': 'str',
            'brief': 'Monitor a plugin for changes',
            'default': None,
        },
        'monitor_reload_delay_ms': {
            'dtype': 'int',
            'brief': 'Monitor reload delay from filesystem changes in milliseconds.',
            'default': 250,
        },
    }

    def __init__(self, parent=None, paths=None):
        self._paths = paths
        self._plugins = {}
        self._mode = None
        self._log = logging.getLogger(__name__)
        super().__init__(parent)
        self._observer = None
        self._change_timer = QtCore.QTimer(self)
        self._change_timer.setSingleShot(True)
        self._change_timer.timeout.connect(self._on_timer)

    def __del__(self):
        self._watch_stop()

    def dispatch(self, event):
        # observer callback, from observer thread (not Qt)
        if '__pycache__' in event.src_path:
            return
        self._log.info('dispatch %s', event)
        self.pubsub.publish(f'{self.topic}/actions/!watch_changed', None)

    def on_action_watch_changed(self):
        self._change_timer.stop()
        self._change_timer.start(self.monitor_reload_delay_ms)

    def _on_timer(self):
        if self.monitor:
            self.on_action_load(self.monitor)

    def _watch_stop(self):
        observer, self._observer = self._observer, None
        if observer is not None:
            self._log.info('watch stop')
            observer.unschedule_all()
            observer.stop()
            observer.join()

    def _watch_start(self, path):
        self._watch_stop()
        if not path:
            return
        self._log.info('watch start %s', path)
        self._observer = Observer()
        self._observer.schedule(self, path, recursive=True)
        self._observer.start()

    def on_pubsub_register(self):
        if self._paths is None:
            path = self.pubsub.query('common/settings/paths/plugins')
            if not os.path.isdir(path):
                os.makedirs(path)
            readme_file = os.path.join(path, 'README.txt')
            if not os.path.isfile(readme_file):
                with open(readme_file, 'wt') as f:
                    f.write('Default Joulescope UI plugin directory.  Add plugin packages here\n')
            self._paths = [path]
        paths = [os.path.dirname(os.path.abspath(path)) for path in reversed(self._paths)]
        for path in paths:
            sys.path.insert(0, path)
        if is_release:
            os.environ['PYTHONPATH'] = os.path.pathsep.join(paths)
        self.pubsub.subscribe(REGISTRY_MANAGER_TOPICS.REGISTRY_ADD, self._on_registry_add)
        self.pubsub.subscribe(REGISTRY_MANAGER_TOPICS.REGISTRY_REMOVE, self._on_registry_remove)
        for item in pkgutil.iter_modules(self._paths):
            if not item.ispkg:
                continue
            if isinstance(item.module_finder, importlib.machinery.FileFinder):
                path = item.module_finder.path
                json_file = os.path.join(path, item.name, 'index.json')
                try:
                    with open(json_file, 'r') as f:
                        info = json.load(f)
                except Exception:
                    self._log.warning('Could not load index.json for %s', item)
                    info = {}
                readme_file = os.path.join(path, item.name, 'README.md')
                if os.path.exists(readme_file):
                    with open(readme_file, 'rt') as f:
                        info['description'] = f.read()
                info['path'] = os.path.join(path, item.name)
            else:
                self._log.warning('Unsupported module_finder for item %s', item)
                continue
            info['state'] = 'new'
            if item.name in self._plugins:
                self._log.warning('Duplicate plugin name: %s', item.name)
                continue
            self._plugins[item.name] = info
        self.available = self._plugins
        for plugin in self.active:
            self.on_action_load(plugin)
        self.on_setting_monitor(self.monitor)

    def on_setting_monitor(self, value):
        if value not in self._plugins:
            self._watch_stop()
            return
        info = self._plugins[value]
        path = info['path']
        self._watch_start(path)

    def _on_registry_add(self, value):
        if self._mode is None:
            return
        action, name = self._mode
        if action != 'load':
            return
        self._plugins[name]['register'].append(value)

    def _on_registry_remove(self, value):
        if self._mode is None:
            return
        action, name = self._mode
        if action != 'unload':
            return
        try:
            self._plugins[name]['register'].remove(value)
        except ValueError:
            pass

    def _active_update(self):
        self.active = [key for key, value in self._plugins.items() if value['state'] == 'loaded']

    def on_action_load(self, value):
        if value not in self._plugins:
            self._log.warning('load %s but not available', value)
            return
        info = self._plugins[value]
        module_name = 'plugins.' + value
        self._log.info('load %s', value)
        self._mode = 'load', value
        try:
            view = None
            if info['state'] == 'loaded':
                view = self.pubsub.query(_VIEW, default=None)
                self.pubsub.publish(_VIEW, None)
                self.on_action_unload(value)
            info['register'] = []
            if info['state'] == 'new':
                importlib.import_module(module_name)
            else:
                self._log.info('reload %s', value)
                module = importlib.import_module(module_name)
                importlib.reload(module)
            self._mode = None
            if view is not None:
                self.pubsub.publish(_VIEW, view)
        finally:
            self._mode = None
        info['state'] = 'loaded'
        self._active_update()
        return [f'{get_topic_name(self)}/actions/unload', value]

    def _unregister(self, unique_id):
        obj = get_instance(unique_id, default=None)
        if isinstance(obj, QtWidgets.QWidget):
            self.pubsub.publish('registry/view/actions/!widget_close', unique_id)
        else:
            self.pubsub.unregister(unique_id)

    def on_action_unload(self, value):
        if value not in self._plugins:
            self._log.warning('unload %s but not available', value)
            return
        info = self._plugins[value]
        if info['state'] != 'loaded':
            self._log.info('unload %s but state %s - skip', value, info['state'])
            return
        self._log.info('unload %s | %s', value, info['register'])
        while len(info['register']):
            unique_id = info['register'].pop(0)
            for instance in self.pubsub.query(f'{get_topic_name(unique_id)}/instances', default=[]):
                self._unregister(instance)
            self._unregister(unique_id)
        info['state'] = 'unloaded'
        self._active_update()
        return [f'{get_topic_name(self)}/actions/load', value]
