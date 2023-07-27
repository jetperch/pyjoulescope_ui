#!/usr/bin/env python3

# Copyright 2018-2022 Jetperch LLC
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

import sys
import argparse
from joulescope_ui import entry_points


def get_parser():
    entry_point_names = []
    parser = argparse.ArgumentParser(
        description='Joulescope UI command line tools.',
    )
    subparsers = parser.add_subparsers(
        dest='subparser_name',
        help='The command to execute')

    for entry_point in entry_points.__all__:
        default_name = entry_point.__name__.split('.')[-1]
        name = getattr(entry_point, 'NAME', default_name)
        entry_point_names.append(name)
        cfg_fn = entry_point.parser_config
        p = subparsers.add_parser(name, help=cfg_fn.__doc__)
        cmd_fn = cfg_fn(p)
        if not callable(cmd_fn):
            raise ValueError(f'Invalid command function for {name}')
        p.set_defaults(func=cmd_fn)

    subparsers.add_parser('help',
                          help='Display the command help. ' +
                               'Use [command] --help to display help for a specific command.')

    return parser, entry_point_names


def run():
    parser, entry_point_names = get_parser()
    if len(sys.argv) == 1:
        sys.argv.append('ui')
    elif sys.argv[1] not in entry_point_names:
        sys.argv.insert(1, 'ui')

    args = parser.parse_args()
    if args.subparser_name is None or args.subparser_name.lower() in ['help']:
        parser.print_help()
        parser.exit()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(run())
