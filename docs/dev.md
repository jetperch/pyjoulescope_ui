

## Guiding Principles

* Easy things must be easy.
  New UI installations must start in Multimeter view and just work.
  Switching to Oscilloscope (Waveform) view should also just work.
* Hard things should be possible, but not necessarily in the UI.
  Forcing some features to Python scripting is acceptable.
  We prioritize UI ease of use over breadth.  Any potential feature
  implementation that compromises the ease of "easy things" MUST
  be redesigned.
* Single instrument support must be automatic and seamless, 
  even if the user swaps instruments.
* Multiple instrument support and controls should be hidden if possible when
  only have a single instrument.  If not hidden, they must not be 
  intrusive or needed.
* When multiple instruments are connected, automatically show multiple 
  instrument controls.


## Notes

* [PubSub](pubsub.md)
* [Qt Advanced Docking System](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System)
  * PySide6-QtAds python bindings:
    [GitHub](https://github.com/mborgerson/Qt-Advanced-Docking-System)
    | [pypi](https://pypi.org/project/PySide6-QtAds/) 
  * [Examples](https://github.com/mborgerson/Qt-Advanced-Docking-System/tree/pyside6/examples)
* [Display PDF in Qt](https://python-forum.io/thread-36741.html)
* Sidebar
  * [QStackedLayout](https://doc.qt.io/qt-6/qstackedlayout.html)
  * Widget Overlay
    * [StackOverflow] (https://stackoverflow.com/questions/19199863/draw-rectangular-overlay-on-qwidget-at-click)
    * TLDR; Don't add to layout, use setGeometry() and raise_().
* [pyinstaller](https://pyinstaller.org/en/stable/):
  [pypi](https://pypi.org/project/pyinstaller/)
  | [GitHub](https://github.com/pyinstaller/pyinstaller)
* [Nuitka](https://nuitka.net/)