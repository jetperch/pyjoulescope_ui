
# Themes

The Joulescope UI relies upon stylesheets to implement themes that
have different display styles.  The Joulescope UI comes with the
following themes:

* default: The standard OS-dependant style.
* light: A theme based upon a light background.
* dark: A them based upon a dark background.

The light and dark themes are based upon 
https://github.com/Alexhuszagh/BreezeStyleSheets.  Thank you!


## Developer

Each theme is compiled into a Qt resource file which is then dynamically
loaded and unloaded.

See the following style references:

* [Qt Style Sheet Syntax](https://doc.qt.io/Qt-5/stylesheet-syntax.html)
* [Qt Style Sheets Reference](https://doc.qt.io/qt-5/stylesheet-reference.html)

See the following Qt Resource references:

* [Qt Resource System](https://doc.qt.io/qt-5/resources.html)
* [QResource](https://doc.qt.io/qt-5/qresource.html#registerResource)
* [Using .qrc files in python](https://doc.qt.io/qtforpython/tutorials/basictutorial/qrcfiles.html)
