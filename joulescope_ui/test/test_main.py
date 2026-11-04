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
from unittest.mock import Mock, patch
from PySide6 import QtCore, QtGui
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

    def test_nuitka_windows(self):
        # Nuitka: sys.frozen unset, sys.executable is a nonexistent python.exe
        # in the dist directory (until multiprocessing import patches it).
        argv = ['C:\\Program Files\\Joulescope\\joulescope.exe', 'ui']
        with patch.object(main, 'is_nuitka', True), \
                patch.object(sys, 'executable', 'C:\\PROGRA~1\\JOULES~1\\python.exe'), \
                patch.object(sys, 'argv', argv):
            args = main._restart_args()
            self.assertEqual(argv, args)
            self.assertIsNot(argv, args)

    def test_nuitka_after_multiprocessing_patch(self):
        # After multiprocessing import, Nuitka patches sys.executable to the
        # binary; the result must not depend on which state we are in.
        argv = ['C:\\Program Files\\Joulescope\\joulescope.exe', 'ui']
        with patch.object(main, 'is_nuitka', True), \
                patch.object(sys, 'executable', 'C:\\PROGRA~1\\JOULES~1\\joulescope.exe'), \
                patch.object(sys, 'argv', argv):
            self.assertEqual(argv, main._restart_args())

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

    def test_spawn_missing_executable_falls_back_to_argv(self):
        argv = ['C:\\Program Files\\Joulescope\\joulescope.exe', 'ui']
        with patch.object(main.subprocess, 'Popen') as popen, \
                patch.object(main, '_restart_args',
                             return_value=['C:\\PROGRA~1\\JOULES~1\\python.exe', '-m', 'joulescope_ui', 'ui']), \
                patch.object(main.shutil, 'which', return_value=None), \
                patch.object(sys, 'argv', argv):
            main._restart_spawn()
            self.assertEqual(argv, popen.call_args.args[0])

    def test_spawn_failure_does_not_raise(self):
        with patch.object(main.subprocess, 'Popen', side_effect=OSError('no such file')):
            main._restart_spawn()


class TestWindowStateRepaint(unittest.TestCase):

    def _filter(self, obj, event_type):
        window = Mock(_window_handle=Mock(), normal_size=None)
        event = QtCore.QEvent(event_type)
        target = window._window_handle if obj is None else obj
        self.assertFalse(main.MainWindow.eventFilter(window, target, event))
        return window.update

    def test_state_change_repaints(self):
        self._filter(None, QtCore.QEvent.Type.WindowStateChange).assert_called_once()

    def test_other_event_ignored(self):
        self._filter(None, QtCore.QEvent.Type.Resize).assert_not_called()

    def test_other_object_ignored(self):
        self._filter(object(), QtCore.QEvent.Type.WindowStateChange).assert_not_called()


class TestWindowStateNormalSize(unittest.TestCase):

    def setUp(self):
        self.window = Mock(_window_handle=Mock())
        self.window.windowState.return_value = QtCore.Qt.WindowState.WindowNoState

    def _state(self, state):
        self.window._window_handle.windowStates.return_value = state
        event = QtCore.QEvent(QtCore.QEvent.Type.WindowStateChange)
        main.MainWindow.eventFilter(self.window, self.window._window_handle, event)

    def test_state(self):
        self._state(QtCore.Qt.WindowState.WindowMaximized)
        self.window.normal_size.on_state.assert_called_with(False)
        self._state(QtCore.Qt.WindowState.WindowFullScreen)
        self.window.normal_size.on_state.assert_called_with(False)
        self._state(QtCore.Qt.WindowState.WindowNoState)
        self.window.normal_size.on_state.assert_called_with(True)

    def _resize(self):
        event = QtGui.QResizeEvent(QtCore.QSize(1000, 700), QtCore.QSize(800, 600))
        main.MainWindow.eventFilter(self.window, self.window._window_handle, event)

    def test_resize_normal(self):
        self._resize()
        self.window.normal_size.on_resize.assert_called_with(1000, 700, True)

    def test_resize_not_normal(self):
        for state in [QtCore.Qt.WindowState.WindowMaximized, QtCore.Qt.WindowState.WindowMinimized]:
            self.window.windowState.return_value = state
            self._resize()
            self.window.normal_size.on_resize.assert_called_with(1000, 700, False)
