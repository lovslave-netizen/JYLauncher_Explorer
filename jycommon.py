"""JYLauncher / JYExplorer 공용 모듈 (경로, JSON 저장, 폰트)

설치형 배포를 전제로 한 규칙:
  - 프로그램 파일(exe, fonts)  : APP_DIR   (Program Files 아래 → 읽기 전용으로 취급)
  - 사용자 데이터(json 등)     : DATA_DIR  (%APPDATA%\\JYTools → 업데이트/재설치해도 유지)
  - exe 옆에 portable.txt 가 있으면 포터블 모드: 데이터도 APP_DIR\\data 에 저장
런처와 탐색기가 같은 DATA_DIR 를 공유하므로 bookmarks.json 도 서로 공유된다.
"""
import json
import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))  # PyInstaller 번들 리소스 위치

# 개발/테스트용: 환경 변수 JY_INSTANCE 를 주면 단일 인스턴스 이름이 달라져서, 이미 설치돼 실행 중인 프로그램과 부딪히지 않음
INSTANCE_SUFFIX = os.environ.get("JY_INSTANCE", "")

PORTABLE = (APP_DIR / "portable.txt").exists()
DATA_DIR = (APP_DIR / "data") if PORTABLE else Path(os.environ.get("APPDATA", str(Path.home()))) / "JYTools"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LAUNCHER_FILE = DATA_DIR / "launcher.json"
VAULT_FILE = DATA_DIR / "vault.json"
SETTINGS_FILE = DATA_DIR / "settings.json"        # 런처 설정
BOOKMARKS_FILE = DATA_DIR / "bookmarks.json"      # 탐색기/피커 공유
EXPLORER_FILE = DATA_DIR / "explorer.json"        # 탐색기 설정/작업공간

FONT_FILE = RES_DIR / "fonts" / "NotoSansKR.ttf"
FONT_FAMILY = "Noto Sans KR"

# 개발 중 프로그램 폴더 옆에 만들어 둔 예전 파일을 한 번만 옮겨 온다.
for _f in (LAUNCHER_FILE, VAULT_FILE, SETTINGS_FILE, BOOKMARKS_FILE):
    _old = Path(__file__).resolve().parent / _f.name
    if not FROZEN and not PORTABLE and _old.exists() and not _f.exists():
        try:
            shutil.copy2(_old, _f)
        except OSError:
            pass


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 원자적 교체: 저장 중 꺼져도 파일이 깨지지 않음


def load_font(app):
    """번들 Noto Sans KR 등록. 실패하면 시스템 폰트로 대체."""
    global FONT_FAMILY
    from PySide6.QtGui import QFont, QFontDatabase
    fid = QFontDatabase.addApplicationFont(str(FONT_FILE))
    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    if fams:
        FONT_FAMILY = fams[0]
    app.setFont(QFont(FONT_FAMILY, 10))
    return FONT_FAMILY


def app_icon(name):
    """번들된 프로그램 아이콘(JYLauncher.ico / JYExplorer.ico). 창/트레이 아이콘용 — 개발 중에도 python 아이콘 대신 이게 보임"""
    from PySide6.QtGui import QIcon
    return QIcon(str(RES_DIR / f"{name}.ico"))


def pick_category(parent, existing, exclude=()):
    """'어느 카테고리에 추가할까요?' 목록 창 (맨 위 '새로 추가' → 기존 카테고리들 → 맨 아래 '새 카테고리 만들기').
    고른 카테고리 이름을 돌려줌 (취소하면 None). 런처/탐색기의 '런처에 추가'가 공용으로 씀."""
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QPushButton, QVBoxLayout
    default = "새로 추가"
    names = [default] + [c for c in existing if c != default and c not in exclude]
    dlg = QDialog(parent)
    dlg.setWindowTitle("카테고리 선택")
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel("어느 카테고리에 추가할까요?"))
    lw = QListWidget()
    lw.setMinimumSize(360, 280)
    for n in names:
        lw.addItem(n)
    lw.addItem("＋ 새 카테고리 만들기…")
    lw.setCurrentRow(0)
    lw.itemActivated.connect(lambda _it: dlg.accept())      # 더블클릭 / Enter
    lay.addWidget(lw)
    row = QHBoxLayout()
    row.addStretch(1)
    ok, cancel = QPushButton("추가"), QPushButton("취소")
    ok.clicked.connect(dlg.accept)
    cancel.clicked.connect(dlg.reject)
    row.addWidget(ok)
    row.addWidget(cancel)
    lay.addLayout(row)
    if dlg.exec() != QDialog.Accepted or lw.currentRow() < 0:
        return None
    if lw.currentRow() < len(names):
        return names[lw.currentRow()]
    name, ok2 = QInputDialog.getText(parent, "새 카테고리", "카테고리 이름:")
    return name.strip() if ok2 and name.strip() else None


def open_in_explorer(path):
    """폴더를 JY Explorer(새 탭)로 엶. JY Explorer 가 없으면 Windows 탐색기(기본 연결)로"""
    import subprocess
    try:
        if FROZEN:
            exe = APP_DIR / "JYExplorer.exe"
            if exe.exists():
                subprocess.Popen([str(exe), str(path)], cwd=str(APP_DIR))
                return True
        else:
            src = APP_DIR / "JYExplorer.py"
            if src.exists():
                py = Path(sys.executable).with_name("pythonw.exe")
                subprocess.Popen([str(py if py.exists() else sys.executable), str(src), str(path)], cwd=str(APP_DIR))
                return True
    except OSError:
        pass
    try:
        os.startfile(str(path))
        return True
    except OSError:
        return False


