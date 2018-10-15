# -*- mode: python -*-

block_cipher = None


a = Analysis(['joulescope_ui\__main__.py'],
             pathex=['D:\\repos\\Jetperch\\pyjoulescope_ui'],
             binaries=[],
             datas=[('joulescope_ui/config_def.json5', 'joulescope_ui')],
             hiddenimports=['secrets'],
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
          name='joulescope',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          icon='joulescope_ui/resources/icon_64x64.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='joulescope')
