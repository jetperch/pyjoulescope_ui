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

"""A Qt widget that displays an rescaled image to fit."""


from PyQt5 import QtGui, QtCore


class AspectRatioLabel(QtGui.QLabel):
    """A QLabel that displays a QPixmap image and rescales it to fit.

    Based upon the C++ code at:
    https://stackoverflow.com/a/22618496/888653
    """

    def __init__(self, *args, **kwargs):
        QtGui.QLabel.__init__(self, *args, **kwargs)
        self._pixmap = None
        self.setMinimumSize(1, 1)
        self.setScaledContents(False)

    def setPixmap(self, pixmap):
        if isinstance(pixmap, str):
            pixmap = QtGui.QPixmap(pixmap)
        self._pixmap = pixmap
        self.on_resize()

    def on_resize(self):
        if self._pixmap:
            QtGui.QLabel.setPixmap(self, self.scaled_pixmap())

    def resizeEvent(self, *args, **kwargs):
        self.on_resize()

    def height_given_width(self, width):
        if self._pixmap is None:
            return self.height()  # no change
        else:
            return self._pixmap.height() * (width / self._pixmap.width())

    def scaled_pixmap(self):
        pixel_ratio = self._pixmap.devicePixelRatioF()
        scaled = self._pixmap.scaled(self.size() * pixel_ratio,
                                     QtCore.Qt.KeepAspectRatio,
                                     QtCore.Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(pixel_ratio)
        return scaled

    def sizeHint(self):
        w = self.width()
        return QtCore.QSize(w, self.height_given_width(w))

