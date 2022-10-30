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

from PySide6 import QtGui, QtCore, QtWidgets
from .signal_def import signal_def
from .signal import Signal
from .signal_viewbox import SignalViewBox
from .text_annotation_dialog import TextAnnotationDialog
from . import text_annotation
from .scrollbar import ScrollBar
from .xaxis import XAxis
from .settings_widget import SettingsWidget
from .font_resizer import FontResizer
from .ymarker_manager import YMarkerManager
from joulescope_ui.file_dialog import FileDialog
from joulescope.data_recorder import construct_record_filename
from joulescope_ui.preferences_def import FONT_SIZES
from pyjls import Writer, DataType, AnnotationType, SignalType, SourceDef, SignalDef, SummaryFSR
import pyqtgraph as pg
import pyqtgraph.exporters
from typing import Dict
import copy
import os
import logging


log = logging.getLogger(__name__)
SIGNAL_OFFSET_ROW = 2


class WaveformWidget(QtWidgets.QWidget):
    """Oscilloscope-style waveform view for multiple signals.

    :param parent: The parent :class:`QWidget`.
    """

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self._cmdp = cmdp
        self._x_limits = [0.0, 30.0]
        self._mouse_pos = None
        self._context_menu_event = None
        self._clipboard_image = None
        self._shortcuts = {}

        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.win = pg.GraphicsLayoutWidget(parent=self, show=True, title="Oscilloscope layout")

        self.win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.win.sceneObj.sigMouseClicked.connect(self._on_mouse_clicked_event)
        self.win.sceneObj.sigMouseMoved.connect(self._on_mouse_moved_event)
        self.layout.addWidget(self.win)

        self._signals_def = {}
        self._signals: Dict[str, Signal] = {}
        self.config = {
            'show_min_max': True,
            'grid_x': 128,
            'grid_y': 128,
            'trace_width': 1,
        }
        self._dataview_data_pending = 0
        self._ymarker_mgr = YMarkerManager(cmdp, self._signals)

        self._settings_widget = SettingsWidget(self._cmdp)
        self.win.addItem(self._settings_widget, row=0, col=0)

        self._scrollbar = ScrollBar(parent=None, cmdp=cmdp)
        self._scrollbar.regionChange.connect(self.on_scrollbarRegionChange)
        self.win.addItem(self._scrollbar, row=0, col=1)

        self._x_axis = XAxis(self._cmdp)
        self.win.addItem(self._x_axis, row=1, col=1)
        self._x_axis.add_to_scene()
        self._x_axis.setGrid(128)
        self._x_axis.sigMarkerMoving.connect(self._on_marker_moving)

        self.win.ci.layout.setRowStretchFactor(0, 1)
        self.win.ci.layout.setRowStretchFactor(1, 1)

        self.win.ci.layout.setColumnStretchFactor(0, 1)
        self.win.ci.layout.setColumnStretchFactor(1, 1000)
        self.win.ci.layout.setColumnAlignment(0, QtCore.Qt.AlignRight)
        self.win.ci.layout.setColumnAlignment(1, QtCore.Qt.AlignLeft)
        self.win.ci.layout.setColumnAlignment(2, QtCore.Qt.AlignLeft)
        self.win.ci.layout.setColumnStretchFactor(2, -1)
        self.signal_configure()
        self.set_xlimits(0.0, 30.0)
        self.set_xview(25.0, 30.0)
        self._statistics_font_resizer = FontResizer()
        cmdp.subscribe('Widgets/Waveform/Statistics/font', self._statistics_font_resizer.on_font, update_now=True)
        self._marker_font_resizer = FontResizer()
        cmdp.subscribe('Widgets/Waveform/Statistics/font', self._marker_font_resizer.on_font, update_now=True)

        c = self._cmdp
        c.register('!Widgets/Waveform/Signals/add', self._cmd_waveform_signals_add,
                   brief='Add a signal to the waveform.',
                   detail='value is list of signal name string and position. -1 inserts at end')
        c.register('!Widgets/Waveform/Signals/remove', self._cmd_waveform_signals_remove,
                   brief='Remove a signal from the waveform by name.',
                   detail='value is signal name string.')

        c.register('!Widgets/Waveform/annotation/add', self._cmd_waveform_signals_annotation_add,
                   brief='Add an annotation to a signal.',
                   detail='value is [signal_name, instance_id, x, y, group_id, text]. '
                   + 'If instance_id is None, a new id will be automatically created.')
        c.register('!Widgets/Waveform/annotation/remove', self._cmd_waveform_signals_annotation_remove,
                   brief='Remove annotations.',
                   detail='value is [instance_id, ...].')
        c.register('!Widgets/Waveform/annotation/signal_hide', self._cmd_waveform_signals_annotation_hide,
                   brief='Hide or show the text of all annotations.',
                   detail='value is [signal_name, show].')
        c.register('!Widgets/Waveform/annotation/clear', self._cmd_waveform_signals_annotation_clear,
                   brief='Remove all annotations from signals.',
                   detail='value is [signal_name, ...].')
        c.register('!Widgets/Waveform/annotation/update', self._cmd_waveform_signals_annotation_update,
                   brief='Change the annotation properties.',
                   detail='value is [instance_id, {dict}].  The dict may contain any of the init keys.')
        c.register('!Widgets/Waveform/annotation/dialog', self._cmd_waveform_signals_annotation_dialog,
                   brief='Request a text update for an annotation.',
                   detail='value is instance_id.')

        c.register('!Widgets/Waveform/annotation/save', self._cmd_waveform_annotation_save,
                   brief='Save annotations to a file.',
                   detail='value is None to save for currently open JLS, or [filename, x_start, x_end].')

        c.subscribe('DataView/#data', self._on_data, update_now=True)
        c.subscribe('Device/#state/source', self._on_device_state_source, update_now=True)
        c.subscribe('Device/#state/play', self._on_device_state_play, update_now=True)
        c.subscribe('Device/#state/name', self._on_device_state_name, update_now=True)
        c.subscribe('Widgets/Waveform/Markers/_state/instances/', self._on_marker_instance_change,
                    update_now=True)
        c.subscribe('Widgets/Waveform/#requests/refresh_markers', self._on_refresh_markers, update_now=True)
        c.subscribe('Widgets/Waveform/#statistics_over_range_resp', self._on_statics_over_range_resp,
                    update_now=True)
        c.subscribe('Device/#state/x_limits', self._on_device_state_limits, update_now=True)
        c.subscribe('Widgets/Waveform/Statistics/font-size', self._on_statistics_settings)
        c.subscribe('Widgets/Waveform/_signals', self._on_signals_active, update_now=True)

        cmdp.subscribe('Appearance/__index__', self._on_colors, update_now=True)

        shortcuts = [
            [QtCore.Qt.Key_Asterisk, self._on_x_axis_zoom_all],
            [QtCore.Qt.Key_Delete, self._on_annotation_clear_all],
            [QtCore.Qt.Key_Backspace, self._on_annotation_clear_all],
            [QtCore.Qt.Key_Left, self._on_left],
            [QtCore.Qt.Key_Right, self._on_right],
            [QtCore.Qt.Key_Up, self._on_zoom_in],
            [QtCore.Qt.Key_Down, self._on_zoom_out],
            [QtCore.Qt.Key_Plus, self._on_zoom_in],
            [QtCore.Qt.Key_Minus, self._on_zoom_out],
        ]
        self._shortcuts_activate(shortcuts)

    def _shortcuts_activate(self, shortcuts):
        for key, cbk in shortcuts:
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            shortcut.activated.connect(cbk)
            self._shortcuts[key] = [key, cbk, shortcut]

    def _on_colors(self, topic, value):
        colors = value['colors']
        self.win.setBackground(colors['waveform_background'])
        pyqtgraph.setConfigOption('background', colors['waveform_background'])
        pyqtgraph.setConfigOption('foreground', colors['waveform_font_color'])

    def _on_mouse_moved_event(self, pos):
        self._mouse_pos = pos

    def _on_mouse_clicked_event(self, ev):
        if ev.isAccepted():
            return
        if ev.button() & QtCore.Qt.RightButton:
            self._context_menu_event = ev
            self._context_menu(ev.screenPos().toPoint())

    def _context_menu_pos_view_x(self):
        p = self._context_menu_event.scenePos().toPoint()
        return self._x_axis.linkedView().mapSceneToView(p).x()

    def _context_menu_pos_view_y(self):
        p = self._context_menu_event.scenePos().toPoint()
        for signal_name, signal in self._signals.items():
            if signal.vb.geometry().contains(p):
                y = signal.vb.mapSceneToView(p).y()
                return signal_name, y
        return None, None

    def _on_annotation_x_single_marker(self):
        x = self._context_menu_pos_view_x()
        self._cmdp.invoke('!Widgets/Waveform/Markers/single_add', x)

    def _on_annotation_x_dual_markers(self):
        x = self._context_menu_pos_view_x()
        self._cmdp.invoke('!Widgets/Waveform/Markers/dual_add', [x])

    def _on_annotation_x_clear_markers(self):
        self._cmdp.invoke('!Widgets/Waveform/Markers/clear', None)

    def _on_annotation_y_single_marker(self):
        signal_name, y = self._context_menu_pos_view_y()
        if signal_name is not None:
            self._cmdp.invoke('!Widgets/Waveform/YMarkers/single_add', [signal_name, y])

    def _on_annotation_y_dual_markers(self):
        signal_name, y = self._context_menu_pos_view_y()
        if signal_name is not None:
            self._cmdp.invoke('!Widgets/Waveform/YMarkers/dual_add', [signal_name, y, None])

    def _on_annotation_y_clear_markers(self):
        signal_name, y = self._context_menu_pos_view_y()
        if signal_name is not None:
            self._cmdp.invoke('!Widgets/Waveform/YMarkers/clear', [signal_name])

    def _on_annotation_text_add(self):
        x = self._context_menu_pos_view_x()
        signal_name, y = self._context_menu_pos_view_y()
        if signal_name is not None:
            self._cmdp.invoke('!Widgets/Waveform/annotation/add', [signal_name, None, x, y, 0, None])

    def _on_annotation_text_hide(self, show=None):
        x = self._context_menu_pos_view_x()
        signal_name, y = self._context_menu_pos_view_y()
        if signal_name is not None:
            self._cmdp.invoke('!Widgets/Waveform/annotation/signal_hide', [signal_name, bool(show)])

    def _on_annotation_text_show(self):
        return self._on_annotation_text_hide(show=True)

    def _on_annotation_text_clear(self):
        signal_name, y = self._context_menu_pos_view_y()
        if signal_name is not None:
            self._cmdp.invoke('!Widgets/Waveform/annotation/clear', [signal_name])

    def _on_annotation_save(self):
        self._cmdp.invoke('!Widgets/Waveform/annotation/save', None)

    def _on_annotation_clear_all(self):
        signals = list(self._signals.keys())
        self._cmdp.invoke('!command_group/start', None)
        self._cmdp.invoke('!Widgets/Waveform/Markers/clear', None)
        self._cmdp.invoke('!Widgets/Waveform/YMarkers/clear', signals)
        self._cmdp.invoke('!Widgets/Waveform/annotation/clear', signals)
        self._cmdp.invoke('!command_group/end', None)

    def _context_menu(self, pos):
        log.debug('_context_menu')
        menu = QtWidgets.QMenu('Waveform menu', self)

        annotations = menu.addMenu('&Annotations')
        anno_x = annotations.addMenu('&Vertical')
        anno_y = annotations.addMenu('&Horizontal')
        anno_text = annotations.addMenu('&Text')

        single_xmarker = anno_x.addAction('&Single marker')
        single_xmarker.triggered.connect(self._on_annotation_x_single_marker)
        dual_xmarkers = anno_x.addAction('&Dual markers')
        dual_xmarkers.triggered.connect(self._on_annotation_x_dual_markers)
        clear_xmarkers = anno_x.addAction('&Clear all')
        clear_xmarkers.triggered.connect(self._on_annotation_x_clear_markers)

        single_ymarker = anno_y.addAction('&Single marker')
        single_ymarker.triggered.connect(self._on_annotation_y_single_marker)
        dual_ymarkers = anno_y.addAction('&Dual markers')
        dual_ymarkers.triggered.connect(self._on_annotation_y_dual_markers)
        clear_xmarkers = anno_y.addAction('&Clear all')
        clear_xmarkers.triggered.connect(self._on_annotation_y_clear_markers)

        annotation_text = anno_text.addAction('&Add text')
        annotation_text.triggered.connect(self._on_annotation_text_add)
        anno_text_hide = anno_text.addAction('&Hide all')
        anno_text_hide.triggered.connect(self._on_annotation_text_hide)
        anno_text_show = anno_text.addAction('&Show all')
        anno_text_show.triggered.connect(self._on_annotation_text_show)
        annotation_clear = anno_text.addAction('&Clear all')
        annotation_clear.triggered.connect(self._on_annotation_text_clear)

        if self._cmdp['Device/#state/source'] == 'File':
            save_all = annotations.addAction('&Save all')
            save_all.triggered.connect(self._on_annotation_save)

        clear_all = annotations.addAction('&Clear all')
        clear_all.triggered.connect(self._on_annotation_clear_all)

        save_image = menu.addAction('Save image')
        save_image.triggered.connect(self.on_save_image)
        copy_image = menu.addAction('Copy image to clipboard')
        copy_image.triggered.connect(self.on_copy_image_to_clipboard)
        export_data = menu.addAction('Export visible data')
        export_data.triggered.connect(self.on_export_visible_data)
        export_data = menu.addAction('Export all data')
        export_data.triggered.connect(self.on_export_all_data)
        menu.exec_(pos)

    def on_export_visible_data(self):
        p1, p2 = self._scrollbar.get_xview()
        value = {
            'name': 'Export data',
            'x_start': min(p1, p2),
            'x_stop': max(p1, p2)
        }
        self._cmdp.invoke('!RangeTool/run', value)

    def on_export_all_data(self):
        p1, p2 = self._scrollbar.get_xlimits()
        value = {
            'name': 'Export data',
            'x_start': min(p1, p2),
            'x_stop': max(p1, p2)
        }
        self._cmdp.invoke('!RangeTool/run', value)

    def _export_as_image(self):
        r = self.window().windowHandle().screen().devicePixelRatio()
        w = self.win.sceneObj.getViewWidget()
        k = w.viewportTransform().inverted()[0].mapRect(w.rect())
        exporter = pg.exporters.ImageExporter(self.win.sceneObj)
        exporter.parameters()['width'] = k.width() * r
        return exporter.export(toBytes=True)

    def on_save_image(self):
        filter_str = 'png (*.png)'
        filename = construct_record_filename()
        filename = os.path.splitext(filename)[0] + '.png'
        path = self._cmdp['General/data_path']
        filename = os.path.join(path, filename)
        dialog = FileDialog(self, 'Save Joulescope Data', filename, 'any')
        dialog.setNameFilter(filter_str)
        filename = dialog.exec_()
        if not bool(filename):
            return
        png = self._export_as_image()
        png.save(filename)

    def on_copy_image_to_clipboard(self):
        self._clipboard_image = self._export_as_image()
        QtWidgets.QApplication.clipboard().setImage(self._clipboard_image)

    def _mouse_as_x(self):
        x = None
        if self._mouse_pos:
            x = self._x_axis.linkedView().mapSceneToView(self._mouse_pos).x()
        return x

    def keyPressEvent(self, ev):
        key = ev.key()
        if key == QtCore.Qt.Key_S:
            self._cmdp.invoke('!Widgets/Waveform/Markers/single_add', self._mouse_as_x())
        elif key == QtCore.Qt.Key_D:
            x = self._mouse_as_x()
            x_min, x_max = self._x_axis.range
            w2 = (x_max - x_min) / 10
            self._cmdp.invoke('!Widgets/Waveform/Markers/dual_add', [x - w2, x + w2])
        elif key == QtCore.Qt.Key_Delete or key == QtCore.Qt.Key_Backspace:
            self._on_annotation_clear_all()
        elif QtCore.Qt.Key_1 <= key <= QtCore.Qt.Key_8:
            self._markers_show(key - QtCore.Qt.Key_1 + 1)

    def _markers_show(self, idx):
        """Show the markers

        :param idx: The marker index, starting from 1.
        """
        n = chr(ord('1') + idx - 1)
        names = [n, f'{n}a', f'{n}b']
        m = [self._x_axis.marker_get(name) for name in names]
        m = [k for k in m if k is not None]
        if len(m) == 1:
            self._scrollbar.zoom_to_point(m[0].get_pos())
        elif len(m) == 2:
            self._scrollbar.zoom_to_range(m[0].get_pos(), m[1].get_pos())

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_all(self):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/zoom_all', None)

    def _on_left(self):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/pan', -1)

    def _on_right(self):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/pan', 1)

    def _on_zoom_in(self):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/zoom', 1)

    def _on_zoom_out(self):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/zoom', -1)

    def _on_statistics_settings(self, topic, value):
        self.win.ci.layout.invalidate()

    def _cmd_waveform_signals_add(self, topic, value):
        if value in self._signals:
            return None
        signals = list(self._signals.keys()) + [value]
        self._cmdp['Widgets/Waveform/_signals'] = signals
        return '!Widgets/Waveform/Signals/remove', value

    def _cmd_waveform_signals_remove(self, topic, value):
        if value not in self._signals:
            return None
        signals = list(self._signals.keys())
        signals.remove(value)
        self._cmdp['Widgets/Waveform/_signals'] = signals
        return '!Widgets/Waveform/Signals/add', value

    def _signal_get(self, signal_name):
        if signal_name not in self._signals:
            log.warning(f'Signal {signal_name} not found')
            return None
        return self._signals[signal_name]

    def _cmd_waveform_signals_annotation_add(self, topic, value):
        if value is None or not len(value):
            return
        if isinstance(value[0], str):
            value = [value]
        redo_info = []
        undo_info = []
        for signal_name, instance_id, x, y, group_id, text in value:
            signal = self._signal_get(signal_name)
            if signal is not None:
                undo_this, redo_this = signal.annotation_add(instance_id, x, y, group_id, text)
                redo_info.append(redo_this)
                undo_info.append(undo_this)
        return (('!Widgets/Waveform/annotation/add', redo_info),
                [('!Widgets/Waveform/annotation/remove', undo_info)])

    def _cmd_waveform_signals_annotation_remove(self, topic, value):
        if value is None or not len(value):
            return
        if isinstance(value[0], str):
            value = [value]
        undo_info = []
        for instance_id in value:
            annotation = text_annotation.find(instance_id)
            signal = self._signal_get(annotation.signal_name)
            if signal is None:
                text_annotation.remove(annotation.id)
            else:
                undo_this = signal.annotation_remove(instance_id)
                undo_info.append(undo_this)
        return '!Widgets/Waveform/annotation/add', undo_info

    def _cmd_waveform_signals_annotation_hide(self, topic, value):
        signal_name = value[0]
        show = bool(value[1])
        signal = self._signal_get(signal_name)
        if signal is not None:
            signal.annotation_show(show)
            return '!Widgets/Waveform/annotation/signal_hide', [signal_name, not show]

    def _cmd_waveform_signals_annotation_clear(self, topic, value):
        undo_info = []
        for signal_name in value:
            signal = self._signal_get(signal_name)
            if signal is not None:
                undo_this = signal.annotation_clear()
                undo_info.extend(undo_this)
        return '!Widgets/Waveform/annotation/add', undo_info

    def _cmd_waveform_signals_annotation_update(self, topic, value):
        instance_id, state = value
        annotation = text_annotation.find(instance_id)
        undo_info = annotation.update(state)
        return '!Widgets/Waveform/annotation/update', undo_info

    def _cmd_waveform_signals_annotation_dialog(self, topic, value):
        annotation = text_annotation.find(value)
        dialog = TextAnnotationDialog(self, self._cmdp, annotation)
        undo = dialog.exec_()
        redo = '!Widgets/Waveform/annotation/update', [annotation.id, annotation.state]
        return redo, [undo]

    def _cmd_waveform_annotation_save(self, topic, value):
        if value is None:
            x_start, x_end = None, None
            fname = self._cmdp['Device/#state/filename']
            if not len(fname) or not fname.endswith('.jls'):
                self._log.warning('Can only save when JLS file source')
                return
            fname = os.path.abspath(fname)[:-4] + '.anno.jls'
        else:
            fname, x_start, x_end = value
        fs = 1000000
        signal_def = {
            # signal_id, source_id, sample_rate, units
            'current': [1, 1, fs, 'A'],
            'voltage': [2, 1, fs, 'V'],
            'power':   [3, 1, fs, 'W'],
        }

        with Writer(fname) as w:
            w.source_def(source_id=1, name='annotations', vendor='-', model='-',
                         version='-', serial_number='-')
            for name, [signal_id, source_id, sample_rate, units] in signal_def.items():
                w.signal_def(signal_id=signal_id, source_id=source_id, sample_rate=sample_rate, name=name, units=units)

            # Horizontal markers first, since x-axis position is 0
            for sname, s in self._signals.items():
                signal_id = signal_def[sname][0]
                for name, m in s.y_axis.markers.items():
                    w.annotation(signal_id, 0, m.y, AnnotationType.HMARKER, 0, name)

            for name, m in self._x_axis.markers.items():
                x = m.get_pos()
                if (x_start is not None and x <= x_start) or (x_end is not None and x >= x_end):
                    continue
                if x_start is not None:
                    x -= x_start  # only for FSR signals, but ok since no VSR yet
                x *= fs
                w.annotation(1, x, None, AnnotationType.VMARKER, 0, name)

            for sname, s in self._signals.items():
                signal_id, _, sample_rate, _ = signal_def[sname]
                for a in s.annotations:
                    x = a.x_pos
                    if (x_start is not None and x <= x_start) or (x_end is not None and x >= x_end):
                        continue
                    if x_start is not None:
                        x -= x_start  # only for FSR signals, but ok since no VSR yet
                    x *= fs
                    w.annotation(signal_id, x, a.y_pos, AnnotationType.TEXT, a.group_id, a.text)

    def _on_signals_active(self, topic, value):
        # must be safe to call repeatedly
        log.debug('_on_signals_active: %s', value)
        signals_previous = list(self._signals.keys())
        signals_next = value
        for signal in signals_previous:
            if signal not in signals_next:
                self.signal_remove(signal)
        for signal in signals_next:
            if signal not in signals_previous:
                self._on_signalAdd(signal)

    def _on_device_state_limits(self, topic, value):
        if value is not None:
            self.set_xlimits(*value)
            self.set_xview(*value)

    def _on_device_state_name(self, topic, value):
        if not value:
            # disconnected from data source
            self.data_clear()
            self._on_annotation_clear_all()

    def _on_device_state_play(self, topic, value):
        if value:
            self.set_display_mode('realtime')
        else:
            self.set_display_mode('buffer')

    def _on_device_state_source(self, topic, value):
        if value == 'USB':
            if self.set_display_mode('realtime'):
                self.request_x_change()
        else:
            self.set_display_mode('buffer')

    def set_display_mode(self, mode):
        """Configure the display mode.

        :param mode: The oscilloscope display mode which is one of:
            * 'realtime': Display realtime data, and do not allow x-axis time scrolling
              away from present time.
            * 'buffer': Display stored data, either from a file or a buffer,
              with a fixed x-axis range.

        Use :meth:`set_xview` and :meth:`set_xlimits` to configure the current
        view and the total allowed range.
        """
        return self._scrollbar.set_display_mode(mode)

    def set_sampling_frequency(self, freq):
        """Set the sampling frequency.

        :param freq: The sampling frequency in Hz.

        This value is used to request appropriate x-axis ranges.
        """
        self._scrollbar.set_sampling_frequency(freq)

    def set_xview(self, x_min, x_max):
        """Set the current view extents for the time x-axis.

        :param x_min: The minimum value to display on the current view in seconds.
        :param x_max: The maximum value to display on the current view in seconds.
        """
        self._scrollbar.set_xview(x_min, x_max)

    def set_xlimits(self, x_min, x_max):
        """Set the allowable view extents for the time x-axis.

        :param x_min: The minimum value in seconds.
        :param x_max: The maximum value in seconds.
        """
        self._x_limits = [x_min, x_max]
        self._scrollbar.set_xlimits(x_min, x_max)
        for signal in self._signals.values():
            signal.set_xlimits(x_min, x_max)

    def signal_configure(self, signals=None):
        """Configure the available signals.

        :param signals: The list of signal definitions.  Each definition is a dict:
            * name: The signal name [required].
            * units: The optional SI units for the signal.
            * y_limit: The list of [min, max].
            * y_log_min: The minimum log value.  None (default) disables logarithmic scale.
            * show: True to show.  Not shown by default.
        """
        if signals is None:
            signals = signal_def
        for signal in signals:
            signal = copy.deepcopy(signal)
            signal['display_name'] = signal.get('display_name', signal['name'])
            self._signals_def[signal['name']] = signal

    def _on_signalAdd(self, name):
        signal = self._signals_def[name]
        self.signal_add(signal)

    def signal_add(self, signal):
        if signal['name'] in self._signals:
            self.signal_remove(signal['name'])
        s = Signal(parent=self, cmdp=self._cmdp,
                   statistics_font_resizer=self._statistics_font_resizer,
                   marker_font_resizer=self._marker_font_resizer,
                   **signal)
        s.addToLayout(self.win, row=self.win.ci.layout.rowCount())
        s.markers = self._x_axis.markers
        s.vb.sigWheelZoomXEvent.connect(self._scrollbar.on_wheelZoomX)
        s.vb.sigPanXEvent.connect(self._scrollbar.on_panX)
        self._signals[signal['name']] = s
        self._vb_relink()  # Linking to last axis makes grid draw correctly
        s.y_axis.setGrid(self.config['grid_y'])
        return s

    def signal_remove(self, name):
        signal = self._signals.get(name)
        if signal is None:
            log.warning('signal_remove(%s) but not found', name)
            return
        self._ymarker_mgr.clear(name)
        signal = self._signals.pop(name, None)
        signal.vb.sigWheelZoomXEvent.disconnect()
        signal.vb.sigPanXEvent.disconnect()
        row = signal.removeFromLayout(self.win)
        for k in range(row + 1, self.win.ci.layout.rowCount()):
            for j in range(3):
                i = self.win.getItem(k, j)
                if i is not None:
                    self.win.removeItem(i)
                    self.win.addItem(i, row=k - 1, col=j)
        self._vb_relink()

    def _vb_relink(self):
        if len(self._signals) <= 0:
            self._x_axis.unlinkFromView()
        else:
            row = SIGNAL_OFFSET_ROW + len(self._signals) - 1
            vb = self.win.ci.layout.itemAt(row, 1)
            self._x_axis.linkToView(vb)
            for p in self._signals.values():
                if p.vb == vb:
                    p.vb.setXLink(None)
                else:
                    p.vb.setXLink(vb)
        self._settings_widget.on_signalsAvailable(list(self._signals_def.values()),
                                                  visible=list(self._signals.keys()))

    def values_column_hide(self):
        for idx in range(self.win.ci.layout.rowCount()):
            item = self.win.ci.layout.itemAt(idx, 2)
            if item is not None:
                item.hide()
                item.setMaximumWidth(0)

    def values_column_show(self):
        for idx in range(self.win.ci.layout.rowCount()):
            item = self.win.ci.layout.itemAt(idx, 2)
            if item is not None:
                item.show()
                item.setMaximumWidth(16777215)

    def _on_data(self, topic, data):
        if not self.isVisible():
            return
        if data is None or not bool(data):
            self.data_clear()
            return
        self._dataview_data_pending += 1
        x_limits = data['time']['limits']['value']
        if x_limits is not None and x_limits != self._x_limits:
            self.set_xlimits(*x_limits)
        self.set_display_mode(data['state']['source_type'])
        x = data['time']['x']['value']
        for name, value in data['signals'].items():
            s = self._signals.get(name)
            if s is None:
                continue
            s.update(x, value)
        self._markers_single_update_all()
        self._markers_dual_update_all()

    def _markers_single_update_all(self):
        markers = [(m.name, m.get_pos()) for m in self._x_axis.markers_single()]
        for s in self._signals.values():
            s.update_markers_single_all(markers)

    def _markers_single_update(self, marker_name):
        marker = self._x_axis.marker_get(marker_name)
        if marker.is_single:
            for s in self._signals.values():
                s.update_markers_single_one(marker.name, marker.get_pos())

    def _on_data_frame_done(self):
        self._dataview_data_pending = 0
        self._cmdp.publish('Widgets/Waveform/#requests/data_next', None)

    def _markers_dual_update_all(self):
        ranges = []
        markers = []
        for m1, m2 in self._x_axis.markers_dual():
            t1 = m1.get_pos()
            t2 = m2.get_pos()
            if t1 > t2:
                t1, t2 = t2, t1
            ranges.append((t1, t2, m2.name))
            markers.append((m2.name, m2.get_pos()))
        if len(ranges):
            request = {
                'ranges': ranges,
                'source_id': 'Waveform._markers_dual_update_all',
                'markers': markers,
                'reply_topic': 'Widgets/Waveform/#statistics_over_range_resp'
            }
            self._cmdp.publish('DataView/#service/range_statistics', request)
        else:
            for s in self._signals.values():
                s.update_markers_dual_all([])
            self._on_data_frame_done()

    def _on_statics_over_range_resp(self, topic, value):
        if value is not None:
            show_dt = self._cmdp['Widgets/Waveform/dual_markers_Δt']
            req = value['request']
            rsp = value['response']
            if rsp is None:
                rsp = [None] * len(req['markers'])
            for s in self._signals.values():
                y = []
                for (name, pos), stat in zip(req['markers'], rsp):
                    if stat is not None:
                        dt = stat['time']['delta']
                        stat = stat['signals'].get(s.name, {})
                        if show_dt:
                            stat['Δt'] = dt
                    y.append((name, pos, stat))
                s.update_markers_dual_all(y)
        self._on_data_frame_done()

    def _on_marker_instance_change(self, topic, value):
        marker_name = topic.split('/')[-2]
        marker = self._x_axis.marker_get(marker_name)
        if marker is None:
            return  # marker still being created
        elif marker.is_single:
            self._markers_single_update(marker_name)
        else:
            self._markers_dual_update_all()  # todo : just update one

    @QtCore.Slot(str, float)
    def _on_marker_moving(self, marker_name, marker_pos):
        for s in self._signals.values():
            s.marker_move(marker_name, marker_pos)

    def _on_refresh_markers(self, topic, value):
        # keep it simple for now, just refresh everything
        self._markers_single_update_all()
        self._markers_dual_update_all()

    def data_clear(self):
        for s in self._signals.values():
            s.data_clear()

    def x_state_get(self):
        """Get the x-axis state.

        :return: The dict of x-axis state including:
            * length: The current length in pixels (integer)
            * x_limits: The tuple of (x_min: float, x_max: float) view limits.
            * x_view: The tuple of (x_min: float, x_max: float) for the current view range.
        """
        length = self.win.ci.layout.itemAt(0, 1).geometry().width()
        length = int(length)
        return {
            'length': length,
            'x_limits': tuple(self._x_limits),
            'x_view': self._scrollbar.get_xview(),
        }

    @QtCore.Slot(float, float, float)
    def on_scrollbarRegionChange(self, x_min, x_max, x_count):
        row_count = self.win.ci.layout.rowCount()
        if x_min > x_max:
            x_min = x_max
        if (row_count > SIGNAL_OFFSET_ROW) and len(self._signals):
            row = SIGNAL_OFFSET_ROW + len(self._signals) - 1
            log.info('on_scrollbarRegionChange(%s, %s, %s)', x_min, x_max, x_count)
            vb = self.win.ci.layout.itemAt(row, 1)
            if vb is not None:
                vb.setXRange(x_min, x_max, padding=0)
        else:
            log.info('on_scrollbarRegionChange(%s, %s, %s) with no ViewBox', x_min, x_max, x_count)
        self._cmdp.publish('DataView/#service/x_change_request', [x_min, x_max, x_count])

    def request_x_change(self):
        self._scrollbar.request_x_change()


