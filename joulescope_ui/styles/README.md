
# Styles

The Joulescope UI relies upon Qt stylesheets to alter the appearance
of the Joulescope UI.  The appearance style is the combination of
* **theme**: Defines the layout and images displayed for UI elements.
* **color_scheme**: Specifies the color for UI elements.
* **font_scheme**: Specifies the fonts for UI elements.
* **misc**: Specifies other optional arguments to the theme templates.

The **theme** determines the layout and images displayed for UI elements.
The Joulescope UI comes with the following **themes**:

* js1: The default Joulescope UI theme
* system: The platform-specific OS-dependent style. 

The **color scheme** determines the color of each UI element.  
The Joulescope UI comes with the following **color schemes**::

* dark: Dark background with lighter foreground elements.
* light: Light background with darker foreground elements.

The included styles are based upon 
https://github.com/Alexhuszagh/BreezeStyleSheets.  Thank you!


## Developer

The style manager actively renders the style using templates for both
impage resources and qss style sheets.  Each theme is responsible for
defining its own templates.  The colors from the color schemes are
then substituted into the templates to produce the final stylesheets
used by the application.

The base application style is organized as follows:

* joulescope_ui/styles
  * color_scheme_{name}.txt   [dark, light]
  * font_scheme_{name}.txt    [js1]
  * defines.txt               additional defines for the theme templates
  * {theme_name}              [js1, system]
    * index.json
    * style.qss
    * style.html (only needed at top-level)
    * ... optional files needed by base theme ...

Widget classes may extend the style.  Most widget classes will not
vary based upon the base theme and often omit the {theme_name} 
subdirectory.

* {widget_package}/styles
  * color_scheme_{name}.txt   [dark, light] - recommended
  * font_scheme_{name}.txt    [js1] - optional
  * style_defines.txt - optional   
  * index.json - required
  * style.qss - optional
  * style.qss - optional
  * ... optional files needed by widget theme ...

The style manager searches for widget styles in the following order:
* {widget_package}/styles/index.json
* {widget_package}/styles/{theme_name}/index.json

Each profile globally defines the theme, color_scheme, and font_scheme.
The style is unique per profile.  However, each widget class and
widget instance can override the **color scheme**.

The joulescope_ui.styles.manager.styled_widget decorator monkeypatches 
every widget class.  See the documentation for details.

If a widget implements an on_style_change method, then the style manager
will call it each time the style changes.

See the following style references:

* [Qt Style Sheet Syntax](https://doc.qt.io/qt-6/stylesheet-syntax.html)
* [Qt Style Sheets Reference](https://doc.qt.io/qt-6/stylesheet-reference.html)
* [SVG Tiny 1.2](https://www.w3.org/TR/SVGTiny12/).  
  Qt only [supports](https://doc.qt.io/qt-6/svgrendering.html) the 
  [static features](https://www.w3.org/Graphics/SVG/feature/1.2/#SVG-static)
  without ECMA scripts and DOM (CSS) manipulation.
