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


from PySide6 import QtGui
import collections.abc
import json


def _validate_str(x):
    if x is not None and not isinstance(x, str):
        raise ValueError(f'validate str failed for {x}')
    return x


def _validate_bytes(x):
    if x is not None and not isinstance(x, bytes):
        raise ValueError(f'validate bytes failed for {x}')
    return x


def _validate_float(x):
    return float(x)


def _validate_int(x, x_min, x_max):
    x = int(x)
    if x_min <= x < x_max:
        return x
    raise ValueError(f'validate int {x} out of range [{x_min}, {x_max})')


def _validate_bool(x):
    if isinstance(x, str):
        x = x.lower()
    if x in [False, 0, '0', 'no', 'off', 'disable', 'disabled', 'false', 'inactive', '', None]:
        return False
    if x in [True, 1, '1', 'yes', 'on', 'enable', 'enabled', 'true', 'active']:
        return True
    raise ValueError(f'validate bool failed for {x}')


def _validate_font(x):
    # Example: "Lato,48,-1,5,87,0,0,0,0,0,Black"
    return x  # todo


def _validate_color(x):
    c = None
    if isinstance(x, str):
        c = QtGui.QColor(x)
    elif isinstance(x, collections.abc.Sequence):
        if len(x) in [3, 4]:
            c = QtGui.QColor(*x)
    if c is None or not c.isValid():
        raise ValueError(f'Invalid color {x}')
    r, g, b, a = c.getRgb()
    return f'#{a:02x}{r:02x}{g:02x}{b:02x}'


def _validate_none(x):
    if x is None:
        return x
    raise ValueError(f'validate none failed for {x}')


def _validate_node(x):
    if x is None:
        return x
    raise ValueError(f'validate node cannot assign value: {x}')


def _validate_unique_strings(x):
    return [_validate_str(z) for z in x]


_INT_RANGE = {
    'u8': (0, 2 ** 8),
    'u16': (0, 2 ** 16),
    'u32': (0, 2 ** 32),
    'u64': (0, 2 ** 64),
    'i8':  (-2 ** 7, 2 ** 7),
    'i16': (-2 ** 15, 2 ** 15),
    'i32': (-2 ** 31, 2 ** 31),
    'i64': (-2 ** 63, 2 ** 63),
}


_VALIDATORS = {
    'obj': lambda x: x,
    'str': _validate_str,
    'bytes': _validate_bytes,
    'bin': _validate_bytes,
    'float': _validate_float,
    'f32': _validate_float,
    'f64': _validate_float,
    'int': lambda x: int(x),
    'u8': lambda x: _validate_int(x, 0, 2 ** 8),
    'u16': lambda x: _validate_int(x, 0, 2 ** 16),
    'u32': lambda x: _validate_int(x, 0, 2 ** 32),
    'u64': lambda x: _validate_int(x, 0, 2 ** 64),
    'i8': lambda x: _validate_int(x, -2 ** 7, 2 ** 7),
    'i16': lambda x: _validate_int(x, -2 ** 15, 2 ** 15),
    'i32': lambda x: _validate_int(x, -2 ** 31, 2 ** 31),
    'i64': lambda x: _validate_int(x, -2 ** 63, 2 ** 63),
    'bool': _validate_bool,
    'font': _validate_font,
    'color': _validate_color,
    'none': _validate_none,
    'node': _validate_node,
    'unique_strings': _validate_unique_strings,
}


_ATTRS = ['dtype', 'brief', 'detail', 'default', 'options', 'range', 'format', 'flags']


