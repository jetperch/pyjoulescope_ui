# Copyright 2024 Jetperch LLC
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

"""Detect if the shift key is pressed to implement recovery modes.

The QtWidgets.QApplication.queryKeyboardModifiers() function only works
correctly after creating the Qt application.  We
"""


import ctypes
import sys
import logging


def _is_shift_pressed_windows():
    VK_SHIFT = 0x10  # Virtual-key code for the Shift key
    return ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000 != 0


def _is_shift_pressed_macos():
    core_graphics = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    kCGEventSourceStateHIDSystemState = 0

    # Function prototype for CGEventSourceKeyState
    core_graphics.CGEventSourceKeyState.argtypes = [ctypes.c_int, ctypes.c_int]
    core_graphics.CGEventSourceKeyState.restype = ctypes.c_bool

    left_shift_pressed = core_graphics.CGEventSourceKeyState(kCGEventSourceStateHIDSystemState,
                                                             0x38)  # 0x38 is the keycode for left Shift
    right_shift_pressed = core_graphics.CGEventSourceKeyState(kCGEventSourceStateHIDSystemState,
                                                              0x3C)  # 0x3C is the keycode for right Shift

    return left_shift_pressed or right_shift_pressed


def is_shift_pressed():
    """Detect if a shift key is pressed.

    :return: True if shift key is pressed, otherwise False.

    This function may be called at anytime, even before creating
    the Qt application.
    """
    try:
        platform = sys.platform
        if platform.startswith('win'):
            return _is_shift_pressed_windows()
        elif platform.startswith('darwin'):
            return _is_shift_pressed_macos()
        else:
            logging.getLogger(__name__).info('Shift key detection not available on Linux')
    except Exception:
        logging.getLogger(__name__).exception('Could not detect shift')
    return False


def _run():
    if is_shift_pressed():
        print('SHIFT PRESSED')
    else:
        print('no shift pressed')
    return 0


if __name__ == '__main__':
    _run()
