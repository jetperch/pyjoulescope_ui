#!/usr/bin/env python
# Copyright 2018 Jetperch LLC
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
Simple programmatic GUI creation for parameters.

Much inspiration for this module was drawn from the excellent
`guidata package <https://code.google.com/p/guidata/>`_.
"""

from PySide2 import QtWidgets, QtGui, QtCore
import os
import numpy as np
from .ui_util import clear_layout
import logging
log = logging.getLogger(__name__)


class Parameter(object):
    """The base class for a parameter value with validation and GUI bindings.

    :param str name: The name for this item.
    :param value: The default value.  None (default).
    :param tooltip: The text for the tooltip.  None (default) is equivalent
        to the empty string ''.

    Once an instance is created, it can be added to a parent widget using the
    :meth:`populate` method.  The parent widget should contain either no
    layout or a form layout.

    The remaining methods are normally used by the derived classes to
    implement their specialized behaviors and should not be called by an
    application.
    """
    def __init__(self, name: str, value=None, tooltip: str=None):
        self.name = str(name)
        self._value = None
        self.tooltip = tooltip

        self.callback = None
        """The callable that is called on any value changes.  The
        callable will be passed self as the sole argument."""

        self.validator = None
        """A custom validation callable that takes a potential value
        as the sole argument and raises and exception for an invalid value.
        The callable returns the new value.
        This callable should be used by the application for any custom
        validation beyond the basic type validation.  A validator must not
        have side effects!"""

        if value is not None:
            try:
                self.value = value
            except Exception:
                log.exception('Invalid initial value for "%s" = "%s"',
                              self.name, value)
                self._value = value
        self.label = None
        self.widget = None
        self.layout = None

    def populate_subclass(self, parent):
        """Populate the parent widget with additional widgets for the
        derived subclass.

        :param parent: The parent widget to populate.

        Use :meth:`addWidget` to add additional GUI widgets.

        The :meth:`on_changed` method is guaranteed to be called following
        this call (if the current value is valid) to ensure that the GUI
        idgets are updated with the current value.  Derived implementations
        do not need to call this trivial base implementation.
        """
        pass

    def populate(self, parent):
        """Populate a parent widget with this parameter.

        :param parent: The parent widget to populate.
        :return: self.

        Do not override this method.  Override :meth:`populate_subclass` which
        is called by this method appropriately.

        Each parameter consists of two default widgets:
        self.label and self.widget.
        The self.label is a QLabel that contains the self.name.  The
        self.widget contains a self.layout, and the exact contents are
        configured by the derived class.  Both widgets are added to the
        parent by calling the parent's layout.addRow().
        """
        layout = parent.layout()
        if layout is None:
            layout = QtWidgets.QFormLayout(parent)
        self.label = QtWidgets.QLabel(self.name, parent)
        if self.tooltip is not None:
            self.label.setToolTip(self.tooltip)
        self.widget = QtWidgets.QWidget(parent)
        self.layout = QtWidgets.QHBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow(self.label, self.widget)
        self.populate_subclass(parent)
        try:
            self.validate(self._value)
            self.on_valid()
            self.on_changed()
        except Exception:
            self.on_invalid()
        return self

    def unpopulate(self, parent):
        """Unpopulated a parent widget to remove this parameter.

        :param parent: The parent widget to unpopulate.
        :return: self.
        """
        if self.label is not None:
            layout = parent.layout()
            layout.takeRow(self.label)
            self.label.deleteLater()
            clear_layout(self.layout)
        self.label = None
        self.widget = None
        self.layout = None

    def add_widget(self, widget, stretch=0):
        """Add a new widget to the layout.

        :param widget: The widget to add which will have its parent set to
            self.widget.
        :param stretch: The stretch value.  0 (Default) uses a balanced layout.
        """
        widget.setParent(self.widget)
        self.layout.addWidget(widget, stretch)

    def validate(self, x):
        """Validate an assignment to value for this parameter.

        :param x: The potential parameter value.
        :return: The actual parameter value.
        :raise ValueError: If x is not an allowed value.

        This method should be considered protected and should only be called
        through the value.setter.  Derived classes should safely presume that
        self._value will be assigned with the result.  Derived implementations
        do not need to call this trivial base implementation.
        """
        return x

    @property
    def value(self):
        """Get the current value for this parameter."""
        return self._value

    @value.setter
    def value(self, x):
        """Set the current value for this parameter.

        :param x: The new value for x.
        :raises ValueError: If x is not valid.

        Derived classes should not override this method.  Instead
        override :meth:`validate` and :meth:`on_changed`.
        """
        try:
            value = self.validate(x)
            if callable(self.validator):
                value = self.validator(value)
            self.on_valid()
        except Exception:
            self.on_invalid()
            raise
        if value != self._value:
            self._value = value
            self.on_changed()
            if self._value is not None and callable(self.callback):
                self.callback(self)  # notify observer

    def on_valid(self):
        """Notify the GUI elements that the current value is valid.

        Derived implementations do not need to call this trivial base
        implementation.
        """
        pass

    def on_invalid(self):
        """Notify the GUI elements that the current value is invalid.

        Derived implementations do not need to call this trivial base
        implementation.
        """
        pass

    def update(self, value=None):
        """Set the value property using a method.

        :param value: The new value for this instance.  If None (Default), then
            do not send up change notifications but mark as invalid.
        :raises ValueError: If x is not valid.

        Calling self.update(value) is very similar to "self.value = value",
        except that a value of None is handled differently.  This method
        should normally be called by derived classes and not application code.
        """
        if value is None:
            self._value = None
            self.on_invalid()
        else:
            self.value = value

    def on_changed(self):
        """Notify the GUI of a value change.

        Derived classes should override to update the GUI elements.
        Every GUI element must be updated as appropriate during calls to
        on_changed.  To prevent a circular loop, GUI elements should only
        change if needed so that they do not unnecessarily signal a change
        when no change occurred.
        """
        pass


class Bool(Parameter):
    """An boolean valued item.

    :param str name: The name for this item.
    :param bool value: The starting value for this item.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=False, tooltip: str=''):
        self.checkbox = None
        Parameter.__init__(self, name, value, tooltip)

    def populate_subclass(self, parent):
        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(self.value)
        self.checkbox.clicked.connect(self.on_clicked)
        self.add_widget(self.checkbox)

    def validate(self, x):
        return bool(x)

    def on_clicked(self):
        self.value = self.checkbox.isChecked()

    def on_changed(self):
        if self.checkbox and self.checkbox.isChecked() != self.value:
            self.checkbox.setChecked(self.value)


