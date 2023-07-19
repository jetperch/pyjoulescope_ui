# Copyright 2018-2023 Jetperch LLC
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

from joulescope_ui import N_, pubsub_singleton
from joulescope_ui import reporter
from joulescope_ui import versioned_file
from joulescope_ui.zip_inspector import ZipInspectorDialog
from PySide6 import QtCore, QtGui, QtWidgets
import json
import markdown
import os


_ERROR_INTRO = N_("The Joulescope UI encountered an error, and it cannot start correctly.")
_TROUBLESHOOT = N_("We are here to help troubleshoot! Fill in the details below, and click Submit.")
_CONTACT_TEXT = N_("""\
    Please consider providing your contact information.
    If you provide your contact information, we may contact
    you to assist with troubleshooting this issue.""")
_HTML = "<html><head></head><body>{body}</body></html>"
_RECOVERY = N_("Select an error recovery option.")
_CONTACT_FILE = os.path.join(pubsub_singleton.query('common/settings/paths/config'), 'contact.json')


class SubmitThread(QtCore.QThread):

    def run(self):
        reporter.publish()


class SubmitWidget(QtWidgets.QWidget):

    finished = QtCore.Signal()

    def __init__(self, parent, report_path):
        self._parent = parent
        self._thread = None
        super().__init__(parent=parent)
        self._report_path = report_path
        self._layout = QtWidgets.QVBoxLayout(self)
        self._help_label = QtWidgets.QLabel(_HTML.format(body=_TROUBLESHOOT), self)
        self._help_label.setWordWrap(True)
        self._layout.addWidget(self._help_label)

        try:
            with open(_CONTACT_FILE, 'rt') as f:
                contact = json.load(f)
        except Exception:
            contact = {}

        self._contact = QtWidgets.QGroupBox(N_('Contact information'), parent=self)
        self._contact_layout = QtWidgets.QGridLayout(self._contact)
        self._contact_details = QtWidgets.QLabel(_HTML.format(body=_CONTACT_TEXT), self._contact)
        self._contact_details.setWordWrap(True)
        self._first_name_label = QtWidgets.QLabel(N_('First name'), self._contact)
        self._first_name = QtWidgets.QLineEdit(self._contact)
        self._first_name.setText(contact.get('first_name', ''))
        self._email_label = QtWidgets.QLabel(N_('Email'), self._contact)
        self._email = QtWidgets.QLineEdit(self._contact)
        self._email.setText(contact.get('email', ''))
        self._contact_layout.addWidget(self._contact_details, 0, 0, 1, 2)
        self._contact_layout.addWidget(self._first_name_label, 1, 0, 1, 1)
        self._contact_layout.addWidget(self._first_name, 1, 1, 1, 1)
        self._contact_layout.addWidget(self._email_label, 2, 0, 1, 1)
        self._contact_layout.addWidget(self._email, 2, 1, 1, 1)
        self._contact.setLayout(self._contact_layout)
        self._layout.addWidget(self._contact)

        self._description = QtWidgets.QGroupBox(N_('Description'), parent=self)
        self._description.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._description_layout = QtWidgets.QVBoxLayout(self._description)
        self._description_tabs = QtWidgets.QTabWidget(self._description)
        self._description_tabs.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._description_edit = QtWidgets.QTextEdit(self._description_tabs)
        self._description_view = QtWidgets.QLabel(self._description_tabs)
        self._description_view.setWordWrap(True)
        self._description_view.setAlignment(QtCore.Qt.AlignTop)
        self._description_tabs.addTab(self._description_edit, N_('Edit'))
        self._description_tabs.addTab(self._description_view, N_('View'))
        self._description_layout.addWidget(self._description_tabs)
        self._description.setLayout(self._description_layout)
        self._layout.addWidget(self._description)

        self._buttons = QtWidgets.QWidget(self)
        self._buttons_layout = QtWidgets.QHBoxLayout(self._buttons)
        self._abort = QtWidgets.QPushButton(N_('Abort'), self._buttons)
        self._view = QtWidgets.QPushButton(N_('View'), self._buttons)
        self._submit = QtWidgets.QPushButton(N_('Submit'), self._buttons)
        self._buttons_layout.addWidget(self._abort)
        self._buttons_layout.addWidget(self._view)
        self._buttons_layout.addWidget(self._submit)
        self._buttons.setLayout(self._buttons_layout)
        self._layout.addWidget(self._buttons)

        self._description_tabs.currentChanged.connect(self._on_description_tab_changed)
        self._abort.pressed.connect(self._on_abort)
        self._view.pressed.connect(self._on_view)
        self._submit.pressed.connect(self._on_submit)

        self.setLayout(self._layout)

    def _on_description_tab_changed(self, index):
        if index == 1:
            md = markdown.Markdown(tab_length=2)
            html = md.convert(self._description_edit.toPlainText())
            html = '<html><head></head><body>' + html + '</body></html>'
            self._description_view.setText(html)

    def _on_abort(self):
        if os.path.isfile(self._report_path):
            os.remove(self._report_path)
        self.finished.emit()

    def _on_view(self):
        ZipInspectorDialog(self._parent, self._report_path)

    @QtCore.Slot()
    def _on_submit(self):
        self.setEnabled(False)
        self._submit.pressed.disconnect()
        contact = {
            'first_name': self._first_name.text(),
            'email': self._email.text(),
        }
        reporter.update_contact(self._report_path, contact)
        with open(_CONTACT_FILE, 'wt') as f:
            json.dump(contact, f)
        description = self._description_edit.toPlainText()
        reporter.update_description(self._report_path, description)
        self._thread = SubmitThread()
        self._thread.finished.connect(self._on_submit_finished)
        self._thread.start()

    @QtCore.Slot()
    def _on_submit_finished(self):
        self.finished.emit()


