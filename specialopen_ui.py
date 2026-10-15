"""설정 → 파일 형식별 특수 열기: 확장자마다 열 프로그램을 지정 (예: .dxb → Duxbury).
규칙이 있는 형식은 Enter/더블클릭 때 specialopen.open_special 방식으로 열림 (프로그램이 없으면 일반 열기)."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

import specialopen as SO


def normalize_ext(text):
    """"dxb", " .DXB " → ".dxb" (비었거나 '.' 만 있으면 빈 글자)"""
    t = (text or "").strip().lower()
    if not t or t == ".":
        return ""
    return t if t.startswith(".") else "." + t


def rules_to_save(rows):
    """표의 [(확장자 글자, 프로그램 경로)…] → explorer.json 의 "special_open" 값.
    기본 규칙(SO.DEFAULT_RULES)과 같은 것은 저장하지 않고, 표에서 지운 기본 규칙은 ""(끔)으로 기록한다.
    빈 칸이거나 같은 확장자가 둘이면 뒤의 것이 이김"""
    cur = {}
    for ext, exe in rows:
        e, x = normalize_ext(ext), (exe or "").strip().strip('"')
        if e and x:
            cur[e] = x
    out = {e: x for e, x in cur.items() if SO.DEFAULT_RULES.get(e) != x}
    for e in SO.DEFAULT_RULES:
        if e not in cur:
            out[e] = ""
    return out


class SpecialOpenDialog(QDialog):
    def __init__(self, parent, custom):
        super().__init__(parent)
        self.setWindowTitle("파일 형식별 특수 열기")
        self.resize(760, 420)
        self.result_rules = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("확장자별로 열 프로그램을 지정합니다. 비워 두면 Windows 기본 프로그램으로 엽니다.\n"
                             "한글 경로를 못 읽는 프로그램(예: Duxbury)용으로, 경로를 붙여넣어 여는 방식을 씁니다."))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["확장자 (예: .dxb)", "프로그램 경로"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 160)
        self.table.verticalHeader().hide()
        lay.addWidget(self.table, 1)
        rules = dict(SO.DEFAULT_RULES)
        for e, x in (custom or {}).items():
            if isinstance(e, str) and isinstance(x, str):
                rules[e.lower()] = x
        for e, x in rules.items():
            if x:
                self.add_row(e, x)
        row = QHBoxLayout()
        add, browse, rm = QPushButton("추가"), QPushButton("프로그램 찾기…"), QPushButton("선택 줄 삭제")
        add.clicked.connect(lambda: self.add_row("", ""))
        browse.clicked.connect(self.browse)
        rm.clicked.connect(self.remove_row)
        ok, cancel = QPushButton("확인"), QPushButton("취소")
        ok.clicked.connect(self._ok)
        cancel.clicked.connect(self.reject)
        for b in (add, browse, rm):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

    def add_row(self, ext, exe):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(ext))
        self.table.setItem(r, 1, QTableWidgetItem(exe))
        self.table.setCurrentCell(r, 0)

    def rows(self):
        return [(self.table.item(r, 0).text() if self.table.item(r, 0) else "",
                 self.table.item(r, 1).text() if self.table.item(r, 1) else "") for r in range(self.table.rowCount())]

    def browse(self):
        r = self.table.currentRow()
        if r < 0:
            return
        cur = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
        p, _ = QFileDialog.getOpenFileName(self, "프로그램 선택", os.path.dirname(cur) if cur else "",
                                           "프로그램 (*.exe);;모든 파일 (*.*)")
        if p:
            self.table.setItem(r, 1, QTableWidgetItem(os.path.normpath(p)))

    def remove_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _ok(self):
        rows = self.rows()
        missing = [x for e, x in rows if normalize_ext(e) and x.strip() and not os.path.exists(x.strip().strip('"'))]
        if missing and QMessageBox.question(
                self, "프로그램을 찾을 수 없음",
                "다음 경로가 없습니다. 그래도 저장할까요? (없는 동안은 일반 열기로 열립니다)\n\n" + "\n".join(missing)
        ) != QMessageBox.Yes:
            return
        self.result_rules = rules_to_save(rows)
        self.accept()