class Int(Parameter):
    """An integer valued item.

    :param str name: The name for this item.
    :param int value: The starting value for this item.
    :param (int, int) vrange: The (min, max) inclusive range for values.
        None (default) allows for unbounded integers.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=None, vrange=None, tooltip: str=''):
        if vrange is not None:
            assert(len(vrange) == 2)
            vrange = (int(vrange[0]), int(vrange[1]))
        if value is None:
            if vrange is not None:
                value = vrange[0]
            else:
                value = 0
        self.vrange = vrange
        self.textedit = None
        self.spinedit = None
        self.slider = None
        Parameter.__init__(self, name, value, tooltip)

    def populate_subclass(self, parent):
        if self.vrange is None:
            self.textedit = QtWidgets.QLineEdit(self.widget)
            self.textedit.setText(str(self.value))
            self.textedit.textChanged.connect(self._on_text_changed)
            self.add_widget(self.textedit)
        else:
            self.spinedit = QtWidgets.QSpinBox(self.widget)
            self.spinedit.setRange(*self.vrange)
            self.spinedit.setValue(self.value)
            self.spinedit.valueChanged.connect(self.update)
            self.add_widget(self.spinedit)
            self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self.widget)
            self.slider.setTracking(True)
            self.slider.setRange(*self.vrange)
            self.slider.setSingleStep(1)
            page_step = (self.vrange[1] - self.vrange[0]) / 10
            self.slider.setPageStep(page_step)
            self.slider.setValue(self.value)
            self.slider.valueChanged.connect(self._on_slider_changed)
            self.add_widget(self.slider)

    def on_valid(self):
        if self.textedit is not None:
            self.textedit.setStyleSheet("")

    def on_invalid(self):
        if self.textedit is not None:
            self.textedit.setStyleSheet("QLineEdit{background:red;}")

    def validate(self, x):
        x = int(x)
        if self.vrange is not None:
            if x < self.vrange[0] or x > self.vrange[1]:
                raise ValueError('Out of range')
        return x

    def _on_slider_changed(self, value):
        v = int(value)
        if v != self._value:
            self.value = v

    def _on_text_changed(self, value):
        try:
            self.value = str(value)
        except ValueError:
            pass

    def on_changed(self):
        v = self.value
        if self.textedit:
            text = str(v)
            if str(self.textedit.text()) != text:
                self.textedit.setText(text)
        if self.spinedit is not None:
            if self.spinedit.value() != v:
                self.spinedit.setValue(v)
        if self.slider is not None:
            if self.slider.value() != v:
                self.slider.setValue(v)


class Float(Parameter):
    """An floating point valued item.

    :param str name: The name for this item.
    :param float value: The starting value for this item.
    :param (float, float) vrange: The (min, max) inclusive range for values.
        None (default) allows for unbounded floating point values.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name:str , value=None, vrange=None, tooltip: str=''):
        if vrange is not None:
            assert(len(vrange) == 2)
            vrange = (float(vrange[0]), float(vrange[1]))
        if value is None:
            if vrange is not None:
                value = vrange[0]
            else:
                value = 0.
        self.textedit = None
        self.slider = None
        self.vrange = vrange
        Parameter.__init__(self, name, value, tooltip)

    def populate_subclass(self, parent):
        self.textedit = QtWidgets.QLineEdit(self.widget)
        self.textedit.setText(str(self.value))
        self.textedit.textChanged.connect(self._on_text_changed)
        self.add_widget(self.textedit)
        if self.vrange is not None:
            self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self.widget)
            self.slider.setTracking(True)
            self.slider.setRange(0, 250)
            self.slider.setSingleStep(1)
            page_step = (self.vrange[1] - self.vrange[0]) / 10
            self.slider.setPageStep(page_step)
            self.slider.setValue(self._float2slider(self.value))
            self.slider.valueChanged.connect(self._on_slider_changed)
            self.add_widget(self.slider, 1)

    def _float2slider(self, x):
        v = (x - self.vrange[0]) * 250 / (self.vrange[1] - self.vrange[0])
        v = np.round(v)
        return int(v)

    def _slider2float(self, x):
        return x * (self.vrange[1] - self.vrange[0]) / 250.  + self.vrange[0]

    def validate(self, x):
        try:
            x = float(x)
            if self.vrange is not None:
                if x < self.vrange[0] or x > self.vrange[1]:
                    raise ValueError('Out of range')
            if self.textedit is not None:
                self.textedit.setStyleSheet("")
        except Exception:
            if self.textedit is not None:
                self.textedit.setStyleSheet("QLineEdit{background:red;}")
            raise
        return x

    def _on_slider_changed(self, value):
        v = self._slider2float(value)
        if self._float2slider(self._value) != value:
            self.value = v

    def _on_text_changed(self, value):
        try:
            self.value = str(value)
        except ValueError:
            self.update(None)

    def on_changed(self):
        v = self.value
        if self.textedit:
            text = str(self.textedit.text())
            if v != float(text):
                self.textedit.setText(str(v))
        if self.slider is not None:
            v_pos = self._float2slider(v)
            if self.slider.value() != v_pos:
                self.slider.setValue(v_pos)


