# -*- mode: python -*-

# Configuration file for PyInstaller
# See https://pyinstaller.readthedocs.io/en/stable/index.html
# > pip install pyinstaller
# > pyinstaller joulescope.spec

# Mac OS X
# https://kivy.org/doc/stable/guide/packaging-osx.html
# hdiutil create ./dist/joulescope.dmg -srcfolder ./dist/joulescope.app -ov

import sys
import ctypes.util
import os

block_cipher = None
specpath = os.path.dirname(os.path.abspath(SPEC))
PATHEX = []


def find_site_packages():
    for p in sys.path:
        if p.endswith('site-packages'):
            return p
    raise RuntimeError('Could not find site-packages')


if sys.platform.startswith('win'):
    EXE_NAME = 'joulescope'
    BINARIES = [  # uses winusb which comes with Windows
        ('C:\\Windows\\System32\\msvcp100.dll', '.'),
        ('C:\\Windows\\System32\\msvcr100.dll', '.'),
        ('C:\\Windows\\System32\\msvcp140.dll', '.'),
    ]
    PATHEX.append(os.path.join(find_site_packages(), 'shiboken2'))
elif sys.platform.startswith('darwin'):
    from joulescope_ui.libusb_mac import mac_binaries
    EXE_NAME = 'joulescope_launcher'
    BINARIES = mac_binaries()
else:
    EXE_NAME = 'joulescope_launcher'
    BINARIES = []  # sudo apt install libusb-1

a = Analysis(['joulescope_ui/__main__.py'],
             pathex=PATHEX,
             binaries=BINARIES,
             datas=[('joulescope_ui/config_def.json5', 'joulescope_ui')],
             hiddenimports=['secrets', 'numpy.core._dtype_ctypes'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['matplotlib', 'scipy'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name=EXE_NAME,
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          icon='joulescope_ui/resources/icon.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='joulescope')

if sys.platform.startswith('darwin'):
    # https://blog.macsales.com/28492-create-your-own-custom-icons-in-10-7-5-or-later
    # iconutil --convert icns joulescope_ui/resources/icon.iconset
    # hdiutil create ./dist/joulescope.dmg -srcfolder ./dist/joulescope.app -ov
    app = BUNDLE(coll,
                 name='joulescope.app',
                 icon='joulescope_ui/resources/icon.icns',
                 bundle_identifier=None,
                 info_plist={
                     'CFBundleVersion': '0.2.1',
                 })

