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

from PySide2 import QtGui, QtCore, QtWidgets
import logging

log = logging.getLogger(__name__)


def comboBoxConfig(comboBox, values, default=None):
    """Configure (or reconfigure) a QT combo box.

    :param comboBox: The combo box to configure.
    :param values: The list of value strings for the combo box.
    :param default: The default value for the combo box which must also be
        in values.  If None, then attempt to keep the current value of the
        combo box if at all possible.  If not, then just select the first
        item.
    :return: The new text value for the combobox.
    """
    if default is not None and default not in values:
        log.warning('Ignoring default value "%s" since it is not in values: %s' % (default, values))
        default = None
    if default is None and comboBox.count():
        # attempt to keep the previous value
        currentValue = str(comboBox.currentText())
        if currentValue in values:
            default = currentValue

    block_state = comboBox.blockSignals(True)
    comboBox.clear()
    for value in values:
        comboBox.addItem(value)
        if value == default:
            comboBox.setCurrentIndex(comboBox.count() - 1)
    comboBox.blockSignals(block_state)
    return str(comboBox.currentText())


def comboBoxDecrement(box):
    idx = box.currentIndex()
    if idx > 0:
        box.setCurrentIndex(idx - 1)
        return True
    return False


def comboBoxIncrement(box):
    idx = box.currentIndex()
    idx += 1
    if idx < box.count():
        box.setCurrentIndex(idx)
        return True
    return False


def comboBoxSelectItemByText(combobox: QtWidgets.QComboBox, value):
    index = combobox.findText(value)
    if index >= 0:
        combobox.setCurrentIndex(index)


def confirmDiscard(parent):
    msgBox = QtGui.QMessageBox(parent)
    msgBox.setText('Existing data has not been saved.')
    msgBox.setInformativeText('Discard data?')
    msgBox.setStandardButtons(QtGui.QMessageBox.Discard | QtGui.QMessageBox.Cancel)
    msgBox.setDefaultButton(QtGui.QMessageBox.Cancel)
    rv = msgBox.exec_()
    if rv != QtGui.QMessageBox.Discard:
        return False
    return True


def confirmOverwrite(parent, targetName=None):
    targetName = 'file' if targetName is None else targetName
    msgBox = QtGui.QMessageBox(parent)
    msgBox.setText('%s already exists.' % targetName.title())
    msgBox.setInformativeText('Overwrite %s?' % targetName)
    msgBox.setStandardButtons(QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel)
    msgBox.setDefaultButton(QtGui.QMessageBox.Cancel)
    rv = msgBox.exec_()
    if rv != QtGui.QMessageBox.Ok:
        return False
    return True


def clear_layout(layout):
    """Clear and delete all widgets from a layout.

    :param layout: The QT layout.
    """
    # https://stackoverflow.com/questions/9374063/remove-widgets-and-layout-as-well
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                clear_layout(item.layout())


def rgba_to_css(rgba):
    r, g, b, a = rgba
    return 'rgba(%d,%d,%d,%f)' % (r, g, b, a / 255.0)


def font_to_css(font):
    # https://forum.qt.io/topic/45970/qfont-support-for-css-font-spec-encoding/2
    fields = []
    font = QtGui.QFont(font)

    # Determine font family
    family = font.family()
    # substitutes seem worthless in Qt - nothing ever returned
    family_subs_baseline = font.substitutes(family)
    if family not in family_subs_baseline:
        family_subs_baseline.insert(0, family)
    family_subs = []
    for family in family_subs_baseline:
        if ' ' in family and family[0] not in ['"', "'"]:
            family = f'"{family}"'
        family_subs.append(family)
    fields.append('font-family: ' + ','.join(family_subs))

    # Font weight and style
    if font.bold():
        fields.append('font-weight: bold')
    if font.style() == QtGui.QFont.StyleItalic:
        fields.append('font-style: italic')
    elif font.style() == QtGui.QFont.StyleOblique:
        fields.append('font-style: oblique')

    # font size
    size_in_points = font.pointSizeF()  # 0 if not defined
    size_in_pixels = font.pixelSize()  # 0 if not defined
    if size_in_points > 0:
        fields.append(f'font-size: {size_in_points}pt')
    elif size_in_pixels > 0:
        fields.append(f'font-size: {size_in_pixels}px')

    # decorations: underline & strikeout
    underline = font.underline()
    strike_out = font.strikeOut()
    if underline or strike_out:
        s = 'text-decoration:'
        if underline:
            s += ' underline'
        if strike_out:
            s += 'line-through'
        fields.append(s)

    return '; '.join(fields)