class Enum(Parameter):
    """An enumerated valued item.

    :param str name: The name for this item.
    :param str value: The starting value for this item.
    :param list(str) values: The list of possible values.
    :param tooltip: The text for the tooltip.
    :param closed: When True, the allowed value states are closed on the set
        of values.  When False, arbitrary string values are allowed.
    """
    def __init__(self, name: str, value=None, values=None, tooltip: str='', closed=True):
        if value is None and values:
            value = values[0]
        self._values = values
        self._closed = closed
        self.comboBox = None
        Parameter.__init__(self, name, value, tooltip)

    def populate_subclass(self, parent):
        self.comboBox = QtWidgets.QComboBox(self.widget)
        self._update_values()
        if not self._closed:
            self.comboBox.setEditable(True)
        self.add_widget(self.comboBox)

    def _update_values(self):
        if self.comboBox is None:
            return
        try:
            self.comboBox.currentIndexChanged.disconnect()
        except Exception:
            pass
        try:
            self.comboBox.editTextChanged.disconnect()
        except Exception:
            pass
        self.comboBox.clear()
        if self._values:
            for v in self._values:
                self.comboBox.addItem(str(v))
            self.comboBox.setEnabled(True)
        elif self._closed:
            self.comboBox.setEnabled(False)
        else:
            self.comboBox.setEnabled(True)
        if self._value is not None:
            idx = self.comboBox.findText(self._value)
            if idx >= 0:
                self.comboBox.setCurrentIndex(idx)
            elif not self._closed:
                self.comboBox.setEditText(self._value)
        self.comboBox.currentIndexChanged.connect(self.update)
        self.comboBox.editTextChanged.connect(self._on_text_changed)

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, values):
        self._values = values
        self._update_values()
        if self._values and self._closed:
            if self._value not in self._values:
                self.value = self._values[0]

    def validate(self, x):
        if x is None:
            pass
        elif isinstance(x, int):  # presume index
            if x < 0 or x >= len(self._values):
                raise ValueError(x)
            x = self._values[x]
        elif isinstance(x, str):  #allowed
            if self._closed: # require to be in values
                self._values.index(x)
        else:
            raise ValueError(x)
        return x

    def on_changed(self):
        v = self.value
        if self.comboBox is not None and v is not None:
            if v != str(self.comboBox.currentText()):
                try:
                    idx = self._values.index(v)
                    self.comboBox.setCurrentIndex(idx)
                except (TypeError, AttributeError, ValueError):
                    if not self._closed:
                        self.comboBox.setEditText(v)

    def _on_text_changed(self, txt):
        txt = str(txt)
        self.update(txt)

    def on_valid(self):
        if self.comboBox is not None:
            self.comboBox.setStyleSheet("")

    def on_invalid(self):
        if self.comboBox is not None:
            self.comboBox.setStyleSheet("QComboBox{background:red;}")


