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

from .cdf_impl import CdfImpl


PLUGIN = {
    'name': 'Complementary Cumulative Distribution Function',
    'description': 'Complementary Cumulative Distribution Function for current/voltage data',
}


class CCDF(CdfImpl):

    def __init__(self):
        CdfImpl.__init__(self, 'ccdf')


def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('Analysis/CCDF', CCDF)
    return True
