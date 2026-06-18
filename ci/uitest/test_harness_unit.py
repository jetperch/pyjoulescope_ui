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

"""Unit tests for the Qt-free uitest harness modules.

These need only ``pyjls`` + numpy (no PySide6 / display), so they run in CI's
``build_sdist`` job and on a bare developer machine.  They cover the JLS
verification, device/credential discovery, installer index resolution, and
station-registry logic.  The UI-driving paths (``UiSession``) are covered by the
device suite on the HIL farm.
"""

import os
import sys
import tempfile
import unittest

import numpy as np
import pyjls

# Allow `from uitest import ...` when run directly (python -m unittest / file),
# matching how pytest puts the `ci/` directory on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uitest import verify, discover, installer, stations, assets, qt  # noqa: E402
from uitest.jls_fixtures import write_fsr_v2  # noqa: E402


def _write_v2(path, *, signal_name='current', units='A', sample_rate=1000,
              data=None, markers=0, start_value=0.0):
    """Write a minimal JLS v2 fixture (thin wrapper over the shared writer)."""
    if data is None:
        data = np.linspace(start_value, start_value + 1.0, 5000, dtype=np.float32)
    return write_fsr_v2(path, signal_name=signal_name, units=units,
                        sample_rate=sample_rate, data=data, markers=markers)


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'rec.jls')

    def test_jls_version_v2(self):
        _write_v2(self.path)
        self.assertEqual(verify.jls_version(self.path), 2)

    def test_jls_version_v1_magic(self):
        p = os.path.join(self.dir, 'v1.jls')
        with open(p, 'wb') as f:
            f.write(verify.JLS_V1_MAGIC + b'\x00' * 32)
        self.assertEqual(verify.jls_version(p), 1)

    def test_jls_version_unknown(self):
        p = os.path.join(self.dir, 'x.bin')
        with open(p, 'wb') as f:
            f.write(b'not a jls file..')
        self.assertIsNone(verify.jls_version(p))

    def test_open_reader_rejects_non_v2(self):
        p = os.path.join(self.dir, 'v1.jls')
        with open(p, 'wb') as f:
            f.write(verify.JLS_V1_MAGIC + b'\x00' * 32)
        with self.assertRaises(ValueError):
            with verify.open_reader(p):
                pass

    def test_summarize(self):
        _write_v2(self.path, sample_rate=1000, data=np.zeros(2000, dtype=np.float32))
        s = verify.summarize(self.path)
        self.assertEqual([sig['name'] for sig in s['signals'].values()], ['current'])
        sig = list(s['signals'].values())[0]
        self.assertEqual(sig['length'], 2000)
        self.assertAlmostEqual(sig['duration_s'], 2.0, places=6)
        self.assertEqual(list(s['sources'].values())[0]['model'], 'JS220')

    def test_assert_recording_ok(self):
        _write_v2(self.path, sample_rate=1000, data=np.full(10000, 0.5, dtype=np.float32))
        verify.assert_recording(self.path, signal_names=['current'],
                                min_duration_s=9.0, value_range=(0.0, 1.0))

    def test_assert_recording_missing_signal(self):
        _write_v2(self.path)
        with self.assertRaises(AssertionError):
            verify.assert_recording(self.path, signal_names=['voltage'])

    def test_assert_recording_duration_short(self):
        _write_v2(self.path, sample_rate=1000, data=np.zeros(500, dtype=np.float32))
        with self.assertRaises(AssertionError):
            verify.assert_recording(self.path, min_duration_s=10.0)

    def test_assert_recording_nonfinite(self):
        data = np.zeros(1000, dtype=np.float32)
        data[10] = np.nan
        _write_v2(self.path, data=data)
        with self.assertRaises(AssertionError):
            verify.assert_recording(self.path, finite=True)

    def test_markers(self):
        _write_v2(self.path, markers=2)
        self.assertEqual(verify.count_annotations(
            self.path, annotation_type=pyjls.AnnotationType.VMARKER), 2)
        verify.assert_has_markers(self.path, 2)
        with self.assertRaises(AssertionError):
            verify.assert_has_markers(self.path, 4)

    def test_compare_subrange_roundtrip(self):
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        full = (np.sin(np.arange(20000) / 50.0)).astype(np.float32)
        _write_v2(ref, data=full)
        offset = 5000
        _write_v2(exp, data=full[offset:offset + 4000])
        found = verify.compare_subrange(ref, exp, 'current', atol=1e-5)
        self.assertEqual(found, offset)

    def test_compare_subrange_mismatch(self):
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        _write_v2(ref, data=np.sin(np.arange(8000) / 50.0).astype(np.float32))
        _write_v2(exp, data=(np.cos(np.arange(2000) / 7.0) * 3.14).astype(np.float32))
        with self.assertRaises(AssertionError):
            verify.compare_subrange(ref, exp, 'current', atol=1e-6)


