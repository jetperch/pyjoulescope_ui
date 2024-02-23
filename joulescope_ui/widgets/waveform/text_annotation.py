# Copyright 2021-2023 Jetperch LLC
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

from PySide6 import QtWidgets, QtGui, QtCore
from joulescope_ui import N_, pubsub_singleton, get_topic_name
from joulescope_ui.ui_util import comboBoxConfig


def _make_path(*args):
    path = QtGui.QPainterPath()
    path.moveTo(*args[0])
    for arg in args[1:]:
        path.lineTo(*arg)
    path.closeSubpath()
    return path


def _rotate(path, angle):
    tr = QtGui.QTransform()
    tr.rotate(angle)
    return tr.map(path)


_circle = QtGui.QPainterPath()
_circle.addEllipse(-1, -1, 2, 2)
_square = QtGui.QPainterPath()
_square.addRect(QtCore.QRectF(-1, -1, 2, 2))
_hex_points = [(0.5, 0.866), (1.0, 0.0), (0.5, -0.866), (-0.5, -0.866), (-1.0, 0), (-0.5, 0.866)]
_plus_points = [(-1, -0.4), (-1, 0.4), (-0.4, 0.4),
                (-0.4, 1), (0.4, 1), (0.4, 0.4),
                (1, 0.4), (1, -0.4), (0.4, -0.4),
                (0.4, -1), (-0.4, -1), (-0.4, -0.4)]
_star_points = [(0.0, -1.25), (-0.28075, -0.38625),
                (-1.18875, -0.38625), (-0.454, 0.1475),
                (-0.73475, 1.01125), (0.0, 0.4775),
                (0.73475, 1.01125), (0.454, 0.1475),
                (1.18875, -0.38625), (0.28075, -0.38625)]


SHAPES_DEF = [
    ['d', N_('diamond'), _make_path((-1, 0), (0, 1), (1, 0), (0, -1))],
    ['o', N_('circle'), _circle],
    ['h', N_('hexagon'), _make_path(*_hex_points)],
    ['s', N_('square'), _square],
    ['*', N_('star'), _make_path(*_star_points)],
    ['+', N_('plus'), _make_path(*_plus_points)],
    ['x', N_('cross'), _rotate(_make_path(*_plus_points), 45)],
    ['^', N_('triangle up'), _make_path((-1, 1), (0, -1), (1, 1))],
    ['v', N_('triangle down'), _make_path((-1, -1), (0, 1), (1, -1))],
    ['>', N_('triangle right'), _make_path((-1, 1), (-1, -1), (1, 0))],
    ['<', N_('triangle left'), _make_path((1, 1), (1, -1), (-1, 0))],
]

Y_POSITION_MODE = [
    ['manual',   N_('Manual')],    # value
    ['centered', N_('Centered')],  # NaN fract 1
]
Y_POSITION_MODE_VALUES = [v[0] for v in Y_POSITION_MODE]
Y_POSITION_MODE_NAMES = [v[1] for v in Y_POSITION_MODE]


class TextAnnotationDialog(QtWidgets.QDialog):
    """Edit text annotations.

    :param parent: The parent widget.
    :param annotation: The annotation instance to edit.

    The "default" QtGui.QInputDialog.getText dialogs does not service the
    timers in the main event loop, which causes sample drops and
    other bad behavior. This implementation keeps the main event loop running.
    """
    def __init__(self, parent, unique_id, annotation):
        self._unique_id = unique_id
        self._annotation = annotation
        super().__init__(parent)
        self.setObjectName('TextAnnotationDialog')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle('Edit annotation')
        self.resize(300, 100)
        self.setModal(True)
        self._layout = QtWidgets.QVBoxLayout(self)
        row = 0

        self._grid_widget = QtWidgets.QWidget(self)
        self._grid_layout = QtWidgets.QGridLayout(self._grid_widget)
        self._grid_layout.setObjectName('TextAnnotationDialogLayout')

        self._text_label = QtWidgets.QLabel(N_('Text'), self._grid_widget)
        self._grid_layout.addWidget(self._text_label, row, 0)
        text = annotation.get('text', '')
        self._text_entry = QtWidgets.QLineEdit(text, self._grid_widget)
        self._text_entry.textChanged.connect(self._on_text_changed)
        self._grid_layout.addWidget(self._text_entry, row, 1)
        row += 1

        self._text_show_label = QtWidgets.QLabel(N_('Show text'), self._grid_widget)
        self._grid_layout.addWidget(self._text_show_label, row, 0)
        text_show = annotation.get('text_show', True)
        self._text_show = QtWidgets.QCheckBox(self._grid_widget)
        self._text_show.setChecked(text_show)
        self._text_show.toggled.connect(self._on_text_show_changed)
        self._grid_layout.addWidget(self._text_show, row, 1)
        row += 1

        self._shape_label = QtWidgets.QLabel(N_('Shape'), self._grid_widget)
        self._grid_layout.addWidget(self._shape_label, row, 0)
        self._shapes = QtWidgets.QComboBox(self)
        shape_names = [x[1] for x in SHAPES_DEF]
        shape = annotation.get('shape', 0)
        comboBoxConfig(self._shapes, shape_names, shape_names[shape])
        self._shapes.currentIndexChanged.connect(self._on_shapes_changed)
        self._grid_layout.addWidget(self._shapes, row, 1)
        row += 1

        self._y_mode_label = QtWidgets.QLabel(N_('Y Mode'), self._grid_widget)
        self._grid_layout.addWidget(self._y_mode_label, row, 0)
        self._y_mode = QtWidgets.QComboBox(self)
        y_mode = annotation.get('y_mode', None)
        try:
            y_mode_index = Y_POSITION_MODE_VALUES.index(y_mode)
        except Exception:
            y_mode_index = 0
        comboBoxConfig(self._y_mode, Y_POSITION_MODE_NAMES, None)
        self._y_mode.setCurrentIndex(y_mode_index)
        self._y_mode.currentIndexChanged.connect(self._on_y_mode_changed)
        self._grid_layout.addWidget(self._y_mode, row, 1)
        row += 1

        # shape_size: small, medium, large
        # font

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
        self.finished.connect(self._on_finished)

    def _update(self):
        if 'id' in self._annotation:
            topic = get_topic_name(self._unique_id)
            pubsub_singleton.publish(f'{topic}/actions/!text_annotation', ['update', self._annotation])

    def _on_text_changed(self, text):
        self._annotation['text'] = text
        self._update()

    def _on_text_show_changed(self, value):
        self._annotation['text_show'] = bool(value)
        self._update()

    def _on_shapes_changed(self, index):
        self._annotation['shape'] = index
        self._update()

    def _on_y_mode_changed(self, index):
        self._annotation['y_mode'] = Y_POSITION_MODE_VALUES[index]
        self._update()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        if 'id' not in self._annotation:
            topic = get_topic_name(self._unique_id)
            pubsub_singleton.publish(f'{topic}/actions/!text_annotation', ['add', self._annotation])
        self.close()


def run_example():
    app = QtWidgets.QApplication()
    annotation = {
        'plot': 0,
        'text': 'hello world!',
        'text_show': True,
        'shape': 1,
        'x': 0,  # i64 timestamp
        'y': None,
        'y_mode': 'centered',  # 'manual', 'centered'
        # potential future keys: shape_size, shape_color, text_font, text_size
    }

    widget = TextAnnotationDialog(None, 'WaveformWidget:000000', annotation)
    widget.show()
    app.exec()


if __name__ == '__main__':
    run_example()
