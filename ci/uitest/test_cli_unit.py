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

"""Unit tests for the one-shot CLI (``ci/uitest/cli.py``).

Qt-free and hardware-free: the ``Client`` is replaced with a fake, so these
run anywhere the other ``test_harness_unit`` tests run.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

# Allow `from uitest import ...` when run directly (python -m unittest / file),
# matching how pytest puts the `ci/` directory on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uitest import cli  # noqa: E402


class _FakeClient:
    """Stand-in for tcp_client.Client covering the CLI's call surface."""

    def __init__(self, values=None, tree=None, png=b'\x89PNG fake'):
        self.values = dict(values or {})
        self.tree = tree or {'class': 'MainWindow', 'objectName': 'main'}
        self.png = png
        self.published = []
        self.actions = []
        self.closed = False

    def query(self, topic):
        return self.values[topic]

    def publish(self, topic, value):
        self.published.append((topic, value))
        self.values[topic] = value   # emulate a retained settings topic

    def enumerate(self, topic, absolute=None):
        return self.values[topic]

    def subscribe(self, topic, callback, flags=None):
        pass

    def unsubscribe(self, topic, callback=None):
        pass

    def qt_inspect(self, path='', max_depth=50):
        return self.tree

    def qt_action(self, action, path='', **kwargs):
        self.actions.append((action, path, kwargs))
        return {'action': action}

    def qt_screenshot(self, path=''):
        return self.png

    def close(self):
        self.closed = True