def _norm(path):
    """Normalize OS path separators to ``/`` so platform-branch assertions hold
    on any host (``app_dir`` builds paths with the host's ``os.path.sep``)."""
    return path.replace(os.sep, '/')


class TestDiscover(unittest.TestCase):
    def test_app_dir_per_platform(self):
        self.assertTrue(_norm(discover.app_dir(platform='linux')).endswith('/.joulescope'))
        mac = _norm(discover.app_dir(platform='darwin'))
        self.assertIn('Library/Application Support/joulescope', mac)
        win = _norm(discover.app_dir(platform='win32'))
        self.assertTrue(win.endswith('joulescope'))

    def test_server_json_path(self):
        p = _norm(discover.server_json_path(platform='linux'))
        self.assertTrue(p.endswith('/.joulescope/server.json'))

    def test_config_file_path(self):
        p = _norm(discover.config_file_path(platform='linux'))
        self.assertTrue(p.endswith('/.joulescope/config/joulescope_ui_config.json'))

    def test_unsupported_platform(self):
        with self.assertRaises(RuntimeError):
            discover.app_dir(platform='sunos')

    def test_model_for_unique_id(self):
        # Real connected-device id form is "<MODEL>-<serial>".
        self.assertEqual(discover.model_for_unique_id('JS220-002557'), 'JS220')
        self.assertEqual(discover.model_for_unique_id('JS320-8W2A'), 'JS320')
        self.assertEqual(discover.model_for_unique_id('JS110-000123'), 'JS110')
        # Tolerate lower case and 'Prefix:js320' style ids.
        self.assertEqual(discover.model_for_unique_id('js220'), 'JS220')
        self.assertEqual(discover.model_for_unique_id('JsdrvDevice:js320'), 'JS320')
        self.assertIsNone(discover.model_for_unique_id('view:multimeter'))
        self.assertIsNone(discover.model_for_unique_id('JlsSource:1'))
        self.assertIsNone(discover.model_for_unique_id(''))

    def test_find_credentials(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'server.json')
        self.assertIsNone(discover.find_credentials(p))
        with open(p, 'w') as f:
            f.write('{"token": "abc", "port": 21861}')
        creds = discover.find_credentials(p)
        self.assertEqual(creds['port'], 21861)
        self.assertEqual(creds['token'], 'abc')

    def test_device_topic(self):
        dev = discover.Device(unique_id='js320_1', model='JS320', serial_number='42')
        self.assertEqual(dev.topic, 'registry/js320_1')


class _FakeClient:
    """Minimal stand-in for tcp_client.Client for discover.enumerate_devices."""
    def __init__(self, values):
        self._values = values

    def query(self, topic):
        if topic not in self._values:
            raise KeyError(topic)
        return self._values[topic]


