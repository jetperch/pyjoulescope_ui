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
import os

MYPATH = os.path.abspath(os.path.dirname(__file__))

# Get the long description from the README file
with open(os.path.join(MYPATH, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setuptools.setup(
    name='joulescope_ui',
    version='0.1.0',
    description='Joulescope™ graphical user interface',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://www.joulescope.com',
    author='Jetperch LLC',
    author_email='joulescope-dev@jetperch.com',
    license='Apache',

    # Classifiers help users find your project by categorizing it.
    #
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[  # Optional
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: End Users/Desktop',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Embedded Systems',

        # Pick your license as you wish
        'License :: OSI Approved :: Apache Software License',

        # Supported Python versions
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],

    keywords='joulescope ui gui "user interface"',

    packages=setuptools.find_packages(exclude=['docs', 'test', 'dist', 'build']),

    # See https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        'json5>=0.6.1',
        'numpy>=1.15.2',
        'pypiwin32>=223',
        'python-dateutil>=2.7.3',
        'PyQt5>=5.11.2',
        'pyqtgraph>=0.10.0',
        'pyjoulescope>=0.1.0',
    ],

    entry_points={
        'console_scripts': [
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