class String(Parameter):
    """An arbitrary string value.

    :param str name: The name for this item.
    :param str value: The starting value for this item.  None (default) is
        equivalent to ''.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=None, tooltip: str=''):
        self.lineEdit = None
        Parameter.__init__(self, name, value, tooltip)

    def populate_subclass(self, parent):
        self.lineEdit = QtWidgets.QLineEdit(self.widget)
        if self.value is not None:
            self.lineEdit.setText(self.value)
        self.lineEdit.textChanged.connect(self._on_text_changed)
        self.add_widget(self.lineEdit)

    def on_valid(self):
        if self.lineEdit is not None:
            self.lineEdit.setStyleSheet("")

    def on_invalid(self):
        if self.lineEdit is not None:
            self.lineEdit.setStyleSheet("QLineEdit{background:red;}")

    def _on_text_changed(self, value):
        try:
            self.value = str(value)
        except ValueError:
            pass

    def on_changed(self):
        v = self.value
        if v is None:
            print('on_changed None')
            return
        if self.lineEdit is not None:
            if v != str(self.lineEdit.text()):
                self.lineEdit.setText(v)


class StringSelect(Enum):
    """An arbitrary string value with choices.

    :param str name: The name for this item.
    :param str value: The starting value for this item.  None (default) is
        equivalent to ''.
    :param list(str) values: The list of possible values.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=None, values=None, tooltip: str=''):
        Enum.__init__(self, name, value, values, tooltip, closed=False)


class RichTextView(Parameter):
    """A rich text view (no GUI edit).

    :param str name: The name for this item.
    :param value: The default value.  None (default).
    :param tooltip: The text for the tooltip.  None (default) is equivalent
        to the empty string ''.
    """
    def __init__(self, name: str, value=None, tooltip: str=None):
        self.view = None
        Parameter.__init__(self, name, value, tooltip)

    def populate_subclass(self, parent):
        self.view = QtWidgets.QLabel()
        self.add_widget(self.view)

    def on_changed(self):
        if self.view is not None:
            if str(self.view.text()) != str(self._value):
                self.view.setText(self.value)


PTYPE_OPEN = ['r', 'read', 'o', 'open']
PTYPE_SAVE = ['w', 'write', 's', 'save']
PTYPE_DIR = ['d', 'dir', 'directory']

PTYPE_MAP = {
    'open': (PTYPE_OPEN, ":/joulescope/resources/play.png"),
    'save': (PTYPE_SAVE, ":/joulescope/resources/record.png"),
    'dir':  (PTYPE_DIR,  ":/joulescope/resources/pause.png"),
}


