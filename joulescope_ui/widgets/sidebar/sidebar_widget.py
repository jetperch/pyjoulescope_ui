# Copyright 2019-2023 Jetperch LLC
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


from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import N_, register, tooltip_format, get_instance, CAPABILITIES
from joulescope_ui.styles import styled_widget, color_as_qcolor
from joulescope_ui.widgets.flyout import FlyoutWidget
from joulescope_ui.widget_tools import CallableSlotAdapter


_STATISTIC_STREAM_SOURCE_TOPIC = f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list'
_SIGNAL_STREAM_SOURCE_TOPIC = f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_STREAM_SOURCE}/list'

_DEVICE_TOOLTIP = tooltip_format(
    N_('Device control'),
    N_("""\
    Click to show the device control widget which displays
    the connected devices and their settings.  Use this
    widget to open and close devices and configure their
    operation.\
    """))

_MEMORY_TOOLTIP = tooltip_format(
    N_('Memory buffer settings'),
    N_("""\
    Streaming signal sample data is stored in your host
    computer's RAM.  Click this button to show the
    memory management widget which allows you to 
    configure the memory used by this Joulescope UI instance.\
    """))

_SETTINGS_TOOLTIP = tooltip_format(
    N_('Settings'),
    N_("""\
    Click to show the settings which allows you
    to change the global, default, and individual
    instance settings for devices and widgets.
    
    Default changes may not affect existing instances,
    and may only apply to future instances.\
    """))

_HELP_TOOLTIP = tooltip_format(
    N_('Get help'),
    N_("""\
    Click to display help options.\
    """))

_MISC_TOOLTIP = tooltip_format(
    N_('Additional settings and actions'),
    N_("""\
    Click to display additional settings and actions.\
    """))


