# Copyright 2026 Jetperch LLC
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

"""One-shot command-line client for the Joulescope UI TCP server.

Each invocation discovers the server credentials (``server.json``), connects,
performs a single operation, prints one JSON object to stdout, and exits.
Intended for interactive automation (agents, shell scripts) against a UI
started with ``--tcp-server``; the pytest suite uses
:class:`uitest.harness.UiSession` instead.

Usage::

    python ci/uitest/cli.py ping
    python ci/uitest/cli.py screenshot out.png --widget WaveformWidget:0
    python ci/uitest/cli.py view multimeter

Exit codes: 0 success; 2 credentials missing/stale or connection refused
(UI not running with ``--tcp-server``); 3 request timeout; 4 server-reported
error; 1 anything else.

This CLI deliberately cannot launch or close the UI: closing (and especially
config-clearing) a developer's live session must remain an explicit,
user-visible action.
"""

import argparse
import dataclasses
import json
import os
import sys
import time

# Allow both `python ci/uitest/cli.py` from any cwd and `python -m uitest.cli`
# with `ci/` on sys.path; also make `joulescope_ui` importable from the repo.
_CI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_DIR = os.path.dirname(_CI_DIR)
for _p in (_CI_DIR, _REPO_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from uitest import discover, qt  # noqa: E402


_VIEW_TOPIC = 'registry/view/settings/active'
_POLL_INTERVAL = 0.1


def _json_default(obj):
    """Best-effort JSON conversion for numpy scalars/arrays and bytes."""
    if isinstance(obj, (bytes, bytearray)):
        return {'__type__': 'bytes', 'length': len(obj)}
    if callable(getattr(obj, 'item', None)) and getattr(obj, 'size', None) == 1:
        return obj.item()
    if callable(getattr(obj, 'tolist', None)) and getattr(obj, 'size', 0) <= 64:
        return obj.tolist()
    return repr(obj)


def _emit(value, file=None):
    print(json.dumps(value, default=_json_default), file=file)


def _fail(exit_code, message):
    _emit({'error': message}, file=sys.stderr)
    return exit_code


def _parse_value(s):
    """Parse a command-line value as JSON, falling back to the raw string."""
    try:
        return json.loads(s)
    except ValueError:
        return s


def _wait_for_value(client, topic, value, timeout):
    """Poll ``query(topic)`` until it equals ``value`` (read-after-write).

    :raises TimeoutError: if the value is not observed within ``timeout``.
    """
    deadline = time.monotonic() + timeout
    while True:
        if client.query(topic) == value:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f'{topic} did not become {value!r} within {timeout} s')
        time.sleep(_POLL_INTERVAL)


def _iter_paths(node, path=''):
    """Yield ``(path, node)`` for every widget in a ``qt_inspect`` tree.

    Paths use the same syntax the server resolves: objectName when set,
    else ``ClassName:index`` with the index 0-based among same-class siblings.
    """
    yield path, node
    class_counts = {}
    for child in node.get('children', []) or []:
        cls = child.get('class', 'QWidget')
        idx = class_counts.get(cls, 0)
        class_counts[cls] = idx + 1
        segment = child.get('objectName') or f'{cls}:{idx}'
        yield from _iter_paths(child, f'{path}/{segment}' if path else segment)


def _open_client(args):
    """Resolve credentials and return an opened ``Client``.

    :raises _CredentialsError: when credentials are absent or the connection
        is refused (UI not running / stale ``server.json``).
    """
    port, token = args.port, args.token
    if token is None:
        creds = discover.find_credentials(args.server_json)
        if creds is None:
            path = args.server_json or discover.server_json_path()
            raise _CredentialsError(
                f'no credentials at {path}: UI not running with --tcp-server')
        port = creds['port'] if port is None else port
        token = creds['token']
    args.port = port  # report the resolved port (e.g. in `ping`)
    from joulescope_ui.tcp_client import Client
    client = Client(port=port, token=token, timeout=args.timeout)
    try:
        client.open()
    except (ConnectionError, OSError) as ex:
        raise _CredentialsError(
            f'connect to port {port} failed ({ex}): '
            'UI not running with --tcp-server, or stale server.json') from ex
    return client


class _CredentialsError(Exception):
    """Credentials absent, stale, or connection refused."""


def _cmd_ping(client, args):
    return {'ok': True, 'view': client.query(_VIEW_TOPIC), 'port': args.port}


def _cmd_screenshot(client, args):
    png = client.qt_screenshot(args.widget)
    out = os.path.abspath(args.output)
    with open(out, 'wb') as f:
        f.write(png)
    return {'path': out, 'bytes': len(png)}


def _cmd_query(client, args):
    return {'topic': args.topic, 'value': client.query(args.topic)}


def _cmd_publish(client, args):
    value = _parse_value(args.value)
    client.publish(args.topic, value)
    out = {'topic': args.topic, 'value': value}
    if args.wait:
        _wait_for_value(client, args.topic, value, args.timeout)
        out['confirmed'] = True
    return out


def _cmd_view(client, args):
    target = f'view:{args.name}'
    previous = client.query(_VIEW_TOPIC)
    client.publish(_VIEW_TOPIC, target)
    _wait_for_value(client, _VIEW_TOPIC, target, args.timeout)
    return {'previous': previous, 'view': target}


def _cmd_enum(client, args):
    return {'topic': args.topic, 'children': client.enumerate(args.topic)}


