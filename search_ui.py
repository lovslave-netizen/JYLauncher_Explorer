"""파일 검색 결과 화면 부품 (런처 '검색' 탭 / 탐색기 '하위 폴더 포함' 공용).
  ResultsTree     : 이름 / 위치 / 크기 / 수정한 날짜 목록 (검색 결과가 조금씩 채워짐)
  EverythingGuard : Everything 이 없거나 꺼져 있거나 관리자 권한으로 떠 있어 접속이 안 될 때의 안내·설치·복구
"""
import os
import threading
import time

from PySide6.QtCore import QFileInfo, QObject, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QFileDialog, QFileIconProvider, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

import filesearch as FS
from jycommon import DATA_DIR, load_json, save_json

SEARCH_FILE = DATA_DIR / "search.json"          # {"everything": "declined"} 등 (두 프로그램 공용)
_provider = QFileIconProvider()
_icon_cache = {}


def fmt_size(n):
    if n is None or n < 0:
        return ""
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def fmt_date(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def ext_icon(path, is_dir):
    """확장자만으로 아이콘을 고름 (디스크/네트워크에 접근하지 않아 수천 개도 빠름)"""
    if is_dir:
        key = "<dir>"
    else:
        key = os.path.splitext(path)[1].lower()
    ic = _icon_cache.get(key)
    if ic is None:
        ic = _provider.icon(QFileIconProvider.Folder) if is_dir else _provider.icon(QFileInfo("x" + (key or ".txt")))
        _icon_cache[key] = ic
    return ic


class ResultsTree(QTreeWidget):
    """검색 결과 목록. 더블클릭/Enter = openRequested(경로, 폴더인지), 우클릭 = menuRequested(경로, 폴더인지, 전역좌표)"""
    openRequested = Signal(str, bool)
    menuRequested = Signal(str, bool, object)
    copyRequested = Signal(list)                 # Ctrl+C: 선택한 결과의 경로 목록
    MAX_ROWS = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHeaderLabels(["이름", "위치", "크기", "수정한 날짜"])
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setSortingEnabled(False)
        h = self.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.Interactive)
        h.setSectionResizeMode(1, QHeaderView.Stretch)             # 위치 열이 남는 폭을 채움 → 가로 스크롤 없음
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        h.setSectionResizeMode(3, QHeaderView.Interactive)
        for c, w in ((0, 320), (2, 90), (3, 150)):
            h.resizeSection(c, w)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemActivated.connect(self._activated)
        self.itemDoubleClicked.connect(self._activated)

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Copy):
            paths = [r[0] for r in self.selected_results() if r]
            if paths:
                self.copyRequested.emit(paths)
            return
        super().keyPressEvent(e)

    def clear_results(self):
        self.clear()

    def add_rows(self, rows):
        room = self.MAX_ROWS - self.topLevelItemCount()
        self.setUpdatesEnabled(False)
        try:
            for r in rows[:max(room, 0)]:
                it = QTreeWidgetItem([r["name"], os.path.dirname(r["path"]), "" if r["is_dir"] else fmt_size(r["size"]),
                                      fmt_date(r["mtime"])])
                it.setIcon(0, ext_icon(r["path"], r["is_dir"]))
                it.setData(0, Qt.UserRole, (r["path"], r["is_dir"]))
                it.setToolTip(0, r["path"])
                it.setToolTip(1, r["path"])
                self.addTopLevelItem(it)
        finally:
            self.setUpdatesEnabled(True)
        if self.currentItem() is None and self.topLevelItemCount():
            self.setCurrentItem(self.topLevelItem(0))

    def current_result(self):
        it = self.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def selected_results(self):
        return [i.data(0, Qt.UserRole) for i in self.selectedItems()]

    def _activated(self, it, _col=0):
        d = it.data(0, Qt.UserRole)
        if d:
            self.openRequested.emit(d[0], d[1])

    def _menu(self, pos):
        it = self.itemAt(pos)
        if it is None:
            return
        if not it.isSelected():
            self.clearSelection()
            it.setSelected(True)
            self.setCurrentItem(it)
        d = it.data(0, Qt.UserRole)
        self.menuRequested.emit(d[0], d[1], self.viewport().mapToGlobal(pos))


