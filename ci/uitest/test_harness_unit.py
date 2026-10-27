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
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pyjls

# Allow `from uitest import ...` when run directly (python -m unittest / file),
# matching how pytest puts the `ci/` directory on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uitest import verify, discover, installer, assets, qt  # noqa: E402
from uitest.harness import HELP_DIALOG, UiSession, UiSessionError  # noqa: E402
from uitest.jls_fixtures import write_fsr_v2  # noqa: E402


def _write_v2(path, *, signal_name='current', units='A', sample_rate=1000,
              data=None, markers=0, start_value=0.0, utc_offset_s=0.0, sample_id_offset=0):
    """Write a minimal JLS v2 fixture (thin wrapper over the shared writer)."""
    if data is None:
        data = np.linspace(start_value, start_value + 1.0, 5000, dtype=np.float32)
    return write_fsr_v2(path, signal_name=signal_name, units=units,
                        sample_rate=sample_rate, data=data, markers=markers,
                        utc_offset_s=utc_offset_s, sample_id_offset=sample_id_offset)


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
        _write_v2(exp, data=full[offset:offset + 4000], utc_offset_s=offset / 1000)
        found = verify.compare_subrange(ref, exp, 'current')
        self.assertEqual(found, offset)

    def test_compare_subrange_quiet_signal(self):
        # A near-constant signal (no load) must align by UTC, not by value.
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        full = np.full(20000, 1e-7, dtype=np.float32)
        full[12000:12010] = 2e-7
        _write_v2(ref, data=full)
        offset = 10000
        _write_v2(exp, data=full[offset:offset + 4000], utc_offset_s=offset / 1000)
        self.assertEqual(verify.compare_subrange(ref, exp, 'current'), offset)
        _write_v2(exp, data=full[offset:offset + 4000], utc_offset_s=1.0)
        with self.assertRaises(AssertionError):
            verify.compare_subrange(ref, exp, 'current')

    def test_compare_subrange_missing_samples(self):
        # Missing samples are NaN in both the recording and the export.
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        full = (np.sin(np.arange(20000) / 50.0)).astype(np.float32)
        full[7000:7050] = np.nan
        _write_v2(ref, data=full)
        offset = 5000
        _write_v2(exp, data=full[offset:offset + 4000], utc_offset_s=offset / 1000)
        self.assertEqual(verify.compare_subrange(ref, exp, 'current'), offset)
        part = full[offset:offset + 4000].copy()
        part[2000:2050] = 0.0
        _write_v2(exp, data=part, utc_offset_s=offset / 1000)
        with self.assertRaisesRegex(AssertionError, '50 of 4000 samples differ, first at export '
                                                    'sample 2000, last at 2049'):
            verify.compare_subrange(ref, exp, 'current')

    def test_compare_subrange_reports_match_offset(self):
        # Beyond max_shift, the failure says where the export actually starts.
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        full = (np.sin(np.arange(20000) / 50.0) + np.arange(20000) * 1e-4).astype(np.float32)
        _write_v2(ref, data=full)
        _write_v2(exp, data=full[5300:9300], utc_offset_s=5.0)
        with self.assertRaisesRegex(AssertionError, r'exact matches .*: \[5300\] '
                                                    r'\(offsets from index: \[300\]'):
            verify.compare_subrange(ref, exp, 'current')

    def test_compare_subrange_reports_correlation(self):
        # Nearly equal values match nowhere exactly but correlate at the offset.
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        rng = np.random.default_rng(1)
        full = rng.normal(size=20000).astype(np.float32)
        _write_v2(ref, data=full)
        _write_v2(exp, data=full[5300:9300] * np.float32(1.001), utc_offset_s=5.0)
        with self.assertRaisesRegex(AssertionError, r'(?s)exact matches .*: \[\].*'
                                    r'best at reference sample 5300 \(offset 300\), '
                                    r'coefficient 1\.0000'):
            verify.compare_subrange(ref, exp, 'current')

    def test_compare_subrange_stream_sample_ids(self):
        # A recording and a live export share the stream's sample ids, so they
        # align exactly however far apart their UTC is.
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        full = np.random.default_rng(2).integers(-3, 4, 20000).astype(np.float32) * 1e-8
        _write_v2(ref, data=full, sample_id_offset=100_000)
        _write_v2(exp, data=full[5000:9000], sample_id_offset=105_000, utc_offset_s=5.2)
        self.assertEqual(5000, verify.compare_subrange(ref, exp, 'current', sample_ids='stream'))
        with self.assertRaises(AssertionError):   # UTC is 200 samples off
            verify.compare_subrange(ref, exp, 'current')
        _write_v2(exp, data=full[5001:9001], sample_id_offset=105_000, utc_offset_s=5.0)
        with self.assertRaisesRegex(AssertionError, r'(?s)alignment: stream; export sample_id_offset '
                                    r'105000, reference sample_id_offset 100000.*'
                                    r'index - UTC = 0 samples.*exact matches .*\[5001'):
            verify.compare_subrange(ref, exp, 'current', sample_ids='stream')

    def test_compare_subrange_file_sample_ids(self):
        # An export from the opened file numbers the file's samples from 0.
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'C.jls')
        full = (np.sin(np.arange(20000) / 50.0)).astype(np.float32)
        _write_v2(ref, data=full, sample_id_offset=100_000)
        _write_v2(exp, data=full[3000:7000], sample_id_offset=3000, utc_offset_s=3.0)
        self.assertEqual(3000, verify.compare_subrange(ref, exp, 'current', sample_ids='file'))
        _write_v2(exp, data=full[3000:7000], sample_id_offset=19000)
        with self.assertRaisesRegex(AssertionError, 'outside the reference'):
            verify.compare_subrange(ref, exp, 'current', sample_ids='file')

    def test_compare_subrange_past_end(self):
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        full = (np.sin(np.arange(8000) / 50.0)).astype(np.float32)
        _write_v2(ref, data=full)
        _write_v2(exp, data=full[6000:], utc_offset_s=7.0)
        with self.assertRaises(AssertionError):
            verify.compare_subrange(ref, exp, 'current')

    def test_compare_subrange_mismatch(self):
        ref = os.path.join(self.dir, 'A.jls')
        exp = os.path.join(self.dir, 'B.jls')
        _write_v2(ref, data=np.sin(np.arange(8000) / 50.0).astype(np.float32))
        _write_v2(exp, data=(np.cos(np.arange(2000) / 7.0) * 3.14).astype(np.float32))
        with self.assertRaises(AssertionError):
            verify.compare_subrange(ref, exp, 'current')

    def test_assert_no_gaps(self):
        data = np.sin(np.arange(20000) / 50.0).astype(np.float32)
        _write_v2(self.path, data=data)
        verify.assert_no_gaps(self.path, ['current'])
        data[12345:12400] = np.nan   # a recorder fills missing samples with NaN
        _write_v2(self.path, data=data)
        with self.assertRaises(AssertionError):
            verify.assert_no_gaps(self.path, ['current'])

    def test_utc_range(self):
        _write_v2(self.path, utc_offset_s=2.0)
        t0, t1 = verify.utc_range(self.path, 'current')
        self.assertEqual(4999 * pyjls.time64.SECOND // 1000, t1 - t0)


def _norm(path):
    """Normalize OS path separators to ``/`` so platform-branch assertions hold
    on any host (``app_dir`` builds paths with the host's ``os.path.sep``)."""
    return path.replace(os.sep, '/')


class TestDiscover(unittest.TestCase):
    def test_saved_changelog_version(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'joulescope_ui_config.json')
            self.assertIsNone(discover.saved_changelog_version(path=path))
            setting = {'value': '1.7.4'}
            config = {'registry': {'children': {'ui': {'children': {'settings': {
                'children': {'changelog_version_show': setting}}}}}}}
            with open(path, 'w') as f:
                json.dump(config, f)
            self.assertEqual('1.7.4', discover.saved_changelog_version(path=path))
            with open(path, 'w') as f:
                json.dump({'registry': {}}, f)
            self.assertIsNone(discover.saved_changelog_version(path=path))

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


class TestConfigFixtures(unittest.TestCase):

    def test_previous_versions(self):
        from uitest import config_fixtures
        index = {'versions': [{'version': v} for v in ([1, 7, 4], [1, 7, 3], [1, 6, 9], [1, 7, 5])]}
        self.assertEqual(['1.7.4', '1.7.3'], config_fixtures.previous_versions('1.7.5', 2, index))
        self.assertEqual(['1.7.3'], config_fixtures.previous_versions('1.7.4', 1, index))
        self.assertEqual([], config_fixtures.previous_versions('1.6.9', 2, index))


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
        # arm64 Linux builds are published only as a Flatpak.
        with self.assertRaises(RuntimeError):
            installer.platform_key('Linux', 'aarch64')

    def test_locate_executable(self):
        d = tempfile.mkdtemp()
        linux = os.path.join(d, 'joulescope_app', 'joulescope_1_7_4')
        os.makedirs(linux)
        exe = os.path.join(linux, 'joulescope_launcher')
        open(exe, 'w').close()
        os.chmod(exe, 0o755)
        self.assertEqual(exe, installer.locate_executable(os.path.join(d, 'joulescope_app'),
                                                          system='Linux'))
        app = os.path.join(d, 'Joulescope.app')
        os.makedirs(os.path.join(app, 'Contents', 'MacOS'))
        mac = os.path.join(app, 'Contents', 'MacOS', 'joulescope_launcher')
        open(mac, 'w').close()
        self.assertEqual(mac, installer.locate_executable(app, system='Darwin'))
        self.assertIsNone(installer.locate_executable(os.path.join(d, 'empty'), system='Linux'))

    def test_windows_install_current_user(self):
        with mock.patch.object(installer.subprocess, 'run') as run:
            self.assertIsNone(installer.install('setup.exe', system='Windows'))
        self.assertIn('/CURRENTUSER', run.call_args[0][0])
        self.assertIn('/NOLAUNCH', run.call_args[0][0])
        d = tempfile.mkdtemp()
        exe = os.path.join(d, 'Programs', 'Joulescope', 'joulescope.exe')
        with mock.patch.dict(os.environ, {'LOCALAPPDATA': d}):
            self.assertIsNone(installer.locate_executable(system='Windows'))
            os.makedirs(os.path.dirname(exe))
            open(exe, 'w').close()
            self.assertEqual(exe, installer.locate_executable(system='Windows'))

    def _macos_install(self, verify_rc):
        import plistlib
        mount, apps = tempfile.mkdtemp(), tempfile.mkdtemp()
        os.makedirs(os.path.join(mount, 'Joulescope.app'))
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd[0])
            stdout = plistlib.dumps({'system-entities': [{'mount-point': mount}]}) \
                if cmd[0] == 'hdiutil' and cmd[1] == 'attach' else ''
            rc = verify_rc if cmd[0] in ('codesign', 'spctl') else 0
            return mock.Mock(returncode=rc, stdout=stdout, stderr='rejected')

        with mock.patch.object(installer.subprocess, 'run', side_effect=run):
            try:
                return installer._install_macos_dmg('a.dmg', apps_dir=apps), calls
            except RuntimeError as ex:
                return ex, calls

    def test_macos_install_copies_like_finder_and_verifies(self):
        dst, calls = self._macos_install(0)
        self.assertTrue(dst.endswith('Joulescope.app'))
        self.assertEqual(['hdiutil', 'ditto', 'codesign', 'spctl', 'hdiutil'], calls)
        ex, calls = self._macos_install(3)
        self.assertIsInstance(ex, RuntimeError)
        self.assertIn('rejected', str(ex))
        self.assertEqual('hdiutil', calls[-1])  # detached on failure too

    def test_release_channel(self):
        index = {'active': {
            'alpha': {'version': [1, 7, 4], 'platform': {'ubuntu': {}, 'macos': {}}},
            'beta': {'version': [1, 7, 3], 'platform': {'ubuntu': {}, 'windows': {}}},
        }}
        self.assertEqual('alpha', installer.release_channel(index, '1.7.4', 'ubuntu'))
        self.assertEqual('beta', installer.release_channel(index, '1.7.3', 'windows'))
        self.assertIsNone(installer.release_channel(index, '1.7.4', 'windows'))
        self.assertIsNone(installer.release_channel(index, '1.7.5', 'ubuntu'))

    def test_install_release_waits_for_index(self):
        # A just-published index can be cached: re-fetch until it appears.
        stale = {'active': {'alpha': {'version': [1, 7, 3], 'platform': {'ubuntu': {}}}}}
        fresh = {'active': {'alpha': {'version': [1, 7, 4], 'platform': {'ubuntu': {}}}}}
        indexes = [stale, fresh]
        with mock.patch.object(installer, 'fetch_index', side_effect=lambda: indexes.pop(0)), \
                mock.patch.object(installer, 'download_installer', return_value='a.tar.gz'), \
                mock.patch.object(installer, 'install', return_value='/opt/app'), \
                mock.patch.object(installer, 'locate_executable', return_value='/opt/app/js'):
            exe = installer.install_release('1.7.4', tempfile.mkdtemp(), key='ubuntu',
                                            wait=10.0, interval=0.0)
        self.assertEqual('/opt/app/js', exe)
        self.assertEqual([], indexes)

    def test_install_release_not_published(self):
        with self.assertRaises(LookupError):
            installer.install_release('9.9.9', tempfile.mkdtemp(), index=self.INDEX, key='ubuntu')

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


