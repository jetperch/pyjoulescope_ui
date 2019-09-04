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

"""This module contains the example 02 plugin that adds markers."""

import numpy as np

PLUGIN = {
    'name': 'Example 02',  # The user-meaningful name
    'description': 'Markers demo plugin',  # A user-meaningful description
}


class MyPlugin:
    """Example 02 plugin implementation."""

    def run(self, data):
        pass

    def run_post(self, data):
        x = data.sample_count / data.sample_frequency
        data.marker_single_add(0.5 * x)
        data.marker_dual_add(0.25 * x, 0.75 * x)


def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('Example/02', MyPlugin)
    return True
