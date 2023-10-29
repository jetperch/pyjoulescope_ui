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

"""Load and save color files."""


ColorsType = dict[str, str]
_re_color_pattern = re.compile(r'^#[0-9a-fA-F]*$')
_re_update_pattern = re.compile(r'^(\s*)([^\s=]+)(\s*=\s*)(#[0-9a-fA-F]+)(\s*#?.*$)')


def load_file(f) -> ColorsType:
    """Load colors from a file."""
    if isinstance(f, str):
        with open(f, 'rt') as fin:
            s = fin.read()
    else:
        s = f.read()
    return parse_str(s)


def parse_str(s: str) -> ColorsType:
    """Parse colors from a string.

    :param s: The string containing color definitions.
    :return: The map of color name strings to #rrggbbaa color strings.
    :raises ValueError: on errors.

    Why a custom file format?  We want a format that is easy to read,
    easy to comment, and easy for both code and humans to update.
    The Joulescope UI color files are a custom format that is similar
    to INI files but without the section headers.

    The color file looks like:

        # This is a comment
        my.color.1 = #ff0000
        my.color.2 = #ff0000        # Can have trailing comment, format is rrggbb, red opaque
        my.color.3 = #ff0000ff      # Format is rrggbbaa, red opaque
        my.color.4 = #ff000080      # Format is rrggbbaa, red, 50% transparent
        good_color = #00ff00        # green opaque

        # Another comment
        another.color = #0000ff80   # blue, 50% transparent
    """
    colors = {}
    line_num = 0
    for line in s.split('\n'):
        line_num += 1
        line = line.strip()
        if not len(line) or line[0] == '#':  # comment line
            continue
        name, value = line.split('=')
        name = name.strip()
        value = value.strip()
        if not len(name):
            raise ValueError(f'invalid name on line {line_num}: {line}')
        if not len(value):
            raise ValueError(f'invalid value on line {line_num}: {line}')
        if value[0] == '#':
            idx = value[1:].find('#')
            if idx > 0:  # trailing line comment
                value = value[:1 + idx].strip()
        if _re_color_pattern.match(value):
            pass  # good!
        else:
            raise ValueError(f'invalid value on line {line_num}: {line}')
        value = value.strip()
        if len(value) == 7:
            value = value + 'ff'
        elif len(value) != 9:
            raise ValueError(f'Invalid color {line_num} : {line} -> {value}')
        colors[name] = value
    return colors


def update_str(s: str, colors: ColorsType):
    """Update the colors defined in the string.

    :param s: The color definition string.
    :param colors: The new values for the colors.
    :return: The updated color definition string with color values replaced
        the values in colors when color names match.
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
            if name in colors:
                color = colors[name]
                s = f'{m.group(1)}{m.group(2)}{m.group(3)}{color}{m.group(5)}'
                output.append(s)
        else:
            output.append(line)
    return '\n'.join(output)


def update_path(p: str, colors: ColorsType):
    """Update the color definition file path.

    :param p: The path to the color definition file.
    :param colors: The new values for the colors.
    """
    with open(p, 'rt') as f:
        s = f.read()
    s = parse_str(s, colors)
    with open(p, 'wt') as f:
        f.write(s)