class TestEnumerateDevices(unittest.TestCase):
    def test_enumerate_dedup_and_model(self):
        stat = 'registry_manager/capabilities/statistics_stream.source/list'
        sig = 'registry_manager/capabilities/signal_stream.source/list'
        client = _FakeClient({
            stat: ['JS220-002557', 'JS320-8W2A'],
            sig: ['JS220-002557'],   # overlap -> deduped
            'registry/JS220-002557/settings/info': {'serial_number': '002557'},
            'registry/JS320-8W2A/settings/info': {'serial_number': '8W2A'},
        })
        devices = discover.enumerate_devices(client)
        self.assertEqual([(d.model, d.unique_id, d.serial_number) for d in devices],
                         [('JS220', 'JS220-002557', '002557'),
                          ('JS320', 'JS320-8W2A', '8W2A')])

    def test_enumerate_ignores_non_devices(self):
        stat = 'registry_manager/capabilities/statistics_stream.source/list'
        client = _FakeClient({stat: ['JlsSource:1', 'JS110-000123']})
        devices = discover.enumerate_devices(client)
        self.assertEqual([d.model for d in devices], ['JS110'])


class TestInstaller(unittest.TestCase):
    INDEX = {
        'active': {
            'alpha': {'platform': {
                'windows': {'arch': ['x86_64'], 'installer': '1/5/1/joulescope_setup.exe'},
                'windows_arm64': {'arch': ['arm64'], 'installer': '1/5/1/joulescope_arm.exe'},
                'macos': {'arch': ['x86_64', 'arm64'], 'installer': '1/5/1/joulescope.dmg'},
                'ubuntu': {'arch': ['x86_64'], 'installer': '1/5/1/joulescope.tar.gz'},
            }},
        },
    }

    def test_platform_key(self):
        self.assertEqual(installer.platform_key('Windows', 'AMD64'), 'windows')
        self.assertEqual(installer.platform_key('Windows', 'ARM64'), 'windows_arm64')
        self.assertEqual(installer.platform_key('Darwin', 'arm64'), 'macos')
        self.assertEqual(installer.platform_key('Darwin', 'x86_64'), 'macos')
        self.assertEqual(installer.platform_key('Linux', 'x86_64'), 'ubuntu')

    def test_platform_key_unsupported(self):
        with self.assertRaises(RuntimeError):
            installer.platform_key('Plan9', 'x86_64')

    def test_installer_relpath(self):
        self.assertEqual(installer.installer_relpath(self.INDEX, 'alpha', 'ubuntu'),
                         '1/5/1/joulescope.tar.gz')

    def test_installer_relpath_missing_channel(self):
        with self.assertRaises(KeyError):
            installer.installer_relpath(self.INDEX, 'stable', 'ubuntu')

    def test_installer_relpath_unknown_channel(self):
        with self.assertRaises(KeyError):
            installer.installer_relpath(self.INDEX, 'nightly', 'ubuntu')

    def test_installer_urls(self):
        url, sha = installer.installer_urls(self.INDEX, 'alpha', 'windows')
        self.assertEqual(url, installer.URL_BASE + '1/5/1/joulescope_setup.exe')
        self.assertEqual(sha, url + '.sha256')

    def test_parse_sha256_sidecar(self):
        hexd = 'a' * 64
        self.assertEqual(installer.parse_sha256_sidecar(f'{hexd} ./joulescope.exe'), hexd)

    def test_parse_sha256_sidecar_invalid(self):
        with self.assertRaises(ValueError):
            installer.parse_sha256_sidecar('not-a-hash ./x')

    def test_launch_command(self):
        self.assertEqual(installer.launch_command('/opt/joulescope'),
                         ['/opt/joulescope', '--tcp-server'])
        dev = installer.launch_command(None)
        self.assertEqual(dev[1:], ['-m', 'joulescope_ui', 'ui', '--tcp-server'])


