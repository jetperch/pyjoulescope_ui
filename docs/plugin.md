
# Plugins

> Requires Joulescope UI 1.1.0 or newer 

The Joulescope UI includes support for plugins.  A plugin adds features
or functionalities to the Joulescope UI without modifying the UI code.
You can install plugins even when using the Joulescope UI distribution.

⚠ Plugins run with the same permissions as the Joulescope UI.
Active plugins have full access to run arbitrary code on this computer.
Make sure you trust a plugin before activating it.

## Installing a Plugin

A plugin consists of a directory.  You must copy the full directory
into the plugin directory.  The plugin directory depends on the
host operating system:

* **Windows**: %LOCALAPPDATA%\\joulescope\\plugins
* **MacOS**: ~/Library/Application Support/joulescope/plugins
* **Linux**: ~/.joulescope/plugins

In the Joulescope UI, select **Widgets** → **Plugins**.  Your new
plugin should be listed.  Click the active checkbox to activate the widget.
Whatever features or functionalities that the plugin provides should
then be available.  Click the active checkbox again to deactivate
the plugin.  While this deactivates most plugin features, you may need to
restart the UI to fully deactivate the plugin.


## Developing a Plugin

A plugin consists of a directory with at least three files:
containing at least:

* **\_\_init\_\_.py**: Python code that implements the plugin functionality.
  This file may perform relative imports to access other Python files.
* **index.json**: Describes the plugin to the Joulescope UI.
* **README.md**: A user-meaningful markdown file that describes the 
  plugin features and functionality.


### File \_\_init\_\_.py

The contents of the plugin may vary.  The plugin has full access to the
UI internals including the PubSub instance.

The Joulescope UI includes tools to explore internals.  Within the UI,
check **Widgets** → **Settings** → **UI** → **developer**.  You can then
add **Widgets** → **Publish Spy** and **Widgets** → **PubSub Explorer**.

Most plugins should start with:

```python
from joulescope_ui.plugins import *
```

Here is the `__init__.py` code for a very simple plugin that adds 
a new Widget to the UI:

```python
from joulescope_ui.plugins import *
from PySide6 import QtCore, QtGui, QtWidgets


@register
@styled_widget(N_('Plugin Example'))
class PluginExampleWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(QtWidgets.QLabel(N_('Hello World!')))

    def on_pubsub_register(self):
        pass

    def mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            settings_action_create(self, menu)
            context_menu_show(menu, event)
```

### File "index.json"

The index.json file defines the plugin.  As of 2024-04-05, it contains
a top level map with three keys:

* **id**: The unique plugin identifier which must be formatted like
  "joulescope_ui.plugins.*my_plugin_name*"
* **version**: The "*major.minor.patch*" version identifier for the plugin.
* **author**: The author string for this plugin.

Example:

```json
{
    "id": "joulescope_ui.plugins.plugin_example",
    "version": "1.0.0",
    "author": "Jetperch LLC"
}
```

### File "README.md"

This file contains user-meaningful markdown that may be displayed
to the user.  The markdown should describe the features and 
functionalities provided by the plugin.

Example:

```markdown
# Example Joulescope UI Plugin

This Joulescope UI plugin provides a trivial Widget example.
```


## Known issues

* Translations for plugins are not yet support
* While you can add a new implementation for any already defined 
  [capability](../joulescope_ui/capabilities.py), you cannot easily
  add new capabilities.
* Hard-coded functionalities, such as the Waveform widget, cannot
  be easily modified.  You can monkeypatch, but at that point you
  are likely better working with the Joulescope development team
  to incorporate your features directly.
