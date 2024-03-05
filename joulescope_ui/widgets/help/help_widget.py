# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_, register, urls
from joulescope_ui.help_ui import format_help
from joulescope_ui.styles import styled_widget

_USERS_GUIDES = N_("User's Guides")
_USER_INTERFACE = N_('User Interface')
_JOULESCOPE_UI_USERS_GUIDE = N_("Joulescope UI User's Guide")
_VISIT_FORUM = N_('Visit the Joulescope forum')
_SOURCE_CODE = N_('Joulescope source code')
_FILE_FORMAT = N_('file format')
_EXAMPLES = N_('examples')
_CONTACT_SUPPORT = N_('Contact support')

_HELP = f"""\
<html>
<head>
{{style}}
</head>
<body>

<p>{_USERS_GUIDES}<p>
<ul>
<li><a href="{urls.UI_USERS_GUIDE}">{_USER_INTERFACE} (UI)</a></li>
<li><a href="{urls.JS220_USERS_GUIDE}">JS220</a></li>
<li><a href="{urls.JS110_USERS_GUIDE}">JS110</a></li>
</ul>

<p>⭐ <a href="https://forum.joulescope.com/">{_VISIT_FORUM}</a> ⭐</p>

<p>{_SOURCE_CODE}</p>
<ul>
<li><a href="https://github.com/jetperch/pyjoulescope_ui">pyjoulescope_ui</a></li>
<li><a href="https://github.com/jetperch/pyjoulescope">pyjoulescope</a></li>
<li><a href="https://github.com/jetperch/joulescope_driver">joulescope_driver</a></li>
<li><a href="https://github.com/jetperch/jls">JLS {_FILE_FORMAT}</a></li>
<li><a href="https://github.com/jetperch/pyjoulescope_examples">Python {_EXAMPLES}</a></li>
</ul>

<p><a href="https://www.joulescope.com/pages/contact">{_CONTACT_SUPPORT}</a></p>
<p></p>
</body>
"""

_REPORT_ISSUE = N_('Report Issue')


@register
@styled_widget('Help')
class HelpWidget(QtWidgets.QWidget):
    CAPABILITIES = []

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('help_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._label = QtWidgets.QLabel('', self)
        self._label.setWordWrap(True)
        self._label.setOpenExternalLinks(True)
        self._layout.addWidget(self._label)

        self._report_issue = QtWidgets.QPushButton(_REPORT_ISSUE, self)
        self._report_issue.pressed.connect(self._on_report_issue)
        self._layout.addWidget(self._report_issue)

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self.on_style_change()

    @QtCore.Slot()
    def _on_report_issue(self):
        self.pubsub.publish('registry/report_issue/actions/!show', self)

    def on_style_change(self):
        _, html = format_help('Help', _HELP)
        self._label.setText(html)
