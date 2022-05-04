# Copyright 2021 Jetperch LLC
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

from PySide6 import QtWidgets


class TextAnnotationDialog(QtWidgets.QDialog):
    """Edit text annotations.

    :param parent: The parent widget.
    :param cmdp: The command processor instance.
    :param annotation: The annotation instance to edit.

    The "default" QtGui.QInputDialog.getText dialogs does not service the
    timers in the main event loop, which causes sample drops and
    other bad behavior. This implementation keeps the main event loop running.
    """
    def __init__(self, parent, cmdp, annotation):
        QtWidgets.QDialog.__init__(self, parent)
        self._annotation = annotation
        self._cmdp = cmdp
        self.setObjectName('TextAnnotationDialog')
        self.setWindowTitle('Edit annotation')
        self.resize(300, 100)
        self.setModal(True)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._grid_widget = QtWidgets.QWidget(self)
        self._grid_layout = QtWidgets.QGridLayout(self._grid_widget)
        self._grid_layout.setObjectName('TextAnnotationDialogLayout')
        self._text_label = QtWidgets.QLabel('Text', self._grid_widget)
        self._grid_layout.addWidget(self._text_label, 0, 0)
        text = annotation.text
        if not isinstance(text, str):
            text = ''
        self._text_entry = QtWidgets.QLineEdit(text, self._grid_widget)
        self._text_entry.textChanged.connect(self._on_text_changed)
        self._grid_layout.addWidget(self._text_entry, 0, 1)

        self._button_frame = QtWidgets.QFrame(self)
        self._button_frame.setObjectName('button_frame')
        self._button_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self._button_frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self._button_layout = QtWidgets.QHBoxLayout(self._button_frame)
        self._button_layout.setObjectName('button_layout')
        self._button_spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._button_layout.addItem(self._button_spacer)

        self.okButton = QtWidgets.QPushButton(self._button_frame)
        self.okButton.setObjectName('okButton')
        self.okButton.pressed.connect(self.accept)
        self._button_layout.addWidget(self.okButton)

        self.cancelButton = QtWidgets.QPushButton(self._button_frame)
        self.cancelButton.setObjectName('cancelButton')
        self.cancelButton.pressed.connect(self.reject)
        self._button_layout.addWidget(self.cancelButton)

        self._layout.addWidget(self._grid_widget)
        self._layout.addWidget(self._button_frame)

        self.cancelButton.setText('Cancel')
        self.okButton.setText('OK')

    def _on_text_changed(self, text):
        self._cmdp.invoke('!Widgets/Waveform/annotation/update', [self._annotation.id, {'text': text}])

    def exec_(self):
        state_orig = self._annotation.state
        rv = QtWidgets.QDialog.exec_(self)
        if rv == 0:
            self._cmdp.invoke('!undo', force_signal=True)
        return '!Widgets/Waveform/annotation/update', [self._annotation.id, state_orig]
