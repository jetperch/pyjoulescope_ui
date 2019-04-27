
# Joulescope UI

Welcome to Joulescope™!  Joulescope is an affordable, precision DC energy 
analyzer that enables you to build better products.
Joulescope™ accurately and simultaneously measures the voltage and current 
supplied to your target device, and it then computes power and energy. 
For more information on Joulescope, see 
[www.joulescope.com](https://www.joulescope.com).

This repository contains the Joulescope graphical user interface (UI).
The UI runs on a host computer and communicates with the Joulescope device 
over USB.  The application source code is available at 
https://github.com/jetperch/pyjoulescope_ui.  

For the list of changes by release, see the [Changelog](CHANGELOG.md).

The Joulescope UI is under active development, and many features remain 
outstanding. See the [future features document](features_future.md) for details.


## Quick start

Most Joulescope users will want to 
[download](https://www.joulescope.com/download) the application.  The
packages are available at pypi, but this project uses a forked version of
pyqtgraph which you will need to install manually.


## Developer

Start by following getting the Joulescope package running using the instructions
located in the [joulescope README](https://github.com/jetperch/pyjoulescope).

Install python3 dependencies

    pip3 install -r requirements.txt

As of May 2019, this package depends upon a 
[forked version of pyqtgraph](https://github.com/jetperch/pyqtgraph) which
is automatically installed from the Joulescope website.
    
If you are just interested in developing the UI, you can install the joulescope
package as described in the 
[joulescope README](https://github.com/jetperch/pyjoulescope). 
However, if you want to develop both, you can modify your pythonpath.

On Windows:

    set PYTHONPATH=C:\path\to\pyjoulescope;C:\path\to\pyjoulescope_ui;

    
### Linux

Install QT5 tools

    sudo apt install qtcreator qt5-default qt5-doc qt5-doc-html qtbase5-doc-html qtbase5-examples

## License

All pyjoulescope_ui code is released under the permissive Apache 2.0 license.
See the [License File](LICENSE.txt) for details.
