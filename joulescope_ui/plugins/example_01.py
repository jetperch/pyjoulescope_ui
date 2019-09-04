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

"""This module contains the example 01 plugin."""

import numpy as np

PLUGIN = {
    'name': 'Example 01',  # The user-meaningful name
    'description': 'Trivial example plugin',  # A user-meaningful description
}


class MyPlugin:
    """Example 01 plugin implementation."""

    def run(self, data):
        """Run the plugin across the data.

        :param data: The :class:`RangeToolInvocation` instance.
        :return: None on success or error message on failure.
        """
        for idx, block in enumerate(data):
            current = float(np.mean(block['current']['value']))
            print(f'{idx}: {current}')


def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('Example/01', MyPlugin)
    return True