class IndexDialog(QDialog):
    """설정 → 검색 색인: Everything 이 색인 중인 볼륨/폴더를 보여주고, 폴더 색인을 추가/제거한다.
    Everything 이 없으면 설치를 권함. (색인 변경은 Everything 을 잠시 종료했다가 다시 켜는 방식 — ini 백업 후 수정)"""
    _done = Signal(bool, str)                    # 작업 스레드 → GUI

    def __init__(self, parent=None):
        super().__init__(parent)
        import everything_ini as EI
        self.EI = EI
        self.setWindowTitle("검색 색인 (Everything)")
        self.setMinimumSize(640, 480)
        self.busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        self.state = QLabel("")
        self.state.setWordWrap(True)
        lay.addWidget(self.state)
        info = QLabel("Everything 이 색인한 위치가 검색 대상입니다. NTFS 드라이브(C:, D: …)는 자동으로 전체가 색인되고, "
                      "네트워크 드라이브/폴더(W:\\, Z:\\, \\\\서버\\공유)는 '폴더 색인'으로 추가해야 검색됩니다.")
        info.setObjectName("dim")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        row = QHBoxLayout()
        self.b_add = QPushButton("폴더 추가…")
        self.b_net = QPushButton("네트워크 경로 추가…")
        self.b_del = QPushButton("선택한 폴더 색인 제거")
        self.b_inst = QPushButton("Everything 설치")
        self.b_inst.setObjectName("accent")
        close = QPushButton("닫기")
        self.b_add.clicked.connect(self.add_folder)
        self.b_net.clicked.connect(self.add_network)
        self.b_del.clicked.connect(self.remove_selected)
        self.b_inst.clicked.connect(self.install)
        close.clicked.connect(self.accept)
        for b in (self.b_add, self.b_net, self.b_del, self.b_inst):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self._done.connect(self._on_done)
        self.reload()

    # ---- 화면 ----
    def reload(self):
        EI = self.EI
        self.list.clear()
        st = FS.Searcher.status()
        self.state.setText({"ready": "상태: Everything 연결됨 — 검색 탭에서 색인 전체를 즉시 검색할 수 있습니다",
                            "elevated": "상태: Everything 이 관리자 권한으로 실행 중이라 이 프로그램이 연결할 수 없습니다 "
                                        "(검색 탭을 처음 열 때 자동 설정을 안내합니다)",
                            "not_running": "상태: Everything 이 실행 중이 아니거나 색인을 불러오는 중입니다",
                            "missing": "상태: Everything 이 설치돼 있지 않습니다. 설치하면 색인 목록을 보고 관리할 수 있고 "
                                       "파일 검색이 매우 빨라집니다 (무료, 가벼움)"}[st])
        installed = bool(FS.find_everything_exe())
        path = EI.find_ini() if installed else None
        self.b_inst.setVisible(not installed)
        for b in (self.b_add, self.b_net, self.b_del):
            b.setEnabled(installed and path is not None and not self.busy)
            b.setVisible(installed)
        if not installed or path is None:
            self.list.addItem("(Everything 이 설치돼 있지 않아 색인 목록이 없습니다)")
            return
        try:
            ini, _bom = EI.read_ini(path)
            idx = EI.read_index(ini)
        except OSError as e:
            self.list.addItem(f"(설정 파일을 읽을 수 없습니다: {e})")
            return
        for p, inc, mon in idx["volumes"]:
            it = QListWidgetItem(f"[드라이브]  {p}    NTFS/ReFS 볼륨 " + ("· 자동 색인" if inc else "· 제외됨") + (" · 변경 감시" if mon and inc else ""))
            it.setData(Qt.UserRole, None)
            self.list.addItem(it)
        for p, mon in idx["folders"]:
            it = QListWidgetItem(f"[폴더]      {p}    폴더 색인" + (" · 변경 감시" if mon else ""))
            it.setData(Qt.UserRole, p)
            self.list.addItem(it)
        if not idx["folders"]:
            self.list.addItem("(폴더 색인이 없습니다 — 네트워크 드라이브는 '폴더 추가'로 넣어야 검색됩니다)")

    def _set_busy(self, on, text=""):
        self.busy = on
        self.msg.setText(text)
        for b in (self.b_add, self.b_net, self.b_del, self.b_inst):
            b.setEnabled(not on)

    # ---- 동작 ----
    def _confirm_restart(self):
        return QMessageBox.question(self, "Everything 다시 시작",
                                    "색인을 바꾸려면 Everything 을 잠시 종료했다가 다시 켭니다.\n"
                                    "(설정 파일은 먼저 자동 백업됩니다. 새 폴더는 켜진 뒤 백그라운드에서 색인됩니다)\n\n계속할까요?") == QMessageBox.Yes

    def _run_change(self, mutate, busy_text):
        if not self._confirm_restart():
            return
        self._set_busy(True, busy_text)

        def work():
            try:
                ok, m = FS.change_index(mutate, log=lambda t: self._done.emit(True, "…" + t))
            except Exception as e:
                ok, m = False, str(e)
            self._done.emit(ok, "!" + m if not ok else "완료: " + m)
        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, ok, text):
        if text.startswith("…"):                     # 진행 메시지
            self.msg.setText(text[1:])
            return
        self._set_busy(False, text.lstrip("!"))
        self.reload()

    def _add(self, path):
        EI = self.EI
        path = EI.normalize_folder(path)
        try:
            ini, _b = EI.read_ini(EI.find_ini())
            vol = EI.covered_by_volume(ini, path)
        except OSError as e:
            QMessageBox.warning(self, "색인", str(e))
            return
        if vol:
            QMessageBox.information(self, "이미 색인됨", f"{path} 는 이미 {vol} 드라이브 전체가 색인되고 있어서 따로 추가할 필요가 없습니다.")
            return
        self._run_change(lambda ini: f"폴더 색인 추가: {path}" if EI.add_folder(ini, path) else None, "색인을 추가하는 중…")

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "색인에 추가할 폴더", "")
        if d:
            self._add(d)

    def add_network(self):
        t, ok = QInputDialog.getText(self, "네트워크 경로 추가", "경로 (예: \\\\서버\\공유  또는  Z:\\):")
        if ok and t.strip():
            self._add(t.strip().strip('"'))

    def remove_selected(self):
        it = self.list.currentItem()
        p = it.data(Qt.UserRole) if it else None
        if not p:
            QMessageBox.information(self, "색인 제거", "제거할 '[폴더]' 항목을 선택하세요. (드라이브 볼륨은 Everything 설정에서 관리합니다)")
            return
        EI = self.EI
        self._run_change(lambda ini: f"폴더 색인 제거: {p}" if EI.remove_folder(ini, p) else None, "색인을 제거하는 중…")

    def install(self):
        self._set_busy(True, "Everything 설치 중… (관리자 권한 확인창이 뜨면 '예')")

        def work():
            try:
                ok = FS.install_everything(lambda t: self._done.emit(True, "…" + t))
            except Exception:
                ok = False
            self._done.emit(ok, "완료: Everything 설치됨" if ok else "!설치하지 못했습니다 (https://www.voidtools.com 에서 직접 설치할 수도 있습니다)")
        threading.Thread(target=work, daemon=True).start()