class TestAdvertisedModels(unittest.TestCase):
    """Hermetic: the environment must not leak into resolution logic."""

    def setUp(self):
        self._old = os.environ.pop(discover.ENV_DEVICES, None)

    def tearDown(self):
        # Restore the variable to exactly its prior state.  Leaving a test's
        # value behind (even '') turns the later device fixtures from
        # auto-detect into expectation mode and fails absent models.
        if self._old is None:
            os.environ.pop(discover.ENV_DEVICES, None)
        else:
            os.environ[discover.ENV_DEVICES] = self._old

    def test_unset_is_auto_detect(self):
        self.assertIsNone(discover.advertised_models())

    def test_empty_and_blank_yield_no_devices(self):
        self.assertEqual((), discover.advertised_models(''))
        self.assertEqual((), discover.advertised_models(' , ,'))
        os.environ[discover.ENV_DEVICES] = ''
        self.assertEqual((), discover.advertised_models())

    def test_env_value_parsed(self):
        os.environ[discover.ENV_DEVICES] = 'js320'
        self.assertEqual(('JS320',), discover.advertised_models())

    def test_case_whitespace_and_duplicates(self):
        self.assertEqual(('JS320', 'JS220'),
                         discover.advertised_models(' js320, JS220 ,js320 '))

    def test_unknown_model_rejected(self):
        with self.assertRaises(ValueError):
            discover.advertised_models('JS999')


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


