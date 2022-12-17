# Copyright 2022 Jetperch LLC
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

import re

"""Load and save parameter (font and style_defines) files."""


_re_update_pattern = re.compile(r'^(\s*)([^\s=]+)(\s*=\s*)(\S[^#]*)(#?.*$)')
_re_value_strip = re.compile(r'^(.*\S)(\s*)')
ParameterType = dict[str, str]


def load_file(f) -> ParameterType:
    """Load parameter entries from a file."""
    if isinstance(f, str):
        with open(f, 'rt') as fin:
            s = fin.read()
    else:
        s = f.read()
    return parse_str(s)


def parse_str(s: str) -> ParameterType:
    """Parse entries from a string.

    :param s: The string containing entry definitions.
    :return: The map of parameter names to value strings.
    :raises ValueError: on errors.

    Why a custom file format?  We want a format that is easy to read,
    easy to comment, and easy for both code and humans to update.
    The Joulescope UI parameter files are a custom format that is similar
    to INI files but without the section headers.

    The color file looks like:

        # This is a comment
        my.param.1 = my_value
        my.param.2 = This is a string

        # Another comment
        another.param = another_value   # comment, good stuff
    """
    parameters = {}
    line_num = 0
    for line in s.split('\n'):
        line_num += 1
        idx = line.find('#')
        if idx >= 0:
            line = line[:idx]
        line = line.strip()
        if not len(line):  # comment line
            continue
        name, value = line.split('=')
        name = name.strip()
        value = value.strip()
        parameters[name] = value
    return parameters


def update_str(s: str, entries: ParameterType):
    """Update the colors defined in the string.

    :param s: The parameter definition string.
    :param entries: The new values for the parameters.
    :return: The updated parameter definition string with
        parameter values replaced the values in entries
         when the parameter names match.
    """
    output = []
    line_num = 0
    for line in s.split('\n'):
        line_num += 1
        line_strip = line.strip()
        if not len(line_strip) or line_strip[0] == '#':  # comment line
            output.append(line)
            continue
        m = _re_update_pattern.match(line)
        if m:
            name = m.group(2)
            m2 = _re_value_strip.match(m.group(4))
            if name in entries:
                value = entries[name]
                s = f'{m.group(1)}{m.group(2)}{m.group(3)}{value}{m2.group(2)}{m.group(5)}'
                output.append(s)
        else:
            output.append(line)
    return '\n'.join(output)


def update_path(p: str, entries: ParameterType):
    """Update the parameter definition file path.

    :param p: The path to the color definition file.
    :param entries: The new values for the parameters.
    """
    with open(p, 'rt') as f:
        s = f.read()
    s = parse_str(s, entries)
    with open(p, 'wt') as f:
        f.write(s)