class EverythingGuard(QObject):
    """Everything 을 쓸 수 있는지 확인하고, 안 되면 안내한다.
      missing     → 설치할지 물음 (설치 / 나중에 / 설치 없이 사용(다시 묻지 않음))
      elevated    → 관리자 권한으로 떠 있어 접속이 막힘 → 서비스 설치 + 일반 권한으로 재시작할지 물음
      not_running → 조용히 실행
    준비가 끝나면 finished(True/False) 신호 (False = Everything 없이 느린 검색으로 진행)"""
    finished = Signal(bool)
    message = Signal(str)
    _finish_signal = Signal(bool)              # 작업 스레드 → GUI 스레드

    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.w = parent_widget
        self._busy = False
        self._asked = set()
        self.settings = load_json(SEARCH_FILE, {})
        self._finish_signal.connect(self._on_finish)

    def ensure(self):
        """상태 확인 후 필요하면 안내. 이미 준비됐으면 바로 finished(True)"""
        if self._busy:
            return
        st = FS.Searcher.status()
        if st == "ready":
            self.finished.emit(True)
            return
        if st == "not_running":
            self._run_bg(lambda: FS.start_everything(12), "Everything 을 시작하는 중…")
            return
        if st == "missing":
            if self.settings.get("everything") == "declined" or "missing" in self._asked:
                self.finished.emit(False)
                return
            self._asked.add("missing")
            box = QMessageBox(self.w)
            box.setWindowTitle("Everything 설치 안내")
            box.setText("파일 검색을 아주 빠르게 해 주는 Everything 이 설치돼 있지 않습니다.")
            box.setInformativeText("Everything 은 무료이고 매우 가벼운 프로그램이라, 설치하면 PC 전체 파일도 즉시 검색됩니다.\n"
                                   "설치하지 않아도 검색은 되지만 폴더를 직접 훑기 때문에 매우 느립니다.\n\n"
                                   "지금 설치할까요? (관리자 권한 확인창이 한두 번 뜹니다)")
            box.setWindowFlag(Qt.WindowStaysOnTopHint)
            yes = box.addButton("설치 (권장)", QMessageBox.AcceptRole)
            later = box.addButton("나중에", QMessageBox.RejectRole)
            never = box.addButton("설치 없이 사용", QMessageBox.DestructiveRole)
            box.exec()
            c = box.clickedButton()
            if c is yes:
                self._run_bg(lambda: FS.install_everything(self.message.emit), "Everything 설치 중… (완료될 때까지 잠시 기다려 주세요)")
            elif c is never:
                self.settings["everything"] = "declined"
                save_json(SEARCH_FILE, self.settings)
                self.finished.emit(False)
            else:
                self.finished.emit(False)
            return
        if st == "elevated":
            if "elevated" in self._asked:
                self.finished.emit(False)
                return
            self._asked.add("elevated")
            box = QMessageBox(self.w)
            box.setWindowTitle("Everything 연결 안내")
            box.setText("Everything 이 '관리자 권한'으로 실행 중이라 이 프로그램이 연결할 수 없습니다.")
            box.setInformativeText("Windows 보안상 일반 권한 프로그램은 관리자 권한 프로그램에 접속할 수 없습니다.\n"
                                   "Everything 의 '서비스'를 설치하고 '관리자 권한으로 실행'을 끄면 (관리자 권한 없이도 전체 색인 가능)\n"
                                   "바로 연결됩니다. 지금 자동으로 설정할까요? (관리자 권한 확인창이 뜹니다)")
            box.setWindowFlag(Qt.WindowStaysOnTopHint)
            yes = box.addButton("자동 설정", QMessageBox.AcceptRole)
            box.addButton("나중에", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is yes:
                self._run_bg(lambda: FS.repair_everything_access(self.message.emit), "Everything 설정 변경 중…")
            else:
                self.finished.emit(False)

    def _run_bg(self, fn, text):
        self._busy = True
        self.message.emit(text)
        ok_box = []

        def work():
            try:
                ok_box.append(bool(fn()))
            except Exception:
                ok_box.append(False)
            self._finish_signal.emit(ok_box[0])
        threading.Thread(target=work, daemon=True).start()

    def _on_finish(self, ok):
        self._busy = False
        ok = ok and FS.Searcher.status() == "ready"
        self.message.emit("Everything 준비 완료" if ok else "Everything 을 사용할 수 없어 느린 검색으로 진행합니다")
        self.finished.emit(ok)
