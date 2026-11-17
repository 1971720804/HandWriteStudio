# -*- mode: python ; coding: utf-8 -*-

# HandWriteStudio 打包脚本（onedir）
# 重新打包：.venv\Scripts\pyinstaller.exe --noconfirm --clean HandWriteStudio.spec

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/fonts", "assets/fonts"),
        ("assets/papers", "assets/papers"),
        ("assets/icon.ico", "assets"),
        ("assets/icon.png", "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.Qt3DCore",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HandWriteStudio",
    icon="assets/icon.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HandWriteStudio",
)