class RecoveryWidget(QtWidgets.QWidget):

    finished = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent=parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._help_label = QtWidgets.QLabel(_HTML.format(body=_RECOVERY), self)
        self._help_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._help_label.setWordWrap(True)
        self._layout.addWidget(self._help_label)

        self._revert1 = QtWidgets.QPushButton(N_('Revert to previous configuration'), self)
        self._defaults = QtWidgets.QPushButton(N_('Revert to defaults'), self)
        self._exit = QtWidgets.QPushButton(N_('Exit'), self)
        self._layout.addWidget(self._revert1)
        self._layout.addWidget(self._defaults)
        self._layout.addWidget(self._exit)

        self._revert1.pressed.connect(self._on_revert)
        self._defaults.pressed.connect(self._on_defaults)
        self._exit.pressed.connect(self._on_exit)

    def _on_revert(self):
        versioned_file.revert(pubsub_singleton.config_file_path, 1)
        self.finished.emit()

    def _on_defaults(self):
        versioned_file.remove(pubsub_singleton.config_file_path)
        self.finished.emit()

    def _on_exit(self):
        self.finished.emit()


class ErrorWindow(QtWidgets.QMainWindow):

    def __init__(self, parent=None, report_path=None):
        super().__init__(parent)
        icon = QtGui.QIcon()
        icon.addFile(u":/icon_64x64.ico", QtCore.QSize(), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)
        self.setWindowTitle(N_('Error'))

        self._center = QtWidgets.QWidget(self)
        self._layout = QtWidgets.QVBoxLayout(self._center)

        self._help_label = QtWidgets.QLabel(_HTML.format(body=_ERROR_INTRO), self)
        self._help_label.setWordWrap(True)

        self._submit = SubmitWidget(self, report_path)
        self._submit.finished.connect(self._on_submit_finished)

        self._recovery = RecoveryWidget(self)
        self._recovery.finished.connect(self.close)
        self._recovery.hide()

        self._layout.addWidget(self._help_label)
        self._layout.addWidget(self._submit)
        self._center.setLayout(self._layout)
        self.setCentralWidget(self._center)

        screen = QtGui.QGuiApplication.screenAt(self.geometry().center())
        if screen is not None:
            geometry = screen.geometry()
            self.resize(0.4 * geometry.width(), 0.6 * geometry.height())
        else:
            self.resize(600, 500)
        self.show()

    def _on_submit_finished(self):
        self._submit.hide()
        self._layout.removeWidget(self._submit)
        self._layout.addWidget(self._recovery)
        self._recovery.show()

    def closeEvent(self, event):
        event.accept()