def _run(argv, client=None):
    """Run cli.main with a fake client; return (exit_code, stdout_json, stderr)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    patch = mock.patch.object(cli, '_open_client',
                              side_effect=lambda args: client)
    with patch, redirect_stdout(stdout), redirect_stderr(stderr):
        rc = cli.main(argv)
    out = stdout.getvalue()
    return rc, json.loads(out) if out else None, stderr.getvalue()


class TestCredentials(unittest.TestCase):
    def test_missing_server_json_exits_2(self):
        missing = os.path.join(tempfile.mkdtemp(), 'server.json')
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            rc = cli.main(['--server-json', missing, 'ping'])
        self.assertEqual(rc, 2)
        err = json.loads(stderr.getvalue())
        self.assertIn('--tcp-server', err['error'])

    def test_open_client_reads_credentials(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'server.json')
        with open(p, 'w') as f:
            json.dump({'token': 'tok', 'port': 12345}, f)
        captured = {}

        class _Client:
            def __init__(self, port=None, token=None, timeout=None):
                captured.update(port=port, token=token, timeout=timeout)

            def open(self):
                raise ConnectionRefusedError('nope')

        fake_module = mock.MagicMock(Client=_Client)
        with mock.patch.dict(sys.modules, {'joulescope_ui.tcp_client': fake_module}):
            args = cli._parser().parse_args(['--server-json', p, 'ping'])
            with self.assertRaises(cli._CredentialsError):
                cli._open_client(args)
        self.assertEqual(captured, {'port': 12345, 'token': 'tok', 'timeout': 15.0})


class TestCommands(unittest.TestCase):
    def test_ping(self):
        client = _FakeClient({'registry/view/settings/active': 'view:multimeter'})
        rc, out, _ = _run(['ping'], client)
        self.assertEqual(rc, 0)
        self.assertTrue(out['ok'])
        self.assertEqual(out['view'], 'view:multimeter')
        self.assertTrue(client.closed)

    def test_query(self):
        client = _FakeClient({'a/b': 42})
        rc, out, _ = _run(['query', 'a/b'], client)
        self.assertEqual(rc, 0)
        self.assertEqual(out, {'topic': 'a/b', 'value': 42})

    def test_publish_json_value(self):
        client = _FakeClient()
        rc, out, _ = _run(['publish', 'a/b', '{"x": 1}'], client)
        self.assertEqual(rc, 0)
        self.assertEqual(client.published, [('a/b', {'x': 1})])
        self.assertEqual(out['value'], {'x': 1})

    def test_publish_string_fallback(self):
        client = _FakeClient()
        rc, out, _ = _run(['publish', 'a/b', 'view:multimeter'], client)
        self.assertEqual(rc, 0)
        self.assertEqual(client.published, [('a/b', 'view:multimeter')])

    def test_publish_wait_confirms(self):
        client = _FakeClient()
        rc, out, _ = _run(['publish', 'a/b', '7', '--wait'], client)
        self.assertEqual(rc, 0)
        self.assertTrue(out['confirmed'])

    def test_view_switch(self):
        client = _FakeClient({'registry/view/settings/active': 'view:oscilloscope'})
        rc, out, _ = _run(['view', 'multimeter'], client)
        self.assertEqual(rc, 0)
        self.assertEqual(out, {'previous': 'view:oscilloscope', 'view': 'view:multimeter'})

    def test_enum(self):
        client = _FakeClient({'registry': ['app', 'view']})
        rc, out, _ = _run(['enum', 'registry'], client)
        self.assertEqual(rc, 0)
        self.assertEqual(out['children'], ['app', 'view'])

    def test_screenshot_writes_file(self):
        client = _FakeClient(png=b'\x89PNG binary')
        dest = os.path.join(tempfile.mkdtemp(), 'shot.png')
        rc, out, _ = _run(['screenshot', dest], client)
        self.assertEqual(rc, 0)
        self.assertEqual(out['bytes'], len(b'\x89PNG binary'))
        with open(dest, 'rb') as f:
            self.assertEqual(f.read(), b'\x89PNG binary')

    def test_action_kwargs(self):
        client = _FakeClient()
        rc, out, _ = _run(
            ['action', 'resize', '--kwargs', '{"width": 800, "height": 600}'], client)
        self.assertEqual(rc, 0)
        self.assertEqual(client.actions, [('resize', '', {'width': 800, 'height': 600})])

    def test_server_error_exits_4(self):
        client = _FakeClient()
        client.query = mock.Mock(side_effect=RuntimeError('widget not found'))
        rc, out, err = _run(['query', 'a/b'], client)
        self.assertEqual(rc, 4)
        self.assertIn('widget not found', json.loads(err)['error'])
        self.assertTrue(client.closed)

    def test_timeout_exits_3(self):
        client = _FakeClient()
        client.query = mock.Mock(side_effect=TimeoutError('Request 1 timed out'))
        rc, out, err = _run(['query', 'a/b'], client)
        self.assertEqual(rc, 3)


_TREE = {
    'class': 'MainWindow', 'objectName': 'main',
    'children': [
        {'class': 'QLabel', 'objectName': 'title',
         'properties': {'text': 'Joulescope'}},
        {'class': 'QWidget', 'objectName': '', 'children': [
            {'class': 'WaveformWidget', 'objectName': '', 'properties': {}},
            {'class': 'WaveformWidget', 'objectName': 'wf2', 'properties': {}},
        ]},
    ],
}


class TestFindPaths(unittest.TestCase):
    def test_iter_paths_object_name_and_class_index(self):
        paths = dict((p, n['class']) for p, n in cli._iter_paths(_TREE))
        self.assertEqual(paths[''], 'MainWindow')
        self.assertEqual(paths['title'], 'QLabel')
        self.assertEqual(paths['QWidget:0/WaveformWidget:0'], 'WaveformWidget')
        self.assertEqual(paths['QWidget:0/wf2'], 'WaveformWidget')

    def test_find_by_class(self):
        client = _FakeClient(tree=_TREE)
        rc, out, _ = _run(['find', '--class', 'WaveformWidget'], client)
        self.assertEqual(rc, 0)
        self.assertEqual(out['count'], 2)
        self.assertEqual([w['path'] for w in out['widgets']],
                         ['QWidget:0/WaveformWidget:0', 'QWidget:0/wf2'])

    def test_find_by_text(self):
        client = _FakeClient(tree=_TREE)
        rc, out, _ = _run(['find', '--text', 'Joulescope'], client)
        self.assertEqual(rc, 0)
        self.assertEqual([w['path'] for w in out['widgets']], ['title'])


class TestJsonDefault(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(cli._json_default(b'abc'), {'__type__': 'bytes', 'length': 3})

    def test_numpy_scalar_and_array(self):
        import numpy as np
        self.assertEqual(cli._json_default(np.float32(1.5)), 1.5)
        self.assertEqual(cli._json_default(np.array([1, 2])), [1, 2])
        self.assertIsInstance(cli._json_default(np.zeros(1000)), str)


if __name__ == '__main__':
    unittest.main()