class TestStations(unittest.TestCase):
    def test_load_default_registry(self):
        regs = stations.load_stations()
        self.assertIn('default', regs)
        self.assertEqual(regs['default'].devices, ())
        self.assertTrue(regs['win11_x64'].advertises('js220'))
        self.assertTrue(regs['win11_x64'].advertises('JS320'))

    def test_load_rejects_unknown_model(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'stations.toml')
        with open(p, 'w') as f:
            f.write('[stations.bad]\ndevices = ["JS999"]\n')
        with self.assertRaises(ValueError):
            stations.load_stations(p)

    def test_current_station_env_override(self):
        regs = stations.load_stations()
        old = os.environ.get(stations.ENV_STATION)
        try:
            os.environ[stations.ENV_STATION] = 'ubuntu_x64'
            self.assertEqual(stations.current_station(regs).name, 'ubuntu_x64')
            os.environ[stations.ENV_STATION] = 'does_not_exist'
            with self.assertRaises(KeyError):
                stations.current_station(regs)
        finally:
            if old is None:
                os.environ.pop(stations.ENV_STATION, None)
            else:
                os.environ[stations.ENV_STATION] = old

    def test_current_station_hostname_and_default(self):
        regs = stations.load_stations()
        old = os.environ.pop(stations.ENV_STATION, None)
        try:
            self.assertEqual(stations.current_station(regs, hostname='JS-HIL-UBU').name,
                             'ubuntu_x64')
            self.assertEqual(stations.current_station(regs, hostname='unknown-host').name,
                             'default')
        finally:
            if old is not None:
                os.environ[stations.ENV_STATION] = old


class TestStationsFileOverride(unittest.TestCase):
    def test_env_file_override(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'custom.toml')
        with open(p, 'w') as f:
            f.write('[stations.localdev]\nplatform = "ubuntu"\ndevices = ["JS220", "JS320"]\n')
        old = os.environ.get(stations.ENV_STATIONS_FILE)
        try:
            os.environ[stations.ENV_STATIONS_FILE] = p
            regs = stations.load_stations()
            self.assertEqual(set(regs), {'localdev'})
            self.assertEqual(regs['localdev'].devices, ('JS220', 'JS320'))
        finally:
            if old is None:
                os.environ.pop(stations.ENV_STATIONS_FILE, None)
            else:
                os.environ[stations.ENV_STATIONS_FILE] = old


_TREE = {
    'class': 'MainWindow', 'objectName': 'main',
    'children': [
        {'class': 'QLabel', 'objectName': 'title',
         'properties': {'text': 'Joulescope UI version 1.5.1'}},
        {'class': 'QWidget', 'objectName': 'body', 'children': [
            {'class': 'QPushButton', 'objectName': 'ok', 'properties': {'text': 'OK'}},
            {'class': 'QLabel', 'objectName': 'drv', 'properties': {'text': 'driver 2.2.4'}},
        ]},
    ],
}


class TestQtTree(unittest.TestCase):
    def test_iter_widgets(self):
        classes = [n['class'] for n in qt.iter_widgets(_TREE)]
        self.assertEqual(classes, ['MainWindow', 'QLabel', 'QWidget', 'QPushButton', 'QLabel'])

    def test_find_widgets_by_class(self):
        labels = qt.find_widgets(_TREE, cls='QLabel')
        self.assertEqual(len(labels), 2)

    def test_find_widget_by_object_name(self):
        node = qt.find_widget(_TREE, object_name='ok')
        self.assertEqual(node['class'], 'QPushButton')

    def test_find_widget_by_text(self):
        node = qt.find_widget(_TREE, text_contains='1.5.1')
        self.assertEqual(node['objectName'], 'title')

    def test_any_text_contains(self):
        self.assertTrue(qt.any_text_contains(_TREE, '2.2.4'))
        self.assertFalse(qt.any_text_contains(_TREE, 'nonexistent'))

    def test_all_texts_present(self):
        self.assertEqual(qt.all_texts_present(_TREE, ['1.5.1', '2.2.4', 'OK']), [])
        self.assertEqual(qt.all_texts_present(_TREE, ['1.5.1', 'missing']), ['missing'])


class TestAssets(unittest.TestCase):
    def test_asset_path_known(self):
        p = assets.asset_path(assets.JLS_V1_EVK1)
        self.assertTrue(p.endswith(assets.JLS_V1_EVK1))

    def test_get_asset_unknown(self):
        with self.assertRaises(KeyError):
            assets.get_asset('nope.jls')

    def test_validate_rejects_wrong_version(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'fake.jls')
        with open(p, 'wb') as f:
            f.write(verify.JLS_V2_MAGIC + b'\x00' * 16)   # v2 content
        with self.assertRaises(ValueError):
            assets._validate(p, expected_version=1)        # expected v1


if __name__ == '__main__':
    unittest.main()
