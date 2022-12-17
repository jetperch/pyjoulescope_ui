# Copyright 2022 Jetperch LLC
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


from . import pubsub_singleton, register, N_, sanitize, get_topic_name, get_unique_id, get_instance
from .styles.manager import style_settings
from PySide6 import QtCore, QtWidgets
import PySide6QtAds as QtAds
import logging


_log = logging.getLogger(__name__)


class DockWidget(QtAds.CDockWidget):

    def __init__(self, widget: QtWidgets.QWidget):
        super().__init__('temp_title')  # replaced by widget name
        self.setWidget(widget)
        topic = get_topic_name(widget)
        self._subscribe_fns = [[f'{topic}/settings/name', self._on_setting_name]]
        for t, fn in self._subscribe_fns:
            pubsub_singleton.subscribe(t, fn, flags=['pub', 'retain'])
        #self.setFeature()

    def _on_setting_name(self, value):
        self.setWindowTitle(value)

    def closeRequested(self):
        widget = self.widget()
        _log.info('closeRequested on widget %s', get_unique_id(widget))
        pubsub_singleton.publish('registry/view/actions/!widget_close', get_topic_name(widget))


VIEW_SETTINGS = {
    'active': {
        'dtype': 'str',
        'brief': 'The unique_id for the active view instance.',
        'default': '',
    },
    'theme': {
        'dtype': 'str',
        'brief': N_('The active theme.'),
        'default': 'js1',
        'options': [['js1', N_('Joulescope standard theme')], ['system', N_('System OS-specific theme')]],
    },
    'color_scheme': {
        'dtype': 'str',
        'brief': N_('The color scheme name.'),
        'default': 'dark',
        'options': [['dark', N_('Dark background')], ['light', N_('Light background')]],
    },
    'ads_state': {
        'dtype': 'str',
        'brief': 'The Advanced Docking System state for restoring widget layout.',
        'default': '',
    }
}


class View:
    CAPABILITIES = ['view@']
    SETTINGS = {**VIEW_SETTINGS, **style_settings(N_('View'))}
    _ui = None
    _dock_manager = None
    _active_instance = None
    fixed_widgets = []  # actual widget objects

    def __init__(self):
        self.name = 'Unnamed view'
        self._theme = 'js1'
        self._color_scheme = 'dark'
        self._colors = None

    @property
    def is_active(self):
        return self == View._active_instance

    @staticmethod
    def on_cls_action_fixed_widget_add(value):
        unique_id = get_unique_id(value)
        View.fixed_widgets.append(unique_id)

    @staticmethod
    def on_cls_setting_active(value):
        """Change the active view."""
        view: View = View._active_instance
        if view is not None:
            _log.info('active view %s: teardown start', view.unique_id)
            topic = get_topic_name(view.unique_id)
            ads_state = View._dock_manager.saveState()
            ads_state = bytes(ads_state).decode('utf-8')
            pubsub_singleton.publish(f'{topic}/settings/ads_state', ads_state)
            children = pubsub_singleton.query(f'{topic}/children', default=None)
            for child in children:
                view.on_action_widget_close(child)
            _log.info('active view %s: teardown done', view.unique_id)
        View._active_instance = None

        if value in ['', None]:
            return

        topic = get_topic_name(value)
        view = get_instance(value, default=None)
        if view is None:
            # should never happen
            _log.warning('active view %s does not exist', value)
            return
        _log.info('active view %s: setup start', view.unique_id)
        children = pubsub_singleton.query(f'{topic}/children', default=None)
        for child in children:
            view.on_action_widget_open(child)
        View._active_instance = view
        ads_state = pubsub_singleton.query(f'{topic}/settings/ads_state', default='')
        if ads_state is not None and len(ads_state):
            View._dock_manager.restoreState(QtCore.QByteArray(ads_state.encode('utf-8')))
        _log.info('active view %s: setup done', view.unique_id)

    @property
    def theme(self):
        return self._theme

    @theme.setter
    def theme(self, value):
        self._theme = value
        if self.is_active:
            self._render()

    @property
    def color_scheme(self):
        return self._color_scheme

    @color_scheme.setter
    def color_scheme(self, value):
        self._color_scheme = value
        self._colors = None
        if self.is_active:
            self._render()

    @property
    def colors(self):
        return self.colors

    @colors.setter
    def colors(self, value):
        self._colors = value
        if self.is_active:
            self._render()

    def on_setting_stylesheet(self, value):
        if self.is_active:
            View._ui.setStyleSheet(value)

    def on_action_widget_open(self, value):
        """Create a widget, possibly reusing existing settings.

        :param value: The topic or unique_id for the widget class
            or previous opened instance.
        """
        topic = get_topic_name(value)
        cls = get_instance(topic, default=None)
        if cls is None:
            cls = pubsub_singleton.query(topic + '/instance_of', default=None)
            if cls is None:
                _log.warning('cannot open widget topic=%s', topic)
                return
            unique_id = get_unique_id(topic)
            cls = get_instance(cls)
        else:
            unique_id = None
        obj: QtWidgets.QWidget = cls()
        topic = pubsub_singleton.register(obj, unique_id=unique_id, parent=self)
        unique_id = get_unique_id(topic)
        obj.setObjectName(unique_id)
        obj.dock_widget = DockWidget(obj)
        obj.dock_widget.setObjectName(f'{unique_id}__dock')
        self._dock_manager.addDockWidget(QtAds.TopDockWidgetArea, obj.dock_widget)
        # todo restore children
        pubsub_singleton.publish('registry/StyleManager:0/actions/!render', unique_id)
        return ['registry/view/actions/!widget_close', topic]

    def on_action_widget_close(self, value):
        """Destroy an existing widget, preserving settings.

        :param value: The topic, unique_id or instance for the
            widget to destroy.
        """
        topic = get_topic_name(value)
        instance_topic = f'{topic}/instance'
        instance: QtWidgets.QWidget = pubsub_singleton.query(instance_topic, default=None)
        if instance is not None:
            dock_widget = instance.dock_widget
            dock_widget.close()
            self._dock_manager.removeDockWidget(dock_widget)
            instance.dock_widget = None
        pubsub_singleton.unregister(topic)
        instance.close()
        return ['registry/view/actions/!widget_open', topic]

    @staticmethod
    def on_cls_action_widget_open(value):
        return View._active_instance.on_action_widget_open(value)

    @staticmethod
    def on_cls_action_widget_close(value):
        return View._active_instance.on_action_widget_close(value)

    @staticmethod
    def on_cls_action_add(value):
        view = View()
        topic = pubsub_singleton.register(view, unique_id=value)
        if View._active_instance is None:
            pubsub_singleton.publish(f'{View.topic}/settings/active', get_unique_id(topic))
        return ['registry/view/actions/!remove', topic]

    @staticmethod
    def on_cls_action_remove(value):
        topic = get_topic_name(value)
        pubsub_singleton.unregister(topic)
        return ['registry/view/actions/!add', topic]

    @staticmethod
    def on_cls_action_ui_connect(value):
        """Connect the UI to the widget"""
        View._ui = value['ui']
        View._dock_manager = value['dock_manager']

    def _render(self):
        return  # todo?
        p = pubsub_singleton
        profile = p.query('common/profile/settings/active')
        view = self.unique_id
        path = p.query('common/paths/styles')
        filename = sanitize(f'{profile}__{view}')
        path = os.path.join(path, filename)
        print('RENDER')
        pass  # todo


register(View, 'view')
