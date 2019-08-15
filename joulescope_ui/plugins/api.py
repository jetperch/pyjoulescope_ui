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
* plugin_register: A function(PluginServiceAPI, app_config, plugin_config)
  that registers the module's functionality.

The plugin module may contain other definitions and statements,
but they are not used directly by the plugin API.  For a basic example,
see the example_01.py file.
"""


class RangeToolInvocation:
    """The object skeleton provided to RangeTool instances."""

    def __init__(self):
        self.sample_count = None        #: The number of samples to process
        self.sample_frequency = None    #: The sampling frequency in Hertz
        self.app_config = None          #: The application configuration data structure
        self.plugin_config = None       #: The plugin configuration data structure for this plugin.
        self.calibration = None         #: The calibration information associated with the data.
        self.statistics = None          #: The statistics (see :meth:`joulescope.driver.statistics_get`).

    def iterate(self, samples_per_iteration=None):
        """Return an iterable over the data.

        :param samples_per_iteration: The number of samples to provide with
            each iteration.  None (default) provides 1 second chunks.
        """
        pass

    def progress(self, fraction):
        """Manually update the progress bar.

        :param fraction: The fraction complete from 0.0 (just starting) to
            1.0 (done).

        If using the provided iterable, the progress bar will be updated
        automatically.
        """
        pass

    def samples_get(self):
        """Get all the data.

        If the user selects too much data, then this method will fail.
        Whenever possible, prefer using the iterate method.
        """
        pass

    def marker_single_add(self, x):
        """Add a single marker to the current oscilloscope view.

        :param x: The x-axis location relative to the start of this range.

        The value x must be within the range of this invocation which is
        between 0.0 and data.sample_count / data.sample_frequency.
        """
        pass

    def marker_dual_add(self, x1, x2):
        """Add a dual markers to the current oscilloscope view.

        :param x1: The first x-axis location relative to the start of this range.
        :param x2: The second x-axis location relative to the start of this range.

        The values x1 and x2 must be within the range of this invocation which is
        between 0.0 and data.sample_count / data.sample_frequency.
        """
        pass


class RangeTool:
    """The object skeleton to be provided to range_tool_register()."""

    def run_pre(self, data: RangeToolInvocation):
        """Optional method run before starting the processing thread.

        :param data: The :class:`RangeToolInvocation` instance to process.
        :return: None on success or error message.
        """
        pass

    def run(self, data: RangeToolInvocation):
        """Required method run in the processing thread.

        :param data: The :class:`RangeToolInvocation` instance to process.
        :return: None on success or error message.
        """
        pass

    def run_post(self, data: RangeToolInvocation):
        """Optional method run after completing the processing thread.

        :param data: The :class:`RangeToolInvocation` instance to process.
        :return: None on success or error message.
        """
        pass


class PluginServiceAPI:
    """The API provided to each plugin's plugin_register() function.

     :attr app_config: The application configuration dict struct.
     :attr plugin_config: The plugin configuration dict struct.
     """

    def range_tool_register(self, name, tool):
        """Add a data range tool.

        :param name: The name for the tool which can be hierarchical separated
            by ".".  For example, "Analysis.USB Inrush".
        :param tool: The callable() to activate the tool. The callable must
            return an object compatible with :class:`RangeTool`, so the
            callable can be a class.  Since the user can select an arbitrary
            range, the number of samples and required memory can be very large.
            The framework cannot guarantee that all samples can fit into
            memory.  The RangeToolInvocation.iterable() allows an convenient,
            memory-friendly access of the sample data.
        """
        raise NotImplementedError()

    # def range_measurement_register(self, name, fn):
    # def streaming_filter_register(self, name, fn)

