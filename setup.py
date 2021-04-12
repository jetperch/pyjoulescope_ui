# Copyright 2018 Jetperch LLC
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

"""
Joulescope python setuptools module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
import setuptools
from setuptools.command.sdist import sdist
import distutils.cmd
import os
import sys
import subprocess
import shutil


JOULESCOPE_VERSION_MIN = '0.9.4'  # also update requirements.txt
MYPATH = os.path.abspath(os.path.dirname(__file__))
VERSION_PATH = os.path.join(MYPATH, 'joulescope_ui', 'version.py')


def qt_rcc_path():
    # As of PySide2 5.15.0, the pyside2-rcc executable ignores the --binary flag
    import PySide2
    path = os.path.dirname(PySide2.__file__)
    fname = [n for n in os.listdir(path) if n.startswith('rcc')]
    if len(fname) != 1:
        raise ValueError('Could not find rcc executable')
    return os.path.join(path, fname[0])


def convert_qt_ui():
    uic_path = shutil.which('pyside2-uic')
    rcc_path = qt_rcc_path()
    path = os.path.join(MYPATH, 'joulescope_ui')
    ignore_filename = os.path.join(path, '.gitignore')
    with open(ignore_filename, 'w', encoding='utf-8') as ignore:
        ignore.write('# Automatically generated.  DO NOT EDIT\n')
        for root, d_names, f_names in os.walk(path):
            for source in f_names:
                _, ext = os.path.splitext(source)
                if ext == '.ui':
                    source = os.path.join(root, source)
                    target = os.path.splitext(source)[0] + '.py'
                    print(f'Generate {os.path.relpath(target, MYPATH)}')
                    rc = subprocess.run([uic_path, source], stdout=subprocess.PIPE)
                    s = rc.stdout.replace(b'\r\n', b'\n').decode('utf-8')
                    s = s.replace('\nimport joulescope_rc\n', '\nfrom joulescope_ui import joulescope_rc\n')
                    with open(target, 'w', encoding='utf-8') as ftarget:
                        ftarget.write(s)
                elif ext == '.qrc':
                    src = os.path.join(root, source)
                    target = os.path.join(os.path.dirname(root), source)
                    target = os.path.splitext(target)[0] + '.rcc'
                    print(f'Generate {os.path.relpath(target, MYPATH)}')
                    rc = subprocess.run([rcc_path, src, '--binary', '--threshold', '33', '-o', target])
                    if rc.returncode:
                        raise RuntimeError('failed on .qrc file')
                else:
                    continue
                ignore_entry = os.path.relpath(target, path).replace('\\', '/')
                ignore.write('%s\n' % ignore_entry)


def _version_get():
    with open(VERSION_PATH, 'r', encoding='utf-8') as fv:
        for line in fv:
            if line.startswith('__version__'):
                return line.split('=')[-1].strip()[1:-1]
    raise RuntimeError('VERSION not found!')


def update_inno_iss():
    version = _version_get()
    path = os.path.join(MYPATH, 'joulescope.iss')
    with open(path, 'r', encoding='utf-8') as fv:
        lines = fv.readlines()
    version_underscore = version.replace('.', '_')
    for idx, line in enumerate(lines):
        if line.startswith('#define MyAppVersionUnderscores'):
            lines[idx] = f'#define MyAppVersionUnderscores "{version_underscore}"\n'
        elif line.startswith('#define MyAppVersion'):
            lines[idx] = f'#define MyAppVersion "{version}"\n'
    with open(path, 'w', encoding='utf-8') as fv:
        fv.write(''.join(lines))


class CustomBuildQt(distutils.cmd.Command):
    """Custom command to build Qt resource file and Qt user interface modules."""

    description = 'Build Qt resource file and Qt user interface modules.'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        convert_qt_ui()


class CustomSdistCommand(sdist):
    def run(self):
        update_inno_iss()
        convert_qt_ui()
        sdist.run(self)


if sys.platform.startswith('win'):
    PLATFORM_INSTALL_REQUIRES = ['pypiwin32>=223']
else:
    PLATFORM_INSTALL_REQUIRES = []


# Get the long description from the README file
with open(os.path.join(MYPATH, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


setuptools.setup(
    name='joulescope_ui',
    version=_version_get(),
    description='Joulescope™ graphical user interface',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://www.joulescope.com',
    author='Jetperch LLC',
    author_email='joulescope-dev@jetperch.com',
    license='Apache 2.0',

    cmdclass={
        'qt': CustomBuildQt,
        'sdist': CustomSdistCommand,
    },

    # Classifiers help users find your project by categorizing it.
    #
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[  # Optional
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: End Users/Desktop',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Embedded Systems',

        # Pick your license as you wish
        'License :: OSI Approved :: Apache Software License',

        # Supported Python versions
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],

    keywords='joulescope ui gui "user interface"',

    packages=setuptools.find_packages(exclude=['docs', 'test', 'dist', 'build']),

    include_package_data=True,
    
    # See https://packaging.python.org/guides/distributing-packages-using-setuptools/#python-requires
    python_requires='~=3.6',    
    
    # See https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        'fs',
        'markdown',
        'pyjls>=0.3.0',
        'pyperclip>=1.7.0',
        'python-dateutil>=2.7.3',
        'pyqtgraph>=0.11.0',
        "pypiwin32>=223; platform_system == 'Windows'",
        # 'pyqtgraph @ https://github.com/jetperch/pyqtgraph/tarball/557e867b377b223589c0c8ffd0799c547965fb46#egg=pyqtgraph-0.11.0.dev1',
        'requests>=2.0.0',
        "PySide2==5.13.2; python_version < '3.8'",
        "PySide2>=5.15.1; python_version >= '3.8'",
        'joulescope>=' + JOULESCOPE_VERSION_MIN,
    ] + PLATFORM_INSTALL_REQUIRES,
    
    extras_require={
        'dev': ['check-manifest', 'Cython', 'coverage', 'wheel', 'pyinstaller'],
    },

    entry_points={
        'gui_scripts': [
            'joulescope_ui=joulescope_ui.main:run',
        ],
    },
    
    project_urls={
        'Bug Reports': 'https://github.com/jetperch/pyjoulescope_ui/issues',
        'Funding': 'https://www.joulescope.com',
        'Twitter': 'https://twitter.com/joulescope',
        'Source': 'https://github.com/jetperch/pyjoulescope_ui/',
    },
)
