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

from PySide6 import QtCore
import tracemalloc

# https://www.fugue.co/blog/diagnosing-and-fixing-memory-leaks-in-python.html


class MemLeakDebugger(QtCore.QObject):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(2000)
        self._snapshot = None
        tracemalloc.start(10)

    def _compare_all(self, snapshot):
        print('SNAPSHOT COMPARE:')
        stats = snapshot.compare_to(self._snapshot, 'filename')
        for stat in stats[:10]:
            print("{} new KiB {} total KiB {} new {} total memory blocks: ".format(stat.size_diff / 1024,
                                                                                   stat.size / 1024,
                                                                                   stat.count_diff, stat.count))
            for line in stat.traceback.format():
                print(line)

    def _compare_module(self, snapshot, name):
        filters = [tracemalloc.Filter(inclusive=True, filename_pattern=f'*{name}*')]
        filtered_stats = snapshot.filter_traces(filters).compare_to(self._snapshot.filter_traces(filters), 'traceback')
        for stat in filtered_stats[:10]:
            print(f'{stat.size_diff/1024} {stat.size / 1024} {stat.count_diff} {stat.count}')
            for line in stat.traceback.format():
                print(line)
    def _on_timer(self):
        snapshot = tracemalloc.take_snapshot()
        if self._snapshot is not None:
            self._compare_all(snapshot)
            #self._compare_module(snapshot, 'pubsub')
        else:
            self._timer.start(10000)
        self._snapshot = snapshot