def file_mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0


def add_item_to_launcher(path, category="새로 추가"):
    """런처 목록(launcher.json)에 항목 추가. 런처/탐색기/셸 우클릭 메뉴 공용. 이미 있으면 False"""
    path = os.path.normpath(path)
    data = load_json(LAUNCHER_FILE, {})

    def apps(items):                       # 폴더 카드 안의 앱까지 포함해서 중복 검사
        for i in items:
            if i.get("type") == "folder":
                yield from apps(i.get("items", []))
            else:
                yield i
    for items in data.values():
        if any(os.path.normcase(i.get("path", "")) == os.path.normcase(path) for i in apps(items)):
            return False
    data.setdefault(category, []).append({"name": Path(path).stem or path, "path": path})
    save_json(LAUNCHER_FILE, data)
    return True


# ───────────── 바로가기(.lnk) 만들기: 시작 메뉴 / 바탕화면 ─────────────
def shortcut_folder(where):
    """where = 'startmenu' | 'desktop' (OneDrive 로 옮겨진 바탕화면도 실제 위치를 물어서 찾음)"""
    if where == "startmenu":
        return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)   # CSIDL_DESKTOPDIRECTORY
    return Path(buf.value)


def _program_launch(script, exe_name):
    """(실행 파일, 인자, 작업 폴더) — 설치된 exe 면 exe 를, 개발 중이면 pythonw + 스크립트를 가리킨다"""
    if FROZEN:
        exe = APP_DIR / exe_name
        return (str(exe), "", str(APP_DIR)) if exe.exists() else None
    py = Path(sys.executable).with_name("pythonw.exe")
    py = py if py.exists() else Path(sys.executable)
    src = APP_DIR / script
    return (str(py), f'"{src}"', str(APP_DIR)) if src.exists() else None


PROGRAMS = (("JY Launcher", "JYLauncher.py", "JYLauncher.exe"),
            ("JY Explorer", "JYExplorer.py", "JYExplorer.exe"))


def make_shortcut(lnk, target, args="", workdir="", desc=""):
    """WScript.Shell 로 .lnk 생성 (경로는 환경 변수로 넘겨 한글/공백 인용 문제를 피함). 성공하면 True"""
    import subprocess
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:JY_LNK);"
          "$s.TargetPath=$env:JY_TARGET;$s.Arguments=$env:JY_ARGS;$s.WorkingDirectory=$env:JY_DIR;"
          "$s.IconLocation=$env:JY_TARGET+',0';$s.Description=$env:JY_DESC;$s.Save()")
    env = dict(os.environ, JY_LNK=str(lnk), JY_TARGET=target, JY_ARGS=args, JY_DIR=workdir, JY_DESC=desc)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env,
                           capture_output=True, creationflags=0x08000000, timeout=30)   # 창 숨김
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and Path(lnk).exists()


def create_app_shortcuts(where, folder=None):
    """런처·탐색기 바로가기를 시작 메뉴/바탕화면에 만든다. 만든 .lnk 경로 목록을 돌려줌"""
    folder = Path(folder) if folder else shortcut_folder(where)
    made = []
    for title, script, exe_name in PROGRAMS:
        spec = _program_launch(script, exe_name)
        if spec is None:
            continue
        lnk = folder / f"{title}.lnk"
        if make_shortcut(lnk, spec[0], spec[1], spec[2], title):
            made.append(lnk)
    return made


BACKUP_DIR = DATA_DIR / "backup"      # 즐겨찾기/북마크 백업 폴더


BACKUP_KEEP_DAYS = 90


def backup_favorites(tag=""):
    """북마크(bookmarks.json)와 탐색기 설정 전체(explorer.json)를 zip 하나로 backup 폴더에 저장하고 그 경로를 돌려줌.
    파일 이름에 날짜/시각이 들어가고, 90일이 지난 백업(예전 json 백업 포함)은 자동으로 지움."""
    import time as _t
    import zipfile
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _t.strftime("%Y-%m-%d_%H%M%S")
    dest = BACKUP_DIR / f"JYExplorer_백업_{stamp}{tag}.zip"
    n = 1
    while dest.exists():
        n += 1
        dest = BACKUP_DIR / f"JYExplorer_백업_{stamp}{tag}_{n}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, name in ((BOOKMARKS_FILE, "bookmarks.json"), (EXPLORER_FILE, "explorer.json")):
            if src.exists():
                zf.write(src, name)
    cleanup_backups()
    return dest


def cleanup_backups(days=BACKUP_KEEP_DAYS):
    """backup 폴더에서 days 일이 지난 파일 삭제 (프로그램을 켤 때와 백업할 때 호출)"""
    import time as _t
    limit = _t.time() - days * 86400
    try:
        for f in BACKUP_DIR.iterdir():
            if f.is_file() and f.stat().st_mtime < limit:
                try:
                    f.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def read_backup(path):
    """백업 zip → (bookmarks 딕셔너리, explorer 설정 딕셔너리). 형식이 맞지 않으면 ValueError"""
    import json
    import zipfile
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            bm = json.loads(zf.read("bookmarks.json").decode("utf-8")) if "bookmarks.json" in names else {"children": []}
            ex = json.loads(zf.read("explorer.json").decode("utf-8")) if "explorer.json" in names else {}
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as e:
        raise ValueError(f"백업 파일을 읽을 수 없습니다: {e}")
    if not isinstance(bm, dict) or not isinstance(bm.get("children", []), list) or not isinstance(ex, dict):
        raise ValueError("백업 파일의 내용이 올바르지 않습니다")
    bm.setdefault("children", [])
    return bm, ex
