"""파일 검색 결과 화면 부품 (런처 '검색' 탭 / 탐색기 '하위 폴더 포함' 공용).
  ResultsTree     : 이름 / 위치 / 크기 / 수정한 날짜 목록 (검색 결과가 조금씩 채워짐)
  EverythingGuard : Everything 이 없거나 꺼져 있거나 관리자 권한으로 떠 있어 접속이 안 될 때의 안내·설치·복구
"""
import os
import threading
import time

from PySide6.QtCore import QFileInfo, QObject, Qt, Signal
from PySide6.QtWidgets import (QFileIconProvider, QHeaderView, QMessageBox, QTreeWidget, QTreeWidgetItem)

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
