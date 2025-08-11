# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['dist_obfuscated\\gui_robot.py'],
    pathex=['dist_obfuscated'],
    binaries=[],
    datas=[('asset', 'asset'), ('Roboto-Regular.ttf', '.')],
    hiddenimports=['PyQt6', 'pytz', 'json', 'logic_engulfing', 'MetaTrader5', 'numpy', 'pandas', 'qtawesome', 'keyring'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EngulfingBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
