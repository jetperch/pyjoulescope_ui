# Copyright 2020 Jetperch LLC
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

import pyqtgraph as pg

# Address issue https://github.com/pyqtgraph/pyqtgraph/issues/732 in 0.11.0
# 2020 Nov 11


class AxisItemPatch(pg.AxisItem):

    def __init__(self, *args, **kwargs):
        pg.AxisItem.__init__(self, *args, **kwargs)

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        try:
            p.setRenderHint(p.Antialiasing, False)
        except AttributeError:
            pass
        try:
            p.setRenderHint(p.TextAntialiasing, True)
        except AttributeError:
            pass

        ## draw long line along axis
        pen, p1, p2 = axisSpec
        p.setPen(pen)
        p.drawLine(p1, p2)
        p.translate(0.5 ,0)  ## resolves some damn pixel ambiguity

        ## draw ticks
        for pen, p1, p2 in tickSpecs:
            p.setPen(pen)
            p.drawLine(p1, p2)

        # Draw all text
        if self.style['tickFont'] is not None:
            p.setFont(self.style['tickFont'])
        p.setPen(self.textPen())

        bounding = self.boundingRect()
        for rect, flags, text in textSpecs:
            # PATCH: only draw text that completely fits
            if bounding.contains(rect):
                p.drawText(rect, int(flags), text)
