# Copyright 2023 Jetperch LLC
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

def tooltip_format(header: str, body: str) -> str:
    """Format a tooltip.

    :param header: The already translated header string.
        The header should be a plain string to be automatically formatted.
    :param body: The already translated body string.
        The body may already be HTML formatted.
        Otherwise, one or more empty lines will be treated as the start of
        a paragraph.
    :return: The HTML formatted tooltip.
    """
    is_in_list = False
    if body is None:
        body = ''
    elif not body.startswith('<'):
        parts = []
        between = True
        for line in body.split('\n'):
            line = line.strip()
            if len(line):
                if between:
                    parts.append('\n<p>')
                    between = False
                else:
                    parts.append('\n')
                if line.startswith('*'):
                    if not is_in_list:
                        parts.append('<ul>')
                        is_in_list = True
                    parts.append('<li>')
                    parts.append(line[1:].strip())
                    parts.append('</li>')
                else:
                    if is_in_list:
                        parts.append('</ul>')
                        is_in_list = False
                    parts.append(line)
            elif not between:
                parts.append('</p>')
                between = True
        if not between:
            parts.append('</p>')
        body = ''.join(parts)
    return f'<html><head/><body><h3>{header}</h3>{body}</body></html>'
