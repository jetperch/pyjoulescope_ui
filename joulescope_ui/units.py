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


FIELD_UNITS_SI = {
    'current': 'A',
    'charge': 'C',
    'voltage': 'V',
    'power': 'W',
    'energy': 'J',
}


FIELD_UNITS_INTEGRAL = {
    'current': 'charge',
    'power': 'energy',
}


UNIT_CONVERTER = {
    # (from, to): conversion function
    ('C', 'Ah'): lambda x: x / 3600.0,
    ('Ah', 'C'): lambda x: x * 3600.0,
    ('J', 'Wh'): lambda x: x / 3600.0,
    ('Wh', 'J'): lambda x: x * 3600.0,
}


def convert_units(value, input_units, output_units):
    key = (input_units, output_units)
    fn = UNIT_CONVERTER.get(key)
    if fn is not None:
        return {
            'value': fn(value),
            'units': output_units}
    return {
        'value': value,
        'units': input_units}

