# Copyright 2019 Jetperch LLC
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


from PySide2 import QtWidgets, QtCore
from joulescope_ui.preferences_ui import widget_factory
from joulescope.units import unit_prefix, three_sig_figs
from joulescope_ui.ui_util import comboBoxConfig
import logging


log = logging.getLogger(__name__)


class QExpanderWidget(QtWidgets.QWidget):

    def __init__(self, parent=None, title='', animationDuration=300):
        """
        References:
            https://stackoverflow.com/a/56275050/888653
            https://doc.qt.io/qt-5/qgridlayout.html
        """
        super(QExpanderWidget, self).__init__(parent=parent)

        self.animationDuration = animationDuration
        self.toggleAnimation = QtCore.QParallelAnimationGroup()
        self.contentArea = QtWidgets.QWidget()  # QScrollArea()
        self.headerLine = QtWidgets.QFrame()
        self.toggleButton = QtWidgets.QToolButton()
        self.mainLayout = QtWidgets.QGridLayout()

        toggleButton = self.toggleButton
        toggleButton.setStyleSheet("QToolButton { border: none; }")
        toggleButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        toggleButton.setArrowType(QtCore.Qt.RightArrow)
        toggleButton.setText(str(title))
        toggleButton.setCheckable(True)
        toggleButton.setChecked(False)

        headerLine = self.headerLine
        headerLine.setFrameShape(QtWidgets.QFrame.HLine)
        headerLine.setFrameShadow(QtWidgets.QFrame.Sunken)
        headerLine.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)

        # start out collapsed
        self.contentArea.setMaximumHeight(0)
        self.contentArea.setMinimumHeight(0)
        # let the entire widget grow and shrink with its content
        toggleAnimation = self.toggleAnimation
        toggleAnimation.addAnimation(QtCore.QPropertyAnimation(self, b"minimumHeight"))
        toggleAnimation.addAnimation(QtCore.QPropertyAnimation(self, b"maximumHeight"))
        toggleAnimation.addAnimation(QtCore.QPropertyAnimation(self.contentArea, b"maximumHeight"))
        # don't waste space
        mainLayout = self.mainLayout
        mainLayout.setVerticalSpacing(0)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        row = 0
        mainLayout.addWidget(self.toggleButton, row, 0, 1, 1, QtCore.Qt.AlignLeft)
        mainLayout.addWidget(self.headerLine, row, 2, 1, 1)
        row += 1
        mainLayout.addWidget(self.contentArea, row, 0, 1, 3)
        self.setLayout(self.mainLayout)

        def start_animation(checked):
            arrow_type = QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            direction = QtCore.QAbstractAnimation.Forward if checked else QtCore.QAbstractAnimation.Backward
            toggleButton.setArrowType(arrow_type)
            self.toggleAnimation.setDirection(direction)
            self.toggleAnimation.start()

        self.toggleButton.clicked.connect(start_animation)

    def resizeContentLayout(self):
        collapsedHeight = self.sizeHint().height() - self.contentArea.maximumHeight()
        contentHeight = self.contentArea.sizeHint().height()
        print(f'sizeHint={contentHeight}')
        for i in range(self.toggleAnimation.animationCount()-1):
            expandAnimation = self.toggleAnimation.animationAt(i)
            expandAnimation.setDuration(self.animationDuration)
            expandAnimation.setStartValue(collapsedHeight)
            expandAnimation.setEndValue(collapsedHeight + contentHeight)
        contentAnimation = self.toggleAnimation.animationAt(self.toggleAnimation.animationCount() - 1)
        contentAnimation.setDuration(self.animationDuration)
        contentAnimation.setStartValue(0)
        contentAnimation.setEndValue(contentHeight)


class DeveloperWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._main_layout = QtWidgets.QVBoxLayout(self)
        self._device_parameters_widget = QExpanderWidget(self, 'Device Parameters')
        self._device_parameters_layout = QtWidgets.QFormLayout(self._device_parameters_widget.contentArea)

        self._device_status_widget = QExpanderWidget(self, 'Device Status')
        self._device_status_layout = QtWidgets.QGridLayout(self._device_status_widget.contentArea)

        self._spacer = QtWidgets.QSpacerItem(20, 461, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._main_layout.addWidget(self._device_parameters_widget)
        self._main_layout.addWidget(self._device_status_widget)
        self._main_layout.addItem(self._spacer)

        self._parameters = {}
        self._status = {}
        self._status_row = 0
        self._source = None
        cmdp.subscribe('Device/#state/status', self._on_device_state_status, update_now=True)
        cmdp.subscribe('Device/#state/source', self._on_device_state_source, update_now=True)

    def _parameters_clean(self):
        for key, widget in self._parameters.items():
            widget.unpopulate(self._device_parameters_widget.contentArea)
        self._parameters = {}
        while self._device_parameters_layout.rowCount():
            self._device_parameters_layout.removeRow(0)
        self._device_parameters_widget.resizeContentLayout()

    def _status_clean(self):
        for key, widgets in self._status.items():
            for widget in widgets:
                self._device_status_layout.removeWidget(widget)
                widget.setParent(None)
        self._status = {}
        self._status_row = 0
        self._device_status_widget.resizeContentLayout()

    def _on_device_state_source(self, topic, value):
        if self._source == value:
            return
        self._source = value
        if value in ['None', 'File']:
            self._status_clean()
            self._parameters_clean()
        else:
            self._parameters_populate()

    def _parameters_populate(self):
        self._parameters_clean()
        for topic, value in self._cmdp.preferences.flatten().items():
            if not topic.startswith('Device/parameter/') or topic[-1] == '/':
                continue
            widget = widget_factory(self._cmdp, topic)
            if widget is not None:
                widget.populate(self._device_parameters_widget.contentArea)
                self._parameters[topic] = widget
        self._device_parameters_layout.activate()
        self._device_parameters_widget.resizeContentLayout()

    def _on_device_state_status(self, topic, status):
        is_changed = False
        for root_key, root_value in status.items():
            if root_key == 'endpoints':
                root_value = root_value.get('2', {})
            for key, value in root_value.items():
                # print(f'{root_key}.{key} = {value}')
                s = self._status.get(key)
                if s is None:  # create
                    # print(f'Create {key} : {self._status_row}')
                    label_name = QtWidgets.QLabel(self._device_status_widget.contentArea)
                    label_value = QtWidgets.QLabel(self._device_status_widget.contentArea)
                    label_units = QtWidgets.QLabel(self._device_status_widget.contentArea)
                    self._device_status_layout.addWidget(label_name, self._status_row, 0, 1, 1)
                    self._device_status_layout.addWidget(label_value, self._status_row, 1, 1, 1)
                    self._device_status_layout.addWidget(label_units, self._status_row, 2, 1, 1)
                    label_name.setText(key)
                    min_height = label_name.sizeHint().height() + 5
                    label_name.setMinimumHeight(min_height)
                    self._device_status_layout.setRowMinimumHeight(self._status_row, min_height)
                    self._status_row += 1
                    s = [label_name, label_value, label_units]
                    self._status[key] = s
                    is_changed = True
                fmt = value.get('format', None)
                v = value['value']
                c = ''
                if fmt is None:
                    v, c, _ = unit_prefix(v)
                    k = three_sig_figs(v)
                else:
                    k = fmt.format(v)
                units = str(c + value['units'])
                s[1].setText(k)
                s[2].setText(units)
        if is_changed:
            self._device_status_widget.resizeContentLayout()


def widget_register(cmdp):
    return {
        'name': 'Developer',
        'brief': 'Developer information and controls.',
        'class': DeveloperWidget,
        'location': QtCore.Qt.LeftDockWidgetArea,
        'singleton': True,
    }