@register
@styled_widget(N_('sidebar'))
class SideBar(QtWidgets.QWidget):

    # Note: does NOT implement widget CAPABILITY, since not instantiable by user or available as a dock widget.

    SETTINGS = {
        'flyout_width': {
            'dtype': 'int',
            'brief': N_('The flyout width in pixels.'),
            'default': 300,
        },
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('side_bar_icons')
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)
        self._style_cache = None
        self._selected_area = None
        self._selected_area_brush = QtGui.QBrush
        self._buttons = {}
        self._buttons_blink = {}
        self._flyout: FlyoutWidget = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(6)
        self._layout.setContentsMargins(3, 3, 3, 3)

    def _on_fuse_button_pressed(self):
        self.pubsub.publish('registry/app/actions/!fuse_clear_all', None)

    def on_pubsub_register(self, pubsub):
        self._flyout = FlyoutWidget(self.parent(), self)
        self.pubsub.register(self._flyout, 'flyout:0', parent='sidebar:0')
        self._add_blink_button('target_power', 'target_power')
        b = self._add_blink_button('fuse', 'fuse_engaged', clear_only=True, skip_connect=True)
        b.pressed.connect(self._on_fuse_button_pressed)
        self._add_blink_button('signal_play', 'signal_stream_enable')
        self._add_blink_button('signal_record', 'signal_stream_record')
        self._add_blink_button('statistics_play', 'statistics_stream_enable')
        self._add_blink_button('statistics_record', 'statistics_stream_record')
        self._add_button('device', _DEVICE_TOOLTIP, 'DeviceControlWidget', 'device_control_widget:flyout')
        self._add_button('memory', _MEMORY_TOOLTIP, 'MemoryWidget', 'memory_widget:flyout')
        self._add_button('settings', _SETTINGS_TOOLTIP, 'settings', 'settings:flyout', width=500)
        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)
        self._add_button('help', _HELP_TOOLTIP, 'HelpWidget', 'help_widget:flyout')
        self._add_button('misc', _MISC_TOOLTIP, 'HamburgerWidget', 'hamburger_widget:flyout')

        self.pubsub.subscribe('registry/ui/events/blink_slow', self._on_blink, ['pub', 'retain'])
        self.pubsub.subscribe(_STATISTIC_STREAM_SOURCE_TOPIC, self._on_statistics_stream_source_list, ['pub', 'retain'])
        self.pubsub.subscribe(_SIGNAL_STREAM_SOURCE_TOPIC, self._on_signal_stream_source_list, ['pub', 'retain'])

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.on_cmd_show(None)
            event.accept()

    def _on_settings_pressed(self, checked):
        self.pubsub.publish('registry/view/actions/!widget_open', {
            'value': 'registry/settings',
            'floating': True,
        })

    def _buttons_enable(self, value, names):
        x = bool(len(value))
        for name in names:
            b = self._buttons_blink[name]
            b.setEnabled(x)
            if not x:
                b.setProperty('disabling', True)

    def _on_statistics_stream_source_list(self, value):
        self._buttons_enable(value, ['signal_play', 'signal_record'])

    def _on_signal_stream_source_list(self, value):
        self._buttons_enable(value, ['statistics_play', 'statistics_record', 'target_power'])

    def _add_blink_button(self, name, app_setting, clear_only=False, skip_connect=False):
        topic = f'registry/app/settings/{app_setting}'
        meta = self.pubsub.metadata(topic)
        tooltip = tooltip_format(meta.brief, meta.detail)
        button = self._add_button(name, tooltip)
        button.setProperty('blink', False)
        button.setProperty('disabling', False)
        button.setCheckable(True)
        self._buttons_blink[name] = button

        def update_from_pubsub(value):
            value = bool(value)
            block_state = button.blockSignals(True)
            button.setChecked(value)
            button.setDisabled(clear_only and not value)
            button.blockSignals(block_state)

        self.pubsub.subscribe(topic, update_from_pubsub, ['pub', 'retain'])
        if not bool(skip_connect):
            adapter = CallableSlotAdapter(button, lambda checked: self.pubsub.publish(topic, bool(checked)))
            button.toggled.connect(adapter.slot)
        return button

    def _add_button(self, name, tooltip, clz=None, unique_id=None, width=None):
        button = QtWidgets.QPushButton(self)
        button.setObjectName(name)
        button.setFlat(True)
        button.setFixedSize(32, 32)
        button.setToolTip(tooltip)
        self._buttons[name] = {
            'name': name,
            'button': button,
            'class': clz,
            'unique_id': unique_id,
            'width': 300 if width is None else int(width),
        }
        if clz is not None:
            button.setProperty('selected', False)
            adapter = CallableSlotAdapter(button, lambda: self.on_cmd_show(name))
            button.clicked.connect(adapter.slot)
        self._layout.addWidget(button)
        return button

    def _on_blink(self, value):
        for b in self._buttons_blink.values():
            disabling = b.property('disabling')
            if disabling:
                b.setProperty('disabling', False)
            if b.isEnabled() or disabling:
                b.setProperty('blink', value and not disabling)
                b.style().unpolish(b)
                b.style().polish(b)

    def on_cmd_show(self, name):
        w = self._buttons.get(name, {}).get('widget')
        if name is None or (w is not None and w == self._flyout.widget()):
            self._flyout.flyout_widget_set(None)
            self._selected_area = None
        else:
            v = self._buttons[name]
            if v.get('widget') is None:
                clz = get_instance(v['class'])
                w = clz(parent=self._flyout)
                w.setContentsMargins(5, 5, 5, 5)
                self.pubsub.register(w, v['unique_id'], parent='flyout:0')
                v['widget'] = w
                self.pubsub.publish(f'registry/style/actions/!render', w)
            self._flyout.flyout_widget_set(v['widget'], v['width'])
            self._selected_area = v['button'].geometry()
        self.update()

    def paintEvent(self, event):
        s = self._style
        if s is None:
            return
        if self._selected_area is not None:
            r = self.geometry()
            x, w = r.x(), r.width()
            r = self._selected_area
            y, h = r.y() - 3, r.height() + 6
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.fillRect(x, y, w, h, s['selected_background_brush'])
            painter.fillRect(x + w - 1, y, 2, h, s['selected_side_brush'])

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        if self._flyout is not None:
            self._flyout.on_sidebar_geometry(self.geometry())

    @property
    def _style(self):
        if self._style_cache is not None:
            return self._style_cache
        if self.style_obj is None:
            self._style_cache = None
            return None
        v = self.style_obj['vars']
        self._style_cache = {
            'selected_background_brush': QtGui.QBrush(color_as_qcolor(v['sidebar.util_background'])),
            'selected_side_brush': QtGui.QBrush(color_as_qcolor(v['sidebar.util_foreground'])),
        }
