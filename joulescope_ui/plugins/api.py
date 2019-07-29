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

"""This module defines the Joulescope UI plugin interface.

A plugin must be a valid python module with definitions:
* PLUGIN: A dict containing the plugin metadata, including any configuration
  options that are available to the user.
* register_plugin: A function(PluginServiceAPI, app_config, plugin_config)
  that registers the module's functionality.

The plugin module may contain other definitions and statements,
but they are not used directly by the plugin API.
"""


PLUGIN = {
    'name': 'Plugin Name',
    'description': 'User-meaningful plugin description',
}


class RangeToolInvocation:

    def __init__(self):
        self.sample_count = None
        self.sample_frequency = None
        self.plugin_config = None
        self.app_config = None
        self.calibration = None

    def iterate(self, samples_per_iteration):
        pass

    def progress(self, fraction):
        pass

    def samples_get(self):
        """Just get all the data which may run out of memory."""
        pass


class RangeTool:

    def run_pre(self, data: RangeToolInvocation):
        pass

    def run(self, data: RangeToolInvocation):
        pass

    def run_post(self, data: RangeToolInvocation):
        pass


class PluginServiceAPI:

    def range_tool_register(self, name, tool):
        """Add a data range tool.

        :param name: The name for the tool which can be hierarchical separated
            by ".".  For example, "Analysis.USB Inrush".
        :param tool: The function() called when the user activates the tool. The
            function must return an object compatible with :class:`RangeTool`.
            Since the user can select an arbitrary range, the number of samples
            and required memory can be very large.  The framework cannot
            guarantee that all samples can fit into memory.  The
            RangeToolInvocation.iterable() allows an convenient,
            memory-friendly access of the sample data.
        """
        raise NotImplementedError()

    # def range_measurement_register(self, name, fn):
    # def streaming_filter_register(self, name, fn)

