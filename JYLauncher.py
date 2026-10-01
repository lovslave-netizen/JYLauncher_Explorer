"""JY Launcher - Big Picture 스타일 전체화면 런처 (런처 / 최근 / 고정 보관함)

실행:  pythonw JYLauncher.py      (콘솔 없이)   /   python JYLauncher.py
데이터: %APPDATA%/JYTools/ (launcher.json, vault.json, settings.json) - 경로 규칙은 jycommon.py 참고
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QFileInfo, QMimeData, QObject, QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QCursor, QDrag, QFont, QFontDatabase, QIcon, QKeyEvent, QPainter, QPen,
                           QPixmap)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QSystemTrayIcon
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup, QComboBox, QDialog, QFileDialog, QMessageBox,
    QFileIconProvider, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMenu, QPushButton, QScrollArea, QSizeGrip, QSizePolicy, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from jycommon import (DATA_DIR, FONT_FAMILY, FROZEN, INSTANCE_SUFFIX, LAUNCHER_FILE, SETTINGS_FILE, VAULT_FILE,
                      add_item_to_launcher, app_icon, create_app_shortcuts, file_mtime, pick_category, load_font, load_json, save_json)
import appsearch
import filesearch as FS
import search_ui as SUI
from jycommon import open_in_explorer
from updater import Updater
from version import __version__

RECENT_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"

FAV = "★ 즐겨찾기"
# 카드 크기 프리셋: (카드 너비, 카드 높이, 간격, 아이콘 px, 글자 px, 이름 표시)
SIZES = {"큰 아이콘": (116, 104, 12, 40, 12, True), "작은 아이콘": (50, 50, 8, 30, 0, False)}
DEFAULT_SIZE = "큰 아이콘"
MARGIN = 8
CARD_W, CARD_H, GAP, ICON_SIZE, NAME_PX, SHOW_NAME = SIZES[DEFAULT_SIZE]
MIME_ITEM = "application/x-jy-item"
MIME_SEC = "application/x-jy-sec"


def set_size(name):
    global CARD_W, CARD_H, GAP, ICON_SIZE, NAME_PX, SHOW_NAME
    CARD_W, CARD_H, GAP, ICON_SIZE, NAME_PX, SHOW_NAME = SIZES.get(name, SIZES[DEFAULT_SIZE])

QSS = """
* { font-family: 'Noto Sans KR', 'Malgun Gothic'; color: #e8eaf6; }
QWidget#root { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0d0f1a, stop:1 #191c33); }
QFrame#sidebar { background: rgba(255,255,255,0.04); border-radius: 20px; }
QLabel#logo { font-size: 22px; font-weight: 800; color: #aab4ff; letter-spacing: 1px; }
QLabel#clock { font-size: 20px; font-weight: 600; color: #c9cdea; }
QLabel#pageTitle { font-size: 26px; font-weight: 700; }
QLabel#dim, QLabel#hint { color: #7f86aa; font-size: 12px; }
QLabel#toast { color: #9fe8c5; font-size: 13px; font-weight: 600; }

QLineEdit#search { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px; padding: 9px 18px; font-size: 15px; min-width: 340px; selection-background-color: #7c8cff; }
QLineEdit#search:focus { border: 1px solid #7c8cff; background: rgba(124,140,255,0.10); }

QPushButton { background: rgba(255,255,255,0.07); border: none; border-radius: 12px; padding: 9px 16px; font-size: 13px; }
QPushButton:hover { background: rgba(255,255,255,0.14); }
QPushButton#nav { text-align: left; padding: 14px 18px; font-size: 15px; font-weight: 600; background: transparent; }
QPushButton#nav:hover { background: rgba(255,255,255,0.07); }
QPushButton#nav:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5b6cff, stop:1 #8a63ff); }
QPushButton#toggle:checked { background: rgba(124,232,190,0.22); color: #9fe8c5; }
QPushButton#wc, QPushButton#close { background: transparent; border-radius: 8px; padding: 0; }
QPushButton#wc:hover { background: rgba(255,255,255,0.16); }
QPushButton#close:hover { background: #e5484d; }

QPushButton#sec { text-align: left; background: transparent; font-size: 15px; font-weight: 700;
    color: #aab4ff; padding: 8px 6px; border-radius: 10px; }
QPushButton#sec:hover { background: rgba(255,255,255,0.05); }
QPushButton#sec[sel="true"] { background: rgba(124,140,255,0.22); }

QFrame#card { background: rgba(255,255,255,0.055); border: 2px solid transparent; border-radius: 14px; }
QFrame#card:hover { background: rgba(255,255,255,0.11); }
QFrame#card[sel="true"] { background: rgba(124,140,255,0.24); border: 2px solid #8b98ff; }
QFrame#card QLabel { background: transparent; }
QFrame#card[drop="before"] { border-left: 4px solid #8b98ff; }
QFrame#card[drop="after"] { border-right: 4px solid #8b98ff; }
QFrame#card[drop="group"] { border: 2px dashed #ffd166; background: rgba(255,209,102,0.14); }
QPushButton#sec[drop="true"] { background: rgba(255,209,102,0.2); }

QTreeWidget { background: rgba(255,255,255,0.035); border: none; border-radius: 16px; padding: 8px; outline: 0; font-size: 14px; }
QTreeWidget::item { padding: 7px 4px; border-radius: 9px; }
QTreeWidget::item:hover { background: rgba(255,255,255,0.07); }
QTreeWidget::item:selected { background: rgba(124,140,255,0.28); color: white; }

QHeaderView { background: transparent; border: none; }
QHeaderView::section { background: transparent; border: none; color: #8a90b0; padding: 6px 8px; font-size: 12px; }
QLineEdit#ext { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.08); border-radius: 13px; padding: 6px 12px; font-size: 13px; selection-background-color: #7c8cff; }
QLineEdit#ext:focus { border: 1px solid #7c8cff; }
QPushButton#chip { background: rgba(255,255,255,0.07); border: none; border-radius: 13px; padding: 6px 14px; font-size: 13px; }
QPushButton#chip:hover { background: rgba(255,255,255,0.15); }
QPushButton#chip:checked { background: #5b6cff; color: white; }
QComboBox { background: rgba(255,255,255,0.07); border: none; border-radius: 12px; padding: 8px 14px; min-width: 110px; }
QComboBox QAbstractItemView { background: #1e2140; border: 1px solid #333863; selection-background-color: #5b6cff; outline: 0; }
QComboBox::drop-down { border: none; width: 22px; }

QDialog, QMessageBox, QInputDialog { background: #1e2140; }
QDialog QLabel, QMessageBox QLabel { color: #e8eaf6; background: transparent; }
QDialog QLineEdit, QInputDialog QLineEdit { background: rgba(255,255,255,0.10); color: #ffffff; border: 1px solid #4a5090;
    border-radius: 8px; padding: 6px 10px; selection-background-color: #5b6cff; }
QDialog QComboBox { background: rgba(255,255,255,0.10); color: #ffffff; border: 1px solid #4a5090; }
QDialog QPushButton { min-width: 72px; }
QPushButton[kb="true"], QComboBox[kb="true"] { border: 2px solid #aab4ff; background: rgba(124,140,255,0.28); }
QToolTip { background: #1e2140; color: #e8eaf6; border: 1px solid #4a5090; padding: 4px 8px; }
QDialog#folderpop { background: #191c33; border: 1px solid #4a5090; border-radius: 18px; }
QLabel#poptitle { font-size: 20px; font-weight: 700; color: #ffffff; }

QMenu { background: #1e2140; border: 1px solid #333863; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 24px; border-radius: 6px; }
QMenu::item:selected { background: #5b6cff; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 14px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.22); border-radius: 5px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: rgba(139,152,255,0.7); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

# ───────────────────────── 유틸 ─────────────────────────
_provider = QFileIconProvider()
_pix_cache = {}


def file_icon(path):
    return _provider.icon(QFileInfo(path))


def icon_pixmap(path, size):
    key = (path, size)
    if key not in _pix_cache:
        _pix_cache[key] = file_icon(path).pixmap(QSize(size, size))
    return _pix_cache[key]


def is_folder(item):
    return item.get("type") == "folder"


def flat_apps(items):
    """카테고리 안의 항목들을 (폴더 안까지 풀어서) 앱 목록으로 반환"""
    for i in items:
        if is_folder(i):
            yield from i.get("items", [])
        else:
            yield i


def folder_pixmap(item, size):
    """폴더 카드 아이콘: 안에 든 앱 아이콘 최대 4개를 2x2 로 미리보기 (시작 메뉴 폴더와 같은 모양)"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.setBrush(QColor(255, 255, 255, 38))
    r = max(4, size // 5)
    p.drawRoundedRect(0, 0, size - 1, size - 1, r, r)
    gap = 2
    cell = (size - 3 * gap - 2) // 2
    for n, child in enumerate(item.get("items", [])[:4]):
        x = 1 + gap + (n % 2) * (cell + gap)
        y = 1 + gap + (n // 2) * (cell + gap)
        p.drawPixmap(x, y, icon_pixmap(child["path"], cell))
    p.end()
    return pm


def reveal(path):
    if os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


def default_launcher():
    cands = {
        "업무": [
            ("Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            ("Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            ("메모장", r"C:\Windows\System32\notepad.exe"),
            ("계산기", r"C:\Windows\System32\calc.exe"),
        ],
        "게임": [("Steam", r"C:\Program Files (x86)\Steam\steam.exe")],
        "도구": [
            ("탐색기", r"C:\Windows\explorer.exe"),
            ("작업 관리자", r"C:\Windows\System32\Taskmgr.exe"),
            ("명령 프롬프트", r"C:\Windows\System32\cmd.exe"),
        ],
    }
    out = {}
    for cat, apps in cands.items():
        out[cat] = [{"name": n, "path": p, "fav": n in ("Chrome", "메모장")}
                    for n, p in apps if os.path.exists(p)]
    return out


class Watcher(QObject):
    finished = Signal()

    def watch(self, proc):
        def run():
            proc.wait()
            self.finished.emit()
        threading.Thread(target=run, daemon=True).start()


# ───────────────────────── 런처 페이지 ─────────────────────────
def _repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


class Card(QFrame):
    clicked = Signal(object)
    menu = Signal(object, object)
    dragRequested = Signal(object)
    dropped = Signal(object, str)      # 대상 카드, 위치("before" / "after" / "group")

    def __init__(self, item, category):
        super().__init__()
        self.item, self.category = item, category
        self.draggable = False
        self._press = None
        self.setObjectName("card")
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        folder = is_folder(item)
        missing = (not folder and not os.path.exists(item["path"])
                   and not item["path"].startswith(("http", "shell:")))
        title = item["name"] + (f"  ({len(item.get('items', []))})" if folder else "")
        lay = QVBoxLayout(self)
        ico = QLabel()
        ico.setAlignment(Qt.AlignCenter)
        ico.setPixmap(folder_pixmap(item, ICON_SIZE) if folder else icon_pixmap(item["path"], ICON_SIZE))
        if SHOW_NAME:
            lay.setContentsMargins(6, 10, 6, 8)
            lay.setSpacing(6)
            name = QLabel(("! " if missing else "") + title)
            name.setAlignment(Qt.AlignCenter)
            name.setWordWrap(True)
            name.setStyleSheet(f"font-size:{NAME_PX}px; font-weight:600;" + ("color:#ff9a9a;" if missing else ""))
            lay.addWidget(ico)
            lay.addWidget(name, 1)
        else:  # 아이콘만: 이름은 마우스를 올리면 툴팁으로
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(ico)
            self.setToolTip(("! " if missing else "") + title)
            if missing:
                ico.setStyleSheet("background: rgba(255,90,90,0.28); border-radius: 10px;")
        if item.get("fav") and category != FAV:
            star = QLabel("★", self)
            star.setStyleSheet(f"color:#ffd166; font-size:{14 if SHOW_NAME else 9}px; background:transparent;")
            star.move(CARD_W - (22 if SHOW_NAME else 13), 5 if SHOW_NAME else 1)
        self.setProperty("sel", False)
        self.setProperty("drop", "")

    def set_selected(self, v):
        self.setProperty("sel", v)
        _repolish(self)

    # 클릭 / 드래그 시작
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
        e.accept()

    def mouseMoveEvent(self, e):
        if self.draggable and self._press is not None and e.buttons() & Qt.LeftButton \
                and (e.position().toPoint() - self._press).manhattanLength() > 10:
            self._press = None
            self.dragRequested.emit(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._press is not None and self.rect().contains(e.position().toPoint()):
            self._press = None
            self.clicked.emit(self)

    def contextMenuEvent(self, e):
        self.menu.emit(self, e.globalPos())
        e.accept()

    # 드롭 대상: 왼쪽 끝=앞에 끼우기, 오른쪽 끝=뒤에 끼우기, 가운데=새 그룹으로 묶기
    def _zone(self, e):
        x = e.position().x() / max(self.width(), 1)
        return "before" if x < 0.25 else "after" if x > 0.75 else "group"

    def _mark(self, zone):
        if self.property("drop") != zone:
            self.setProperty("drop", zone)
            _repolish(self)

    def dragEnterEvent(self, e):
        if self.draggable and e.mimeData().hasFormat(MIME_ITEM):
            e.acceptProposedAction()
            self._mark(self._zone(e))
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self.draggable and e.mimeData().hasFormat(MIME_ITEM):
            e.acceptProposedAction()
            self._mark(self._zone(e))

    def dragLeaveEvent(self, e):
        self._mark("")

    def dropEvent(self, e):
        zone = self._zone(e)
        self._mark("")
        e.acceptProposedAction()
        self.dropped.emit(self, zone)


class SecButton(QPushButton):
    """카테고리(그룹) 헤더: 드래그로 그룹 순서 변경, 카드를 여기에 놓으면 그 그룹 끝으로 이동"""
    dragRequested = Signal(object)
    dropped = Signal(object, str)      # 이 헤더, 드래그 종류("item" / "sec")

    def __init__(self, name):
        super().__init__()
        self.sec_name = name
        self.draggable = False
        self._press = None
        self.setAcceptDrops(True)
        self.setProperty("drop", "")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.draggable and self._press is not None and e.buttons() & Qt.LeftButton \
                and (e.position().toPoint() - self._press).manhattanLength() > 10:
            self._press = None
            self.dragRequested.emit(self)
            self.setDown(False)
            return
        super().mouseMoveEvent(e)

    def _ok(self, e):
        m = e.mimeData()
        return self.draggable and (m.hasFormat(MIME_ITEM) or m.hasFormat(MIME_SEC))

    def dragEnterEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()
            self.setProperty("drop", "true")
            _repolish(self)
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.setProperty("drop", "")
        _repolish(self)

    def dropEvent(self, e):
        self.setProperty("drop", "")
        _repolish(self)
        e.acceptProposedAction()
        self.dropped.emit(self, "sec" if e.mimeData().hasFormat(MIME_SEC) else "item")


class Section:
    def __init__(self, name, header, body, grid, cards):
        self.name, self.header, self.body, self.grid, self.cards = name, header, body, grid, cards


def _index_of(lst, item):
    """== 가 아니라 같은 객체(is)로 위치를 찾는다 (이름·경로가 같은 항목이 있어도 헷갈리지 않게)"""
    return next((n for n, x in enumerate(lst) if x is item), -1)


class FolderPopup(QDialog):
    """폴더 카드를 열었을 때 뜨는 창: 안에 묶인 앱들을 카드로 보여줌 (윈도우 시작 메뉴 폴더처럼)"""

    def __init__(self, page, folder):
        super().__init__(page.window())
        self.page, self.folder = page, folder
        self.setObjectName("folderpop")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.cards, self.cur, self.cols = [], -1, 1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 14)
        lay.setSpacing(12)
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("poptitle")
        close = QPushButton("닫기")
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(self.reject)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(close)
        lay.addLayout(head)
        self.grid = QGridLayout()
        self.grid.setSpacing(GAP)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lay.addLayout(self.grid)
        hint = QLabel("Enter 실행   ←↑↓→ 이동   우클릭 = 이름 변경 / 폴더에서 꺼내기 / 삭제   Esc 닫기")
        hint.setObjectName("hint")
        lay.addWidget(hint)
        self.fill()

    def fill(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        items = self.folder["items"]
        self.title.setText(f"{self.folder['name']}   {len(items)}")
        self.cols = max(1, min(6 if SHOW_NAME else 9, len(items)))
        self.cards = []
        for n, it in enumerate(items):
            c = Card(it, self.folder["name"])
            c.clicked.connect(self.run)
            c.menu.connect(self.menu)
            self.grid.addWidget(c, n // self.cols, n % self.cols)
            self.cards.append(c)
        self.cur = -1
        self.select(0)
        self.setMinimumWidth(max(360, self.cols * (CARD_W + GAP) + 60))
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            self.move(parent.geometry().center() - self.rect().center())

    def select(self, i):
        if not self.cards:
            return
        i = max(0, min(len(self.cards) - 1, i))
        if 0 <= self.cur < len(self.cards):
            self.cards[self.cur].set_selected(False)
        self.cur = i
        self.cards[i].set_selected(True)

    def run(self, card):
        self.accept()
        self.page.activated.emit(card.item["path"])

    def menu(self, card, pos):
        it = card.item
        m = QMenu(self)
        m.addAction("실행", lambda: self.run(card))
        m.addAction("이름 변경…", lambda: self._rename(it))
        m.addAction("폴더에서 꺼내기", lambda: self._eject(it))
        m.addAction("삭제", lambda: self._delete(it))
        m.exec(pos)

    def _changed(self):
        self.page.save()
        if not self.folder["items"]:          # 비면 폴더도 함께 사라짐
            self.page.drop_item(self.folder)
            self.page.save()
            self.accept()
        else:
            self.fill()
        self.page.rebuild()

    def _rename(self, it):
        name, ok = QInputDialog.getText(self, "이름 변경", "이름:", text=it["name"])
        if ok and name.strip():
            it["name"] = name.strip()
            self._changed()

    def _eject(self, it):
        self.page.eject_from_folder(self.folder, it)
        self._changed()

    def _delete(self, it):
        n = _index_of(self.folder["items"], it)
        if n >= 0:
            del self.folder["items"][n]
        self._changed()

    def keyPressEvent(self, e):
        k = e.key()
        step = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -self.cols, Qt.Key_Down: self.cols}.get(k)
        if step is not None:
            self.select(self.cur + step)
        elif k in (Qt.Key_Return, Qt.Key_Enter) and 0 <= self.cur < len(self.cards):
            self.run(self.cards[self.cur])
        else:
            super().keyPressEvent(e)          # Esc = 닫기


class LauncherPage(QScrollArea):
    activated = Signal(str)
    pinRequested = Signal(dict)
    toast = Signal(str)

    def __init__(self, data, settings):
        super().__init__()
        self.data, self.settings = data, settings
        self.setWidgetResizable(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.sections, self.rows = [], []
        self.filter, self.current, self._cols, self._want_col = "", None, 0, 0
        self.inner = QWidget()
        self.vbox = QVBoxLayout(self.inner)
        self.vbox.setContentsMargins(MARGIN, 0, 12, 24)
        self.vbox.setSpacing(6)
        self.setWidget(self.inner)
        self.mtime = file_mtime(LAUNCHER_FILE)
        self.rebuild()

    # ---- 구성 ----
    def save(self):
        save_json(LAUNCHER_FILE, self.data)
        self.mtime = file_mtime(LAUNCHER_FILE)

    def cols(self):
        avail = self.viewport().width() - MARGIN - 12
        return max(1, (avail + GAP) // (CARD_W + GAP))

    def set_filter(self, text):
        self.filter = text.strip().lower()
        self.rebuild()

    def rebuild(self):
        keep = self.current.item if isinstance(self.current, Card) else None
        scroll = self.verticalScrollBar().value()
        self.current = None
        while self.vbox.count():
            it = self.vbox.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.sections = []
        f = self.filter
        match = lambda i: not f or f in i["name"].lower()
        groups = []
        favs = [(c, i) for c, items in self.data.items() for i in flat_apps(items) if i.get("fav")]
        if favs and not f:
            groups.append((FAV, favs))
        for cat, items in self.data.items():
            # 검색 중에는 폴더 안의 앱까지 풀어서 찾고, 평소에는 폴더 카드를 그대로 보여준다
            sel = [(cat, i) for i in (flat_apps(items) if f else items) if match(i)]
            if sel or not f:
                groups.append((cat, sel))
        for name, pairs in groups:
            header = SecButton(name)
            header.draggable = name != FAV and not f
            header.dragRequested.connect(self.start_drag)
            header.dropped.connect(self.on_sec_drop)
            header.setObjectName("sec")
            header.setCursor(Qt.PointingHandCursor)
            header.setFocusPolicy(Qt.NoFocus)
            header.setContextMenuPolicy(Qt.CustomContextMenu)
            header.setProperty("sel", False)
            body = QWidget()
            grid = QGridLayout(body)
            grid.setContentsMargins(0, 4, 0, 10)
            grid.setSpacing(GAP)
            grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            cards = []
            for cat, item in pairs:
                c = Card(item, name)
                c.draggable = name != FAV and not f      # 즐겨찾기 묶음/검색 중에는 이동 불가
                c.dragRequested.connect(self.start_drag)
                c.dropped.connect(self.on_card_drop)
                c.clicked.connect(lambda card: self.activate(card))
                c.menu.connect(self.card_menu)
                cards.append(c)
            sec = Section(name, header, body, grid, cards)
            header.clicked.connect(lambda _=False, s=sec: self.toggle(s))
            header.customContextMenuRequested.connect(lambda _p, s=sec: self.header_menu(s))
            self.sections.append(sec)
            self.vbox.addWidget(header)
            self.vbox.addWidget(body)
            self._update_header(sec)
        self.vbox.addStretch(1)
        if not self.sections:
            empty = QLabel("검색 결과가 없습니다" if f else "우클릭 → 앱 추가")
            empty.setObjectName("dim")
            self.vbox.insertWidget(0, empty)
        self._cols = self.cols()
        self._layout_rows()
        target = None
        if keep is not None:
            target = next((c for s in self.sections for c in s.cards if c.item is keep), None)
        if target is None:
            first = next((s.cards[0] for s in self.sections if s.cards and not self._collapsed(s)), None)
            target = first
        if target:
            self.select(target, scroll=False)
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(scroll))

    def _collapsed(self, sec):
        return not self.filter and sec.name in self.settings.get("collapsed", [])

    def _update_header(self, sec):
        arrow = "+" if self._collapsed(sec) else "−"
        sec.header.setText(f"{arrow}  {sec.name}   {len(sec.cards)}")

    def toggle(self, sec):
        if self.filter:
            return
        col = self.settings.setdefault("collapsed", [])
        col.remove(sec.name) if sec.name in col else col.append(sec.name)
        save_json(SETTINGS_FILE, self.settings)
        self._update_header(sec)
        self._layout_rows()
        self.select(sec.header, scroll=False)

    def _layout_rows(self):
        cols = self._cols = self.cols()
        self.rows = []
        for s in self.sections:
            self.rows.append([s.header])
            if self._collapsed(s):
                s.body.hide()
                continue
            s.body.show()
            while s.grid.count():
                s.grid.takeAt(0)
            for i, c in enumerate(s.cards):
                s.grid.addWidget(c, i // cols, i % cols)
                c.show()
            for k in range(0, len(s.cards), cols):
                self.rows.append(s.cards[k:k + cols])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.rows and self.cols() != self._cols:
            cur = self.current
            self._layout_rows()
            if cur is not None:
                self.select(cur, scroll=False)

    # ---- 선택/이동 ----
    def select(self, w, scroll=True):
        if self.current is not None:
            try:
                self.current.setProperty("sel", False)
                self.current.style().unpolish(self.current)
                self.current.style().polish(self.current)
            except RuntimeError:
                pass
        self.current = w
        w.setProperty("sel", True)
        w.style().unpolish(w)
        w.style().polish(w)
        if scroll:
            self.ensureWidgetVisible(w, 40, 70)

    def _locate(self):
        for r, row in enumerate(self.rows):
            for c, w in enumerate(row):
                if w is self.current:
                    return r, c
        return None

    def move(self, dr=0, dc=0):
        if not self.rows:
            return
        pos = self._locate()
        if pos is None:
            self.select(self.rows[min(1, len(self.rows) - 1)][0])
            return
        r, c = pos
        if dc:
            c += dc
            if c < 0:
                if r == 0:
                    return
                r -= 1
                c = len(self.rows[r]) - 1
            elif c >= len(self.rows[r]):
                if r == len(self.rows) - 1:
                    return
                r, c = r + 1, 0
            self._want_col = c
        else:
            r = max(0, min(len(self.rows) - 1, r + dr))
            c = min(self._want_col, len(self.rows[r]) - 1)
        self.select(self.rows[r][c])

    def at_top(self):
        """선택이 맨 윗줄에 있거나 아직 선택이 없음 → ↑ 를 누르면 위쪽 버튼줄로 올라갈 수 있음"""
        return not self.rows or self.current is None or self.current in self.rows[0]

    def handle_key(self, e):
        k = e.key()
        moves = {Qt.Key_Up: (-1, 0), Qt.Key_Down: (1, 0), Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1),
                 Qt.Key_PageUp: (-3, 0), Qt.Key_PageDown: (3, 0)}
        if k in moves:
            self.move(*moves[k])
        elif k == Qt.Key_Home and self.rows:
            self._want_col = 0
            self.select(self.rows[0][0])
        elif k == Qt.Key_End and self.rows:
            self.select(self.rows[-1][0])
        elif k in (Qt.Key_Return, Qt.Key_Enter) and self.current is not None:
            self.activate(self.current)
        elif k == Qt.Key_Space and self.current is not None:   # 스페이스: 그룹 열기/닫기 (+ / −)
            sec = next((s for s in self.sections if s.header is self.current or self.current in s.cards), None)
            if sec is not None:
                self.toggle(sec)
        elif k == Qt.Key_Delete and isinstance(self.current, Card):
            self.remove(self.current)
        else:
            return False
        return True

    def activate(self, w):
        if isinstance(w, Card):
            self.select(w, scroll=False)
            if is_folder(w.item):
                self.open_folder(w.item)
            else:
                self.activated.emit(w.item["path"])
        else:
            sec = next(s for s in self.sections if s.header is w)
            self.toggle(sec)

    # ---- 드래그로 이동 / 그룹 묶기 ----
    _payload = None

    def start_drag(self, w):
        if self.filter:
            return
        is_card = isinstance(w, Card)
        self._payload = ("item", w.item) if is_card else ("sec", w.sec_name)
        drag = QDrag(w)
        mime = QMimeData()
        mime.setData(MIME_ITEM if is_card else MIME_SEC, b"1")
        drag.setMimeData(mime)
        pm = w.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(pm.rect().center())
        drag.exec(Qt.MoveAction)
        self._payload = None

    def on_card_drop(self, target, zone):
        p = self._payload
        if not p or p[0] != "item" or p[1] is target.item:
            return
        item, tgt, cat = p[1], target.item, target.category
        QTimer.singleShot(0, lambda: self._card_drop(item, tgt, cat, zone))  # 드래그가 끝난 뒤 갱신

    def _list_of(self, item):
        """항목이 들어 있는 목록(카테고리 목록 또는 폴더의 items). 없으면 None"""
        for lst in self.data.values():
            if _index_of(lst, item) >= 0:
                return lst
            for f in lst:
                if is_folder(f) and _index_of(f["items"], item) >= 0:
                    return f["items"]
        return None

    def drop_item(self, item):
        lst = self._list_of(item)
        if lst is not None:
            del lst[_index_of(lst, item)]

    def eject_from_folder(self, folder, item):
        """폴더 안의 앱을 폴더 바로 뒤(같은 카테고리)로 꺼낸다"""
        lst = self._list_of(folder)
        n = _index_of(folder["items"], item)
        if lst is None or n < 0:
            return
        del folder["items"][n]
        lst.insert(_index_of(lst, folder) + 1, item)

    def open_folder(self, folder):
        FolderPopup(self, folder).exec()

    def _card_drop(self, item, tgt, cat, zone):
        src = self._list_of(item)
        dst = self.data.get(cat)
        if src is None or dst is None or _index_of(dst, tgt) < 0:
            return
        if zone == "group" and not is_folder(item):
            if is_folder(tgt):                     # 폴더 위에 놓으면 그 폴더 안으로
                src.pop(_index_of(src, item))
                tgt["items"].append(item)
            else:                                  # 앱 위에 놓으면 둘을 새 폴더로 묶음
                name, ok = QInputDialog.getText(self, "폴더로 묶기", "새 폴더 이름:", text="새 폴더")
                if not ok or not name.strip():
                    return
                src.pop(_index_of(src, item))
                dst[_index_of(dst, tgt)] = {"type": "folder", "name": name.strip(), "items": [tgt, item]}
        else:                                      # 가장자리 = 그 자리에 끼우기
            src.pop(_index_of(src, item))
            dst.insert(_index_of(dst, tgt) + (0 if zone == "before" else 1), item)
        self.save()
        self.rebuild()

    def on_sec_drop(self, header, kind):
        p, target = self._payload, header.sec_name
        if not p or p[0] != kind:
            return
        payload = p[1]
        QTimer.singleShot(0, lambda: self._sec_drop(kind, payload, target))

    def _sec_drop(self, kind, payload, target):
        if kind == "item":
            src = self._list_of(payload)
            dst = self.data.get(target)
            if src is None or dst is None:
                return
            src.pop(_index_of(src, payload))
            dst.append(payload)            # 그룹 맨 끝으로
        else:
            if payload == target or payload not in self.data or target not in self.data:
                return
            names = [k for k in self.data if k != payload]
            names.insert(names.index(target), payload)   # 대상 그룹 앞으로
            self.data = {k: self.data[k] for k in names}
        self.save()
        self.rebuild()

    # ---- 편집 ----
    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("앱 추가…", self.add_app)
        m.addAction("새 카테고리…", self.add_category)
        m.exec(e.globalPos())

    def card_menu(self, card, pos):
        self.select(card, scroll=False)
        it = card.item
        m = QMenu(self)
        if is_folder(it):
            m.addAction("열기", lambda: self.activate(card))
            m.addAction("이름 변경…", lambda: self.rename(it))
            m.addAction("폴더 풀기 (앱들을 밖으로)", lambda: self.unfold(it))
            m.addAction("폴더와 안의 앱 삭제", lambda: self.remove_folder(it))
            m.exec(pos)
            return
        m.addAction("실행", lambda: self.activate(card))
        m.addAction("즐겨찾기 해제" if it.get("fav") else "즐겨찾기 추가", lambda: self.toggle_fav(it))
        m.addAction("보관함에 고정", lambda: self.pinRequested.emit(it))
        m.addAction("파일 위치 열기", lambda: reveal(it["path"]))
        m.addSeparator()
        m.addAction("이름 변경…", lambda: self.rename(it))
        m.addAction("삭제", lambda: self.remove(card))
        m.exec(pos)

    def header_menu(self, sec):
        if sec.name == FAV:
            return
        m = QMenu(self)
        m.addAction("카테고리 이름 변경…", lambda: self.rename_category(sec.name))
        m.addAction("카테고리 삭제", lambda: self.delete_category(sec.name))
        m.addAction("새 카테고리…", self.add_category)
        m.exec(QCursor.pos())

    def toggle_fav(self, it):
        it["fav"] = not it.get("fav")
        self.save()
        self.rebuild()

    def rename(self, it):
        name, ok = QInputDialog.getText(self, "이름 변경", "이름:", text=it["name"])
        if ok and name.strip():
            it["name"] = name.strip()
            self.save()
            self.rebuild()

    def remove(self, card):
        if is_folder(card.item):
            self.remove_folder(card.item)
            return
        self.drop_item(card.item)
        self.save()
        self.rebuild()

    def unfold(self, folder):
        lst = self._list_of(folder)
        if lst is None:
            return
        n = _index_of(lst, folder)
        lst[n:n + 1] = folder["items"]
        self.save()
        self.rebuild()

    def remove_folder(self, folder):
        cnt = len(folder["items"])
        if cnt and QMessageBox.question(
                self, "폴더 삭제", f"'{folder['name']}' 폴더와 안의 앱 {cnt}개를 런처에서 지울까요?\n"
                "(프로그램 파일 자체는 지워지지 않습니다)") != QMessageBox.Yes:
            return
        self.drop_item(folder)
        self.save()
        self.rebuild()

    def add_category(self):
        name, ok = QInputDialog.getText(self, "새 카테고리", "카테고리 이름:")
        if ok and name.strip() and name.strip() not in self.data and name.strip() != FAV:
            self.data[name.strip()] = []
            self.save()
            self.rebuild()

    def rename_category(self, old):
        new, ok = QInputDialog.getText(self, "카테고리 이름 변경", "이름:", text=old)
        if ok and new.strip() and new.strip() not in self.data:
            self.data = {(new.strip() if k == old else k): v for k, v in self.data.items()}
            self.save()
            self.rebuild()

    def delete_category(self, name):
        self.data.pop(name, None)
        self.save()
        self.rebuild()

    def add_app(self):
        path, _ = QFileDialog.getOpenFileName(self, "앱/파일 선택", "", "모든 파일 (*.*)")
        if not path:
            return
        path = os.path.normpath(path)
        cat = pick_category(self, self.data.keys(), exclude=(FAV,))
        if not cat:
            return
        self.data.setdefault(cat, []).append({"name": Path(path).stem, "path": path})
        self.save()
        self.rebuild()


# ───────────────────────── 트리 페이지 (최근 / 보관함) ─────────────────────────
class VaultTree(QTreeWidget):
    changed = Signal()
    filesDropped = Signal(list, object)

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls() and e.source() is not self:
            it = self.itemAt(e.position().toPoint())
            if it is not None and it.data(0, Qt.UserRole + 1) != "folder":
                it = it.parent()
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            self.filesDropped.emit(paths, it)
            e.acceptProposedAction()
            return
        super().dropEvent(e)
        self.changed.emit()


def make_tree(cls=QTreeWidget):
    t = cls()
    t.setHeaderHidden(True)
    t.setColumnCount(2)
    t.setRootIsDecorated(False)
    t.setIndentation(26)
    t.setIconSize(QSize(26, 26))
    t.setUniformRowHeights(True)
    t.setFocusPolicy(Qt.NoFocus)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setExpandsOnDoubleClick(False)
    return t


def forward_tree_key(tree, e):
    k = e.key()
    if k in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End):
        if tree.currentItem() is None and tree.topLevelItemCount():
            tree.setCurrentItem(tree.topLevelItem(0))
        else:
            QApplication.sendEvent(tree, QKeyEvent(e.type(), k, e.modifiers()))
        cur = tree.currentItem()
        if cur:
            tree.scrollToItem(cur)
        return True
    return False


class RecentPage(QWidget):
    activated = Signal(str)

    def __init__(self):
        super().__init__()
        self.filter = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = make_tree()
        self.tree.setColumnWidth(0, 520)
        self.tree.itemClicked.connect(lambda it, _c: self.activated.emit(it.data(0, Qt.UserRole)))
        lay.addWidget(self.tree)
        self.entries = []

    def refresh(self):
        try:
            files = [p for p in RECENT_DIR.glob("*.lnk")]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            self.entries = [(p, p.stat().st_mtime) for p in files[:50]]
        except OSError:
            self.entries = []
        self.apply()

    def set_filter(self, text):
        self.filter = text.strip().lower()
        self.apply()

    def apply(self):
        self.tree.clear()
        for p, mt in self.entries:
            if self.filter and self.filter not in p.stem.lower():
                continue
            it = QTreeWidgetItem([p.stem, time.strftime("%m-%d  %H:%M", time.localtime(mt))])
            it.setIcon(0, file_icon(str(p)))
            it.setData(0, Qt.UserRole, str(p))
            it.setForeground(1, QColor("#7f86aa"))
            self.tree.addTopLevelItem(it)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def handle_key(self, e):
        if forward_tree_key(self.tree, e):
            return True
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.tree.currentItem():
            self.activated.emit(self.tree.currentItem().data(0, Qt.UserRole))
            return True
        return False


SORTS = ["사용자 지정", "파일명", "확장자", "수정 날짜", "최근 사용"]


class VaultPage(QWidget):
    activated = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.root = load_json(VAULT_FILE, {"children": []})
        self.filter, self.sort, self.nodes = "", settings.get("sort", SORTS[0]), []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = make_tree(VaultTree)
        self.tree.setColumnWidth(0, 520)
        self.tree.itemClicked.connect(self.on_click)
        self.tree.changed.connect(self.on_dropped)
        self.tree.filesDropped.connect(self.on_files)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.menu)
        lay.addWidget(self.tree)
        self.render()

    # ---- 모델 ----
    def save(self):
        save_json(VAULT_FILE, self.root)

    def sort_key(self):
        s = self.sort
        mt = lambda n: os.path.getmtime(n["path"]) if os.path.exists(n["path"]) else 0
        ext = lambda n: os.path.splitext(n["path"])[1].lower()
        return {"파일명": lambda n: n["name"].lower(),
                "확장자": lambda n: (ext(n), n["name"].lower()),
                "수정 날짜": lambda n: -mt(n),
                "최근 사용": lambda n: -n.get("last", 0)}.get(s)

    def is_custom(self):
        return self.sort == "사용자 지정" and not self.filter

    def render(self):
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        self.nodes = []
        self.tree.setDragDropMode(QAbstractItemView.InternalMove if self.is_custom()
                                  else QAbstractItemView.NoDragDrop)
        self.tree.setAcceptDrops(True)
        self._fill(self.tree.invisibleRootItem(), self.root["children"])
        self.tree.setUpdatesEnabled(True)
        if self.tree.topLevelItemCount() and self.tree.currentItem() is None:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _matches(self, node):
        if not self.filter:
            return True
        if node["type"] == "file":
            return self.filter in node["name"].lower() or self.filter in node["path"].lower()
        return self.filter in node["name"].lower() or any(self._matches(c) for c in node["children"])

    def _fill(self, parent, children):
        key = self.sort_key()
        kids = list(children)
        if key:
            kids.sort(key=lambda n: (n["type"] != "folder", key(n) if n["type"] == "file" else n["name"].lower()))
        for n in kids:
            if not self._matches(n):
                continue
            self.nodes.append(n)
            it = QTreeWidgetItem()
            it.setData(0, Qt.UserRole + 1, n["type"])
            it.setData(0, Qt.UserRole + 2, len(self.nodes) - 1)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
            if n["type"] == "folder":
                it.setFlags(flags | Qt.ItemIsDropEnabled)
                it.setIcon(0, _provider.icon(QFileIconProvider.Folder))
                parent.addChild(it)
                self._fill(it, n["children"])
                it.setExpanded(bool(n.get("open")) or bool(self.filter))
                self._folder_text(it, n)
                it.setText(1, f"{it.childCount()}개")
                it.setForeground(1, QColor("#7f86aa"))
                it.setFont(0, QFont(FONT_FAMILY, 11, QFont.Bold))
            else:
                it.setFlags(flags)
                it.setText(0, n["name"])
                it.setText(1, os.path.dirname(n["path"]))
                it.setForeground(1, QColor("#7f86aa"))
                it.setIcon(0, file_icon(n["path"]))
                parent.addChild(it)

    def _folder_text(self, it, n):
        it.setText(0, ("−  " if it.isExpanded() else "+  ") + n["name"])

    def node_of(self, it):
        return self.nodes[it.data(0, Qt.UserRole + 2)]

    def _serialize(self, parent):
        out = []
        for i in range(parent.childCount()):
            it = parent.child(i)
            n = self.node_of(it)
            if n["type"] == "folder":
                n["open"] = it.isExpanded()
                n["children"] = self._serialize(it)
            out.append(n)
        return out

    def on_dropped(self):
        self.root["children"] = self._serialize(self.tree.invisibleRootItem())
        self.save()
        self.render()

    def on_files(self, paths, target_item):
        target = self.node_of(target_item) if target_item is not None else self.root
        self.add_paths(paths, target)

    def add_paths(self, paths, target=None):
        target = target or self.root
        for p in paths:
            p = os.path.normpath(p)
            target["children"].append({"type": "file", "name": Path(p).name or p, "path": p,
                                       "added": time.time(), "last": 0})
        if target is not self.root:
            target["open"] = True
        self.save()
        self.render()

    def pin_item(self, it):
        self.add_paths([it["path"]])

    def set_filter(self, text):
        self.filter = text.strip().lower()
        self.render()

    def set_sort(self, s):
        self.sort = s
        self.settings["sort"] = s
        save_json(SETTINGS_FILE, self.settings)
        self.render()

    # ---- 동작 ----
    def on_click(self, it, _c):
        n = self.node_of(it)
        if n["type"] == "folder":
            it.setExpanded(not it.isExpanded())
            self._folder_text(it, n)
            if not self.filter:
                n["open"] = it.isExpanded()
                self.save()
        else:
            n["last"] = time.time()
            self.save()
            self.activated.emit(n["path"])

    def selected_target(self):
        it = self.tree.currentItem()
        if it is None:
            return self.root
        n = self.node_of(it)
        if n["type"] == "folder":
            return n
        p = it.parent()
        return self.node_of(p) if p else self.root

    def add_folder(self):
        name, ok = QInputDialog.getText(self, "새 폴더", "폴더 이름:")
        if ok and name.strip():
            self.selected_target()["children"].append(
                {"type": "folder", "name": name.strip(), "open": True, "children": []})
            self.save()
            self.render()

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "보관할 파일 선택")
        if paths:
            self.add_paths(paths, self.selected_target())

    def add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "보관할 폴더 선택")
        if d:
            self.add_paths([d], self.selected_target())

    def _remove(self, node, children=None):
        children = self.root["children"] if children is None else children
        if node in children:
            children.remove(node)
            return True
        return any(self._remove(node, c["children"]) for c in children if c["type"] == "folder")

    def delete_current(self):
        it = self.tree.currentItem()
        if it is not None:
            self._remove(self.node_of(it))
            self.save()
            self.render()

    def menu(self, pos):
        it = self.tree.itemAt(pos)
        m = QMenu(self)
        if it is not None:
            self.tree.setCurrentItem(it)
            n = self.node_of(it)
            if n["type"] == "file":
                m.addAction("열기", lambda: self.on_click(it, 0))
                m.addAction("파일 위치 열기", lambda: reveal(n["path"]))
            m.addAction("이름 변경…", lambda: self.rename(n))
            m.addAction("삭제", self.delete_current)
            m.addSeparator()
        m.addAction("새 폴더…", self.add_folder)
        m.addAction("파일 추가…", self.add_files)
        m.addAction("폴더 추가…", self.add_dir)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def rename(self, n):
        name, ok = QInputDialog.getText(self, "이름 변경", "이름:", text=n["name"])
        if ok and name.strip():
            n["name"] = name.strip()
            self.save()
            self.render()

    def handle_key(self, e):
        if forward_tree_key(self.tree, e):
            return True
        it = self.tree.currentItem()
        if it is None:
            return False
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.on_click(it, 0)
        elif e.key() == Qt.Key_Right and self.node_of(it)["type"] == "folder" and not it.isExpanded():
            self.on_click(it, 0)
        elif e.key() == Qt.Key_Left and self.node_of(it)["type"] == "folder" and it.isExpanded():
            self.on_click(it, 0)
        elif e.key() == Qt.Key_Delete:
            self.delete_current()
        else:
            return False
        return True


# ───────────────────────── 창 조절 버튼 아이콘 (폰트 글자에 의존하지 않고 직접 그림) ─────────────────────────
def win_icon(kind):
    pm = QPixmap(28, 28)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#e8eaf6"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if kind == "min":
        p.drawLine(8, 14, 20, 14)
    elif kind == "max":
        p.drawRect(8, 8, 12, 12)
    elif kind == "restore":
        p.drawRect(8, 11, 10, 10)
        p.drawLine(11, 8, 20, 8)
        p.drawLine(20, 8, 20, 17)
    else:
        p.drawLine(9, 9, 19, 19)
        p.drawLine(19, 9, 9, 19)
    p.end()
    return QIcon(pm)


# ───────────────────────── 설정 페이지 ─────────────────────────
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "JYLauncher"


def startup_command():
    if FROZEN:  # 설치된 exe
        return f'"{sys.executable}" --background'
    exe = Path(sys.executable).with_name("pythonw.exe")
    exe = exe if exe.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve()}" --background'


def startup_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def set_startup(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


CTX_KEYS = [r"Software\Classes\*\shell\JYLauncherAdd", r"Software\Classes\Directory\shell\JYLauncherAdd"]


def ctx_command():
    if FROZEN:
        return f'"{sys.executable}" --add "%1"'
    exe = Path(sys.executable).with_name("pythonw.exe")
    exe = exe if exe.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve()}" --add "%1"'


def ctx_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CTX_KEYS[0]):
            return True
    except OSError:
        return False


def set_ctx(on):
    """탐색기 우클릭 메뉴(파일/폴더)에 '런처에 추가' 등록/해제 (현재 사용자만, 관리자 권한 불필요)"""
    import winreg
    for k in CTX_KEYS:
        if on:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, k) as h:
                winreg.SetValue(h, "", winreg.REG_SZ, "런처에 추가")
                winreg.SetValueEx(h, "Icon", 0, winreg.REG_SZ, sys.executable)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, k + r"\command") as h:
                winreg.SetValue(h, "", winreg.REG_SZ, ctx_command())
        else:
            for sub in (k + r"\command", k):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except FileNotFoundError:
                    pass


EXT_GROUPS = (("xlsx", ("xlsx", "xls", "xlsm")), ("hwp", ("hwp", "hwpx")), ("pdf", ("pdf",)), ("docx", ("docx", "doc")),
              ("pptx", ("pptx", "ppt")), ("txt", ("txt", "md", "csv")),
              ("이미지", ("jpg", "jpeg", "png", "gif", "bmp", "webp")), ("동영상", ("mp4", "mkv", "avi", "mov", "wmv")))


class SearchPage(QWidget):
    """검색 탭: 왼쪽 = 앱 검색(시작 메뉴 앱. 평소엔 접혀 있다가 펼칠 때 목록을 만듦), 오른쪽 = 파일 검색(Everything).
    입력은 맨 위 검색창을 그대로 씀 (아무 글자나 치면 검색창으로 들어감)"""
    _apps_ready = Signal(list)

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.text = ""
        self.apps = None                  # 앱 색인 (펼칠 때 처음 한 번 만듦)
        self.indexing = False
        self.active = "files"
        self.searcher = FS.Searcher(self)
        self.searcher.results.connect(self._on_results)
        self.searcher.done.connect(self._on_done)
        self.guard = SUI.EverythingGuard(self)
        self.guard.message.connect(main.say)
        self.guard.finished.connect(self._on_guard)
        self._gen, self._use_everything, self._guard_done = 0, True, False
        self._timer = QTimer(self, singleShot=True, interval=350)
        self._timer.timeout.connect(self.run)
        self._apps_ready.connect(self._on_apps_ready)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        opts = QHBoxLayout()
        opts.setSpacing(8)
        lbl = QLabel("검색 위치")
        lbl.setObjectName("dim")
        opts.addWidget(lbl)
        self.scope = QComboBox()
        self.scope.setFocusPolicy(Qt.NoFocus)
        home = Path.home()
        for name, path in (("전체 (Everything)", None), ("사용자 폴더", str(home)), ("문서", str(home / "Documents")),
                           ("바탕화면", str(home / "Desktop")), ("다운로드", str(home / "Downloads"))):
            self.scope.addItem(name, path)
        self.scope.addItem("폴더 선택…", "__pick__")
        self._scope_idx = 0
        self.scope.currentIndexChanged.connect(self._scope_changed)
        opts.addWidget(self.scope)
        opts.addSpacing(10)
        self.chips = []
        for label, exts in EXT_GROUPS:
            b = QPushButton(label)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip("확장자: " + ", ".join(exts))
            b.toggled.connect(lambda _v: self._timer.start())
            self.chips.append((b, exts))
            opts.addWidget(b)
        self.ext_edit = QLineEdit()
        self.ext_edit.setObjectName("ext")
        self.ext_edit.setPlaceholderText("확장자 직접 입력 (예: xlsx, hwp)")
        self.ext_edit.setFixedWidth(230)
        self.ext_edit.textChanged.connect(lambda _t: self._timer.start())
        opts.addWidget(self.ext_edit)
        opts.addStretch(1)
        self.ev_btn = QPushButton("Everything 상태")
        self.ev_btn.setObjectName("chip")
        self.ev_btn.setFocusPolicy(Qt.NoFocus)
        self.ev_btn.setToolTip("Everything 설치 / 연결 상태를 확인하고 필요하면 설치·설정합니다")
        self.ev_btn.clicked.connect(self._check_everything)
        opts.addWidget(self.ev_btn)
        lay.addLayout(opts)

        self.status = QLabel("맨 위 검색창에 검색어를 입력하세요  (파일 이름 / 앱 이름).  확장자 버튼으로 xlsx, hwp 같은 파일만 찾을 수도 있습니다")
        self.status.setObjectName("dim")
        lay.addWidget(self.status)

        body = QHBoxLayout()
        body.setSpacing(14)
        # 앱 검색 (접힘/펼침)
        self.app_panel = QFrame()
        self.app_panel.setObjectName("sidebar")
        al = QVBoxLayout(self.app_panel)
        al.setContentsMargins(10, 10, 10, 10)
        al.setSpacing(8)
        self.app_btn = QPushButton("앱 검색  (펼치기)")
        self.app_btn.setObjectName("chip")
        self.app_btn.setCheckable(True)
        self.app_btn.setFocusPolicy(Qt.NoFocus)
        self.app_btn.setToolTip("시작 메뉴에서 검색되는 앱을 찾아 실행합니다. 펼칠 때 처음 한 번 목록을 만듭니다")
        self.app_btn.toggled.connect(self._toggle_apps)
        al.addWidget(self.app_btn)
        self.app_note = QLabel("")
        self.app_note.setObjectName("dim")
        self.app_note.setWordWrap(True)
        self.app_note.hide()
        al.addWidget(self.app_note)
        self.app_list = make_tree()
        self.app_list.setColumnCount(1)
        self.app_list.hide()
        self.app_list.itemActivated.connect(self._launch_app_item)
        self.app_list.itemClicked.connect(self._launch_app_item)
        al.addWidget(self.app_list, 1)
        al.addStretch(0)
        self.app_panel.setFixedWidth(200)
        body.addWidget(self.app_panel)
        # 파일 검색 결과
        self.tree = SUI.ResultsTree()
        self.tree.openRequested.connect(self.open_result)
        self.tree.menuRequested.connect(self._result_menu)
        body.addWidget(self.tree, 1)
        lay.addLayout(body, 1)

    # ---- 입력 ----
    def set_filter(self, text):
        self.text = text
        self._timer.start()

    def selected_exts(self):
        out = []
        for b, exts in self.chips:
            if b.isChecked():
                out += list(exts)
        for e in self.ext_edit.text().replace(";", ",").replace(" ", ",").split(","):
            e = e.strip().lstrip(".*").lower()
            if e:
                out.append(e)
        return list(dict.fromkeys(out))

    def _scope_changed(self, i):
        if self.scope.itemData(i) == "__pick__":
            d = QFileDialog.getExistingDirectory(self, "검색할 폴더", str(Path.home()))
            if d:
                d = os.path.normpath(d)
                self.scope.blockSignals(True)
                self.scope.setItemText(i, d)
                self.scope.setItemData(i, d)
                self.scope.blockSignals(False)
            else:
                self.scope.blockSignals(True)
                self.scope.setCurrentIndex(self._scope_idx)
                self.scope.blockSignals(False)
                return
        self._scope_idx = self.scope.currentIndex()
        self._timer.start()

    # ---- 검색 실행 ----
    def run(self):
        text, exts = self.text.strip(), self.selected_exts()
        self._refresh_apps()
        if not text and not exts:
            self.searcher.cancel()
            self._gen += 1
            self.tree.clear_results()
            self.status.setText("맨 위 검색창에 검색어를 입력하세요  (파일 이름 / 앱 이름).  확장자 버튼으로 xlsx, hwp 같은 파일만 찾을 수도 있습니다")
            return
        if not self._guard_done and FS.Searcher.status() != "ready":      # 처음 한 번만 Everything 상태 확인/안내
            self._guard_done = True
            self.guard.ensure()
            return
        self._guard_done = True
        root = self.scope.currentData()
        if root == "__pick__":
            root = None
        if root is None and not self._use_everything:
            root = str(Path.home())                    # Everything 없이는 전체 검색이 불가 → 사용자 폴더만
            self.status.setText((FS.Searcher.reason() or "Everything 을 사용할 수 없습니다") + " → 사용자 폴더만 직접 검색합니다 (느림)")
        self.tree.clear_results()
        self.status.setText("검색 중…")
        self._gen = self.searcher.search(text, root, exts, 2000, use_everything=self._use_everything)

    def _on_guard(self, ok):
        self._use_everything = ok
        self._guard_done = True
        self.run()

    def _check_everything(self):
        self._guard_done = False
        self._asked_reset()
        st = FS.Searcher.status()
        if st == "ready":
            self.main.say("Everything 연결됨 — 전체 검색을 빠르게 쓸 수 있습니다")
            self._use_everything = True
            return
        self.guard.settings["everything"] = ""       # 사용자가 직접 눌렀으니 예전에 '설치 안 함'을 골랐어도 다시 안내
        self.guard.ensure()

    def _asked_reset(self):
        self.guard._asked.clear()

    def _on_results(self, gen, rows):
        if gen != self._gen:
            return
        self.tree.add_rows(rows)
        self.status.setText(f"검색 중…  {self.tree.topLevelItemCount():,}개")

    def _on_done(self, gen, info):
        if gen != self._gen:
            return
        n = self.tree.topLevelItemCount()
        how = {"everything": "Everything (빠름)", "scan": "직접 검색 (느림 — Everything 을 설치하면 즉시 검색)"}.get(info.get("backend"), "")
        msg = f"파일 {n:,}개" + (f"  ·  {how}" if how else "")
        if info.get("truncated"):
            msg += "  ·  결과가 많아 일부만 표시 (검색어를 더 구체적으로)"
        if info.get("note"):
            msg += "  ·  " + info["note"]
        if info.get("error"):
            msg += "  ·  " + info["error"]
        elif n == 0:
            msg += "  ·  결과 없음"
        self.status.setText(msg)

    # ---- 앱 검색 ----
    def _toggle_apps(self, on):
        self.app_btn.setText("앱 검색  (접기)" if on else "앱 검색  (펼치기)")
        self.app_panel.setFixedWidth(400 if on else 200)
        self.app_list.setVisible(on)
        self.app_note.setVisible(on and self.apps is None)
        if on:
            self.active = "apps"
            self._refresh_apps()
        else:
            self.active = "files"

    def _refresh_apps(self):
        if not self.app_btn.isChecked():
            return
        if self.apps is None:
            if not self.indexing:
                self.indexing = True
                self.app_note.setText("앱 목록을 만드는 중…")
                self.app_note.show()
                threading.Thread(target=lambda: self._apps_ready.emit(appsearch.build_index()), daemon=True).start()
            return
        self.app_list.clear()
        hits = appsearch.filter_apps(self.apps, self.text)[:80]
        for a in hits:
            it = QTreeWidgetItem([a["name"]])
            it.setData(0, Qt.UserRole, a)
            it.setToolTip(0, a["name"] + ("\n" + a["folder"] if a.get("folder") else ""))
            it.setIcon(0, file_icon(a["target"]) if a["kind"] == "lnk" else file_icon("x.exe"))
            self.app_list.addTopLevelItem(it)
        if hits:
            self.app_list.setCurrentItem(self.app_list.topLevelItem(0))
        self.app_note.setText(f"{len(hits)}개" if self.text.strip() else f"앱 {len(self.apps)}개 — 위 검색창에 이름을 입력하세요")
        self.app_note.setVisible(True)

    def _on_apps_ready(self, apps):
        self.apps = apps
        self.indexing = False
        self._refresh_apps()

    def _launch_app_item(self, it, _c=0):
        a = it.data(0, Qt.UserRole)
        if not a:
            return
        try:
            appsearch.launch(a)
            self.main.say(f"실행: {a['name']}")
            if self.main.hide_btn.isChecked():
                self.main.hide()
        except Exception as ex:
            self.main.say(f"! 실행 실패: {ex}")

    # ---- 파일 결과 동작 ----
    def open_result(self, path, is_dir):
        if is_dir:
            open_in_explorer(path)
            return
        try:
            os.startfile(path)
            self.main.say("열기: " + os.path.basename(path))
        except OSError as ex:
            self.main.say(f"! 열 수 없음: {ex}")

    def _result_menu(self, path, is_dir, pos):
        m = QMenu(self)
        m.addAction("열기", lambda: self.open_result(path, is_dir))
        folder = path if is_dir else os.path.dirname(path)
        m.addAction("폴더 열기 (JY Explorer)", lambda: open_in_explorer(folder))
        m.addAction("경로 복사", lambda: QApplication.clipboard().setText(path))
        m.addAction("런처에 추가", lambda: (add_item_to_launcher(path), self.main.reload_launcher(), self.main.say("런처에 추가했습니다")))
        m.exec(pos)

    # ---- 키 (런처 공통 키 처리에서 넘어옴) ----
    def current_tree(self):
        return self.app_list if (self.active == "apps" and self.app_btn.isChecked()) else self.tree

    def handle_key(self, e):
        k = e.key()
        if k == Qt.Key_Left and self.app_btn.isChecked():
            self.active = "apps"
            return True
        if k == Qt.Key_Right:
            self.active = "files"
            return True
        t = self.current_tree()
        if forward_tree_key(t, e):
            return True
        if k in (Qt.Key_Return, Qt.Key_Enter) and t.currentItem():
            (self._launch_app_item if t is self.app_list else self.tree._activated)(t.currentItem())
            return True
        return False


class SettingsPage(QWidget):
    toast = Signal(str)

    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.startup = self.row(lay, "Windows 시작 시 자동 실행",
                                "부팅하면 트레이에 상주합니다. 단축키(%s)로 바로 호출" % HOTKEY_TEXT,
                                startup_enabled(), self.on_startup, ("켜짐", "꺼짐"))
        self.hide = self.row(lay, "앱 실행 후 런처 숨김",
                             "앱(.exe)을 실행하면 런처를 숨기고, 앱이 끝나면 다시 표시",
                             main.hide_btn.isChecked(), main.hide_btn.setChecked, ("켜짐", "꺼짐"))
        self.ctx = self.row(lay, "탐색기 우클릭 메뉴에 '런처에 추가'",
                            "파일/폴더를 우클릭 → '런처에 추가' (Windows 11 은 '더 많은 옵션 표시' 안). '새로 추가' 그룹에 들어갑니다",
                            ctx_enabled(), self.on_ctx, ("켜짐", "꺼짐"))
        self.shortcut_row(lay)
        self.update_row(lay)
        for text, fn in (("데이터 폴더 열기", lambda: os.startfile(DATA_DIR)), ("런처 종료", main.quit_app)):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, f=fn: f())
            row = QHBoxLayout()
            row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
        lay.addStretch(1)

    def row(self, lay, title, desc, checked, fn, labels):
        box = QFrame()
        box.setObjectName("sidebar")
        h = QHBoxLayout(box)
        h.setContentsMargins(20, 14, 20, 14)
        col = QVBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("font-size:15px; font-weight:700;")
        d = QLabel(desc)
        d.setObjectName("dim")
        col.addWidget(t)
        col.addWidget(d)
        b = QPushButton()
        b.setObjectName("toggle")
        b.setCheckable(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setFixedWidth(84)
        b.setChecked(checked)
        b.setText(labels[0] if checked else labels[1])

        def toggled(v):
            b.setText(labels[0] if v else labels[1])
            fn(v)
        b.toggled.connect(toggled)
        h.addLayout(col, 1)
        h.addWidget(b)
        lay.addWidget(box)
        return b

    def shortcut_row(self, lay):
        box = QFrame()
        box.setObjectName("sidebar")
        col = QVBoxLayout(box)
        col.setContentsMargins(20, 14, 20, 14)
        t = QLabel("바로가기 만들기 (런처 + 탐색기)")
        t.setStyleSheet("font-size:15px; font-weight:700;")
        d = QLabel("작업 표시줄에 고정: 시작 메뉴에 만든 뒤 → 시작 메뉴에서 'JY Launcher' / 'JY Explorer' 우클릭 → "
                   "'작업 표시줄에 고정' (Windows 가 프로그램이 직접 고정하는 것을 막아 둬서 이 한 단계만 직접 해야 합니다)")
        d.setObjectName("dim")
        d.setWordWrap(True)
        row = QHBoxLayout()
        for text, where in (("시작 메뉴에 만들기", "startmenu"), ("바탕화면에 만들기", "desktop")):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, w=where, n=text: self.make_shortcuts(w, n))
            row.addWidget(b)
        row.addStretch(1)
        col.addWidget(t)
        col.addWidget(d)
        col.addLayout(row)
        lay.addWidget(box)

    def update_row(self, lay):
        """업데이트 상태 표시 + 지금 확인 + 시작 후 자동 확인 토글 (Updater 는 창이 다 만들어진 뒤 attach_updater 로 연결)"""
        box = QFrame()
        box.setObjectName("sidebar")
        h = QHBoxLayout(box)
        h.setContentsMargins(20, 14, 20, 14)
        col = QVBoxLayout()
        t = QLabel("업데이트")
        t.setStyleSheet("font-size:15px; font-weight:700;")
        self.update_label = QLabel(f"현재 버전 {__version__}")
        self.update_label.setObjectName("dim")
        col.addWidget(t)
        col.addWidget(self.update_label)
        self.update_btn = QPushButton("지금 확인")
        self.update_btn.setFocusPolicy(Qt.NoFocus)
        self.update_auto = QPushButton()
        self.update_auto.setObjectName("toggle")
        self.update_auto.setCheckable(True)
        self.update_auto.setFocusPolicy(Qt.NoFocus)
        self.update_auto.setFixedWidth(120)
        h.addLayout(col, 1)
        h.addWidget(self.update_btn)
        h.addWidget(self.update_auto)
        lay.addWidget(box)

    def attach_updater(self, updater):
        def sync():
            self.update_label.setText(updater.status_text())
            self.update_btn.setText("업데이트 설치…" if updater.available else "지금 확인")
        sync()
        updater.changed.connect(sync)
        self.update_btn.clicked.connect(lambda: updater.prompt_install() if updater.available else updater.check(manual=True))
        self.update_auto.setChecked(updater.auto)
        self.update_auto.setText("자동 확인 켜짐" if updater.auto else "자동 확인 꺼짐")

        def auto_toggled(v):
            self.update_auto.setText("자동 확인 켜짐" if v else "자동 확인 꺼짐")
            updater.set_auto(v)
        self.update_auto.toggled.connect(auto_toggled)

    def make_shortcuts(self, where, label):
        made = create_app_shortcuts(where)
        if made:
            self.toast.emit(f"{label}: {', '.join(p.stem for p in made)} 완료")
            if where == "startmenu":
                os.startfile(made[0].parent)      # 시작 메뉴 폴더를 열어 바로 우클릭→고정 할 수 있게
        else:
            self.toast.emit("! 바로가기를 만들지 못했습니다")

    def on_startup(self, v):
        try:
            set_startup(v)
            self.toast.emit("시작프로그램에 등록했습니다" if v else "시작프로그램에서 뺐습니다")
        except OSError as ex:
            self.toast.emit(f"! 실패: {ex}")
            self.startup.blockSignals(True)
            self.startup.setChecked(not v)
            self.startup.setText("켜짐" if not v else "꺼짐")
            self.startup.blockSignals(False)

    def on_ctx(self, v):
        try:
            set_ctx(v)
            self.toast.emit("우클릭 메뉴에 등록했습니다" if v else "우클릭 메뉴에서 뺐습니다")
        except OSError as ex:
            self.toast.emit(f"! 실패: {ex}")

    def refresh(self):
        self.ctx.blockSignals(True)
        self.ctx.setChecked(ctx_enabled())
        self.ctx.setText("켜짐" if self.ctx.isChecked() else "꺼짐")
        self.ctx.blockSignals(False)
        self.startup.blockSignals(True)
        self.startup.setChecked(startup_enabled())
        self.startup.setText("켜짐" if self.startup.isChecked() else "꺼짐")
        self.startup.blockSignals(False)

    def set_filter(self, text):
        pass

    def handle_key(self, e):
        return False


# ───────────────────────── 메인 윈도우 ─────────────────────────
class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("JY Launcher")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.settings = load_json(SETTINGS_FILE, {})
        set_size(self.settings.get("card_mode", DEFAULT_SIZE))
        if not LAUNCHER_FILE.exists():
            save_json(LAUNCHER_FILE, default_launcher())
        self.watcher = Watcher()
        self.watcher.finished.connect(self.restore)
        self.win_mode = self.settings.get("win_mode", "full")   # full(전체화면) / max(최대화) / normal(창)
        self._sized = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 26, 36, 18)
        outer.setSpacing(18)

        # 상단 바
        top = QHBoxLayout()
        logo = QLabel("◆  JY LAUNCHER")
        logo.setObjectName("logo")
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("검색   ( / 또는 그냥 입력 )")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.on_search)
        self.search.installEventFilter(self)
        self.clock = QLabel()
        self.clock.setObjectName("clock")
        self.min_btn = self._wc("min", "최소화", self.showMinimized)
        self.max_btn = self._wc("max", "최대화 / 이전 크기  (상단 더블클릭)", self.toggle_max)
        close = self._wc("close", "닫기 (트레이로 숨김)", self.close, name="close")
        top.addWidget(logo)
        top.addStretch(1)
        top.addWidget(self.search)
        top.addStretch(1)
        top.addWidget(self.clock)
        top.addSpacing(10)
        top.addWidget(self.min_btn)
        top.addWidget(self.max_btn)
        top.addWidget(close)
        outer.addLayout(top)

        # 본문
        body = QHBoxLayout()
        body.setSpacing(22)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 14, 12, 14)
        sl.setSpacing(6)
        self.stack = QStackedWidget()
        self.group = QButtonGroup(self)
        self.launcher = LauncherPage(load_json(LAUNCHER_FILE, {}), self.settings)
        self.recent = RecentPage()
        self.vault = VaultPage(self.settings)
        self.hide_btn = QPushButton()  # 설정 페이지가 참조 (아래에서 다시 구성)
        self.hide_btn.setCheckable(True)
        self.hide_btn.setChecked(self.settings.get("hide_on_launch", False))
        self.hide_btn.toggled.connect(self.on_hide_toggle)
        self.settings_page = SettingsPage(self)
        self.settings_page.toast.connect(self.say)
        self.search_page = SearchPage(self)
        self.pages = [("런처", "런처", self.launcher), ("최근", "최근 항목", self.recent),
                      ("보관함", "고정 보관함", self.vault), ("검색", "검색  ·  파일 / 앱", self.search_page),
                      ("설정", "설정", self.settings_page)]
        for i, (label, _t, page) in enumerate(self.pages):
            b = QPushButton(label)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, i=i: self.goto(i))
            self.group.addButton(b, i)
            sl.addWidget(b)
            self.stack.addWidget(page)
        sl.addStretch(1)
        body.addWidget(side)

        right = QVBoxLayout()
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        right.addLayout(head)
        right.addWidget(self.stack, 1)
        body.addLayout(right, 1)
        outer.addLayout(body, 1)

        # 하단
        foot = QHBoxLayout()
        hint = QLabel("↑↓←→ 이동   Enter 실행   Space 그룹 열기/닫기   Ctrl+F 검색↔목록 (Tab)   드래그로 이동·묶기   Ctrl+1~5 탭   F11 전체화면   Esc 닫기")
        hint.setObjectName("hint")
        self.toast_lbl = QLabel()
        self.toast_lbl.setObjectName("toast")
        foot.addWidget(hint)
        foot.addStretch(1)
        foot.addWidget(self.toast_lbl)
        outer.addLayout(foot)

        for p in (self.launcher, self.recent, self.vault):
            p.activated.connect(self.launch)
        self.launcher.pinRequested.connect(self.pin)
        self.build_actions()
        self.goto(0)

        t = QTimer(self)
        t.timeout.connect(self.tick)
        t.start(10000)
        self.tick()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: self.toast_lbl.clear())
        self.setMinimumSize(960, 600)
        self.grip = QSizeGrip(self)          # 창 모드에서 오른쪽 아래를 끌어 크기 조절
        self.grip.resize(18, 18)
        self.grip.hide()

    def _wc(self, kind, tip, fn, name="wc"):
        b = QPushButton()
        b.setObjectName(name)
        b.setFixedSize(42, 32)
        b.setIcon(win_icon(kind))
        b.setIconSize(QSize(28, 28))
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(lambda: fn())
        return b

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.grip.move(self.width() - 18, self.height() - 18)
        self.grip.raise_()

    # 창 모드에서 위쪽 빈 곳을 끌면 창 이동, 더블클릭하면 최대화/복원
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.win_mode == "normal" and e.position().y() < 76:
            h = self.windowHandle()
            if h:
                h.startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 76:
            self.toggle_max()
            return
        super().mouseDoubleClickEvent(e)

    # ---- 페이지/액션 ----
    def build_actions(self):
        def btn(text, fn):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda: fn())
            return b
        size_btns = []
        size_group = QButtonGroup(self)
        for name in SIZES:
            b = QPushButton(name)
            b.setObjectName("toggle")
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setChecked(name == self.settings.get("card_mode", DEFAULT_SIZE))
            b.clicked.connect(lambda _=False, n=name: self.change_size(n))
            size_group.addButton(b)
            size_btns.append(b)
        self.action_sets = [
            size_btns + [btn("＋ 앱 추가", self.launcher.add_app), btn("＋ 카테고리", self.launcher.add_category)],
            [btn("새로고침", self.recent.refresh)],
        ]
        sort = QComboBox()
        sort.setFocusPolicy(Qt.NoFocus)
        sort.addItems(SORTS)
        sort.setCurrentText(self.vault.sort)
        sort.currentTextChanged.connect(self.vault.set_sort)
        self.action_sets.append([sort, btn("＋ 폴더", self.vault.add_folder),
                                 btn("＋ 파일", self.vault.add_files)])
        self.action_sets.append([])          # 검색 탭
        self.action_sets.append([])          # 설정 탭
        for s in self.action_sets:
            for w in s:
                self.actions.addWidget(w)
                w.hide()

    def change_size(self, name):
        set_size(name)
        self.settings["card_mode"] = name
        save_json(SETTINGS_FILE, self.settings)
        self.launcher.rebuild()

    # ---- 위쪽 버튼줄(＋ 앱 추가, 아이콘 크기 등)을 키보드로 ----
    def header_widgets(self):
        return [w for w in self.action_sets[self.index] if w.isEnabled()]

    def _page_at_top(self):
        p = self.page()
        if hasattr(p, "at_top"):
            return p.at_top()
        t = getattr(p, "tree", None)
        if t is not None:
            return t.currentItem() is None or not t.indexAbove(t.currentIndex()).isValid()
        return False

    def set_header(self, i):
        """위쪽 버튼줄에서 i 번째 버튼에 키보드 선택 표시 (-1 = 해제)"""
        ws = self.header_widgets()
        self._hdr = i if 0 <= i < len(ws) else -1
        for w in [x for s in self.action_sets for x in s]:
            on = self._hdr >= 0 and w is ws[self._hdr]
            if w.property("kb") != on:
                w.setProperty("kb", on)
                _repolish(w)

    def header_key(self, e):
        """위쪽 버튼줄 선택 중의 키 처리. 처리했으면 True"""
        ws = self.header_widgets()
        k = e.key()
        if k == Qt.Key_Left:
            self.set_header((self._hdr - 1) % len(ws))
        elif k == Qt.Key_Right:
            self.set_header((self._hdr + 1) % len(ws))
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            w = ws[self._hdr]
            if isinstance(w, QComboBox):
                w.showPopup()
            else:
                w.click()
        elif k in (Qt.Key_Down, Qt.Key_Escape):
            self.set_header(-1)
        else:
            return False
        return True

    def goto(self, i):
        if self._hdr >= 0:
            self.set_header(-1)
        self.index = i
        self.group.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)
        self.title.setText(self.pages[i][1])
        for k, s in enumerate(self.action_sets):
            for w in s:
                w.setVisible(k == i)
        if i == 1:
            self.recent.refresh()
        elif i == 4:
            self.settings_page.refresh()
        self.on_search(self.search.text())

    def page(self):
        return self.pages[self.index][2]

    def on_search(self, text):
        self.page().set_filter(text)

    def on_hide_toggle(self, v):
        self.settings["hide_on_launch"] = v
        save_json(SETTINGS_FILE, self.settings)

    def pin(self, item):
        self.vault.pin_item(item)
        self.say(f"보관함에 고정: {item['name']}")

    def tick(self):
        self.clock.setText(time.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후"))

    def say(self, msg):
        self.toast_lbl.setText(msg)
        self._toast_timer.start(3000)

    # ---- 실행 ----
    def launch(self, path):
        if not path.startswith(("http", "shell:")) and not os.path.exists(path):
            self.say(f"! 경로를 찾을 수 없음: {path}")
            return
        name = Path(path).stem or path
        try:
            if self.hide_btn.isChecked() and path.lower().endswith(".exe"):
                try:
                    proc = subprocess.Popen([path], cwd=os.path.dirname(path))
                except OSError:  # 관리자 권한 요구 등
                    os.startfile(path)
                    self.say(f"실행: {name}")
                    return
                self.hide()
                self.watcher.watch(proc)
            else:
                os.startfile(path)
                self.say(f"실행: {name}")
        except Exception as ex:
            self.say(f"! 실행 실패: {ex}")

    def apply_mode(self):
        m = self.win_mode
        if m in ("full", "max"):
            # 전체화면도 작업 표시줄이 보이도록, 화면 전체(showFullScreen)가 아니라 작업 영역만 채우는 최대화로 표시
            self.showMaximized()
        else:
            self.showNormal()
            if not self._sized:
                self.resize(1280, 800)
                self._sized = True
        self.grip.setVisible(m == "normal")
        self.max_btn.setIcon(win_icon("max" if m == "normal" else "restore"))

    def set_mode(self, m):
        self.win_mode = m
        self.settings["win_mode"] = m
        save_json(SETTINGS_FILE, self.settings)
        self.apply_mode()

    def toggle_max(self):
        self.set_mode("normal" if self.win_mode in ("full", "max") else "max")

    def restore(self):
        self.apply_mode()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ---- 상주(트레이) ----
    def summon(self):
        """숨어 있던 런처를 즉시 띄움 (프로세스 재시작 없음)."""
        self.search.clear()
        if file_mtime(LAUNCHER_FILE) != self.launcher.mtime:   # 탐색기/우클릭 메뉴에서 추가된 항목 반영
            self.reload_launcher()
        if self.index == 1:
            self.recent.refresh()
        self.restore()
        # 다른 앱이 포커스를 쥐고 있어도 앞으로 가져오기
        ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        self.search.clearFocus()
        self.setFocus()

    def toggle_visible(self):
        self.hide() if self.isVisible() and self.isActiveWindow() else self.summon()

    def quit_app(self):
        self.quitting = True
        QApplication.quit()

    def closeEvent(self, e):
        if getattr(self, "quitting", False):
            e.accept()
        else:
            e.ignore()
            self.hide()

    def toggle_fullscreen(self):
        self.set_mode("normal" if self.win_mode == "full" else "full")

    def focus_list(self):
        """검색창 → 목록(런처)으로 포커스 복귀 (검색어는 유지)"""
        self.search.clearFocus()
        self.setFocus()

    def reload_launcher(self):
        self.launcher.data = load_json(LAUNCHER_FILE, {})
        self.launcher.mtime = file_mtime(LAUNCHER_FILE)
        self.launcher.rebuild()

    # ---- 키 처리 ----
    NAV_KEYS = (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter,
                Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End, Qt.Key_Delete)

    def eventFilter(self, obj, e):
        if obj is self.search and e.type() == e.Type.KeyPress:
            k = e.key()
            if k == Qt.Key_Tab:                       # Tab: 검색창 → 목록으로 복귀
                self.focus_list()
                return True
            if k in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Return, Qt.Key_Enter, Qt.Key_PageUp, Qt.Key_PageDown) \
                    or k == Qt.Key_Escape:
                self.keyPressEvent(e)
                return True
        return super().eventFilter(obj, e)

    _hdr = -1

    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        if self._hdr >= 0:                                    # 위쪽 버튼줄 선택 중
            if self.header_key(e):
                return
            self.set_header(-1)
        elif k == Qt.Key_Up and not mods and self.header_widgets() and self._page_at_top():
            self.focus_list()
            self.set_header(0)                                # 맨 위에서 ↑ → 위쪽 버튼줄로 (← → 이동, Enter 실행, ↓ 로 복귀)
            return
        if k == Qt.Key_Escape:
            if self.search.text():
                self.search.clear()
            else:
                self.hide()
        elif k == Qt.Key_F11:
            self.toggle_fullscreen()
        elif mods & Qt.ControlModifier and Qt.Key_1 <= k <= Qt.Key_5:
            self.goto(k - Qt.Key_1)
        elif mods & Qt.ControlModifier and k == Qt.Key_F:      # Ctrl+F: 검색 ↔ 목록 왕복
            if self.search.hasFocus():
                self.focus_list()
            else:
                self.search.setFocus()
                self.search.selectAll()
        elif k == Qt.Key_Slash and not self.search.hasFocus():
            self.search.setFocus()
            self.search.selectAll()
        elif k == Qt.Key_Space and not self.search.hasFocus():  # 스페이스: 그룹 열기/닫기
            self.page().handle_key(e)
        elif k in self.NAV_KEYS and not (self.search.hasFocus() and k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Delete)):
            self.page().handle_key(e)
        elif e.text() and e.text().isprintable() and not mods & (Qt.ControlModifier | Qt.AltModifier):
            self.search.setFocus()
            self.search.insert(e.text())
        else:
            super().keyPressEvent(e)


SERVER_NAME = "JYLauncher-single-instance" + INSTANCE_SUFFIX
HOTKEY_ID = 0x4A59
HOTKEY_TEXT = "Ctrl+Alt+L"


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        mods = 0x0002 | 0x0001 | 0x4000  # CTRL | ALT | NOREPEAT
        self.ok = bool(ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mods, ord("L")))

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:
                self.callback()
        return False, 0


def send_to_running(msg):
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(150):
        sock.write(msg)
        sock.waitForBytesWritten(300)
        return True
    return False


STARTUP_LOG = DATA_DIR / "startup_log.txt"


def _log_startup(msg):
    """--background(시작프로그램)로 뜰 때만 기록 — 부팅 직후 조용히 실행에 실패해도 원인을 나중에 볼 수 있게.
    파일이 커지지 않도록 최근 20줄만 유지."""
    try:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
        old = STARTUP_LOG.read_text(encoding="utf-8").splitlines(True) if STARTUP_LOG.exists() else []
        STARTUP_LOG.write_text("".join(old[-19:]) + line, encoding="utf-8")
    except OSError:
        pass


def main():
    args = sys.argv[1:]
    if "--background" in args:
        _log_startup(f"시작 (pid={os.getpid()}, cwd={os.getcwd()}, exe={sys.executable})")
        sys.excepthook = lambda *exc: (_log_startup("미처리 예외: " + "".join(
            __import__("traceback").format_exception(*exc))), sys.__excepthook__(*exc))
    if "--install-everything" in args:   # 설치 프로그램의 'Everything 설치' 체크 → 창 없이 설치/설정 (관리자 확인창만 뜸)
        FS.install_everything()
        return
    if "--add" in args:  # 탐색기 우클릭 메뉴: 런처에 추가 (창 없이 처리)
        for pth in [a for a in args[args.index("--add") + 1:] if not a.startswith("--")]:
            add_item_to_launcher(pth)
        send_to_running(b"reload")   # 실행 중이면 목록 새로고침, 아니면 다음 실행 때 반영
        return
    # 이미 떠 있는 인스턴스가 있으면 "show"만 보내고 종료 → 체감상 즉시 표시
    if send_to_running(b"show"):
        return

    app = QApplication(sys.argv)
    load_font(app)
    app.setStyleSheet(QSS)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon("JYLauncher"))
    w = Main()

    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    hk = HotkeyFilter(w.toggle_visible)
    app.installNativeEventFilter(hk)

    tray = QSystemTrayIcon(app_icon("JYLauncher"), app)
    tray.setToolTip(f"JY Launcher  ({HOTKEY_TEXT})")
    tm = QMenu()
    tm.addAction("열기", w.summon)
    tm.addAction("종료", w.quit_app)
    tray.setContextMenu(tm)
    tray.activated.connect(lambda r: w.summon() if r == QSystemTrayIcon.Trigger else None)
    tray.show()
    updater = Updater("launcher", w.quit_app)
    updater.attach(w, tray, tm)
    w.settings_page.attach_updater(updater)

    def on_conn():
        s = server.nextPendingConnection()

        def read():
            msg = bytes(s.readAll()).decode("utf-8", "ignore")
            if msg.startswith("quit"):          # 업데이트 설치 전에 다른 JY 프로그램이 종료를 요청
                w.quit_app()
            elif msg.startswith("reload"):
                w.reload_launcher()
                tray.showMessage("JY Launcher", "런처에 추가했습니다", QSystemTrayIcon.Information, 2500)
            else:
                w.summon()
        s.readyRead.connect(read)
    server.newConnection.connect(on_conn)

    if "--windowed" in sys.argv:
        w.win_mode = "normal"
    if "--background" not in sys.argv:
        w.summon()
    else:
        _log_startup("트레이 상주 시작됨 (창 없이 대기)")
    if "--selftest" in sys.argv:
        (DATA_DIR / "selftest_launcher.txt").write_text(
            f"everything_dll={FS.Searcher.client().dll is not None} status={FS.Searcher.status()} "
            f"pages={[p[0] for p in w.pages]}\n", encoding="utf-8")
        QTimer.singleShot(1500, w.quit_app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
