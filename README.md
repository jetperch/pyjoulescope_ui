
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

Many Joulescope users will want to 
[download](https://www.joulescope.com/download) the application distribution.

However, you may also use this python package directly.  As of July 2019, 
this package is not available on pypi since it requires a forked version of 
pyqtgraph. Follow the Developer instructions below to run the Joulescope UI 
from the source GitHub repository.


## Developer

The Joulescope User Interface requires Python 3.6 or newer. 
Install [Python 3.6+](https://www.python.org/) on your system and then verify
your python version at the terminal or command line:

    > python3 -VV
    Python 3.7.5 (tags/v3.7.5:5c02a39a0b, Oct 15 2019, 00:11:34) [MSC v.1916 64 bit (AMD64)]
    
Ensure that you have Python 3.6 or newer and 64-bit.


### Configure virtualenv [optional]

Although not required, using 
[virtualenv](https://virtualenv.pypa.io/en/latest/)
avoids dependency conflicts, especially if you use your python installation for 
other programs.  Joulescope does require a forked version of pyqtgraph and the
latest versions of most package dependencies.  Using virtualenv ensures that
the Joulescope software has the right dependencies without changing the rest
of your system.


#### For Windows:

Install virtualenv and create a new virtual environment:

    pip3 install -U virtualenv
    virtualenv c:\venv\joulescope

Activate the virtual environment whenever you start a new terminal:

    c:\venv\joulescope\Scripts\activate


#### For POSIX including (Linux, Mac OS X with homebrew):

Install virtualenv and create a new virtual environment:

    pip3 install -U virtualenv
    virtualenv ~/venv/joulescope
    
Activate the virtual environment whenever you start a new terminal:
    
    source ~/venv/joulescope/bin/activate
    

### Clone & Run

Clone and configure the Joulescope UI from the terminal or command line:

    pip3 uninstall pyqtgraph
    cd {path/to/repos}
    git clone https://github.com/jetperch/pyjoulescope_ui.git
    cd pyjoulescope_ui
    pip3 install -U -r requirements.txt
    python3 setup.py qt

Replace {path/to/repos} with your desired path.

As of July 2019, this package depends upon a 
[forked version of pyqtgraph](https://github.com/jetperch/pyqtgraph) which
is automatically installed using requirements.txt.

You should now be able to run the Joulescope UI:

    cd {path/to/repos}/pyjoulescope_ui
    python3 -m joulescope_ui


If you see an error importing win32api on Windows, you should try running this
command from an Administrator command prompt:

   python {path_to_python}\scripts\pywin32_postinstall.py -install


### Simultaneously develop the Joulescope driver

If you also want to simultaneously develop the Joulescope UI and the 
Joulescope driver:

    pip3 uninstall joulescope
    cd {path/to/repos}
    git clone https://github.com/jetperch/pyjoulescope.git
    cd pyjoulescope
    pip3 install -U -r requirements.txt    
    python3 setup.py build_ext --inplace

You should then modify your python path. On Windows:

    set PYTHONPATH={C:\path\to\repos}\pyjoulescope;{C:\path\to\repos}\pyjoulescope_ui

and on POSIX (Linux, Mac OS X with homebrew):

    export PYTHONPATH={path/to/repos}/pyjoulescope:{path/to/repos}/pyjoulescope_ui


You should then be able to run the user interface from this directory:

    python3 -m joulescope_ui


## License

All pyjoulescope_ui code is released under the permissive Apache 2.0 license.
See the [License File](LICENSE.txt) for details.
