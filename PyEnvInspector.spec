# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置: PyEnv Inspector (onedir, GUI 无控制台)。

用法(项目根目录执行):
    python -m PyInstaller --noconfirm --clean PyEnvInspector.spec
产物: dist/PyEnvInspector/PyEnvInspector.exe 及同目录运行时文件
"""

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["packaging"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 应用只用 QtWidgets/QtGui/QtCore + packaging; 裁掉未使用的 Qt 大模块
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
        "PySide6.QtQuick3D", "PySide6.QtQuickControls2",
        "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
        "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtGraphs", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtBluetooth",
        "PySide6.QtNfc", "PySide6.QtSerialPort", "PySide6.QtSensors",
        "PySide6.QtTest", "PySide6.QtRemoteObjects", "PySide6.QtSql",
        "PySide6.QtUiTools", "PySide6.QtDesigner", "PySide6.QtHelp",
        "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
        "PySide6.QtWebSockets", "PySide6.QtHttpServer", "PySide6.QtNetworkAuth",
        "tkinter", "curses", "unittest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PyEnvInspector",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # GUI 应用, 不弹控制台
    icon="assets/pyenv.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PyEnvInspector",
)
