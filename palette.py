"""Ctrl+K 이동 팔레트: 열린 탭 / 북마크 / 빠른 이동 / 최근 방문 폴더를 한 목록에서 글자 몇 개로 골라 이동.
Enter = 지금 탭에서 열기, Ctrl+Enter(또는 Shift+Enter) = 새 탭, Esc = 닫기. 폴더 경로를 직접 붙여 넣어도 이동됨."""
import os

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

MAX_ROWS = 60


def build_entries(groups):
    """groups: [(종류 이름, [(제목, 경로)…])…] → 경로가 같은 것은 먼저 나온 종류 하나만 남긴 [(종류, 제목, 경로)…]"""
    seen, out = set(), []
    for kind, rows in groups:
        for title, path in rows:
            key = os.path.normcase(os.path.normpath(path)) if path else ""
            if not path or key in seen:
                continue
            seen.add(key)
            out.append((kind, title or os.path.basename(path.rstrip("\\/")) or path, path))
    return out


def filter_entries(entries, query):
    """공백으로 나눈 모든 조각이 제목+경로에 들어 있는 항목만 (대소문자 무시).
    제목이 첫 조각으로 시작하는 항목을 앞으로. 순서는 원래 목록(탭 → 북마크 → …)을 유지"""
    toks = [t for t in query.lower().split() if t]
    if not toks:
        return list(entries)[:MAX_ROWS]
    hits = [e for e in entries if all(t in (e[1] + " " + e[2]).lower() for t in toks)]
    hits.sort(key=lambda e: 0 if e[1].lower().startswith(toks[0]) else 1)      # 정렬은 안정적 → 나머지는 원래 순서
    return hits[:MAX_ROWS]


class Palette(QDialog):
    chosen = Signal(str, bool)                       # 경로, 새 탭 여부

    def __init__(self, entries, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setObjectName("palette")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.entries = entries
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        self.q = QLineEdit()
        self.q.setPlaceholderText("이동할 곳 입력   (탭 · 북마크 · 빠른 이동 · 최근 폴더, 경로 붙여넣기 가능)")
        self.q.textChanged.connect(self.refill)
        self.q.installEventFilter(self)
        self.list = QListWidget()
        self.list.setMinimumHeight(320)
        self.list.itemActivated.connect(lambda it: self.pick(False))
        self.list.itemClicked.connect(lambda it: self.pick(False))
        self.hint = QLabel("Enter 열기   Ctrl+Enter 새 탭   Esc 닫기")
        self.hint.setStyleSheet("color:#7f86aa; font-size:12px;")
        lay.addWidget(self.q)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.hint)
        self.refill()

    def refill(self):
        text = self.q.text().strip().strip('"')
        self.list.clear()
        if text and os.path.isdir(text):               # 경로를 직접 입력/붙여넣기 한 경우 맨 위에
            self._add("경로", os.path.basename(text.rstrip("\\/")) or text, text)
        for kind, title, path in filter_entries(self.entries, text):
            self._add(kind, title, path)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _add(self, kind, title, path):
        it = QListWidgetItem(f"[{kind}]  {title}    {path}")
        it.setData(Qt.UserRole, path)
        self.list.addItem(it)

    def pick(self, new_tab):
        it = self.list.currentItem()
        if it is None:
            return
        path = it.data(Qt.UserRole)
        self.accept()
        self.chosen.emit(path, new_tab)

    def eventFilter(self, obj, e):
        if obj is self.q and e.type() == QEvent.KeyPress:
            k = e.key()
            if k in (Qt.Key_Down, Qt.Key_Up):
                n = self.list.count()
                if n:
                    self.list.setCurrentRow((self.list.currentRow() + (1 if k == Qt.Key_Down else -1)) % n)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.pick(bool(e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)))
                return True
        return super().eventFilter(obj, e)

    def showEvent(self, e):
        super().showEvent(e)
        p = self.parentWidget()
        if p is not None:                              # 부모 창 위쪽 가운데에
            g = p.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.top() + 90)
        self.q.setFocus()
        self.q.selectAll()