class _StubSession(UiSession):
    """UiSession with the TCP transport stubbed out (no UI process)."""

    def __init__(self, render_info=None, plot_geo=(0, 0, 800, 400), window_sizes=()):
        super().__init__()
        self.render_info = render_info if render_info is not None else {}
        self.plot_geo = None if plot_geo is None else list(plot_geo)
        self.window_sizes = list(window_sizes)
        self.actions = []

    def qt_action(self, action, path='', **kwargs):
        self.actions.append(action)
        if action == 'call':
            info = self.render_info
            if isinstance(info, Exception):
                raise info
            if callable(info):
                info = info()
            return {'ok': True, 'result': info}
        return {'ok': True}

    def qt_inspect(self, path='', max_depth=50):
        size = self.window_sizes.pop(0) if self.window_sizes else [0, 0]
        return {'geometry': [0, 0, *size]}

    def plot_geometry(self, waveform_id):
        return self.plot_geo

    def wait(self, duration):
        pass


class TestRenderProbe(unittest.TestCase):

    def test_rendered(self):
        s = _StubSession({'paint_count': 3, 'plots': {'0': [300, 40, 340]}})
        self.assertTrue(s.is_waveform_rendered('WaveformWidget:1'))
        self.assertEqual(['call'], s.actions)  # no input events  #352

    def test_not_painted(self):
        s = _StubSession({'paint_count': 0, 'plots': {}})
        self.assertFalse(s.is_waveform_rendered('WaveformWidget:1'))

    def test_too_small(self):
        s = _StubSession({'paint_count': 3, 'plots': {'0': [50, 40, 90]}}, plot_geo=(0, 0, 800, 90))
        self.assertFalse(s.is_waveform_rendered('WaveformWidget:1'))

    def test_error_is_not_rendered(self):
        s = _StubSession(RuntimeError('Widget not found'))
        self.assertFalse(s.is_waveform_rendered('WaveformWidget:1'))

    def test_wait_for_paint(self):
        counts = iter([5, 5, 6])
        s = _StubSession(lambda: {'paint_count': next(counts)})
        self.assertTrue(s.wait_for_paint('WaveformWidget:1', 5))

    def test_wait_for_paint_timeout(self):
        s = _StubSession({'paint_count': 5})
        self.assertFalse(s.wait_for_paint('WaveformWidget:1', 5, timeout=0.05))