def ptype_lookup(ptype):
    if ptype is None:
        return 'open'
    ptype = str(ptype).lower()
    for key, (values, _) in PTYPE_MAP.items():
        if ptype in values:
            return key
    raise ValueError(ptype)


class Path(String):
    """A path.

    :param str name: The name for this item.
    :param str value: The starting value for this item.  None (default) is
        equivalent to ''.
    :param str ptype: The path type which is one of the values in
        :data:`PTYPE_OPEN`, :data:`PTYPE_SAVE` or :data:`PTYPE_DIR`.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=None, ptype=None, tooltip: str=''):
        self.ptype = ptype_lookup(ptype)
        String.__init__(self, name, value=value, tooltip=tooltip)
        self.path_button = None

    def populate_subclass(self, parent):
        String.populate_subclass(self, parent)
        self.path_button = QtWidgets.QPushButton(self.widget)
        self.path_button.clicked.connect(self._on_path_change)
        icon1 = QtGui.QIcon()
        icon_path = PTYPE_MAP[self.ptype][1]
        icon1.addPixmap(QtGui.QPixmap(icon_path), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.path_button.setIcon(icon1)
        self.path_button.setFlat(True)
        self.path_button.setObjectName("pathButton")
        self.path_button.setStyleSheet('QPushButton:flat {   border: none; }')
        self.path_button.setFocusPolicy(QtCore.Qt.TabFocus)
        self.add_widget(self.path_button)
        return self

    def _on_path_change(self, event):
        v = str(self.lineEdit.text())
        if self.ptype == 'open':
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self.widget, 'Select file to open', v)
        elif self.ptype == 'save':
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self.widget, 'Select file to save', v)
        else:  # self.ptype == 'dir':
            path = QtWidgets.QFileDialog.getExistingDirectory(self.widget, 'Select directory', v)
        if len(path):
            self.lineEdit.setText(path)
            self.value = path
        else:
            self.update(None)

    def validate(self, x):
        if x is None:
            return x
        x = str(x)
        if self.ptype == 'open':
            if not os.path.isfile(x):
                raise ValueError('File not found "%s"' % x)
        elif self.ptype == 'save':
            parent = os.path.dirname(os.path.abspath(x))
            if not os.path.isdir(parent):
                raise ValueError('Parent directory not found: %s' % parent)
        else:  # self.ptype == 'dir':
            if not os.path.isdir(x):
                raise ValueError('Directory not found: %s' % x)
        return x


class Directory(Path):
    """A directory.

    :param str name: The name for this item.
    :param str value: The starting value for this item.  None (default) is
        equivalent to ''.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=None, tooltip: str=None):
        Path.__init__(self, name, value, 'dir', tooltip)


class FileOpen(Path):
    """An existing file.

    :param str name: The name for this item.
    :param str value: The starting value for this item.  None (default) is
        equivalent to ''.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=None, tooltip: str=None):
        Path.__init__(self, name, value, 'open', tooltip)


class FileSave(Path):
    """A file.

    :param str name: The name for this item.
    :param str value: The starting value for this item.  None (default) is
        equivalent to ''.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=None, tooltip: str=None):
        Path.__init__(self, name, value, 'save', tooltip)


class QClickLabel(QtWidgets.QLabel):

    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        QtWidgets.QLabel.__init__(self, parent)

    def mousePressEvent(self, ev):
        self.clicked.emit()


class Color(Parameter):
    """An color selection item.

    :param str name: The name for this item.
    :param bool value: The starting value for this item.
    :param tooltip: The text for the tooltip.
    """
    def __init__(self, name: str, value=False, tooltip: str=''):
        self.label = None
        self._parent = None
        Parameter.__init__(self, name, value, tooltip)
        self.picture = None

    def populate_subclass(self, parent):
        self._parent = parent
        self.label = QClickLabel()
        self.label.clicked.connect(self.onClick)
        self.picture = QtGui.QPicture()
        self.draw()
        self.add_widget(self.label)

    def to_qt_color(self, x=None):
        if x is None:
            x = self._value
        if isinstance(x, QtGui.QColor):
            pass  # No action necessary
        elif isinstance(x, str):
            x = QtGui.QColor(x)
        else:
            x = QtGui.QColor(*x)
        return x

    def draw(self):
        painter = QtGui.QPainter()
        painter.begin(self.picture)
        color = self.to_qt_color()
        print('%s : %s' % (self._value, color.getRgb()))
        painter.fillRect(QtCore.QRect(0, 0, 60, 20), QtGui.QBrush(color))
        painter.end()
        self.label.setPicture(self.picture)

    def validate(self, x):
        if x is None:
            return None
        return self.to_qt_color(x).getRgb()[:3]

    def onClick(self):
        dialog = QtWidgets.QColorDialog(self.to_qt_color(), self._parent)
        if dialog.exec_():
            self.value = dialog.selectedColor()

    def on_changed(self):
        if self.label is not None:
            self.draw()


