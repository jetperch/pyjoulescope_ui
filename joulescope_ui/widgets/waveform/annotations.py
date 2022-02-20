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


from pyjls import Reader, DataType, AnnotationType, SignalType, SourceDef, SignalDef, SummaryFSR
import logging
import os
from PySide2 import QtWidgets, QtGui, QtCore


def annotation_filenames(filename):
    fpaths = []
    filename = os.path.abspath(filename)
    path = os.path.dirname(filename)
    basename = os.path.basename(filename)
    fbase, fext = os.path.splitext(basename)
    for fname in os.listdir(path):
        if fname.startswith(fbase) and fname != basename and fname.endswith(fext):
            fpath = os.path.join(path, fname)
            fpaths.append(fpath)
    return fpaths


class AnnotationSignals(QtCore.QObject):
    progress = QtCore.Signal(float)  # progress from 0.0 to 1.0
    finished = QtCore.Signal()


class AnnotationLoader(QtCore.QRunnable):

    def __init__(self, parent, filename, cmdp):
        """Load annotations

        :param parent: The parent QObject.
        :param filename: The base JLS filename or list of JLS filenames.
        :param cmdp: The command processor instance.
        """
        QtCore.QRunnable.__init__(self, parent)
        self.signals = AnnotationSignals(parent)
        if isinstance(filename, str):
            self._filenames = annotation_filenames(filename)
        else:
            self._filenames = filename.copy()
        self._cmdp = cmdp
        if len(self._filenames):
            basename = os.path.basename(self._filenames[0])
            basename = basename.split('.')[0]
        else:
            basename = 'none'
        self._log = logging.getLogger(f'{__name__}.{basename}')
        self._stats = [0, 0, 0, 0, 0]

    def publish(self, reader: Reader):
        """Publish all annotations from the JLS file.

        :param reader: The JLS reader instance.
        """
        if self._cmdp is None:
            return
        self._cmdp.invoke('!command_group/start', None)
        for signal in reader.signals.values():
            dual_vmarkers = {}
            dual_hmarkers = {}

            def cbk(timestamp, y, annotation_type, group_id, data):
                if signal.signal_type == SignalType.FSR:
                    # convert to seconds
                    # todo make this respect UTC, when UTC is implemented
                    timestamp = timestamp / signal.sample_rate
                elif signal.signal_type == SignalType.VSR:
                    pass  # already in UTC seconds
                else:
                    raise RuntimeError(f'invalid signal type {signal.signal_type}')
                if annotation_type == AnnotationType.TEXT:
                    self._cmdp.invoke('!Widgets/Waveform/annotation/add',
                                      [signal.name, None, timestamp, y, group_id, data])
                    self._stats[0] += 1
                elif annotation_type == AnnotationType.VMARKER:
                    if data[-1] in 'ab':
                        name = data[:-1]
                        if name in dual_vmarkers:
                            t2 = dual_vmarkers.pop(name)
                            value = sorted([timestamp, t2])
                            self._stats[1] += 1
                            self._cmdp.invoke('!Widgets/Waveform/Markers/dual_add', value)
                        else:
                            dual_vmarkers[name] = timestamp
                    else:
                        self._stats[2] += 1
                        self._cmdp.invoke('!Widgets/Waveform/Markers/single_add', timestamp)
                elif annotation_type == AnnotationType.HMARKER:
                    if data[-1] in 'ab':
                        name = data[:-1]
                        if name in dual_hmarkers:
                            t2 = dual_hmarkers.pop(name)
                            value = [signal.name] + sorted([y, t2])
                            self._stats[3] += 1
                            self._cmdp.invoke('!Widgets/Waveform/YMarkers/dual_add', value)
                        else:
                            dual_hmarkers[name] = y
                    else:
                        self._stats[4] += 1
                        self._cmdp.invoke('!Widgets/Waveform/YMarkers/single_add', [signal.name, y])
                return 0

            reader.annotations(signal.signal_id, 0, cbk)
        self._cmdp.invoke('!command_group/end', None)

    def run(self):
        try:
            self.signals.progress.emit(0.0)
            self._log.info('annotation load start')
            for fname in self._filenames:
                with Reader(fname) as r:
                    self.publish(r)
            self._log.info(f'annotation load done with {self._stats}')
        finally:
            self.signals.progress.emit(1.0)
            self.signals.finished.emit()