class TestResizeWindowSettled(unittest.TestCase):

    def test_retries_until_size_holds(self):
        s = _StubSession(window_sizes=[[580, 560], [1600, 900]])
        self.assertTrue(s.resize_window_settled(1600, 900))
        self.assertEqual(['resize', 'resize'], s.actions)

    def test_timeout(self):
        s = _StubSession(window_sizes=[[580, 560]] * 1000)
        self.assertFalse(s.resize_window_settled(1600, 900, timeout=0.05))


class _DialogSession(_StubSession):
    """Stub session whose startup dialog is visible on the ``polls`` listed."""

    def __init__(self, version, polls):
        super().__init__()
        self.version = version
        self.polls = list(polls)   # per inspect: True visible, None absent
        self.keys = []

    def query(self, topic):
        return self.version

    def qt_inspect(self, path='', max_depth=50):
        assert path == HELP_DIALOG
        visible = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
        if visible is None:
            raise RuntimeError('Widget not found')
        return {'visible': visible}

    def qt_action(self, action, path='', **kwargs):
        self.keys.append((path, kwargs.get('key')))
        return {'ok': True}

    def wait(self, seconds):
        pass


class TestSuppressStartupDialogs(unittest.TestCase):

    def test_dialog_appears_after_ready(self):
        s = _DialogSession('1.7.6', [None, None, True, None])
        s._suppress_startup_dialogs(None)
        self.assertEqual([(HELP_DIALOG, 'Escape')], s.keys)

    def test_changelog_after_upgrade(self):
        s = _DialogSession('1.7.6', [True, None])
        s._suppress_startup_dialogs('1.7.4')
        self.assertEqual([(HELP_DIALOG, 'Escape')], s.keys)

    def test_same_version_no_dialog(self):
        s = _DialogSession('1.7.6', [True])
        s._suppress_startup_dialogs('1.7.6')
        self.assertEqual([], s.keys)

    def test_dialog_never_appears(self):
        s = _DialogSession('1.7.6', [None])
        with self.assertRaisesRegex(UiSessionError, 'did not appear'):
            s._suppress_startup_dialogs(None, timeout=0.05)

    def test_dialog_never_closes(self):
        s = _DialogSession('1.7.6', [True])
        with self.assertRaisesRegex(UiSessionError, 'did not close'):
            s._suppress_startup_dialogs(None, timeout=0.05)


class TestFirmwareFirst(unittest.TestCase):

    def test_collection_order(self):
        # The conftest hook moves the firmware test ahead of every other test.
        ci_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = {**os.environ, 'JS_UITEST_DEVICES': 'JS220'}
        rsp = subprocess.run(
            [sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider',
             os.path.join(ci_dir, 'uitest')],
            cwd=os.path.dirname(ci_dir), env=env, capture_output=True, text=True, timeout=120)
        if rsp.returncode != 0:
            self.skipTest(f'collection needs the UI stack: {rsp.stdout[-500:]}')
        first = rsp.stdout.splitlines()[0]
        self.assertIn('test_device_firmware.py::test_device_firmware', first)


if __name__ == '__main__':
    unittest.main()
