# Copyright 2020 Jetperch LLC
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

"""VERY simple template class.

This template use Jinja-style templates with {% var %} replacement
which gives much cleaner syntax than Python's built-in string formatting
methods, at least for CSS.
"""


import re


_r = re.compile(r'{%\s*([a-zA-Z0-9_]+)\s*%}')


def render(template, **values):
    """Render the template.

    :param template: The template to render.
    :param values: The values to replace in the template.
    :return: The template with values replaced.

    Here is an example template:

        template = '''\
            QLabel {
              background-color: {% background_color %};
              color: {% color %};
            }
        '''

        render(template, background_color='black', color='green')
    """

    def replace(matchobj):
        return values[matchobj.group(1)]
    return _r.sub(replace, template)