def _cmd_inspect(client, args):
    return client.qt_inspect(args.path, max_depth=args.depth)


def _cmd_find(client, args):
    tree = client.qt_inspect('')
    matched = {id(n) for n in qt.find_widgets(
        tree, cls=args.cls, object_name=args.name, text_contains=args.text)}
    out = []
    for path, node in _iter_paths(tree):
        if id(node) in matched:
            out.append({'path': path,
                        'class': node.get('class'),
                        'objectName': node.get('objectName')})
    return {'count': len(out), 'widgets': out}


def _cmd_action(client, args):
    kwargs = json.loads(args.kwargs) if args.kwargs else {}
    return client.qt_action(args.name, path=args.path, **kwargs)


def _cmd_devices(client, args):
    devices = discover.enumerate_devices(client)
    return {'devices': [dataclasses.asdict(d) for d in devices]}


def _cmd_stats(client, args):
    topic = 'registry/+/events/statistics/!data'
    samples = []
    client.subscribe(topic, lambda t, value: samples.append((t, value)))
    time.sleep(args.duration)
    client.unsubscribe(topic)
    if not samples:
        return {'count': 0, 'sample': None}
    topic, value = samples[-1]
    return {'count': len(samples), 'topic': topic, 'sample': value}


def _common_options(suppress):
    """Build the shared option parser.

    The subparser copy uses ``SUPPRESS`` defaults: a subparser parses into a
    fresh namespace and copies it over the main one, so real defaults there
    would clobber global options given before the subcommand.
    """
    d = argparse.SUPPRESS if suppress else None
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--timeout', type=float,
                        default=argparse.SUPPRESS if suppress else 15.0,
                        help='request timeout in seconds (default 15)')
    common.add_argument('--port', type=int, default=d,
                        help='server port (default: from server.json)')
    common.add_argument('--token', default=d,
                        help='auth token (default: from server.json)')
    common.add_argument('--server-json', default=d,
                        help='server.json path (default: platform app dir)')
    return common


def _parser():
    common = _common_options(suppress=True)

    p = argparse.ArgumentParser(
        prog='cli.py',
        description='One-shot client for the Joulescope UI TCP server.',
        parents=[_common_options(suppress=False)])
    sub = p.add_subparsers(dest='command', required=True)

    s = sub.add_parser('ping', parents=[common],
                       help='connect and report the active view')
    s.set_defaults(func=_cmd_ping)

    s = sub.add_parser('screenshot', parents=[common],
                       help='capture a widget (default: main window) as PNG')
    s.add_argument('output', help='output PNG file path')
    s.add_argument('--widget', default='', help='widget path (default: main window)')
    s.set_defaults(func=_cmd_screenshot)

    s = sub.add_parser('query', parents=[common], help='query a pubsub topic value')
    s.add_argument('topic')
    s.set_defaults(func=_cmd_query)

    s = sub.add_parser('publish', parents=[common], help='publish a value to a topic')
    s.add_argument('topic')
    s.add_argument('value', help='JSON value; non-JSON text is sent as a string')
    s.add_argument('--wait', action='store_true',
                   help='poll query(topic) until it reflects the published value')
    s.set_defaults(func=_cmd_publish)

    s = sub.add_parser('view', parents=[common], help='switch the active view and wait')
    s.add_argument('name', choices=['multimeter', 'oscilloscope', 'file'])
    s.set_defaults(func=_cmd_view)

    s = sub.add_parser('enum', parents=[common], help='enumerate child topics')
    s.add_argument('topic')
    s.set_defaults(func=_cmd_enum)

    s = sub.add_parser('inspect', parents=[common], help='dump the Qt widget tree')
    s.add_argument('path', nargs='?', default='', help='widget path (default: main window)')
    s.add_argument('--depth', type=int, default=3, help='max tree depth (default 3)')
    s.set_defaults(func=_cmd_inspect)

    s = sub.add_parser('find', parents=[common],
                       help='find widget paths by class/objectName/text')
    s.add_argument('--class', dest='cls', default=None, help='match class name exactly')
    s.add_argument('--name', default=None, help='match objectName exactly')
    s.add_argument('--text', default=None, help='match any string property containing')
    s.set_defaults(func=_cmd_find)

    s = sub.add_parser('action', parents=[common],
                       help='perform a qt_action (click/drag/key/menu_invoke/...)')
    s.add_argument('name', help='action name, e.g. click, key, resize, menu_items')
    s.add_argument('--path', default='', help='widget path (default: main window)')
    s.add_argument('--kwargs', default=None, help='action parameters as a JSON object')
    s.set_defaults(func=_cmd_action)

    s = sub.add_parser('devices', parents=[common], help='list connected Joulescope devices')
    s.set_defaults(func=_cmd_devices)

    s = sub.add_parser('stats', parents=[common],
                       help='sample live statistics and print the last one')
    s.add_argument('--duration', type=float, default=2.0,
                   help='seconds to listen (default 2)')
    s.set_defaults(func=_cmd_stats)

    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        client = _open_client(args)
    except _CredentialsError as ex:
        return _fail(2, str(ex))
    try:
        result = args.func(client, args)
    except TimeoutError as ex:
        return _fail(3, str(ex))
    except RuntimeError as ex:
        return _fail(4, str(ex))
    finally:
        client.close()
    _emit(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
