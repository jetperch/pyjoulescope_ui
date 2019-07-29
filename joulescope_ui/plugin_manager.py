# Copyright 2019 Jetperch LLC
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

from joulescope_ui.plugins import PLUGINS_BUILTIN


class RangeTool:

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn


class PluginImpl:

    def __init__(self, manager):
        self._manager = manager
        self._undo = []

    def range_tool_register(self, name, fn):
        tool = RangeTool(name, fn)
        self._manager.range_tools[name] = tool
        self._undo.append(lambda: self._manager.range_tools.pop(name, None))


class PluginManager:

    def __init__(self):
        self.context = []
        self.range_tools = {}  # passed read-only to application, do not replace!

    def __enter__(self):
        c = PluginImpl(self)
        self.context.append(c)
        return c

    def __exit__(self, exc_type, exc_val, exc_tb):
        c = self.context.pop()
        pass

    def builtin_register(self, app_config):
        for plugin in PLUGINS_BUILTIN:
            meta = plugin.PLUGIN
            with self as c:
                plugin_config = app_config.get('plugins', {}).get(meta['name'], {})
                plugin.register_plugin(c, app_config=app_config, plugin_config=plugin_config)
