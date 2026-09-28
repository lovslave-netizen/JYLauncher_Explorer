# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙: 런처 + 탐색기 exe 2개를 폴더 하나(dist\JYTools)에 같이 묶는다.
# (Qt 런타임 _internal 을 공유해서 용량이 절반, 서로 exe 를 찾아 연동하기도 쉬움)
#   빌드:  pyinstaller --noconfirm JYTools.spec      (또는 build.ps1)

HIDDEN = ["win32com.shell.shell", "win32com.shell.shellcon", "win32gui", "win32api", "win32con", "winreg"]
EXCLUDES = ["tkinter", "unittest", "pydoc_data",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.QtQml",
            "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization"]
DATAS = [("fonts", "fonts"), ("JYLauncher.ico", "."), ("JYExplorer.ico", ".")]   # .ico: 창/트레이 아이콘용 (exe 아이콘은 icon= 으로 따로)


def build(script, name):
    a = Analysis([script], pathex=["."], datas=DATAS, hiddenimports=HIDDEN, excludes=EXCLUDES)
    pyz = PYZ(a.pure)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name, console=False, upx=False, icon=name + ".ico")
    return a, exe


la, lexe = build("JYLauncher.py", "JYLauncher")
ea, eexe = build("JYExplorer.py", "JYExplorer")

COLLECT(lexe, la.binaries, la.datas,
        eexe, ea.binaries, ea.datas,
        strip=False, upx=False, name="JYTools")
