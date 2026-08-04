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

"""
Test the main module restart support.
"""

import sys
import unittest
from unittest.mock import patch
from joulescope_ui import main


class TestRestartArgs(unittest.TestCase):

    def test_frozen(self):
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, 'executable', '/opt/joulescope/joulescope'), \
                patch.object(sys, 'argv', ['/opt/joulescope/joulescope', 'file.jls']):
            self.assertEqual(['/opt/joulescope/joulescope', 'file.jls'], main._restart_args())

    def test_python_m(self):
        with patch.object(sys, 'executable', '/usr/bin/python3'), \
                patch.object(sys, 'argv', ['/repo/joulescope_ui/__main__.py', 'ui', '--safe_mode']):
            self.assertEqual(['/usr/bin/python3', '-m', 'joulescope_ui', 'ui', '--safe_mode'],
                             main._restart_args())

    def test_joulescope_console_script(self):
        with patch.object(sys, 'executable', '/venv/bin/python3.13'), \
                patch.object(sys, 'argv', ['/venv/bin/joulescope', 'ui']):
            self.assertEqual(['/venv/bin/python3.13', '-m', 'joulescope_ui', 'ui'],
                             main._restart_args())

    def test_gui_script_windows_pythonw(self):
        # bare name: os.path.basename only splits backslash paths on Windows
        with patch.object(sys, 'executable', 'pythonw.exe'), \
                patch.object(sys, 'argv', ['joulescope_ui']):
            self.assertEqual(['pythonw.exe', '-m', 'joulescope_ui'],
                             main._restart_args())

    def test_unknown_executable_uses_argv(self):
        argv = ['/opt/custom/launcher', '--flag']
        with patch.object(sys, 'executable', '/opt/custom/launcher'), \
                patch.object(sys, 'argv', argv):
            args = main._restart_args()
            self.assertEqual(argv, args)
            self.assertIsNot(argv, args)


class TestRestartSpawn(unittest.TestCase):

    @unittest.skipUnless(sys.platform == 'win32', 'Windows detach flags')
    def test_spawn_windows(self):
        import subprocess
        with patch.object(main.subprocess, 'Popen') as popen:
            main._restart_spawn()
            flags = popen.call_args.kwargs['creationflags']
            self.assertEqual(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, flags)

    @unittest.skipIf(sys.platform == 'win32', 'POSIX detach flags')
    def test_spawn_posix(self):
        with patch.object(main.subprocess, 'Popen') as popen, \
                patch.object(sys, 'executable', '/usr/bin/python3'), \
                patch.object(sys, 'argv', ['/venv/bin/joulescope', 'ui']):
            main._restart_spawn()
            args = popen.call_args.args[0]
            self.assertEqual(['/usr/bin/python3', '-m', 'joulescope_ui', 'ui'], args)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])

    def test_spawn_scrubs_forced_qt_platform(self):
        with patch.object(main.subprocess, 'Popen') as popen, \
                patch.object(main, '_qt_platform_forced', True), \
                patch.dict(main.os.environ, {'QT_QPA_PLATFORM': 'xcb'}):
            main._restart_spawn()
            env = popen.call_args.kwargs['env']
            self.assertNotIn('QT_QPA_PLATFORM', env)

    def test_spawn_keeps_explicit_qt_platform(self):
        with patch.object(main.subprocess, 'Popen') as popen, \
                patch.object(main, '_qt_platform_forced', False), \
                patch.dict(main.os.environ, {'QT_QPA_PLATFORM': 'offscreen'}):
            main._restart_spawn()
            self.assertNotIn('env', popen.call_args.kwargs)

    def test_spawn_failure_does_not_raise(self):
        with patch.object(main.subprocess, 'Popen', side_effect=OSError('no such file')):
            main._restart_spawn()
