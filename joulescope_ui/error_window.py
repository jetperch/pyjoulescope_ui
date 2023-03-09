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


from .logging_util import log_info
import io
import pyperclip
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QMainWindow, QSizePolicy, QVBoxLayout, QWidget
import traceback


_ERROR_MESSAGE = """\
<html>
<head>
</head>
<body>
<h2>Unexpected Error</h2>
<p>The Joulescope UI encountered an error,<br/>
and it cannot start correctly.<p>
<p>Please report this error by contacting us:
<ul>
   <li><a href="https://www.joulescope.com/contact">Contact form</a></li>
   <li><a href="https://forum.joulescope.com/">Joulescope forum</a></li>
   <li><a href="https://github.com/jetperch/pyjoulescope_ui/issues">GitHub</a></li>
</ul>
</p>
<p>Please include the text below,<br/>
which has been automatically copied to your clipboard.</p>
<pre>
{msg_err}
</pre>
</body></html>
"""


class ErrorWindow(QMainWindow):

    def __init__(self):
        super(ErrorWindow, self).__init__()
        with io.StringIO() as f:
            traceback.print_exc(file=f)
            t = f.getvalue()

        msg_err = '\n'.join([
            "--------------------",
            f"Exception on Joulescope UI startup. ",
            '',
            t,
            'info = ' + log_info(),
            "--------------------",
        ])
        pyperclip.copy(msg_err)
        msg = _ERROR_MESSAGE.format(msg_err=msg_err)

        self.setObjectName('ErrorWindow')
        self.resize(600, 300)

        icon = QIcon()
        icon.addFile(u":/icon_64x64.ico", QSize(), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)
        self.setWindowTitle('Joulescope UI Launch Error')

        self.centralwidget = QWidget(self)
        self.centralwidget.setObjectName('centralwidget')
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.label = QLabel(self.centralwidget)
        self.label.setObjectName(u"label")
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)

        self.label.setText(msg)
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.label.setOpenExternalLinks(True)

        self.verticalLayout.addWidget(self.label)
        self.setCentralWidget(self.centralwidget)
        self.show()
