# Copyright 2023-2024 Jetperch LLC
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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_, pubsub_singleton
import platform

_PROMPT_TOPIC = 'registry/app/settings/intel_graphics_prompt'
_OPENGL_RENDERER_TOPIC = 'registry/app/settings/opengl'

_P1 = N_("""This computer has Intel graphics.
If the computer has a discrete graphics card, please adjust
your graphics settings to run
this application using the graphics card.""")
_P2 = N_("""If the computer only has Intel graphics, we recommend that you
update your graphics drivers.  You can download the latest graphics
drivers from your computer manufacturer or Intel.""")
_P3 = N_('You may observe strange graphics hangs with the latest Intel driver.')
_P4 = N_("""If this happens on your computer, 
then you can switch to the software OpenGL renderer.
The software OpenGL renderer may work around Intel driver instabilities,
but it runs slower possibly causing performance issues.
On a small number of computers,
it does not run correctly causing a white application screen.
You will need to close and reopen this application for the change
to take effect.""")
_P5 = N_('Would you like to switch to the software OpenGL renderer?')
_P6 = N_("""If you are unsure, select "No" and leave "Do not show again" unchecked.
If you observe the graphics hangs, you can select "Yes" in the future.
You can select the OpenGL renderer at any time using
Widgets → Settings → Common → opengl.  The default is "desktop".""")


_MSG = N_(f"""<html><body>
<p>{_P1}</p>
<p>{_P2}
[<a href="https://www.intel.com/content/www/us/en/search.html#sort=relevancy&f:@tabfilter=[Downloads]&f:@stm_10385_en=[Graphics]">Intel</a>]
</p>
<p>{_P3}
[<a href="https://github.com/jetperch/pyjoulescope_ui/issues/216">issue #216</a>]
{_P4}</p>
<p>{_P5}</p>
<p>{_P6}</p>
</body></html>""")


class IntelGraphicsDialog(QtWidgets.QDialog):
    """Display OpenGL dialog to change to software renderer."""

    shown = False

    def __init__(self, pubsub, done_action):
        self.pubsub = pubsub
        self._done_action = done_action
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self.setObjectName("opengl_dialog")
        self._layout = QtWidgets.QVBoxLayout(self)

        self._label = QtWidgets.QLabel(_MSG, self)
        self._label.setWordWrap(True)
        self._label.setOpenExternalLinks(True)
        self._layout.addWidget(self._label)

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._checkbox = QtWidgets.QCheckBox(N_('Do not show again'), self)
        self._layout.addWidget(self._checkbox)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Yes | QtWidgets.QDialogButtonBox.No)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

        self.resize(600, 400)
        self.setWindowTitle(N_('Intel graphics detected'))
        self.finished.connect(self._on_finish)

        self.open()
        IntelGraphicsDialog.shown = True

    @QtCore.Slot()
    def _on_finish(self):
        pubsub_singleton.publish(_PROMPT_TOPIC, not self._checkbox.isChecked())
        if self.result():
            pubsub_singleton.publish(_OPENGL_RENDERER_TOPIC, 'software')
        if self._done_action is not None:
            self.pubsub.publish(*self._done_action)
        self.close()


def intel_graphics_dialog(pubsub, done_action):
    if IntelGraphicsDialog.shown:
        return
    if platform.system() != 'Windows':
        return
    opengl_renderer = pubsub_singleton.query(_OPENGL_RENDERER_TOPIC, default=None)
    if opengl_renderer == 'software':
        return
    show = pubsub_singleton.query(_PROMPT_TOPIC, default=True)
    if show:
        IntelGraphicsDialog(pubsub, done_action)
    elif done_action is not None:
        pubsub.publish(*done_action)
