# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app.ico', '.'),  # Include icon
        ('licenses.db', '.'),  # Include default licenses database
        ('license_dashboard', 'license_dashboard'),  # Include embedded license dashboard web assets
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'cryptography',
        'cryptography.fernet',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.hashes',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.backends',
        'pymysql',
        'requests',
        'apscheduler',
        'apscheduler.schedulers.background',
        'apscheduler.triggers.cron',
        'apscheduler.triggers.interval',
        'google.generativeai',
        'fastapi',
        'uvicorn',
        'sqlalchemy',
        'pydantic',
        'pydantic_core',
        'anyio',
        'click',
        'h11',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Harmulizer_Pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico'  # Application icon
)