class Metadata:

    def __init__(self, *args, **kwargs):
        """Define and validate topic metadata.

        Metadata(metadata: Metadata)
        Metadata(d: dict)
        Metadata(json: str)
        Metadata(dtype, brief=None, detail=None, default=None, options=None, range=None, format=None, flags=None)

        :param dtype: The value data type.
            * obj: can be retained, but cannot be saved across sessions
            * str
            * bytes, bin
            * float, f32, f64
            * int, u8, u16, u32, u64, i8, i16, i32, i64
            * bool
            * font
            * color
            * none (used for events without values)
            * node (hierarchical node only, publish not allowed)
            * unique_strings: A ordered list of unique strings.
              If options is given, the list contents are constrained to the
              options elements.
        :param brief: (required) The brief description for this topic (required).
        :param detail: (recommended) The detailed description for this topic (recommended).
        :param default: (optional) The default initial value for the topic.
        :param options: (optional) The allowed values for this topic.
            The options are specified as a list,
            where each option is each a flat list of:
            [value [, alt1 [, ...]]] The alternates must be given in preference order.
            The first value must be the value as dtype. The second value alt1
            (when provided) is used to automatically populate user interfaces,
            and it can be the same as value. Additional values will be
            interpreted as equivalents.
        :param range: (optional) The allowed integer range, inclusive.
            The list of [v_min, v_max] or [v_min, v_max, v_step].
            Both v_min and v_max are inclusive. v_step defaults to 1 if omitted.
        :param format: (optional) The formatting hints string.
            * version: The u32 dtype should be interpreted as major8.minor8.patch16.
        :param flags: (optional) The list of flag strings which include:
            * ro: This topic cannot be updated.
            * hide: This topic should not appear in the user interface.
            * dev: Developer option that should not be used in production.
            * skip_undo: This topic should not be added to the undo list.
            * tmp: Temporary value that is not persisted.
            * noinit: Do not attempt to get default value from class or persist.
        """
        if len(args) == 1 and len(kwargs) == 0:
            v = args[0]
            if isinstance(v, Metadata):
                kwargs = v.to_map()
            elif isinstance(v, dict):
                kwargs = v
            elif isinstance(v, str):
                kwargs = json.loads(v)
            else:
                raise ValueError('invalid meta argument')
        else:
            for idx, arg in enumerate(args):
                kwargs[_ATTRS[idx]] = arg

        if 'dtype' not in kwargs:
            raise ValueError('dtype required')
        self.dtype = kwargs['dtype']
        if not callable(self.dtype) and self.dtype not in _VALIDATORS:
            raise ValueError(f'unsupported dtype {self.dtype}')

        self.brief = kwargs.get('brief')
        self.detail = kwargs.get('detail')
        self.default = None
        self.options = None
        self._options_map = None
        self.range = None
        self.format = kwargs.get('format')
        self.flags = kwargs.get('flags')
        if self.flags is None:
            self.flags = []

        if callable(self.dtype):
            self._validate_fn = self.dtype
        else:
            self._validate_fn = _VALIDATORS.get(self.dtype)
            if not callable(self._validate_fn):
                raise ValueError(f'validate invalid dtype={self.dtype}')

        options = kwargs.get('options')
        if options is not None:
            self.options = options
            self._options_map = {}
            for option in options:
                x = option[0]
                for y in option:
                    self._options_map[y] = x

        v_range = kwargs.get('range')
        if v_range is not None:
            r = [int(x) for x in v_range]
            if len(r) == 3:
                pass
            elif len(r) == 2:
                r.append(1)
            else:
                raise ValueError(f'Invalid range specification range')
            self.range = r

        default = kwargs.get('default')
        if default is not None:
            self.default = self.validate(default)

    def __repr__(self):
        z = [f'{p}={repr(getattr(self, p))}' for p in _ATTRS]
        s = ', '.join(z)
        return f'Metadata({s})'

    def validate(self, value):
        """Validate a value.

        :param value: The value to validate.
        :return: The validated value.
        :raise ValueError: If validation fails.
        """
        if self.options is not None:
            try:
                if self.dtype == 'unique_strings':
                    value = [self._options_map[v] for v in value]
                else:
                    value = self._options_map[value]
            except KeyError:
                raise ValueError(f'value {value} not in options')
        value = self._validate_fn(value)
        if self.dtype == 'unique_strings':
            d = dict([v, None] for v in value)
            if len(d) != len(value):
                raise ValueError(f'value {value} contains duplicates')
        if self.range is not None:
            x_min, x_max, x_step = self.range
            if not x_min <= value <= x_max:
                raise ValueError(f'value {value} out of range {self.range}')
            x = (value - x_min) % x_step
            if x != 0:
                raise ValueError(f'value {value} not on increment {self.range}')
        return value

    def to_map(self):
        return dict([(p, getattr(self, p)) for p in _ATTRS if getattr(self, p) is not None])
