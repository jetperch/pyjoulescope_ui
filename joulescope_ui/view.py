# Copyright 2022-2024 Jetperch LLC
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


from . import pubsub_singleton, register, N_, sanitize, \
    get_topic_name, get_unique_id, get_instance
from joulescope_ui.pubsub import pubsub_attr
from .styles.manager import style_settings
from PySide6 import QtCore, QtWidgets
import PySide6QtAds as QtAds
import logging
import weakref


_log = logging.getLogger(__name__)


class DockWidget(QtAds.CDockWidget):

    def __init__(self, widget: QtWidgets.QWidget, parent=None):
        unique_id = get_unique_id(widget)
        topic = get_topic_name(widget)
        name = widget.pubsub.query(f'{topic}/settings/name')
        super().__init__(name, parent)
        self.setObjectName(f'{unique_id}__dock')
        self.setWidget(widget)
        widget.pubsub.subscribe(f'{topic}/settings/name', self._on_setting_name, ['pub', 'retain'])
        self.setFeatures(
            QtAds.CDockWidget.DockWidgetClosable |
            QtAds.CDockWidget.DockWidgetMovable |
            QtAds.CDockWidget.DockWidgetFloatable |
            QtAds.CDockWidget.DockWidgetFocusable |
            QtAds.CDockWidget.CustomCloseHandling |
            QtAds.CDockWidget.DockWidgetForceCloseWithArea |
            0)
        self.closeRequested.connect(self._on_close_request)

    def _on_setting_name(self, value):
        self.setWindowTitle(value)

    @QtCore.Slot()
    def _on_close_request(self):
        widget = self.widget()
        _log.info('close %s', get_unique_id(widget))
        pubsub_singleton.publish('registry/view/actions/!widget_close', get_topic_name(widget))


VIEW_SETTINGS = {
    'active': {
        'dtype': 'str',
        'brief': 'The unique_id for the active view instance.',
        'default': None,
        'flags': ['hide'],
    },
    'theme': {
        'dtype': 'str',
        'brief': N_('The active theme.'),
        'default': 'js1',
        'options': [['js1', N_('Joulescope standard theme')], ['system', N_('System OS-specific theme')]],
        'flags': ['hide'],
    },
    'color_scheme': {
        'dtype': 'str',
        'brief': N_('The color scheme name.'),
        'default': 'dark',
        'options': [['dark', N_('Dark background')], ['light', N_('Light background')]],
    },
    'font_scheme': {
        'dtype': 'str',
        'brief': N_('The font scheme name.'),
        'default': 'js1',
        'options': [['js1', N_('Joulescope standard font theme')]],
    },
    'ads_state': {
        'dtype': 'str',
        'brief': 'The Advanced Docking System state for restoring widget layout.',
        'default': '',
        'flags': ['hide'],
    },
    'geometry': {
        'dtype': 'obj',
        'brief': 'The window size for restoring the view.',
        'default': None,
        'flags': ['hide'],
    }
}


