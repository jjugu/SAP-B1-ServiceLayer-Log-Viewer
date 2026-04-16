# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None
base_dir = SPECPATH
app_dir = os.path.join(base_dir, 'app')

a = Analysis(
    [os.path.join(app_dir, 'main.py')],
    pathex=[app_dir],
    binaries=[],
    datas=[
        (os.path.join(app_dir, 'templates'), 'app/templates'),
        (os.path.join(app_dir, 'static'), 'app/static'),
    ],
    hiddenimports=[
        'flask',
        'jinja2',
        'markupsafe',
        'werkzeug',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SL_Log_Viewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
