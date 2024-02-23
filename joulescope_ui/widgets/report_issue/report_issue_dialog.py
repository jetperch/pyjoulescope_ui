# Copyright 2023 Jetperch LLC
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

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import logging_util
from joulescope_ui.error_window import SubmitWidget
from joulescope_ui import reporter


class ReportIssueDialog(QtWidgets.QDialog):

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        logging_util.flush_all()
        path = reporter.create('user')

        self._layout = QtWidgets.QVBoxLayout(self)
        self._submit = SubmitWidget(self, path)
        self._submit.finished.connect(self._on_finish)
        self._layout.addWidget(self._submit)

        screen = QtGui.QGuiApplication.screenAt(self.geometry().center())
        if screen is not None:
            geometry = screen.geometry()
            self.resize(0.4 * geometry.width(), 0.6 * geometry.height())
        else:
            self.resize(600, 500)

    @QtCore.Slot()
    def _on_finish(self):
        self._submit.finished.disconnect(self._on_finish)
        self.close()

    @staticmethod
    def on_cls_action_show(pubsub, topic, value):
        dialog = ReportIssueDialog(value)
        if value is not None:
            dialog.setModal(True)
        dialog.open()