class View:
    CAPABILITIES = ['view@']
    SETTINGS = {**VIEW_SETTINGS, **style_settings(N_('New View'))}
    _ui = None
    _dock_manager = None
    _active_instance = None

    def __init__(self):
        pass

    @property
    def is_active(self):
        return self == View._active_instance

    @staticmethod
    def on_cls_setting_active(value):
        """Change the active view."""
        style_enable_topic = 'registry/style/settings/enable'
        if style_enable_topic not in pubsub_singleton:
            return
        pubsub_singleton.publish(style_enable_topic, False)
        view: View = View._active_instance
        ui = pubsub_singleton.query('registry/ui/instance', default=None)
        if view is not None:
            _log.info('active view %s: teardown start', view.unique_id)
            topic = get_topic_name(view.unique_id)
            if ui is not None:
                pubsub_singleton.publish(f'{topic}/settings/geometry', ui.saveGeometry().data())
            ads_state = View._dock_manager.saveState()
            ads_state = bytes(ads_state).decode('utf-8')
            pubsub_singleton.publish(f'{topic}/settings/ads_state', ads_state)
            children = pubsub_singleton.query(f'{topic}/children', default=None)
            for child in children:
                view._widget_suspend(child)
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
        if ui is None:
            geometry = None
        else:
            geometry = pubsub_singleton.query(f'{topic}/settings/geometry', default=None)
        if geometry is not None:
            ui.restoreGeometry(geometry)

        children = pubsub_singleton.query(f'{topic}/children', default=None)
        if children is not None:
            for child in children:
                view.on_action_widget_open(child)
        View._active_instance = view
        ads_state = pubsub_singleton.query(f'{topic}/settings/ads_state', default='')
        if ads_state is not None and len(ads_state):
            View._dock_manager.restoreState(QtCore.QByteArray(ads_state.encode('utf-8')))
        if geometry is not None:
            # Ubuntu needs restoreGeometry after ADS restore state
            ui.restoreGeometry(geometry)
        pubsub_singleton.publish(style_enable_topic, True)
        view._render()
        _log.info('active view %s: setup done', view.unique_id)

    def on_setting_theme(self):
        if self.is_active:
            self._render()

    def on_setting_color_scheme(self):
        if self.is_active:
            self._render()

    def on_setting_colors(self):
        if self.is_active:
            self._render()

    def on_action_widget_open(self, value):
        """Create a widget, possibly reusing existing settings.

        :param value: One of several options:
            * The class unique_id or instance
            * The instance unique_id, instance or existing widget object
            * A dict containing:
              * value: topic, unique_id, or instance required
              * args: optional positional arguments for constructor
              * kwargs: optional keyword arguments for constructor
              * floating: optional window float control.
                True to make floating on top.
                When missing, do not float.
        """
        _log.debug('widget_open %s', value)
        obj: QtWidgets.QWidget = None
        floating = False
        unique_id = None
        args = []
        kwargs = {}
        if isinstance(value, dict):
            floating = bool(value.get('floating', False))
            spec = value['value']
            args = value.get('args', args)
            kwargs = value.get('kwargs', kwargs)
        else:
            spec = value
        if isinstance(spec, str):
            cls_unique_id = get_unique_id(spec)
            if ':' in spec:
                unique_id = spec
                cls_unique_id = unique_id.split(':')[0]
            spec = get_instance(cls_unique_id, default=None)
        if isinstance(spec, type):
            obj = spec(*args, **kwargs)
        else:
            obj = spec
        if obj is None:
            _log.warning('Could not open %s', spec)
            return
        pubsub_singleton.register(obj, unique_id=unique_id, parent=self)
        unique_id = obj.unique_id
        obj.setObjectName(unique_id)
        obj.destroyed.connect(self._on_destroyed)
        dock_widget = DockWidget(obj)
        dock_widget.destroyed.connect(self._on_destroyed)
        pubsub_attr(obj)['dock_widget'] = weakref.ref(dock_widget)
        tab_widget = dock_widget.tabWidget()
        tab_widget.setElideMode(QtCore.Qt.TextElideMode.ElideNone)
        self._dock_manager.addDockWidget(QtAds.TopDockWidgetArea, dock_widget)
        pubsub_singleton.publish('registry/style/actions/!render', unique_id)
        if floating:
            dock_widget.setFloating()
            c = dock_widget.floatingDockContainer()
            c.resize(800, 600)
        if getattr(obj, 'view_skip_undo', False):
            return None
        else:
            return [['registry/view/actions/!widget_close', unique_id],
                    ['registry/view/actions/!widget_open', unique_id]]

    @QtCore.Slot(QtCore.QObject)
    def _on_destroyed(self, obj):
        _log.debug('Destroyed %s', obj)

    def _widget_suspend(self, value, delete=None):
        """Suspend a widget.

        :param value: The topic, unique_id or instance for the
            widget to suspend.
        :param delete: True to also delete the pubsub entries.
            This prevents state restore.
        :return: The unique_id for the suspended widget or None

        Suspending a widget closes the Qt Widget with the associated
        DockWidget, freeing all resources.  However, it preserves the
        pubsub entries so that it can restore state.  Suspend is
        normally used when switching views.
        """
        unique_id = get_unique_id(value)
        _log.info('widget_suspend(%s, delete=%s)', unique_id, delete)
        topic = get_topic_name(unique_id)
        instance_topic = f'{topic}/instance'
        instance: QtWidgets.QWidget = pubsub_singleton.query(instance_topic, default=None)
        for child in pubsub_singleton.query(f'{topic}/children', default=[]):
            _log.info('widget_suspend_child %s', child)
            self._widget_suspend(child, delete)
        if instance is None:
            dock_widget = self._dock_manager.findChild(DockWidget, f'{unique_id}__dock')
        else:
            dock_widget = pubsub_attr(instance).get('dock_widget', None)
            if dock_widget is not None:
                dock_widget = dock_widget()  # weakref
        pubsub_singleton.unregister(topic, delete=delete)
        if instance is not None:
            instance.close()
            try:
                if dock_widget is None:
                    _log.info(f'widget_suspend {topic}: dock_widget is None')
                    instance.deleteLater()
                else:
                    self._dock_manager.removeDockWidget(dock_widget)
                    dock_widget.deleteLater()
            except Exception:
                _log.exception(f'widget_suspend {topic}: Delete or remove dock widget raised exception')
        return unique_id

    def on_action_widget_close(self, value):
        """Destroy an existing widget.

        :param value: The topic, unique_id or instance for the
            widget to destroy.

        Destroying a widget:
        * Closes the Qt widget and associated DockWidget.
        * Deletes the associated pubsub entries
        * Removes the widget from its view.
        """
        _log.debug('widget_close %s', value)
        skip_undo = getattr(get_instance(value), 'view_skip_undo', False)
        # todo save settings and dock geometry for undo
        unique_id = self._widget_suspend(value, delete=True)
        if skip_undo:
            return None
        else:
            return [['registry/view/actions/!widget_open', unique_id],
                    ['registry/view/actions/!widget_close', unique_id]]

    @staticmethod
    def on_cls_action_widget_open(value):
        return View._active_instance.on_action_widget_open(value)

    @staticmethod
    def on_cls_action_widget_close(value):
        if value == '*':
            topic = get_topic_name(View._active_instance)
            for widget in pubsub_singleton.query(f'{topic}/children'):
                View._active_instance.on_action_widget_close(widget)
            return None
        else:
            return View._active_instance.on_action_widget_close(value)

    @staticmethod
    def on_cls_action_add(value):
        _log.info('add %s', value)
        view = View()
        pubsub_singleton.register(view, unique_id=value)
        unique_id = view.unique_id
        if View._active_instance is None:
            pubsub_singleton.publish(f'{View.topic}/settings/active', unique_id)
        return [['registry/view/actions/!remove', unique_id],
                ['registry/view/actions/!add', unique_id]]

    @staticmethod
    def on_cls_action_remove(value):
        _log.info('remove %s', value)
        unique_id = get_unique_id(value)
        if unique_id == View._active_instance:
            raise ValueError('Cannot remove active view')
        pubsub_singleton.unregister(value, delete=True)

        return [['registry/view/actions/!add', unique_id],
                ['registry/view/actions/!remove', unique_id]]

    @staticmethod
    def on_cls_action_ui_connect(value):
        """Connect the UI to the widget"""
        View._ui = value['ui']
        View._dock_manager = value['dock_manager']

    @staticmethod
    def on_cls_action_ui_disconnect(value):
        """Disconnect the UI."""
        # hack to clean up active view
        view_topic = 'registry/view/settings/active'
        active_view = pubsub_singleton.query(view_topic)
        _log.info('disconnect ui: active_view=%s', active_view)
        pubsub_singleton.publish(view_topic, None)
        pubsub_singleton.process()
        pubsub_singleton._topic_by_name[view_topic].value = active_view

    def _render(self):
        pubsub_singleton.publish('registry/style/actions/!render', None)


register(View, 'view')