def demo():
    # logging.basicConfig(level=logging.INFO)
    import sys
    path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
    print(path)
    sys.path.insert(0, path)
    from joulescope_ui import joulescope_rc

    app = QtWidgets.QApplication([])
    window = QtWidgets.QMainWindow()
    widget = QtWidgets.QWidget(window)
    window.setCentralWidget(widget)
    window.setGeometry(QtWidgets.QStyle.alignedRect(QtCore.Qt.LeftToRight, QtCore.Qt.AlignCenter, window.size(),
                       QtWidgets.QApplication.desktop().availableGeometry()))
    status = RichTextView('Status', tooltip='Display the source parameter and value on any change.')
    status.populate(widget)

    removeV = Float('REMOVED', 10.0)

    enumV = Enum('enumV', 'goober', None)
    strV  = StringSelect('strV', 'two', None)

    params = [
        Bool('bool1', True,
             tooltip='<span><h3>A boolean checkbox value</h3>'
                     '<p>'
                     'This is a very long tooltip that will continue across '
                     'multiple lines.  Remember that adjacent python strings '
                     'are automatically joined by the lexer, and no trailing '
                     'backslash is needed inside parenthesis. '
                     'We need to ensure that QT correctly wraps this text '
                     'inside the tooltip. '
                     'Ensure that this text is very long so that it will '
                     'need more than a single QT line on the screen.'
                     '</p></span>'),
        Int('int1', 10),
        Int('int2', 123, (100, 200)),
        Int('int3', None, (100, 200)),
        Int('int4', 'hello'),
        Float('float1', 10.0),
        Float('float2', 123., (100, 200)),
        Float('float3', None, (100, 200)),
        removeV,
        Enum('enum1', 'world', ['hello', 'there', 'world']),
        Enum('enum2', None, ['hello', 'there', 'world']),
        Enum('enumE', None, None),
        enumV,
        String('str1', u'\u221A(-1) 2\u00B3 \u03A3 \u03C0... and it was delicious! --Anonymous'),
        StringSelect('str2', 'world', ['hello', 'there', 'world']),
        StringSelect('str3', u'\u24D7\u24D4\u24DB\u24DB\u24DE', ['hello', 'there', 'world']),
        StringSelect('strS', u'\u24D7\u24D4\u24DB\u24DB\u24DE', None),
        strV,
        Directory('dir1', os.path.expanduser('~')),
        FileOpen('open1', os.path.join(os.path.expanduser('~'), 'guiparams.txt')),
        FileSave('save1', os.path.join(os.path.expanduser('~'), 'guiparams.txt')),
        Color('color1', (0, 0, 255), 'A nice blue'),
        Color('color2', '#400080', 'A nice purple'),
    ]

    def callback(item):
        try:
            value = item.value
        except Exception as ex:
            value = str(ex)
        status.value = '%s %s' % (item.name, value)

    pV = {}
    for p in params:
        pV[p.name] = p
        p.callback = callback
        p.populate(widget)
    removeV.unpopulate(widget)

    assert(pV['enum1'].value == 'world')
    assert(pV['enum2'].value == 'hello')

    assert(enumV.value == 'goober')
    enumV.values = ['hello', 'there', 'world']
    assert(enumV.value == 'hello')
    enumV.values = ['one', 'two', 'three', 'four']
    assert(enumV.value == 'one')

    assert(strV.value == 'two')
    strV.values = ['hello', 'there', 'world']
    assert(strV.value == 'two')
    strV.values = ['one', 'two', 'three', 'four']
    assert(strV.value == 'two')

    window.show()
    app.exec_()
    return 0


if __name__ == '__main__':
    demo()
