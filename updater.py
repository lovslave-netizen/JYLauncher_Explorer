"""GitHub Releases 기반 업데이트 (런처/탐색기 공용).

흐름: 최신 릴리스 조회(하루 1회 자동 / 수동) → 새 버전이면 트레이 알림 + 메뉴 항목 →
      사용자가 수락하면 Setup.exe 다운로드 → sha256 검증 → 다른 JY 프로그램에 종료 요청 →
      Setup.exe /SILENT 실행(설치 후 켜져 있던 프로그램 자동 재실행) → 이 프로그램도 종료.
설치 폴더에 쓰는 일은 전부 Inno Setup 이 하므로 여기서는 파일을 직접 덮어쓰지 않는다.
설정/상태는 두 프로그램이 공유하는 %APPDATA%\\JYTools\\update.json (자동 확인 여부, 마지막 확인 시각, 발견한 최신 버전).
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon

from jycommon import DATA_DIR, FROZEN, PORTABLE, load_json, save_json
from version import GITHUB_OWNER, GITHUB_REPO, RELEASES_API, __version__

STATE_FILE = DATA_DIR / "update.json"
CHECK_INTERVAL = 20 * 3600            # 자동 확인 간격(초)
ALLOWED_PREFIX = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/"
SERVER_NAMES = {"launcher": "JYLauncher-single-instance", "explorer": "JYExplorer-single-instance"}
CREATE_NO_WINDOW, DETACHED_PROCESS, NEW_GROUP = 0x08000000, 0x00000008, 0x00000200


def parse_version(text):
    return tuple(int(n) for n in re.findall(r"\d+", text)[:4])


def is_newer(latest, current=__version__):
    return parse_version(latest) > parse_version(current)


def _open(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": f"JYTools/{__version__}", "Accept": "application/octet-stream, application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest():
    """최신 릴리스 정보 {version, url, sha_url, notes}. 새 버전이 없거나 설치 파일이 없으면 None. 네트워크 오류는 예외"""
    with _open(RELEASES_API) as r:
        rel = json.loads(r.read().decode("utf-8"))
    tag = rel.get("tag_name", "")
    if not tag or not is_newer(tag):
        return None
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    setup = next((n for n in assets if re.fullmatch(r"JYTools-Setup-[\d.]+\.exe", n)), None)
    if not setup or setup + ".sha256" not in assets:
        return None                    # 설치 파일이나 해시 파일이 없는 릴리스는 무시 (검증 없이 실행하지 않음)
    if not (assets[setup].startswith(ALLOWED_PREFIX) and assets[setup + ".sha256"].startswith(ALLOWED_PREFIX)):
        return None
    return {"version": tag.lstrip("vV"), "url": assets[setup], "sha_url": assets[setup + ".sha256"],
            "name": setup, "notes": (rel.get("body") or "").strip()}


def download_verified(info, progress=None):
    """Setup.exe 를 임시 폴더에 받아 sha256 을 검증한 뒤 경로를 돌려줌. 불일치하면 삭제하고 예외"""
    with _open(info["sha_url"]) as r:
        expected = r.read().decode("ascii", "ignore").split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("해시 파일 형식이 올바르지 않습니다")
    folder = Path(tempfile.gettempdir()) / "JYTools-update"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / info["name"]
    h = hashlib.sha256()
    with _open(info["url"], timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(256 * 1024):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(int(done * 100 / total))
    if h.hexdigest() != expected:
        dest.unlink(missing_ok=True)
        raise ValueError("다운로드한 파일의 해시가 일치하지 않습니다 (손상되었거나 변조됨)")
    return dest


def ask_running_to_quit(skip):
    """다른 JY 프로그램(skip 제외)이 떠 있으면 종료를 요청하고, 종료 요청을 받은 프로그램 이름 목록을 돌려줌"""
    was_running = []
    for key, server in SERVER_NAMES.items():
        if key == skip:
            continue
        s = QLocalSocket()
        s.connectToServer(server)
        if s.waitForConnected(300):
            s.write(b"quit")
            s.waitForBytesWritten(300)
            s.disconnectFromServer()
            was_running.append(key)
    return was_running


class Updater(QObject):
    _found = Signal(object, bool, str)     # (info | None, 수동 확인 여부, 오류 메시지) — 스레드 → GUI
    _failed = Signal(str)
    _progress = Signal(int)
    _ready = Signal(object)
    changed = Signal()                     # 확인 결과가 바뀜 (설정 화면의 표시 갱신용)

    def __init__(self, me, on_quit, parent=None):
        """me = 'launcher' | 'explorer' (자기 자신), on_quit = 이 프로그램을 정상 종료하는 함수"""
        super().__init__(parent)
        self.me, self.on_quit = me, on_quit
        self.state = load_json(STATE_FILE, {})
        self.available = None
        self.busy = False
        self._prompted = False
        self.widget = self.tray = self.action = None
        self._found.connect(self._on_found)
        self._failed.connect(self._on_failed)
        self._progress.connect(lambda p: self._notify(f"업데이트 다운로드 중… {p}%", quiet=True))
        self._ready.connect(self._launch)
        latest = self.state.get("latest")
        if latest and is_newer(latest.get("version", "0")):   # 다른 프로그램이 이미 찾아 둔 새 버전
            self.available = latest

    # ── 설정 ──
    @property
    def auto(self):
        return self.state.get("auto", True)

    def set_auto(self, on):
        self.state = load_json(STATE_FILE, {})
        self.state["auto"] = bool(on)
        save_json(STATE_FILE, self.state)

    @property
    def can_install(self):
        return FROZEN and not PORTABLE

    # ── UI 연결 ──
    def attach(self, widget, tray, tray_menu):
        """widget = 메시지 상자 부모, tray = QSystemTrayIcon, tray_menu = 트레이 메뉴(항목 하나 추가)"""
        self.widget, self.tray = widget, tray
        self.action = QAction(self)
        self.action.triggered.connect(lambda: self.prompt_install() if self.available else self.check(manual=True))
        acts = tray_menu.actions()
        if acts:
            tray_menu.insertAction(acts[-1], self.action)      # "종료" 바로 위
        else:
            tray_menu.addAction(self.action)
        tray.messageClicked.connect(lambda: self.available and self.prompt_install())
        self._refresh_action()
        QTimer.singleShot(8000, self.check_if_due)         # 시작 직후 부하를 피해 조금 뒤에

    def _refresh_action(self):
        if self.action:
            self.action.setText(f"업데이트 {self.available['version']} 설치…" if self.available else "업데이트 확인")

    def status_text(self):
        if self.available:
            return f"현재 {__version__} · 새 버전 {self.available['version']} 을(를) 설치할 수 있습니다"
        return f"현재 버전 {__version__}"

    def _notify(self, text, quiet=False):
        if self.tray and self.tray.isVisible() and not quiet:
            self.tray.showMessage("JY Tools 업데이트", text, QSystemTrayIcon.Information, 6000)

    # ── 확인 ──
    def check_if_due(self):
        if not self.auto or self.busy:
            return
        self.state = load_json(STATE_FILE, {})
        if time.time() - self.state.get("last_check", 0) < CHECK_INTERVAL:
            if self.available:                 # 최근에 이미 확인했고 새 버전이 있음 → 실행할 때마다 다시 물어봄
                self._refresh_action()
                self._auto_prompt()
            return
        self.check(manual=False)

    def _auto_prompt(self):
        """프로그램을 켰을 때 새 버전이 있으면 '업데이트하시겠습니까?' 를 바로 물어봄.
        런처와 탐색기가 동시에 뜨면 창이 두 번 뜨지 않게, 런처가 떠 있으면 탐색기는 물어보지 않음"""
        if self._prompted or not self.available or not self.can_install:
            return
        if self.me != "launcher":
            s = QLocalSocket()
            s.connectToServer(SERVER_NAMES["launcher"])
            if s.waitForConnected(300):
                s.disconnectFromServer()
                return
        self._prompted = True
        self.prompt_install()

    def check(self, manual=True):
        if self.busy:
            return
        self.busy = True

        def work():
            try:
                self._found.emit(fetch_latest(), manual, "")
            except Exception as ex:                        # 네트워크 없음 등 — 자동 확인이면 조용히 넘어감
                self._found.emit(None, manual, str(ex))
        threading.Thread(target=work, daemon=True).start()

    def _on_found(self, info, manual, err):
        self.busy = False
        if not err:
            self.state = load_json(STATE_FILE, {})
            self.state.update(last_check=time.time(), latest=info)
            save_json(STATE_FILE, self.state)
            self.available = info
        self._refresh_action()
        self.changed.emit()
        if err:
            if manual:
                QMessageBox.warning(self.widget, "업데이트 확인", "업데이트를 확인하지 못했습니다.\n인터넷 연결을 확인해 주세요.\n\n" + err)
        elif info:
            if manual:
                self.prompt_install()
            elif self.can_install:
                self._auto_prompt()
            else:
                self._notify(f"새 버전 {info['version']} 이(가) 있습니다.")
        elif manual:
            QMessageBox.information(self.widget, "업데이트 확인", f"최신 버전입니다. (현재 {__version__})")

    # ── 설치 ──
    def prompt_install(self):
        info = self.available
        if not info or self.busy:
            return
        if not self.can_install:
            QMessageBox.information(self.widget, "업데이트", f"새 버전 {info['version']} 이(가) 있습니다.\n"
                                    "설치형으로 설치된 프로그램에서만 자동 업데이트를 지원합니다.\n"
                                    f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases 에서 받아 주세요.")
            return
        notes = info["notes"][:600] + ("…" if len(info["notes"]) > 600 else "")
        box = QMessageBox(self.widget)
        box.setWindowFlag(Qt.WindowStaysOnTopHint)         # 창 없이 트레이에만 떠 있을 때도 눈에 띄게
        box.setWindowTitle("업데이트")
        box.setText(f"새 버전 {info['version']} 을(를) 설치할까요?  (현재 {__version__})")
        box.setInformativeText("설치하는 동안 런처와 탐색기가 잠시 종료되었다가 자동으로 다시 시작됩니다.\n"
                               "북마크·런처 목록 등 내 데이터는 그대로 유지됩니다."
                               + (("\n\n변경 내용:\n" + notes) if notes else ""))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("지금 업데이트")
        box.button(QMessageBox.No).setText("나중에")
        if box.exec() != QMessageBox.Yes:
            return
        self.busy = True
        self._notify("업데이트를 내려받는 중입니다…")

        def work():
            try:
                self._ready.emit(download_verified(info, self._progress.emit))
            except Exception as ex:
                self._failed.emit(str(ex))
        threading.Thread(target=work, daemon=True).start()

    def _on_failed(self, err):
        self.busy = False
        QMessageBox.warning(self.widget, "업데이트", "업데이트를 설치하지 못했습니다.\n\n" + err)

    def _launch(self, setup):
        relaunch = [self.me] + ask_running_to_quit(self.me)
        subprocess.Popen([str(setup), "/SILENT", "/NOCANCEL", "/CLOSEAPPLICATIONS", "/RELAUNCH=" + ",".join(relaunch)],
                         creationflags=DETACHED_PROCESS | NEW_GROUP, close_fds=True)
        self.on_quit()