def widget_register(cmdp):
    cmdp.define('Widgets/Waveform/', 'Waveform display settings')
    cmdp.define(
        topic='Widgets/Waveform/show_min_max',
        brief='Display the minimum and maximum for ease of finding short events.',
        dtype='str',
        options={
            'off':   {'brief': 'Hide the min/max indicators'},
            'lines': {'brief': 'Display minimum and maximum lines'},
            'fill':  {'brief': 'Fill the region between min and max.'}},
        default='lines')
    cmdp.define(
        topic='Widgets/Waveform/grid_x',
        brief='Display the x-axis grid',
        dtype='bool',
        default=True)
    cmdp.define(
        topic='Widgets/Waveform/grid_y',
        brief='Display the y-axis grid',
        dtype='bool',
        default=True)
    cmdp.define(
        topic='Widgets/Waveform/trace_width',
        brief='The trace width in pixels',
        detail='Increasing trace width SIGNIFICANTLY degrades performance',
        dtype='str',
        options=['1', '2', '4', '6', '8'],
        default='1')
    cmdp.define(
        topic='Widgets/Waveform/scale',
        brief='The default y-axis scale for current and power signals.',
        dtype='str',
        options=['linear', 'logarithmic'],
        default='linear')

    cmdp.define(
        topic='Widgets/Waveform/Statistics/font',
        brief='The font for the statistics text on the right-hand side of the waveform display.',
        dtype='font',
        default='Lato,10,-1,5,87,0,0,0,0,0,Black')
    cmdp.define(
        topic='Widgets/Waveform/dual_markers_Δt',
        brief='Show the Δt statistics with dual markers.',
        dtype='bool',
        default=True)
    cmdp.define(
        topic='Widgets/Waveform/_signals',
        brief='The signal configurations.',
        dtype='obj',
        default=['current', 'voltage'])

    cmdp.define('Widgets/Waveform/#requests/refresh_markers', dtype=object)  # list of marker names
    cmdp.define('Widgets/Waveform/#requests/data_next', dtype='none')
    cmdp.define('Widgets/Waveform/#statistics_over_range_resp', dtype=object)

    return {
        'name': 'Waveform',
        'brief': 'Display waveforms of values over time.',
        'class': WaveformWidget,
        'location': QtCore.Qt.RightDockWidgetArea,
        'singleton': True,
        'sizePolicy': ['expanding', 'expanding'],
    }
