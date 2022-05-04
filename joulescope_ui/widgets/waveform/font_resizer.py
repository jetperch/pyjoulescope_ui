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

import weakref
from PySide6.QtGui import QFont


class FontResizer:
    """Resize a font to fit in all target objects.

    :param
    """

    def __init__(self):
        self.font = None
        self._objects = []  # weakrefs to SignalStatistics

    def on_font(self, topic, value):
        font = QFont()
        font.fromString(value)
        self.font = font
        self.resize()

    def add(self, obj):
        """Add a target object for automatic font size adjustment.

        :param obj: The object to add which must support the following methods:
            * setFont(QFont): Set the font.
            * height(): Get the actual widget height.
            * preferred_height(): Return the preferred height with the current font.
        """
        self._objects.append(weakref.ref(obj))
        self.resize()

    def remove(self, obj):
        for idx, k in enumerate(self._objects):
            if k() == obj:
                self._objects.pop(idx)
                return True
        return False

    def resize(self, *args, **kwargs):
        h_ratio = 1.0
        if self.font is None:
            return
        objects_ref = self._objects
        objects = []
        self._objects = []
        p = self.font.pointSizeF()
        for k in objects_ref:
            obj = k()
            if obj is None:
                continue
            self._objects.append(k)
            objects.append(obj)
            obj.setFont(self.font)
            h_obj = obj.height()
            h_txt = obj.preferred_height()
            h_ratio = min(h_obj / h_txt, h_ratio)
        point_size = p * h_ratio
        if point_size <= 1:
            point_size = 1
        font = QFont(self.font)
        font.setPointSizeF(point_size)
        for obj in objects:
            obj.setFont(font)
