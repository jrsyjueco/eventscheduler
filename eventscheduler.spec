# -*- mode: python ; coding: utf-8 -*-
from kivy_deps import sdl2, glew

block_cipher = None

a = Analysis(['C:\\Users\\Arts LC\\dev\\eventscheduler\\eventscheduler.py'],
             pathex=['C:\\Users\\ARTSLC~1\\Envs\\EVENTS~1\\EventScheduler'],
             binaries=[],
             datas=[],
             hiddenimports=['win32timezone'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['picamera', 'gi', 'opencv', 'enchant'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

a.datas += [('eventscheduler.kv', 'C:\\Users\\Arts LC\\dev\\eventscheduler\\eventscheduler.kv', 'DATA')]

exe = EXE(pyz, Tree('C:\\Users\\Arts LC\\dev\\eventscheduler\\'),
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
          name='EventScheduler',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )
