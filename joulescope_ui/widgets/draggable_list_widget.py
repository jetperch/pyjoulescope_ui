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


from PySide6 import QtWidgets, QtGui, QtCore


class DraggableListWidget(QtWidgets.QWidget):
    """A widget that holds an ordered list of items.

    :param parent: The parent widget.

    This class manages a list of items that the user can reorder.
    Call drag_start() to start a drag operation.  The drag operation
    is terminated automatically when needed without further intervention.
    Connect to the order_changed signal to get notified of updates.
    """

    order_changed = QtCore.Signal(object)
    """The signal emitted when the item order changes.
    
    The argument is the ordered list of items.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._items = []
        self.setAcceptDrops(True)
        self._drag = None

    @property
    def items(self):
        return self._items

    def item_add(self, item: QtWidgets.QWidget):
        """Add a new draggable item to this widget.

        :param item: The item to add.  This item will get the
            "drag" property, initially set to False, which can
            be used in QSS to style the widget.
        """
        self._layout.addWidget(item)
        self._items.append(item)
        self.order_changed.emit(self.items)

    def item_remove(self, item: QtWidgets.QWidget):
        self._layout.removeWidget(item)
        self._items.remove(item)
        self.order_changed.emit(self.items)

    def _update_item_drag(self, item, value):
        fn = getattr(item, 'setDrag', None)
        if callable(fn):
            fn(bool(value))

    def drag_start(self, item, pos=None):
        """Start a drag operation.

        :param item: The item to drag for reordering.
        :param pos: The optional mouse position in the widget's coordinates
            which is used to align the drag image.
        """
        mime_data = QtCore.QMimeData()
        mime_data.setText("DraggableListWidget")

        drag = QtGui.QDrag(item)
        drag.setMimeData(mime_data)

        pixmap = QtGui.QPixmap(item.size())
        item.render(pixmap)
        drag.setPixmap(pixmap)
        if pos is not None:
            drag.setHotSpot(pos)
        drag.targetChanged.connect(self._drag_target_changed)

        self._update_item_drag(item, True)
        self._drag = drag
        self._drag.exec(QtCore.Qt.MoveAction)

    def _drag_stop(self):
        if self._drag is not None:
            item = self._drag.source()
            self._update_item_drag(item, False)
            self._drag = None

    @QtCore.Slot(QtCore.QObject)
    def _drag_target_changed(self, new_target):
        if self._drag is not None and new_target != self:
            self._drag.cancel()
            self._drag_stop()

    def dragMoveEvent(self, event):
        if self._drag is None:
            return
        if event.mimeData().hasText() and event.mimeData().text() == "DraggableListWidget":
            container_position = self.mapFromGlobal(QtGui.QCursor.pos())
            layout = self._layout
            target_item = None
            for item in self._items:
                if container_position.y() <= (item.y() + item.height()):
                    target_item = item
                    break

            source_item = event.source()
            if source_item != target_item:
                target_index = layout.indexOf(target_item)
                layout.removeWidget(source_item)
                layout.insertWidget(target_index, source_item)
                self._items.remove(source_item)
                self._items.insert(target_index, source_item)
                self.order_changed.emit(self.items)

            event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text() == "DraggableListWidget":
            event.accept()

    def dropEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text() == "DraggableListWidget":
            self._drag_stop()
            event.accept()


###############################################################################
#                               Example                                       #
###############################################################################


class _ExampleWidget(QtWidgets.QWidget):
    """The class for a draggable item.

    :param parent: The parent, which is a DraggableListWidget.
    :param name: The name for this instance.

    There is nothing special about this class.  However, to
    start a drag reorder operation, it must call
    self.parentWidget().drag_start(self, pos)

    If the item has :meth:`setDrag`, then it will be called
    with True at the start of a drag operation and False
    at the end.
    """

    def __init__(self, parent, name):
        super().__init__(parent)
        self._layout = QtWidgets.QHBoxLayout(self)

        self._move_start = QtWidgets.QLabel('Click here to drag', self)
        self._name = QtWidgets.QLabel(name, self)
        self._action = QtWidgets.QPushButton(self)
        self._action.setText('Action')

        self._layout.addWidget(self._move_start)
        self._layout.addWidget(self._name)
        self._layout.addWidget(self._action)

    @property
    def name(self):
        return self._name.text()

    @QtCore.Slot(bool)
    def setDrag(self, value):
        print(f'drag {value} on {self.name}')

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._move_start.underMouse():
            # Start the drag operation
            pos = event.position().toPoint()
            self.parentWidget().drag_start(self, pos)


class _MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Draggable List Widget")
        self.draggable_list_widget = DraggableListWidget(self)
        for i in range(10):
            item = _ExampleWidget(self, f"Item {i}")
            self.draggable_list_widget.item_add(item)
        self.setCentralWidget(self.draggable_list_widget)
        self.draggable_list_widget.order_changed.connect(self._on_order_changed)

        self.setWindowTitle("Drag & Drop Items")
        self.resize(800, 600)
        self.show()

    @QtCore.Slot(object)
    def _on_order_changed(self, items):
        names = [w.name for w in items]
        print(', '.join(names))

            
if __name__ == "__main__":
    app = QtWidgets.QApplication()
    container = _MainWindow()
    app.exec()
