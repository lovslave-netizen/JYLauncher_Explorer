"""JY Explorer - 탭 + 2패널 + 북마크 탐색기

실행:  pythonw JYExplorer.py [열어볼 폴더 ...]
- 이미 실행 중이면 새 창 대신 실행 중인 창의 새 탭으로 열림 (런처 연동용)
- 데이터: %APPDATA%/JYTools/ (bookmarks.json 은 런처와 공유, explorer.json 은 세션/작업공간)
"""
import ctypes
from ctypes import wintypes
import math
import os
import re
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (QByteArray, QDir, QFileInfo, QItemSelectionModel, QMimeData, QPointF, QModelIndex, QObject, QSize, Qt, QTimer, QUrl,
                            Signal)
from PySide6.QtGui import (QColor, QCursor, QDrag, QGuiApplication, QIcon, QKeySequence, QPainter, QPen,
                           QPixmap, QPolygonF, QShortcut)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFileIconProvider, QFileSystemModel, QFrame,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QSplitter, QStackedWidget, QTabBar,
    QSystemTrayIcon, QToolButton, QTreeView, QVBoxLayout, QWidget,
)

import fileops as F
from jycommon import (BACKUP_DIR, BOOKMARKS_FILE, EXPLORER_FILE, FROZEN, LAUNCHER_FILE, add_item_to_launcher, app_icon, backup_favorites,
                      load_font, load_json, pick_category, save_json)
from updater import Updater
from version import __version__

SERVER_NAME = "JYExplorer-single-instance"
HOME = str(Path.home())
DROP_EFFECT = 'application/x-qt-windows-mime;value="Preferred DropEffect"'  # 1=복사, 2=이동 (Windows 탐색기와 호환)

QSS = """
* { color: #e8eaf6; }
QMainWindow, QWidget#root { background: #10121d; }
QFrame#panel { background: rgba(255,255,255,0.035); border-radius: 14px; }
QFrame#panel[active="true"] { background: rgba(124,140,255,0.10); border: 2px solid #8b98ff; }
QFrame#panel[active="false"][split="true"] { background: rgba(255,255,255,0.02); border: 2px solid transparent; }
QFrame#panel[split="true"][active="false"] QTabBar::tab:selected { background: rgba(255,255,255,0.14); }
QLabel#badge { background: #5b6cff; color: white; border-radius: 8px; padding: 2px 10px; font-size: 11px; font-weight: 700; }
QLabel#badgeoff { background: rgba(255,255,255,0.06); color: #7f86aa; border-radius: 8px; padding: 2px 10px; font-size: 11px; }
QFrame#bmbar { background: rgba(255,255,255,0.035); border-radius: 12px; }
QPushButton#bm { background: transparent; border-radius: 8px; padding: 4px 10px; }
QPushButton#bm:hover { background: rgba(255,255,255,0.13); }
QPushButton#bm[drop="before"] { border-left: 3px solid #8b98ff; border-radius: 0; }
QPushButton#bm[drop="after"] { border-right: 3px solid #8b98ff; border-radius: 0; }
QPushButton#bm[drop="group"] { background: rgba(255,209,102,0.28); }
QLabel#dim { color: #7f86aa; font-size: 12px; }
QLabel#sect { color: #aab4ff; font-size: 12px; font-weight: 700; padding: 6px 4px 2px 4px; }
QLabel#status { color: #9aa0c4; font-size: 12px; }

QLineEdit { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
    padding: 6px 12px; selection-background-color: #7c8cff; }
QLineEdit:focus { border: 1px solid #7c8cff; background: rgba(124,140,255,0.10); }
QAbstractItemView QLineEdit { background: #262a4a; border: 1px solid #7c8cff; border-radius: 4px; padding: 0 4px; }
QAbstractItemView QLineEdit:focus { background: #262a4a; border: 1px solid #7c8cff; }
QPushButton, QToolButton { background: rgba(255,255,255,0.07); border: none; border-radius: 9px; padding: 6px 12px; }
QPushButton:hover, QToolButton:hover { background: rgba(255,255,255,0.15); }
QPushButton:checked { background: #5b6cff; }
QPushButton#accent { background: #5b6cff; }
QPushButton#accent:hover { background: #6f7eff; }
QToolButton#nav { padding: 6px 9px; min-width: 16px; }
QToolButton#tabclose { background: transparent; padding: 0 4px; border-radius: 6px; color: #9aa0c4; }
QToolButton#tabclose:hover { background: rgba(255,255,255,0.18); color: white; }

QTabBar::tab { background: rgba(255,255,255,0.05); padding: 6px 12px; margin-right: 3px; border-radius: 9px;
    min-width: 60px; max-width: 200px; }
QTabBar::tab:hover { background: rgba(255,255,255,0.11); }
QTabBar::tab:selected { background: rgba(124,140,255,0.32); }

QTreeView, QTreeWidget, QListWidget { background: transparent; border: none; outline: 0; alternate-background-color: rgba(255,255,255,0.02); }
QTreeView::item { padding: 4px 2px; }
QTreeWidget::item, QListWidget::item { padding: 4px 2px; border-radius: 7px; }
QTreeView::item:hover, QTreeWidget::item:hover, QListWidget::item:hover { background: rgba(255,255,255,0.07); }
QTreeView::item:selected, QTreeWidget::item:selected, QListWidget::item:selected { background: rgba(124,140,255,0.32); color: white; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section { background: transparent; border: none; color: #8a90b0; padding: 6px 8px; font-size: 12px; }
QTreeView QTableCornerButton::section { background: transparent; border: none; }
QHeaderView::section:hover { color: white; }

QMenu { background: #1e2140; border: 1px solid #333863; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 24px; border-radius: 6px; }
QMenu::item:selected { background: #5b6cff; }
QMenu::separator { height: 1px; background: #333863; margin: 5px 8px; }
QDialog, QMessageBox, QInputDialog { background: #171a2b; }
QComboBox { background: #262a4a; color: #ffffff; border: 1px solid #4a5090; border-radius: 8px; padding: 6px 12px; min-width: 110px; }
QComboBox QLineEdit { background: transparent; border: none; padding: 0; color: #ffffff; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #1e2140; color: #e8eaf6; border: 1px solid #333863;
    selection-background-color: #5b6cff; selection-color: #ffffff; outline: 0; }
QDialog QLabel, QMessageBox QLabel { background: transparent; }
QToolTip { background: #1e2140; color: #e8eaf6; border: 1px solid #4a5090; padding: 4px 8px; }
QProgressBar { background: rgba(255,255,255,0.08); border: none; border-radius: 6px; height: 12px; text-align: center; font-size: 10px; }
QProgressBar::chunk { background: #7c8cff; border-radius: 6px; }
QSplitter::handle { background: transparent; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.2); border-radius: 5px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: rgba(139,152,255,0.7); }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: rgba(255,255,255,0.2); border-radius: 5px; min-width: 36px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""

_provider = QFileIconProvider()
MIME_BM = "application/x-jy-bookmark"
LAUNCHER_SERVER = "JYLauncher-single-instance"


def dir_exists(path, timeout=5.0):
    """네트워크(UNC) 경로는 서버가 죽어 있으면 isdir 가 오래 멈추므로 시간 제한을 둠"""
    if not path.startswith("\\\\"):
        return os.path.isdir(path)
    res = [False]
    th = threading.Thread(target=lambda: res.__setitem__(0, os.path.isdir(path)), daemon=True)
    th.start()
    th.join(timeout)
    return res[0]


def drive_label(path):
    """네트워크 드라이브는 'Z:  \\\\서버\\공유' 처럼 원래 주소를 같이 표시"""
    try:
        if ctypes.windll.kernel32.GetDriveTypeW(path) == 4:  # DRIVE_REMOTE
            buf = ctypes.create_unicode_buffer(512)
            n = ctypes.c_ulong(512)
            if ctypes.windll.mpr.WNetGetConnectionW(path[:2], buf, ctypes.byref(n)) == 0:
                return f"{path[:2]}  {buf.value}"
    except Exception:
        pass
    return path


def credential_targets():
    """Windows 자격 증명 관리자에 저장된 서버 목록 (cmdkey /list). 저장된 계정으로 자동 로그인됨"""
    try:
        r = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, errors="ignore",
                           creationflags=0x08000000, timeout=10)
    except Exception:
        return []
    out = []
    for m in re.finditer(r"target=(\S+)", r.stdout, re.I):
        v = m.group(1)
        low = v.lower()
        if low.startswith(("microsoftaccount", "virtualapp", "windowslive", "sso_pop", "termsrv/", "git:", "adobe")) \
                or "://" in v:
            continue
        if v not in out:
            out.append(v)
    return out


def free_drive_letters():
    used = {d.absolutePath()[:2].upper() for d in QDir.drives()}
    return [f"{c}:" for c in "ZYXWVUTSRQPONMLKJIHGFED" if f"{c}:" not in used]


def fmt_size(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def tab_title(path):
    if not path:
        return "내 PC"
    name = os.path.basename(path.rstrip("\\/"))
    return name or path.rstrip("\\/") or path


def dark_titlebar(widget):
    try:
        v = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(widget.winId()), 20, ctypes.byref(v), 4)
    except Exception:
        pass


# ───────────────────────── 파일 뷰 ─────────────────────────
class FSModel(QFileSystemModel):
    HEADERS = ("이름", "크기", "종류", "수정한 날짜")

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and section < len(self.HEADERS):
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)


class FileView(QTreeView):
    pathChanged = Signal(str)
    newTabRequested = Signal(str)
    dropped = Signal(list, str, bool, bool)      # 경로들, 대상 폴더, Ctrl, Shift
    menuRequested = Signal(object, list)         # 전역 좌표, 선택 경로
    keyAction = Signal(str)
    selectionSummary = Signal()

    COLS = {0: 420, 1: 100, 2: 140, 3: 160}      # 열 너비 (모든 탭 공용, 사용자가 바꾸면 explorer.json 에 저장)
    on_cols_changed = None

    def __init__(self, path, show_hidden=False):
        super().__init__()
        self.pinned = False
        self._filter = []
        self._edit_closed = 0.0
        self.hist, self.hi = [], -1
        self.path = ""
        self.model_ = FSModel(self)
        self.model_.setReadOnly(False)
        self.set_hidden(show_hidden)
        self.setModel(self.model_)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setRootIsDecorated(False)
        self.setItemsExpandable(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setIconSize(QSize(20, 20))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.doubleClicked.connect(self.activate)
        self.setExpandsOnDoubleClick(False)
        h = self.header()
        h.setStretchLastSection(True)
        h.setSectionsMovable(False)
        h.setMinimumSectionSize(40)
        for c, w in self.COLS.items():          # 모든 열을 마우스로 늘이고 줄일 수 있음
            h.setSectionResizeMode(c, QHeaderView.Interactive)
            h.resizeSection(c, w)
        h.sectionResized.connect(self._col_resized)
        self.sortByColumn(0, Qt.AscendingOrder)
        # 이름 검색: 폴더 표시 방식 대신 행을 숨김 → 목록이 (비동기로) 채워지거나 바뀔 때마다 다시 적용
        for sig in (self.model_.rowsInserted, self.model_.layoutChanged, self.model_.directoryLoaded):
            sig.connect(self._schedule_filter)
        self._filter_t = QTimer(self, singleShot=True, interval=0)
        self._filter_t.timeout.connect(self._apply_filter)
        self.itemDelegate().closeEditor.connect(lambda *_: setattr(self, "_edit_closed", time.monotonic()))
        self.navigate(path)

    def _col_resized(self, col, _old, new):
        if col < 3 and new != self.COLS[col]:        # 마지막 열은 남는 폭을 채우므로 저장하지 않음
            FileView.COLS[col] = new
            if FileView.on_cols_changed:
                FileView.on_cols_changed()

    def set_hidden(self, on):
        f = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.System
        self.model_.setFilter(f | QDir.Hidden if on else f)

    # ---- 탐색 ----
    def navigate(self, path, record=True):
        path = os.path.normpath(path) if path else ""
        if path and not dir_exists(path):
            return False
        if path and len(path) == 2 and path[1] == ":":
            path += "\\"
        idx = self.model_.setRootPath(path)
        self.setRootIndex(idx if path else self.model_.index(""))
        self.path = path
        if record:
            del self.hist[self.hi + 1:]
            if not self.hist or self.hist[-1] != path:
                self.hist.append(path)
            self.hi = len(self.hist) - 1
        self.clearSelection()
        self._filter_t.start()          # 검색어가 있으면 새 폴더에도 적용, 없으면 예전에 숨긴 행을 되살림
        self.pathChanged.emit(path)
        return True

    def back(self):
        if self.hi > 0:
            self.hi -= 1
            self.navigate(self.hist[self.hi], record=False)

    def forward(self):
        if self.hi < len(self.hist) - 1:
            self.hi += 1
            self.navigate(self.hist[self.hi], record=False)

    def up(self):
        if not self.path:
            return
        parent = os.path.dirname(self.path.rstrip("\\/"))
        if not parent or parent == self.path.rstrip("\\/") or (len(self.path) <= 3 and self.path[1:2] == ":"):
            self.navigate("")  # 드라이브 루트에서 위로 → 내 PC
        else:
            self.navigate(parent)

    def set_filter(self, text):
        """이름에 검색어가 '포함'된 항목만 표시 (대소문자 무시, 폴더도 포함, 공백으로 여러 단어 = 모두 포함)"""
        self._filter = text.lower().split()
        self._apply_filter()

    def _schedule_filter(self, *_):
        if self._filter or self._hidden_by_filter:
            self._filter_t.start()

    _hidden_by_filter = False

    def _apply_filter(self):
        root = self.rootIndex()
        model = self.model_
        words = self._filter
        for r in range(model.rowCount(root)):
            name = model.index(r, 0, root).data(Qt.DisplayRole) or ""
            low = name.lower()
            self.setRowHidden(r, root, bool(words) and not all(w in low for w in words))
        self._hidden_by_filter = bool(words)
        self.selectionSummary.emit()

    def visible_count(self):
        root = self.rootIndex()
        return sum(1 for r in range(self.model_.rowCount(root)) if not self.isRowHidden(r, root))

    def selected_paths(self):
        seen, out = set(), []
        for i in self.selectionModel().selectedRows(0):
            p = self.model_.filePath(i)
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def activate(self, idx):
        p = self.model_.filePath(idx.siblingAtColumn(0))
        if os.path.isdir(p):
            self.navigate(p)
        else:
            try:
                os.startfile(p)
            except OSError as e:
                QMessageBox.warning(self, "열 수 없음", str(e))

    def start_rename(self):
        idx = self.currentIndex()
        if idx.isValid():
            self.edit(idx.siblingAtColumn(0))

    def select_path(self, path, rename=False):
        idx = self.model_.index(path)
        if idx.isValid():
            self.setCurrentIndex(idx)
            self.selectionModel().select(idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            self.scrollTo(idx)
            if rename:
                self.edit(idx)
            return True
        return False

    # ---- 입력 ----
    def keyPressEvent(self, e):
        k, m = e.key(), e.modifiers()
        ctrl, shift = bool(m & Qt.ControlModifier), bool(m & Qt.ShiftModifier)
        if k in (Qt.Key_Return, Qt.Key_Enter) and (self.state() == QAbstractItemView.EditingState
                                                   or time.monotonic() - self._edit_closed < 0.4):
            e.accept()          # 이름 바꾸기 입력을 확정한 Enter 가 '실행'으로 이어지지 않게
            return
        if k in (Qt.Key_Return, Qt.Key_Enter) and not (ctrl or shift):
            for p in (self.selected_paths() or []):
                if os.path.isdir(p) and len(self.selected_paths()) == 1:
                    self.navigate(p)
                else:
                    try:
                        os.startfile(p)
                    except OSError:
                        pass
        elif k == Qt.Key_Backspace or (k == Qt.Key_Up and m & Qt.AltModifier):
            self.up()
        elif k == Qt.Key_Left and m & Qt.AltModifier:
            self.back()
        elif k == Qt.Key_Right and m & Qt.AltModifier:
            self.forward()
        elif ctrl and k == Qt.Key_C:
            self.keyAction.emit("copy")
        elif ctrl and k == Qt.Key_X:
            self.keyAction.emit("cut")
        elif ctrl and k == Qt.Key_V:
            self.keyAction.emit("paste")
        elif ctrl and shift and k == Qt.Key_N:
            self.keyAction.emit("newfolder")
        elif k == Qt.Key_Delete:
            self.keyAction.emit("permdelete" if shift else "delete")
        else:
            super().keyPressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                p = self.model_.filePath(idx.siblingAtColumn(0))
                if os.path.isdir(p):
                    self.newTabRequested.emit(p)
            return
        super().mouseReleaseEvent(e)

    def selectionChanged(self, a, b):
        super().selectionChanged(a, b)
        self.selectionSummary.emit()

    def _menu(self, pos):
        idx = self.indexAt(pos)
        if idx.isValid() and not self.selectionModel().isSelected(idx):
            self.setCurrentIndex(idx)
        self.menuRequested.emit(self.viewport().mapToGlobal(pos), self.selected_paths())

    # ---- 드래그 & 드롭 (모델 기본 동작은 파일을 지워버릴 수 있어 직접 처리) ----
    def startDrag(self, actions):
        idxs = [i for i in self.selectedIndexes() if i.column() == 0]
        if not idxs:
            return
        mime = self.model_.mimeData(idxs)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)  # 결과는 무시: 원본 삭제를 모델에 맡기지 않음

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if not e.mimeData().hasUrls():
            e.ignore()
            return
        idx = self.indexAt(e.position().toPoint())
        target = self.path
        if idx.isValid():
            p = self.model_.filePath(idx.siblingAtColumn(0))
            if os.path.isdir(p):
                target = p
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        mods = QGuiApplication.keyboardModifiers()
        e.setDropAction(Qt.CopyAction)
        e.accept()
        if target and paths:
            self.dropped.emit(paths, target, bool(mods & Qt.ControlModifier), bool(mods & Qt.ShiftModifier))


# ───────────────────────── 패널 (탭 묶음) ─────────────────────────
class Pane(QFrame):
    activated = Signal(object)
    changed = Signal()
    statusChanged = Signal()

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setObjectName("panel")
        self.setProperty("active", False)
        self.setProperty("split", False)
        self.views = {}
        self._next = 1
        self.side = "왼쪽"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.badge = QLabel("")
        self.badge.hide()
        lay.addWidget(self.badge, 0, Qt.AlignLeft)
        nav = QHBoxLayout()
        nav.setSpacing(4)
        self.btn_back, self.btn_fwd, self.btn_up = (self._nav_btn(t, tip) for t, tip in
                                                    (("◀", "뒤로 (Alt+←)"), ("▶", "앞으로 (Alt+→)"), ("▲", "위로 (Backspace)")))
        self.btn_back.clicked.connect(lambda: self.view() and self.view().back())
        self.btn_fwd.clicked.connect(lambda: self.view() and self.view().forward())
        self.btn_up.clicked.connect(lambda: self.view() and self.view().up())
        self.pathbar = QLineEdit()
        self.pathbar.returnPressed.connect(self._go)
        self.star = self.pathbar.addAction(star_icon(False), QLineEdit.TrailingPosition)
        self.star.triggered.connect(lambda: self.main.toggle_bookmark(self.view().path if self.view() else ""))
        self.btn_new = self._nav_btn("+", "새 탭 (Ctrl+T)")
        self.btn_new.clicked.connect(lambda: self.add_tab(self.view().path if self.view() else HOME))
        for w in (self.btn_back, self.btn_fwd, self.btn_up):
            nav.addWidget(w)
        nav.addWidget(self.pathbar, 1)
        nav.addWidget(self.btn_new)
        lay.addLayout(nav)

        self.tabbar = QTabBar()
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDrawBase(False)
        self.tabbar.setElideMode(Qt.ElideRight)
        self.tabbar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabbar.customContextMenuRequested.connect(self._tab_menu)
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.tabbar.tabBarDoubleClicked.connect(lambda i: self.add_tab(self.view().path if self.view() else HOME)
                                                if i < 0 else None)
        self.tabbar.installEventFilter(self)
        lay.addWidget(self.tabbar)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

    def _nav_btn(self, text, tip):
        b = QToolButton()
        b.setObjectName("nav")
        b.setText(text)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def eventFilter(self, obj, e):
        if obj is self.tabbar and e.type() == e.Type.MouseButtonRelease and e.button() == Qt.MiddleButton:
            i = self.tabbar.tabAt(e.position().toPoint())
            if i >= 0:
                self.close_tab(self.tabbar.tabData(i))
                return True
        if obj is self.tabbar and e.type() == e.Type.MouseButtonDblClick and self.tabbar.tabAt(e.position().toPoint()) < 0:
            self.add_tab(self.view().path if self.view() else HOME)
            return True
        return super().eventFilter(obj, e)

    # ---- 탭 관리 ----
    def view(self):
        w = self.stack.currentWidget()
        return w if isinstance(w, FileView) else None

    def _index_of(self, vid):
        for i in range(self.tabbar.count()):
            if self.tabbar.tabData(i) == vid:
                return i
        return -1

    def add_tab(self, path, pinned=False, activate=True):
        v = FileView(path, self.main.show_hidden)
        vid = self._next
        self._next += 1
        self.views[vid] = v
        v.pinned = pinned
        v.pathChanged.connect(lambda p, vid=vid: self._path_changed(vid, p))
        v.newTabRequested.connect(lambda p: self.add_tab(p, activate=False))
        v.dropped.connect(self.main.on_drop)
        v.menuRequested.connect(lambda pos, paths, v=v: self.main.show_file_menu(self, v, pos, paths))
        v.keyAction.connect(lambda a, v=v: self.main.key_action(a, self, v))
        v.selectionSummary.connect(self.statusChanged)
        self.stack.addWidget(v)
        i = self.tabbar.addTab(tab_title(v.path))
        self.tabbar.setTabData(i, vid)
        self.tabbar.setTabToolTip(i, v.path or "내 PC")
        self._refresh_tab(vid)
        if self.tabbar.currentIndex() == i:  # 첫 탭은 데이터 설정 전에 이미 선택돼 신호를 놓침
            self._tab_changed(i)
        if pinned:
            self.tabbar.moveTab(i, self._pinned_count() - 1)
        if activate:
            self.tabbar.setCurrentIndex(self._index_of(vid))
        self.changed.emit()
        return v

    def _pinned_count(self):
        return sum(1 for v in self.views.values() if v.pinned)

    def _refresh_tab(self, vid):
        i = self._index_of(vid)
        v = self.views[vid]
        if i < 0:
            return
        self.tabbar.setTabText(i, ("◆ " if v.pinned else "") + tab_title(v.path))
        self.tabbar.setTabToolTip(i, v.path or "내 PC")
        if v.pinned:
            self.tabbar.setTabButton(i, QTabBar.RightSide, None)
        else:
            b = QToolButton()
            b.setObjectName("tabclose")
            b.setText("×")
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, vid=vid: self.close_tab(vid))
            self.tabbar.setTabButton(i, QTabBar.RightSide, b)

    def update_star(self):
        v = self.view()
        on = bool(v) and self.main.is_bookmarked(v.path)
        self.star.setIcon(star_icon(on))
        self.star.setToolTip("북마크 해제 (Ctrl+D)" if on else "이 폴더를 북마크에 추가 (Ctrl+D)")

    def _path_changed(self, vid, path):
        self._refresh_tab(vid)
        if self.view() is self.views.get(vid):
            self.pathbar.setText(path or "내 PC")
            self.update_star()
            self.statusChanged.emit()
        self.changed.emit()

    def _tab_changed(self, i):
        vid = self.tabbar.tabData(i) if i >= 0 else None
        v = self.views.get(vid)
        if v:
            self.stack.setCurrentWidget(v)
            self.pathbar.setText(v.path or "내 PC")
            self.update_star()
            self.statusChanged.emit()
        self.changed.emit()

    def current_vid(self):
        i = self.tabbar.currentIndex()
        return self.tabbar.tabData(i) if i >= 0 else None

    def close_tab(self, vid, force=False):
        v = self.views.get(vid)
        if v is None or (v.pinned and not force):
            return
        if len(self.views) == 1:  # 마지막 탭은 닫지 않고 홈으로
            v.navigate(HOME)
            return
        i = self._index_of(vid)
        self.tabbar.removeTab(i)
        self.stack.removeWidget(v)
        v.deleteLater()
        del self.views[vid]
        self.changed.emit()

    def close_current(self):
        if self.view():
            vid = next(k for k, x in self.views.items() if x is self.view())
            self.close_tab(vid)

    def toggle_pin(self, vid):
        v = self.views[vid]
        v.pinned = not v.pinned
        self._refresh_tab(vid)
        i = self._index_of(vid)
        n = self._pinned_count()
        self.tabbar.moveTab(i, n - 1 if v.pinned else n)
        self._refresh_tab(vid)
        self.changed.emit()

    def cycle(self, d):
        n = self.tabbar.count()
        if n > 1:
            self.tabbar.setCurrentIndex((self.tabbar.currentIndex() + d) % n)

    def _tab_menu(self, pos):
        i = self.tabbar.tabAt(pos)
        m = QMenu(self)
        if i >= 0:
            vid = self.tabbar.tabData(i)
            v = self.views[vid]
            m.addAction("탭 고정 해제" if v.pinned else "탭 고정", lambda: self.toggle_pin(vid))
            m.addAction("탭 복제", lambda: self.add_tab(v.path))
            m.addAction("이 탭을 북마크에", lambda: v.path and self.main.add_bookmark(v.path))
            m.addAction("반대편 패널로 보내기  (Ctrl+Alt+←/→)", lambda: self.main.send_tab_to_other(self, vid))
            if not v.pinned:
                m.addAction("탭 닫기", lambda: self.close_tab(vid))
            others = [k for k, x in self.views.items() if k != vid and not x.pinned]
            if others:
                m.addAction("다른 탭 모두 닫기", lambda: [self.close_tab(k) for k in others])
            m.addSeparator()
        m.addAction("새 탭", lambda: self.add_tab(self.view().path if self.view() else HOME))
        m.exec(QCursor.pos())

    def _go(self):
        t = self.pathbar.text().strip().strip('"')
        v = self.view()
        if not v:
            return
        if t in ("", "내 PC"):
            v.navigate("")
        elif os.path.isdir(os.path.expandvars(t)):
            v.navigate(os.path.expandvars(t))
        else:
            self.pathbar.setText(v.path or "내 PC")
            self.main.say("존재하지 않는 경로입니다")
        v.setFocus()

    def set_active(self, on, split=None):
        """on: 활성 여부, split: 2개 보기 중인지 (표시 스타일용)"""
        if split is not None:
            self.setProperty("split", split)
            self.badge.setVisible(split)
        self.setProperty("active", bool(on))
        if self.property("split"):
            self.badge.setText(f"{self.side} 패널 · 선택됨 (새 탭이 여기에 열림)" if on else f"{self.side} 패널")
            self.badge.setObjectName("badge" if on else "badgeoff")
            self.badge.adjustSize()
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)
        for w in (self, *self.findChildren(QTabBar)):
            w.style().unpolish(w)
            w.style().polish(w)

    # ---- 상태 저장/복원 ----
    def state(self):
        order = [self.tabbar.tabData(i) for i in range(self.tabbar.count())]
        return {"tabs": [{"path": self.views[k].path, "pinned": self.views[k].pinned} for k in order],
                "current": self.tabbar.currentIndex()}

    def restore(self, st):
        for vid in list(self.views):
            v = self.views.pop(vid)
            self.stack.removeWidget(v)
            v.deleteLater()
        while self.tabbar.count():
            self.tabbar.removeTab(0)
        for t in st.get("tabs", []):
            p = t.get("path", "")
            if p and not os.path.isdir(p):
                p = HOME
            self.add_tab(p, t.get("pinned", False), activate=False)
        if not self.views:
            self.add_tab(HOME)
        self.tabbar.setCurrentIndex(max(0, min(st.get("current", 0), self.tabbar.count() - 1)))


# ───────────────────────── 사이드바: 빠른 이동 + 북마크 ─────────────────────────
class QuickList(QListWidget):
    """빠른 이동: 기본 폴더 + 내가 추가한 폴더/네트워크 + 드라이브"""
    openPath = Signal(str, bool)   # 경로, 새 탭 여부
    menuAt = Signal(object, object)  # 사용자 추가 항목(dict, 없으면 None), 전역 좌표

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.NoFocus)
        self.setIconSize(QSize(20, 20))
        self.custom = []
        self.names = {}     # 기본 항목(바탕화면/드라이브 등)의 이름 바꾸기 기록 {경로: 이름}
        self.itemClicked.connect(lambda it: self.openPath.emit(it.data(Qt.UserRole), False))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, pos):
        it = self.itemAt(pos)
        entry = None
        if it is not None:
            idx = it.data(Qt.UserRole + 1)
            if isinstance(idx, int) and 0 <= idx < len(self.custom):
                entry = self.custom[idx]            # 내가 추가한 항목
            else:                                   # 기본 항목(내 PC, 바탕화면, 드라이브 …)도 이름 변경 가능
                entry = {"name": it.text(), "path": it.data(Qt.UserRole), "builtin": True}
        self.menuAt.emit(entry, self.viewport().mapToGlobal(pos))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            it = self.itemAt(e.position().toPoint())
            if it:
                self.openPath.emit(it.data(Qt.UserRole), True)
            return
        super().mouseReleaseEvent(e)

    def refresh(self, custom=None, names=None):
        if custom is not None:
            self.custom = custom
        if names is not None:
            self.names = names
        self.clear()

        def add(name, path, icon, idx=-1, tip=""):
            it = QListWidgetItem(self.names.get(os.path.normcase(path), name))
            it.setData(Qt.UserRole, path)
            it.setData(Qt.UserRole + 1, idx)
            it.setIcon(icon)
            it.setToolTip(tip or path)
            self.addItem(it)
        add("내 PC", "", _provider.icon(QFileIconProvider.Computer))
        for name, sub in (("바탕화면", "Desktop"), ("다운로드", "Downloads"), ("문서", "Documents"),
                          ("사진", "Pictures")):
            p = os.path.join(HOME, sub)
            if os.path.isdir(p):
                add(name, p, _provider.icon(QFileInfo(p)))
        for i, c in enumerate(self.custom):
            icon = _provider.icon(QFileIconProvider.Network) if c.get("net") else _provider.icon(QFileIconProvider.Folder)
            add(c["name"], c["path"], icon, i)
        for d in QDir.drives():
            p = d.absolutePath().replace("/", "\\")
            add(drive_label(p), p, _provider.icon(QFileInfo(p)), tip=p)
        row = max(self.sizeHintForRow(0), 26)
        self.setFixedHeight(min(self.count(), 16) * row + 12)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)


def pair_icon():
    """세트 북마크(왼쪽/오른쪽 폴더 2개) 아이콘: 폴더 아이콘 두 개를 나란히"""
    f = _provider.icon(QFileIconProvider.Folder).pixmap(QSize(18, 18))
    pm = QPixmap(38, 18)
    pm.fill(Qt.transparent)
    pt = QPainter(pm)
    pt.drawPixmap(0, 0, f)
    pt.drawPixmap(20, 0, f)
    pt.end()
    return QIcon(pm)


def star_icon(on):
    """경로줄 별 아이콘: 북마크됨=노란 별, 아니면 빈 별 (폰트 글자에 의존하지 않고 직접 그림)"""
    pm = QPixmap(40, 40)
    pm.fill(Qt.transparent)
    pt = QPainter(pm)
    pt.setRenderHint(QPainter.Antialiasing)
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = 17 if i % 2 == 0 else 7.4
        pts.append(QPointF(20 + r * math.cos(ang), 21.5 + r * math.sin(ang)))
    if on:
        pt.setBrush(QColor("#ffd166"))
        pt.setPen(QPen(QColor("#ffd166"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    else:
        pt.setBrush(Qt.NoBrush)
        pt.setPen(QPen(QColor("#9aa0c4"), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    pt.drawPolygon(QPolygonF(pts))
    pt.end()
    return QIcon(pm)


class BmMenu(QMenu):
    """크롬 북마크 폴더 드롭다운: 좌클릭=열기, 가운데 클릭=새 탭, 우클릭=그 항목의 메뉴(모두 열기·수정·삭제 …)"""

    def __init__(self, bar, parent=None):
        super().__init__(parent)
        self.bar = bar
        self.nodes = {}          # QAction → 북마크 노드

    def mouseReleaseEvent(self, e):
        act = self.actionAt(e.position().toPoint())
        node = self.nodes.get(act)
        if node is not None and e.button() in (Qt.RightButton, Qt.MiddleButton):
            pos, btn, bar = e.globalPosition().toPoint(), e.button(), self.bar
            w = QApplication.activePopupWidget()          # 열려 있는 드롭다운을 모두 닫고
            while w is not None:
                w.close()
                w = QApplication.activePopupWidget()
            if btn == Qt.RightButton:
                QTimer.singleShot(0, lambda: bar.menuAt.emit(node, pos))
            elif node["type"] == "bookmark":
                QTimer.singleShot(0, lambda: bar.openPair.emit(node) if node.get("path2")
                                  else bar.openPath.emit(node["path"], True))
            else:
                QTimer.singleShot(0, lambda: bar.openFolderAsTabs.emit(node))
            e.accept()
            return
        super().mouseReleaseEvent(e)


class BmButton(QPushButton):
    dragRequested = Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self._press = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press is not None and e.buttons() & Qt.LeftButton \
                and (e.position().toPoint() - self._press).manhattanLength() > 10:
            self._press = None
            self.dragRequested.emit(self)
            self.setDown(False)
            return
        super().mouseMoveEvent(e)


class BookmarksBar(QFrame):
    """크롬처럼 화면 위쪽에 한 줄로 뜨는 북마크 바.
    폴더는 눌러서 펼침, 넘치면 » 메뉴, 드래그로 순서 변경(가장자리) / 폴더로 묶기(가운데), 오른쪽 + 로 추가."""
    openPath = Signal(str, bool)          # 경로, 새 탭 여부
    openFolderAsTabs = Signal(object)     # 폴더 노드
    menuAt = Signal(object, object)       # 노드(빈 곳/+ 버튼이면 None), 전역 좌표
    dirsDropped = Signal(list, object)    # 드롭된 폴더 경로들, 대상 폴더 노드(없으면 None)
    openPair = Signal(object)             # 세트 북마크(양쪽 패널에 열기)
    nodeDropped = Signal(object, object, str)   # 끌어온 노드, 대상 노드(없으면 None=맨 끝), 위치(before/after/group)

    def __init__(self):
        super().__init__()
        self.setObjectName("bmbar")
        self.setFixedHeight(42)
        self.setAcceptDrops(True)
        self.root = {"children": []}
        self.items = []                   # (버튼, 노드)
        self.icons_only = False
        self.folder_click_opens = False  # 기본(크롬처럼): 폴더 클릭 = 목록 펼치기. True 면 클릭 = 안의 북마크 모두 탭으로
        self._drag = None
        self.more = QPushButton("»", self)
        self.more.setObjectName("bm")
        self.more.setFocusPolicy(Qt.NoFocus)
        self.more.clicked.connect(self._more_menu)
        self.more.hide()
        self.add_btn = QPushButton("+", self)
        self.add_btn.setObjectName("bm")
        self.add_btn.setFocusPolicy(Qt.NoFocus)
        self.add_btn.setToolTip("북마크 추가")
        self.add_btn.clicked.connect(lambda: self.menuAt.emit(None, self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft())))
        self.hint = QLabel("북마크가 없습니다 — 경로줄 오른쪽 별이나 오른쪽 + 로 추가하세요", self)
        self.hint.setObjectName("dim")
        self._hidden = []

    def load(self, root):
        self.root = root
        self.render()

    def render(self):
        for b, _ in self.items:
            b.deleteLater()
        self.items = []
        for n in self.root["children"]:
            b = BmButton(self)
            b.setObjectName("bm")
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("drop", "")
            name = n["name"] if len(n["name"]) <= 18 else n["name"][:17] + "…"
            b.setText("" if self.icons_only else name)
            b.setIconSize(QSize(18, 18))
            if n["type"] == "folder":
                b.setIcon(_provider.icon(QFileIconProvider.Folder))
                cnt = sum(1 for _ in self._leaves(n["children"]))
                b.setToolTip(n["name"] + (f"\n클릭: 안의 북마크 {cnt}개를 탭으로 한 번에 열기\nShift+클릭: 목록 보기"
                                          if self.folder_click_opens else f"\n클릭: 북마크 {cnt}개 목록\n우클릭: 모두 탭으로 열기 등"))
            elif n.get("path2"):                                   # 세트 북마크: 폴더 2개
                b.setIcon(pair_icon())
                b.setIconSize(QSize(38, 18))
                b.setToolTip(f"{n['name']}\n왼쪽: {n['path']}\n오른쪽: {n['path2']}\n클릭: 2개 보기로 양쪽 패널에 각각 열기")
                if not (os.path.exists(n["path"]) and os.path.exists(n["path2"])):
                    b.setStyleSheet("color:#ff9a9a;")
            else:
                b.setToolTip(n["name"] + "\n" + n["path"])
                b.setIcon(_provider.icon(QFileInfo(n["path"])) if os.path.exists(n["path"])
                          else _provider.icon(QFileIconProvider.Folder))
                if not os.path.exists(n["path"]):
                    b.setStyleSheet("color:#ff9a9a;")
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, n=n, b=b: self.menuAt.emit(n, b.mapToGlobal(pos)))
            b.clicked.connect(lambda _=False, n=n, b=b: self._click(n, b))
            b.dragRequested.connect(lambda btn, n=n: self.start_drag(n, btn))
            b.installEventFilter(self)
            b.show()
            self.items.append((b, n))
        self.hint.setVisible(not self.items)
        self.hint.move(14, 12)
        self.relayout()

    # ---- 배치 (넘치면 » 로, 오른쪽 끝에 + ) ----
    def relayout(self):
        x, avail, more_w = 8, self.width() - 8 - 40, 40
        self._hidden = []
        for i, (b, n) in enumerate(self.items):
            w = b.sizeHint().width()
            last = i == len(self.items) - 1
            fits = not self._hidden and (x + w <= avail - (0 if last else more_w) or x + w <= avail and last)
            if fits:
                b.setGeometry(x, 5, w, 32)
                b.show()
                x += w + 4
            else:
                b.hide()
                self._hidden.append(n)
        if self._hidden:
            self.more.setGeometry(x, 5, 34, 32)
            self.more.show()
        else:
            self.more.hide()
        self.add_btn.setGeometry(self.width() - 40, 5, 32, 32)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    # ---- 동작 ----
    def _leaves(self, kids):
        for c in kids:
            if c["type"] == "bookmark":
                yield c
            else:
                yield from self._leaves(c["children"])

    def _click(self, n, b):
        if n["type"] == "bookmark":
            if n.get("path2"):
                self.openPair.emit(n)
            else:
                self.openPath.emit(n["path"], False)
        elif self.folder_click_opens and not (QGuiApplication.keyboardModifiers() & Qt.ShiftModifier):
            self.openFolderAsTabs.emit(n)             # 폴더 한 번 클릭 = 안의 북마크 전부를 각각 탭으로
        else:
            self._folder_menu(n).exec(b.mapToGlobal(b.rect().bottomLeft()))

    def _fill_menu(self, m, kids):
        folder_icon = _provider.icon(QFileIconProvider.Folder)
        for c in kids:
            if c["type"] == "bookmark":
                a = m.addAction(pair_icon() if c.get("path2") else folder_icon, c["name"])
                a.triggered.connect(lambda _=False, c=c: self.openPair.emit(c) if c.get("path2")
                                    else self.openPath.emit(c["path"], False))
            else:
                sub = BmMenu(self, m)
                sub.setTitle(c["name"])
                sub.setIcon(folder_icon)
                a = m.addMenu(sub)
                self._folder_menu(c, sub)
            m.nodes[a] = c

    def _folder_menu(self, n, m=None):
        """폴더를 누르면 안의 북마크들이 목록으로 뜸 (크롬과 동일). 모두 열기 등은 폴더 우클릭 메뉴에 있음"""
        m = m or BmMenu(self)
        if not n["children"]:
            m.addAction("(비어 있음)").setEnabled(False)
        self._fill_menu(m, n["children"])
        return m

    def _more_menu(self):
        m = BmMenu(self)
        self._fill_menu(m, self._hidden)
        m.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def eventFilter(self, obj, e):
        if e.type() == e.Type.MouseButtonRelease and e.button() == Qt.MiddleButton:
            for b, n in self.items:
                if b is obj:
                    if n["type"] == "bookmark":
                        self.openPair.emit(n) if n.get("path2") else self.openPath.emit(n["path"], True)
                    else:
                        self.openFolderAsTabs.emit(n)
                    return True
        return super().eventFilter(obj, e)

    def contextMenuEvent(self, e):
        self.menuAt.emit(None, e.globalPos())

    # ---- 드래그로 정렬 / 폴더로 묶기 ----
    def start_drag(self, node, btn):
        self._drag = node
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_BM, b"1")
        drag.setMimeData(mime)
        pm = btn.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(pm.rect().center())
        drag.exec(Qt.MoveAction)
        self._drag = None
        self._mark(None, "")

    def _zone_at(self, pos):
        for b, n in self.items:
            if b.isVisible() and b.geometry().contains(pos):
                x = (pos.x() - b.x()) / max(b.width(), 1)
                return b, n, ("before" if x < 0.28 else "after" if x > 0.72 else "group")
        return None, None, ""

    def _mark(self, btn, zone):
        for b, _ in self.items:
            z = zone if b is btn else ""
            if b.property("drop") != z:
                b.setProperty("drop", z)
                b.style().unpolish(b)
                b.style().polish(b)

    def _accepts(self, e):
        m = e.mimeData()
        return m.hasUrls() or m.hasFormat(MIME_BM)

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if self._accepts(e) else e.ignore()

    def dragMoveEvent(self, e):
        if not self._accepts(e):
            e.ignore()
            return
        e.acceptProposedAction()
        b, n, zone = self._zone_at(e.position().toPoint())
        if e.mimeData().hasFormat(MIME_BM):
            self._mark(b, zone)
        else:
            self._mark(b if n is not None and n["type"] == "folder" else None, "group")

    def dragLeaveEvent(self, e):
        self._mark(None, "")

    def dropEvent(self, e):
        b, n, zone = self._zone_at(e.position().toPoint())
        self._mark(None, "")
        e.setDropAction(Qt.MoveAction if e.mimeData().hasFormat(MIME_BM) else Qt.CopyAction)
        e.accept()
        if e.mimeData().hasFormat(MIME_BM):
            if self._drag is not None:
                self.nodeDropped.emit(self._drag, n, zone)
            return
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile() and os.path.isdir(u.toLocalFile())]
        if paths:
            self.dirsDropped.emit(paths, n if n is not None and n["type"] == "folder" else None)


class NetworkDialog(QDialog):
    """네트워크 위치 추가: 자격 증명 관리자에 저장된 서버를 고르면 저장된 계정으로 접속"""

    def __init__(self, parent, targets):
        super().__init__(parent)
        self.setWindowTitle("네트워크 위치 추가")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(8)
        info = QLabel("Windows 자격 증명 관리자에 저장된 계정으로 접속합니다.\n"
                      "저장된 서버를 고르거나 직접 입력하세요. (계정이 저장돼 있으면 비밀번호를 다시 묻지 않습니다)")
        info.setObjectName("dim")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addWidget(QLabel("서버 (저장된 자격 증명)"))
        self.server = QComboBox()
        self.server.setEditable(True)
        self.server.addItems(targets)
        self.server.setCurrentText("")
        self.server.lineEdit().setPlaceholderText("서버 이름 또는 IP  (예: NAS, 192.168.0.10)")
        lay.addWidget(self.server)
        lay.addWidget(QLabel("공유 폴더"))
        self.share = QLineEdit()
        self.share.setPlaceholderText("공유 이름 (비워두면 서버 전체)   예: 자료실")
        lay.addWidget(self.share)
        lay.addWidget(QLabel("표시 이름 (선택)"))
        self.name = QLineEdit()
        lay.addWidget(self.name)
        self.map_chk = QCheckBox("네트워크 드라이브로 연결 (문자 지정, 재부팅 후에도 유지)")
        lay.addWidget(self.map_chk)
        self.letter = QComboBox()
        self.letter.addItems(free_drive_letters())
        self.letter.setEnabled(False)
        self.map_chk.toggled.connect(self.letter.setEnabled)
        lay.addWidget(self.letter)
        self.preview = QLabel()
        self.preview.setObjectName("dim")
        lay.addWidget(self.preview)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("추가")
        ok.setObjectName("accent")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        self.server.editTextChanged.connect(self._upd)
        self.share.textChanged.connect(self._upd)

    def _upd(self, *_):
        self.preview.setText("주소: " + (self.path() or ""))

    def path(self):
        srv = self.server.currentText().strip()
        sh = self.share.text().strip().strip("\\/")
        if srv.startswith("\\\\"):
            return srv.rstrip("\\") + (("\\" + sh) if sh else "")
        srv = srv.strip("\\/")
        return ("\\\\" + srv + (("\\" + sh) if sh else "")) if srv else ""


# ───────────────────────── 충돌 대화상자 ─────────────────────────
class ConflictDialog(QDialog):
    def __init__(self, parent, src, dst):
        super().__init__(parent)
        self.setWindowTitle("같은 이름의 파일이 있습니다")
        self.answer = "cancel"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        t = QLabel(f"<b>{os.path.basename(dst)}</b> 이(가) 이미 있습니다.")
        lay.addWidget(t)

        def info(label, p):
            try:
                st = os.stat(p)
                return f"{label}\n{p}\n{fmt_size(st.st_size)} · {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}"
            except OSError:
                return f"{label}\n{p}"
        for label, p in (("이동/복사할 파일 (새)", src), ("대상 위치의 파일 (기존)", dst)):
            l = QLabel(info(label, p))
            l.setObjectName("dim")
            l.setWordWrap(True)
            lay.addWidget(l)
        self.all_chk = QCheckBox("이후 충돌에도 같은 처리 적용")
        lay.addWidget(self.all_chk)
        row = QHBoxLayout()
        for text, ans, name in (("덮어쓰기", "overwrite", "accent"), ("건너뛰기", "skip", ""),
                                ("이름 바꿔서 저장", "rename", ""), ("취소", "cancel", "")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(lambda _=False, a=ans: self.done_with(a))
            row.addWidget(b)
        lay.addLayout(row)
        self.setMinimumWidth(460)

    def done_with(self, a):
        self.answer = a
        self.accept()


# ───────────────────────── 백그라운드 작업 ─────────────────────────
class JobRunner(QObject):
    progress = Signal(int, int, str)
    started = Signal(str)
    finished = Signal(str, list, bool)
    conflict = Signal(str, str, object)
    queueChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.queue = []
        self.current = None
        self._cv = threading.Condition()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def submit(self, op, sources, dest):
        job = F.Job(op, sources, dest, self._resolve)
        with self._cv:
            self.queue.append(job)
            self._cv.notify()
        self.queueChanged.emit(len(self.queue) + (1 if self.current else 0))

    def cancel_all(self):
        with self._cv:
            for j in self.queue:
                j.cancel.set()
            self.queue.clear()
        if self.current:
            self.current.cancel.set()

    def _resolve(self, src, dst):
        holder = {"ev": threading.Event(), "ans": "cancel"}
        self.conflict.emit(src, dst, holder)
        holder["ev"].wait()
        return holder["ans"]

    def _loop(self):
        while True:
            with self._cv:
                while not self.queue:
                    self._cv.wait()
                job = self.queue.pop(0)
            self.current = job
            label = {"copy": "복사", "move": "이동", "delete": "삭제"}.get(job.op, "작업")
            self.started.emit(f"{label} 중…")
            ok = job.run(lambda d, t, n: self.progress.emit(d, t, n))
            self.current = None
            summary = f"{label} {'완료' if ok else '취소됨'} · 파일 {job.files_done:,}개"
            self.finished.emit(summary, job.errors, ok)
            self.queueChanged.emit(len(self.queue))


class FavImportDialog(QDialog):
    """Windows 탐색기 즐겨찾기(고정 폴더) 가져오기: 항목 선택 + 가져올 위치 + 교체 여부"""

    def __init__(self, parent, entries, have_quick, have_bm):
        super().__init__(parent)
        self.setWindowTitle("Windows 탐색기 즐겨찾기 불러오기")
        self.setMinimumSize(560, 460)
        self.entries = entries
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(8)
        info = QLabel("Windows 탐색기 '즐겨찾기'에 고정돼 있는 폴더입니다. 가져올 항목을 선택하세요.\n"
                      "기본은 지금 있는 내용을 그대로 두고 추가만 합니다. 가져오기 전에 현재 내용은 자동 백업됩니다.")
        info.setObjectName("dim")
        info.setWordWrap(True)
        lay.addWidget(info)
        from PySide6.QtWidgets import QListWidget as _LW
        self.list = _LW()
        self.have_quick, self.have_bm = have_quick, have_bm
        for e in entries:
            it = QListWidgetItem(f"{e['name']}    {e['path']}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("가져올 위치"))
        self.dest = QComboBox()
        self.dest.addItems(["빠른 이동", "북마크 바"])
        self.dest.currentIndexChanged.connect(self._mark_dups)
        row.addWidget(self.dest)
        row.addStretch(1)
        lay.addLayout(row)
        self.replace = QCheckBox("현재 내용을 지우고 이것으로 교체 (교체 전 자동 백업)")
        lay.addWidget(self.replace)
        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton("가져오기")
        ok.setObjectName("accent")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)
        self._mark_dups()

    def _mark_dups(self, *_):
        have = self.have_quick if self.dest.currentIndex() == 0 else self.have_bm
        for i, e in enumerate(self.entries):
            it = self.list.item(i)
            dup = os.path.normcase(e["path"]) in have
            it.setText(f"{e['name']}    {e['path']}" + ("    (이미 있음)" if dup else ""))
            it.setCheckState(Qt.Unchecked if dup else Qt.Checked)

    def selected(self):
        return [e for i, e in enumerate(self.entries) if self.list.item(i).checkState() == Qt.Checked]


# ───────────────────────── 메인 윈도우 ─────────────────────────
class Main(QMainWindow):
    _ui = Signal(object)   # 작업 스레드에서 화면 갱신을 안전하게 요청

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JY Explorer")
        self.resize(1400, 860)
        self.data = load_json(EXPLORER_FILE, {})
        for c, w in self.data.get("col_widths", {}).items():      # 열 너비 복원 (json 키는 문자열)
            if str(c).isdigit() and int(c) in FileView.COLS and isinstance(w, int) and 40 <= w <= 3000:
                FileView.COLS[int(c)] = w

        def cols_changed():
            self.data["col_widths"] = dict(FileView.COLS)
            self.schedule_save()
        FileView.on_cols_changed = cols_changed
        self.show_hidden = self.data.get("show_hidden", False)
        self.sync_fav = self.data.get("sync_fav", True)
        self.bm = load_json(BOOKMARKS_FILE, {"children": []})
        self.bm.setdefault("children", [])
        self.quitting = False
        self.tray_ok = False
        self.hook = None
        self.quick_items = self.data.setdefault("quick", [])   # 빠른 이동에 내가 추가한 항목
        self.quick_names = self.data.setdefault("quick_names", {})  # 기본 항목 이름 바꾸기 기록
        self._ui.connect(lambda f: f())
        self.clip_paths, self.clip_cut = [], False
        self.runner = JobRunner()
        self.runner.progress.connect(self.on_progress)
        self.runner.started.connect(self.on_job_started)
        self.runner.finished.connect(self.on_job_finished)
        self.runner.conflict.connect(self.on_conflict)
        self.runner.queueChanged.connect(self.on_queue)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 8)
        outer.setSpacing(8)

        # 상단 도구줄
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addStretch(1)  # 버튼들은 검색창 바로 왼쪽에 오른쪽 정렬

        def btn(text, fn, tip="", checkable=False):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.clicked.connect(lambda _=False: fn())
            bar.addWidget(b)
            return b
        self.one_btn = btn("1개 보기", self.toggle_split, "패널 1개 (F3 로 전환)", True)
        self.split_btn = btn("2개 보기", self.toggle_split, "패널 2개 (F3 로 전환)", True)
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        grp.addButton(self.one_btn)
        grp.addButton(self.split_btn)
        self.one_btn.setChecked(True)
        btn("북마크 추가", lambda: self.add_bookmark(self.active_view().path), "현재 폴더를 북마크에 (Ctrl+D)")
        self.ws_btn = btn("작업공간", lambda: None, "작업공간 저장 / 열기")
        self.ws_btn.clicked.disconnect()
        self.ws_btn.clicked.connect(self.workspace_menu)
        self.opt_btn = btn("설정", lambda: None)
        self.opt_btn.clicked.disconnect()
        self.opt_btn.clicked.connect(self.options_menu)
        bar.addSpacing(10)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("이 폴더에서 이름 검색 (Ctrl+F)")
        self.filter.setClearButtonEnabled(True)
        self.filter.setFixedWidth(280)
        self.filter.textChanged.connect(lambda t: self.active_view().set_filter(t))
        bar.addWidget(self.filter)
        outer.addLayout(bar)

        # 북마크 바 (크롬처럼 위쪽)
        self.bmbar = BookmarksBar()
        self.bmbar.icons_only = self.data.get("bm_icons_only", False)
        self.bmbar.folder_click_opens = self.data.get("bm_folder_tabs", False)
        self.bmbar.load(self.bm)
        self.bmbar.openPath.connect(self.open_path)
        self.bmbar.openFolderAsTabs.connect(self.open_all)
        self.bmbar.dirsDropped.connect(self.on_bookmark_drop)
        self.bmbar.menuAt.connect(self.bookmark_menu)
        self.bmbar.nodeDropped.connect(self.on_bm_drop)
        self.bmbar.openPair.connect(self.open_pair)
        outer.addWidget(self.bmbar)

        # 본문: 사이드바 + 패널들
        body = QSplitter(Qt.Horizontal)
        side = QFrame()
        side.setObjectName("panel")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(8, 8, 8, 8)
        sl.setSpacing(2)
        qhead = QHBoxLayout()
        qhead.addWidget(self._sect("빠른 이동"))
        qhead.addStretch(1)
        qadd = QToolButton()
        qadd.setObjectName("nav")
        qadd.setText("+")
        qadd.setToolTip("빠른 이동 추가 (현재 폴더 / 폴더 선택 / 네트워크)")
        qadd.setFocusPolicy(Qt.NoFocus)
        qadd.clicked.connect(lambda: self.quick_menu(None, QCursor.pos()))
        qhead.addWidget(qadd)
        sl.addLayout(qhead)
        self.quick = QuickList()
        self.quick.openPath.connect(self.open_path)
        self.quick.menuAt.connect(self.quick_menu)
        sl.addWidget(self.quick)
        sl.addStretch(1)
        side.setMinimumWidth(190)
        body.addWidget(side)

        self.panes_split = QSplitter(Qt.Horizontal)
        self.panes = [Pane(self), Pane(self)]
        self.panes[0].side, self.panes[1].side = "왼쪽", "오른쪽"
        for p in self.panes:
            self.panes_split.addWidget(p)
            p.changed.connect(self.schedule_save)
            p.statusChanged.connect(self.update_status)
        body.addWidget(self.panes_split)
        body.setStretchFactor(1, 1)
        body.setSizes([230, 1100])
        outer.addWidget(body, 1)

        # 하단 상태줄
        foot = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("status")
        self.toast = QLabel()
        self.toast.setStyleSheet("color:#9fe8c5; font-weight:600;")
        self.job_label = QLabel()
        self.job_label.setObjectName("status")
        self.job_bar = QProgressBar()
        self.job_bar.setFixedWidth(220)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setFocusPolicy(Qt.NoFocus)
        self.cancel_btn.clicked.connect(self.runner.cancel_all)
        for w in (self.job_label, self.job_bar, self.cancel_btn):
            w.hide()
        foot.addWidget(self.status)
        foot.addStretch(1)
        foot.addWidget(self.toast)
        foot.addWidget(self.job_label)
        foot.addWidget(self.job_bar)
        foot.addWidget(self.cancel_btn)
        outer.addLayout(foot)

        self.active = self.panes[0]
        self._toast_t = QTimer(self, singleShot=True)
        self._toast_t.timeout.connect(lambda: self.toast.clear())
        self._save_t = QTimer(self, singleShot=True)
        self._save_t.timeout.connect(self.save_session)
        QApplication.instance().focusChanged.connect(self.on_focus)
        QApplication.instance().installEventFilter(self)  # 패널 안 아무 곳(버튼 포함)이나 클릭해도 그 패널이 선택됨

        self.setup_shortcuts()
        self.quick.refresh(self.quick_items, self.quick_names)
        self.restore_session()

    # ---- 구성 보조 ----
    def _sect(self, text):
        l = QLabel(text)
        l.setObjectName("sect")
        return l

    def setup_shortcuts(self):
        def sc(key, fn):
            QShortcut(QKeySequence(key), self, activated=fn)
        sc("F3", lambda: (self.one_btn if self.split_btn.isChecked() else self.split_btn).click())
        sc("F5", lambda: self.to_other("copy"))
        sc("F6", lambda: self.to_other("move"))
        sc("Ctrl+T", lambda: self.active.add_tab(self.active_view().path))
        sc("Ctrl+W", lambda: self.active.close_current())
        sc("Ctrl+PgUp", lambda: self.active.cycle(-1))        # 탭 이동
        sc("Ctrl+PgDown", lambda: self.active.cycle(1))
        sc("Ctrl+Tab", self.switch_pane)                      # 패널 이동
        sc("Ctrl+Shift+Tab", self.switch_pane)
        sc("Ctrl+Alt+Right", self.send_tab_to_other)          # 현재 탭을 반대편 패널로 보내기
        sc("Ctrl+Alt+Left", self.send_tab_to_other)
        sc("Ctrl+L", lambda: (self.active.pathbar.setFocus(), self.active.pathbar.selectAll()))
        sc("Ctrl+F", lambda: (self.filter.setFocus(), self.filter.selectAll()))
        sc("Ctrl+D", lambda: self.toggle_bookmark(self.active_view().path))
        sc("Ctrl+Shift+D", self.add_pair_bookmark)
        sc("Ctrl+H", self.toggle_hidden)
        sc("F4", lambda: self.switch_pane())
        sc("Esc", self.on_escape)

    def on_escape(self):
        if self.filter.text():
            self.filter.clear()
        self.active_view().setFocus()

    def active_view(self):
        return self.active.view()

    def visible_panes(self):
        return [p for p in self.panes if p.isVisible()]

    def other_pane(self):
        vp = self.visible_panes()
        return next((p for p in vp if p is not self.active), None)

    def send_tab_to_other(self, pane=None, vid=None):
        """탭을 반대편 패널로 넘김. 마지막 남은 탭이면 복제해서 보냄"""
        src = pane or self.active
        o = self.panes[1] if src is self.panes[0] else self.panes[0]
        vid = src.current_vid() if vid is None else vid
        v = src.views.get(vid)
        if v is None:
            return
        if not self.split_btn.isChecked():
            self.split_btn.click()
        o.add_tab(v.path, pinned=v.pinned)
        if len(src.views) > 1:
            src.close_tab(vid, force=True)
            self.say(f"탭을 {o.side} 패널로 보냈습니다")
        else:
            self.say(f"마지막 탭이라 복제해서 {o.side} 패널에 열었습니다")
        self.set_active(o)

    def switch_pane(self):
        o = self.other_pane()
        if o:
            self.set_active(o)
            o.view().setFocus()

    def eventFilter(self, obj, e):
        if e.type() == e.Type.MouseButtonPress and isinstance(obj, QWidget) and self.isAncestorOf(obj):
            w = obj
            while w is not None:
                if isinstance(w, Pane):
                    self.set_active(w)
                    break
                w = w.parentWidget()
        return False

    def on_focus(self, old, new):
        w = new
        while w is not None:
            if isinstance(w, Pane):
                self.set_active(w)
                return
            w = w.parentWidget()

    def refresh_active_marks(self):
        split = self.split_btn.isChecked()
        for p in self.panes:
            p.set_active(p is self.active and split, split)

    def set_active(self, pane):
        if pane is self.active and pane.property("active") == self.split_btn.isChecked():
            return
        changed = pane is not self.active
        self.active = pane
        self.refresh_active_marks()
        if changed:
            self.filter.blockSignals(True)
            self.filter.clear()
            self.filter.blockSignals(False)
        self.update_status()

    def toggle_split(self):
        on = self.split_btn.isChecked()
        self.panes[1].setVisible(on)
        if on and len(self.panes[1].views) == 0:
            self.panes[1].add_tab(self.panes[0].view().path or HOME)
        if not on and self.active is self.panes[1]:
            self.active = self.panes[0]
        self.refresh_active_marks()
        self.panes_split.setSizes([1, 1])
        self.update_status()
        self.say("패널 2개: 클릭한 쪽이 선택되고, 새 탭은 선택된 쪽에 열립니다" if on else "패널 1개")
        self.schedule_save()

    def toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        for p in self.panes:
            for v in p.views.values():
                v.set_hidden(self.show_hidden)
        self.data["show_hidden"] = self.show_hidden
        self.schedule_save()

    def say(self, msg):
        self.toast.setText(msg)
        self._toast_t.start(3500)

    def update_status(self):
        v = self.active_view()
        if not v:
            return
        sel = v.selected_paths()
        total = v.visible_count()
        s = (f"[{self.active.side} 패널]   " if self.split_btn.isChecked() else "") + f"{total:,}개 항목"
        if sel:
            size = 0
            for p in sel:
                try:
                    if os.path.isfile(p):
                        size += os.path.getsize(p)
                except OSError:
                    pass
            s += f"   ·   {len(sel):,}개 선택" + (f" ({fmt_size(size)})" if size else "")
        self.status.setText(s)

    # ---- 열기 ----
    def open_path(self, path, new_tab):
        if path and not dir_exists(path):
            self.say("경로를 찾을 수 없습니다: " + path)
            return
        if new_tab:
            self.active.add_tab(path)
        else:
            self.active_view().navigate(path)
            self.active_view().setFocus()

    def open_external(self, path):
        """런처 등 다른 프로그램의 요청: 새 탭으로 열고 창을 앞으로"""
        if os.path.isfile(path):
            folder, sel = os.path.dirname(path), path
        else:
            folder, sel = path, None
        if os.path.isdir(folder):
            v = self.active.add_tab(folder)
            if sel:
                QTimer.singleShot(400, lambda: v.select_path(sel))
        self.bring_to_front()

    def bring_to_front(self):
        """창을 앞으로 가져와 활성화 (숨어 있거나 최소화돼 있어도). 이미 떠 있으면 그냥 활성화만 함 — 새 창/새 탭 없음"""
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        u = ctypes.windll.user32
        u.keybd_event(0x12, 0, 0, 0)      # Alt 를 한 번 눌렀다 떼면 다른 프로그램이 포커스를 쥐고 있어도 전환이 허용됨
        u.keybd_event(0x12, 0, 2, 0)
        u.SetForegroundWindow(int(self.winId()))
        v = self.active_view()
        if v:
            v.setFocus()

    def quit_app(self):
        self.quitting = True
        self.save_session()
        if self.hook is not None:
            self.hook.uninstall()
        QApplication.quit()

    def apply_win_e(self):
        """설정에 따라 Win+E 가로채기를 켜거나 끔. 성공 여부 반환"""
        on = self.data.get("win_e", True)
        if on and self.hook is None:
            h = WinEHook(self.bring_to_front)
            if not h.install():
                return False
            self.hook = h
        elif not on and self.hook is not None:
            self.hook.uninstall()
            self.hook = None
        return True

    # ---- 클립보드 / 붙여넣기 ----
    def key_action(self, action, pane, view):
        self.set_active(pane)
        paths = view.selected_paths()
        if action in ("copy", "cut"):
            if paths:
                self.set_clipboard(paths, action == "cut")
        elif action == "paste":
            self.paste(view.path)
        elif action == "delete":
            self.delete(paths, False)
        elif action == "permdelete":
            self.delete(paths, True)
        elif action == "newfolder":
            self.new_folder(view)

    def set_clipboard(self, paths, cut):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        mime.setData(DROP_EFFECT, QByteArray(struct.pack("<I", 2 if cut else 1)))
        QApplication.clipboard().setMimeData(mime)
        self.clip_paths, self.clip_cut = paths, cut
        self.say(f"{len(paths)}개 {'잘라내기' if cut else '복사'}")

    def paste(self, dest):
        if not dest:
            self.say("드라이브/폴더 안에서 붙여넣으세요")
            return
        mime = QApplication.clipboard().mimeData()
        if not mime or not mime.hasUrls():
            return
        paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        cut = False
        if mime.hasFormat(DROP_EFFECT):
            d = bytes(mime.data(DROP_EFFECT))
            cut = len(d) >= 4 and struct.unpack("<I", d[:4])[0] & 2 == 2
        if paths:
            self.runner.submit("move" if cut else "copy", paths, dest)
            if cut:
                QApplication.clipboard().clear()

    def to_other(self, op):
        o = self.other_pane()
        if not o:
            self.say("F3 으로 분할 화면을 켜세요")
            return
        paths = self.active_view().selected_paths()
        if not paths:
            return
        if not o.view().path:
            self.say("반대편이 '내 PC' 입니다. 폴더로 이동하세요")
            return
        self.runner.submit(op, paths, o.view().path)

    def on_drop(self, paths, target, ctrl, shift):
        """드롭 기본 동작: 같은 드라이브면 이동, 다르면 복사 (Ctrl=복사 강제, Shift=이동 강제)"""
        if ctrl:
            op = "copy"
        elif shift:
            op = "move"
        else:
            op = "move" if paths and F.same_volume(paths[0], target) else "copy"
        self.runner.submit(op, paths, target)

    def _count_entries(self, paths, limit):
        """삭제 대상에 들어 있는 항목 수를 limit 까지만 셈 (큰 폴더인지 판단용)"""
        n, stack = 0, list(paths)
        while stack and n < limit:
            p = stack.pop()
            n += 1
            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    with os.scandir(p) as it:
                        stack.extend(e.path for e in it)
            except OSError:
                pass
        return n

    def delete(self, paths, permanent):
        """Del = 휴지통(복구 가능). 항목이 아주 많으면 휴지통은 느리므로 '빠른 삭제(병렬, 복구 불가)'를 권함.
        Shift+Del = 영구 삭제 = 바로 빠른 삭제"""
        if not paths:
            return
        v = self.active_view()
        fast = permanent
        if permanent:
            if QMessageBox.question(self, "완전 삭제", f"{len(paths)}개 항목을 완전히 삭제합니다.\n휴지통으로 가지 않으며 복구할 수 없습니다.\n\n계속할까요?") != QMessageBox.Yes:
                return
        elif self._count_entries(paths, 3000) >= 3000:
            box = QMessageBox(self)
            box.setWindowTitle("항목이 매우 많습니다")
            box.setText("삭제할 파일이 3,000개가 넘습니다.\n휴지통으로 보내면 오래 걸립니다.")
            slow = box.addButton("휴지통으로 (느림, 복구 가능)", QMessageBox.AcceptRole)
            quick = box.addButton("빠르게 삭제 (병렬, 복구 불가)", QMessageBox.DestructiveRole)
            box.addButton("취소", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is quick:
                fast = True
            elif box.clickedButton() is not slow:
                return
        if fast:
            self.runner.submit("delete", paths, "")      # 백그라운드 + 진행률 + 취소, 화면은 멈추지 않음
        else:
            F.delete_paths(paths, False, int(self.winId()))
            self.say(f"{len(paths)}개 휴지통으로 이동")
        v.setFocus()

    def new_folder(self, view):
        if not view.path:
            return
        p = F.unique_path(os.path.join(view.path, "새 폴더"))
        try:
            os.mkdir(p)
        except OSError as e:
            self.say(str(e))
            return
        QTimer.singleShot(250, lambda: view.select_path(p, rename=True))

    # ---- 작업 진행 ----
    def on_job_started(self, label):
        self.job_label.setText(label)
        for w in (self.job_label, self.job_bar, self.cancel_btn):
            w.show()

    def on_progress(self, done, total, name):
        self.job_bar.setValue(int(done * 100 / max(total, 1)))
        job = self.runner.current
        by_count = job is not None and getattr(job, "unit", "bytes") == "count"
        amount = f"{done:,} / {total:,}개" if by_count else f"{fmt_size(done)} / {fmt_size(total)}"
        self.job_label.setText(f"{name[:40]}   {amount}" if name else self.job_label.text())

    def on_queue(self, n):
        self.cancel_btn.setText(f"취소 ({n})" if n > 1 else "취소")

    def on_job_finished(self, summary, errors, ok):
        if not self.runner.queue:
            for w in (self.job_label, self.job_bar, self.cancel_btn):
                w.hide()
        self.say(summary + (f" · 오류 {len(errors)}" if errors else ""))
        if errors:
            msg = "\n".join(f"{os.path.basename(p)}: {e}" for p, e in errors[:12])
            QMessageBox.warning(self, "일부 항목을 처리하지 못했습니다", msg + ("\n…" if len(errors) > 12 else ""))

    def on_conflict(self, src, dst, holder):
        dlg = ConflictDialog(self, src, dst)
        dlg.exec()
        ans = dlg.answer
        holder["ans"] = (ans, dlg.all_chk.isChecked()) if ans != "cancel" else "cancel"
        holder["ev"].set()

    # ---- 컨텍스트 메뉴 ----
    def _shell_menu(self, pane, view, pos, paths):
        """일반 Windows 탐색기와 똑같은 우클릭 메뉴(반디집, Notepad++ 등 포함)를 띄우고 맨 위에 내 항목을 추가"""
        import shellmenu as SM
        m = SM.ShellMenu(paths, view.path, extended=bool(QGuiApplication.keyboardModifiers() & Qt.ShiftModifier))
        try:
            actions, items = {}, []

            def add(text, fn):
                cid = SM.CUSTOM_BASE + len(actions)
                actions[cid] = fn
                items.append((cid, text))
            other = self.other_pane()
            single = paths[0] if len(paths) == 1 else None
            if paths:
                if single and os.path.isdir(single):
                    add("열기", lambda: view.navigate(single))
                    add("새 탭에서 열기", lambda: pane.add_tab(single))
                    add("북마크에 추가", lambda: self.add_bookmark(single))
                    add("빠른 이동에 추가", lambda: self.add_quick(single))
                    add("Windows 즐겨찾기에 고정", lambda: self.pin_windows(single))
                    add("런처에 추가", lambda: self.add_to_launcher(paths))
                else:
                    add("열기", lambda: [os.startfile(x) for x in paths[:20]])
                    add("런처에 추가", lambda: self.add_to_launcher(paths))
                if other:
                    add("반대편으로 복사  (F5)", lambda: self.to_other("copy"))
                    add("반대편으로 이동  (F6)", lambda: self.to_other("move"))
            elif view.path:
                add("새 탭에서 열기", lambda: pane.add_tab(view.path))
                add("이 폴더 북마크에 추가", lambda: self.add_bookmark(view.path))
                add("이 폴더 빠른 이동에 추가", lambda: self.add_quick(view.path))
                add("이 폴더 런처에 추가", lambda: self.add_to_launcher([view.path]))
            if items:
                m.add_custom(items)
            scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
            dpr = scr.devicePixelRatio()
            cmd = m.track(pos.x() * dpr, pos.y() * dpr)
            if cmd >= SM.CUSTOM_BASE:
                actions[cmd]()
            elif cmd:
                self._run_shell_cmd(m, cmd, view, paths)
        finally:
            m.close()

    def _run_shell_cmd(self, m, cmd, view, paths):
        """복사/잘라내기/붙여넣기/삭제/이름 바꾸기/열기는 이 프로그램의 기능(진행률·백그라운드)으로 처리하고,
        나머지(반디집, Notepad++, 속성, 보내기 …)는 Windows 에 그대로 맡김"""
        verb = m.verb(cmd)
        single = paths[0] if len(paths) == 1 else None
        if verb == "copy" and paths:
            self.set_clipboard(paths, False)
        elif verb == "cut" and paths:
            self.set_clipboard(paths, True)
        elif verb == "paste":
            self.paste(single if single and os.path.isdir(single) else view.path)
        elif verb == "delete" and paths:
            self.delete(paths, False)
        elif verb == "rename" and single:
            view.select_path(single, rename=True)
        elif verb == "open" and single and os.path.isdir(single):
            view.navigate(single)
        else:
            m.invoke(cmd, int(self.winId()))

    def show_file_menu(self, pane, view, pos, paths):
        self.set_active(pane)
        if self.data.get("shell_menu", True):
            try:
                self._shell_menu(pane, view, pos, paths)
                return
            except Exception:      # 드라이브 루트/내 PC 이거나 셸 메뉴를 못 만들 때 → 아래 기본 메뉴
                pass
        m = QMenu(self)
        other = self.other_pane()
        if paths:
            single = paths[0] if len(paths) == 1 else None
            m.addAction("열기", lambda: [view.activate(view.model_.index(p)) if len(paths) == 1 else os.startfile(p)
                                         for p in paths[:1 if single else 20]])
            if single and os.path.isdir(single):
                m.addAction("새 탭에서 열기", lambda: pane.add_tab(single))
                m.addAction("북마크에 추가", lambda: self.add_bookmark(single))
                m.addAction("빠른 이동에 추가", lambda: self.add_quick(single))
                m.addAction("Windows 즐겨찾기에 고정", lambda: self.pin_windows(single))
            m.addAction("런처에 추가", lambda: self.add_to_launcher(paths))
            m.addSeparator()
            m.addAction("복사  (Ctrl+C)", lambda: self.set_clipboard(paths, False))
            m.addAction("잘라내기  (Ctrl+X)", lambda: self.set_clipboard(paths, True))
        m.addAction("붙여넣기  (Ctrl+V)", lambda: self.paste(view.path))
        if paths and other:
            m.addAction("반대편으로 복사  (F5)", lambda: self.to_other("copy"))
            m.addAction("반대편으로 이동  (F6)", lambda: self.to_other("move"))
        if paths:
            m.addSeparator()
            if len(paths) == 1:
                m.addAction("이름 바꾸기  (F2)", view.start_rename)
            m.addAction("삭제  (Del)", lambda: self.delete(paths, False))
            m.addAction("경로 복사", lambda: QApplication.clipboard().setText("\n".join(paths)))
            m.addAction("속성", lambda: [self.props(p) for p in paths[:1]])
        m.addSeparator()
        m.addAction("새 폴더  (Ctrl+Shift+N)", lambda: self.new_folder(view))
        if view.path:
            m.addAction("이 폴더 북마크에 추가  (Ctrl+D)", lambda: self.add_bookmark(view.path))
        m.exec(pos)

    def props(self, p):
        try:
            os.startfile(p, "properties")
        except OSError:
            pass

    # ---- 북마크 ----
    def save_bookmarks(self):
        save_json(BOOKMARKS_FILE, self.bm)

    def add_bookmark(self, path, target=None, quiet=False):
        if not path or not os.path.isdir(path):
            self.say("북마크할 폴더가 없습니다")
            return
        parent = target if target is not None else self.bm
        if any(n["type"] == "bookmark" and os.path.normcase(n["path"]) == os.path.normcase(path)
               for n in parent["children"]):
            if not quiet:
                self.say("이미 북마크에 있습니다")
            return
        parent["children"].append({"type": "bookmark", "name": tab_title(path), "path": path})
        if target is not None:
            target["open"] = True
        self.bookmarks_changed()
        if not quiet:
            self.say("북마크 추가: " + tab_title(path))
        if self.sync_fav:
            self.pin_windows(path, quiet=True)

    def on_bookmark_drop(self, paths, target):
        for p in paths:
            self.add_bookmark(p, target)

    def pin_windows(self, path, quiet=False):
        def run():
            ok = F.pin_home(path)
            if not quiet:
                self._ui.emit(lambda: self.say("Windows 즐겨찾기에 고정" if ok else "즐겨찾기 고정 실패"))
        threading.Thread(target=run, daemon=True).start()

    def _all_paths(self, kids):
        for n in kids:
            if n["type"] == "bookmark":
                if not n.get("path2"):
                    yield n["path"]
            else:
                yield from self._all_paths(n["children"])

    def _remove_node(self, node, kids=None):
        kids = self.bm["children"] if kids is None else kids
        if node in kids:
            kids.remove(node)
            return True
        return any(self._remove_node(node, k["children"]) for k in kids if k["type"] == "folder")

    def bookmarks_changed(self):
        self.save_bookmarks()
        self.bmbar.render()
        self.refresh_stars()

    def refresh_stars(self):
        for p in self.panes:
            p.update_star()

    def is_bookmarked(self, path):
        return bool(path) and os.path.normcase(os.path.normpath(path)) in \
            {os.path.normcase(os.path.normpath(x)) for x in self._all_paths(self.bm["children"])}

    def toggle_bookmark(self, path):
        """경로줄의 별: 이미 북마크면 해제, 아니면 추가"""
        if not path:
            self.say("드라이브/폴더 안에서 북마크하세요")
            return
        if not self.is_bookmarked(path):
            self.add_bookmark(path)
            return
        key = os.path.normcase(os.path.normpath(path))
        found = []

        def walk(kids):
            for n in kids:
                if n["type"] == "bookmark":
                    if not n.get("path2") and os.path.normcase(os.path.normpath(n["path"])) == key:
                        found.append(n)
                else:
                    walk(n["children"])
        walk(self.bm["children"])
        for n in found:
            self._remove_node(n)
        self.bookmarks_changed()
        self.say("북마크 해제: " + tab_title(path))
        if self.sync_fav:
            threading.Thread(target=F.unpin_home, args=(path,), daemon=True).start()

    def _parent_list(self, node, kids=None):
        kids = self.bm["children"] if kids is None else kids
        if node in kids:
            return kids
        for k in kids:
            if k["type"] == "folder":
                r = self._parent_list(node, k["children"])
                if r is not None:
                    return r
        return None

    def move_node(self, n, d):
        lst = self._parent_list(n)
        if lst is None:
            return
        i = lst.index(n)
        j = i + d
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self.bookmarks_changed()

    def bookmark_menu(self, n, pos):
        m = QMenu(self)
        if n is not None:
            if n["type"] == "bookmark" and n.get("path2"):
                m.addAction("열기 (양쪽 패널에 각각)", lambda: self.open_pair(n))
                m.addAction("두 개의 북마크로 나누기", lambda: self.split_pair(n))
            elif n["type"] == "bookmark":
                m.addAction("열기", lambda: self.open_path(n["path"], False))
                m.addAction("새 탭에서 열기", lambda: self.open_path(n["path"], True))
                m.addAction("반대편 패널에서 열기", lambda: self.open_in_other(n["path"]))
            else:
                cnt = sum(1 for _ in self.bmbar._leaves(n["children"]))
                m.addAction(f"모두 열기 ({cnt}개, 현재 패널의 탭으로)", lambda: self.open_all(n))
                m.addAction("반대편 패널에 모두 열기", lambda: self.open_all(n, other=True))
                m.addAction("안의 북마크 목록 보기", lambda: self.bmbar._folder_menu(n).exec(QCursor.pos()))
                m.addAction("폴더 풀기 (안의 북마크를 밖으로)", lambda: self.unwrap_folder(n))
            m.addAction("이름 변경…", lambda: self.rename_node(n))
            m.addAction("왼쪽으로 이동", lambda: self.move_node(n, -1))
            m.addAction("오른쪽으로 이동", lambda: self.move_node(n, 1))
            m.addAction("삭제", lambda: self.delete_node(n))
            m.addSeparator()
        m.addAction("현재 폴더 북마크에 추가", lambda: self.add_bookmark(self.active_view().path))
        m.addAction("폴더 선택하여 북마크 추가…", self.add_bookmark_dialog)
        m.addAction("양쪽 패널 세트를 북마크로 추가  (Ctrl+Shift+D)", self.add_pair_bookmark)
        m.addAction("새 북마크 폴더…", self.new_bm_folder)
        m.addSeparator()
        f = m.addAction("폴더 클릭 = 안의 북마크 모두 탭으로 열기")
        f.setCheckable(True)
        f.setChecked(self.bmbar.folder_click_opens)
        f.triggered.connect(self.toggle_bm_folder_click)
        a = m.addAction("이름 숨기고 아이콘만 보기")
        a.setCheckable(True)
        a.setChecked(self.bmbar.icons_only)
        a.triggered.connect(self.toggle_bm_icons)
        m.exec(pos)

    def toggle_bm_folder_click(self):
        self.bmbar.folder_click_opens = not self.bmbar.folder_click_opens
        self.data["bm_folder_tabs"] = self.bmbar.folder_click_opens
        self.schedule_save()
        self.bmbar.render()
        self.say("북마크 폴더 클릭: " + ("안의 북마크를 모두 탭으로 열기" if self.bmbar.folder_click_opens else "목록 펼치기"))

    # ---- 세트 북마크 (폴더 2개를 북마크 1개로) ----
    def add_pair_bookmark(self):
        """지금 왼쪽·오른쪽 패널에 열려 있는 두 폴더를 북마크 1개(세트)로 저장"""
        if not self.split_btn.isChecked():
            self.say("'2개 보기'로 양쪽에 폴더를 열어 둔 다음 눌러주세요")
            return
        a, b = self.panes[0].view().path, self.panes[1].view().path
        if not a or not b:
            self.say("양쪽 패널 모두 폴더 안에 있어야 합니다")
            return
        name, ok = QInputDialog.getText(self, "세트 북마크", "이름:", text=f"{tab_title(a)} + {tab_title(b)}")
        if ok and name.strip():
            self.bm["children"].append({"type": "bookmark", "name": name.strip(), "path": a, "path2": b})
            self.bookmarks_changed()
            self.say("세트 북마크 추가: " + name.strip())

    def open_pair(self, n):
        """세트 북마크: 2개 보기로 전환하고 왼쪽 패널에 path, 오른쪽 패널에 path2 를 각각 새 탭으로 엶"""
        ok1, ok2 = dir_exists(n["path"]), dir_exists(n["path2"])
        if not (ok1 or ok2):
            self.say("세트 안의 폴더를 찾을 수 없습니다")
            return
        if not self.split_btn.isChecked():
            self.split_btn.click()
        if ok1:
            self.panes[0].add_tab(n["path"])
        if ok2:
            self.panes[1].add_tab(n["path2"])
        self.set_active(self.panes[0])
        self.say(f"세트 열기: {n['name']}" + ("" if ok1 and ok2 else "  (일부 폴더 없음)"))

    def split_pair(self, n):
        lst = self._parent_list(n)
        if lst is not None:
            i = lst.index(n)
            lst[i:i + 1] = [{"type": "bookmark", "name": tab_title(n["path"]), "path": n["path"]},
                            {"type": "bookmark", "name": tab_title(n["path2"]), "path": n["path2"]}]
            self.bookmarks_changed()

    def toggle_bm_icons(self):
        self.bmbar.icons_only = not self.bmbar.icons_only
        self.data["bm_icons_only"] = self.bmbar.icons_only
        self.schedule_save()
        self.bmbar.render()

    def add_bookmark_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "북마크할 폴더 선택", self.active_view().path or HOME)
        if d:
            self.add_bookmark(os.path.normpath(d))

    def unwrap_folder(self, n):
        lst = self._parent_list(n)
        if lst is not None:
            i = lst.index(n)
            lst[i:i + 1] = n["children"]
            self.bookmarks_changed()

    def _contains(self, folder, node):
        return any(c is node or (c["type"] == "folder" and self._contains(c, node)) for c in folder["children"])

    def on_bm_drop(self, node, target, zone):
        """북마크 바에서 끌어다 놓기: 가장자리=순서 변경, 가운데=폴더로 묶기, 빈 곳=맨 끝"""
        if node is target:
            return
        if target is not None and node["type"] == "folder" and (target is node or self._contains(node, target)):
            return  # 폴더를 자기 안으로 넣을 수 없음
        QTimer.singleShot(0, lambda: self._bm_drop(node, target, zone))   # 드래그가 끝난 뒤 처리

    def _bm_drop(self, node, target, zone):
        src = self._parent_list(node)
        if src is None or (target is not None and self._parent_list(target) is None):
            return
        if target is not None and node["type"] == "folder" and self._contains(node, target):
            return
        if target is None:
            src.remove(node)
            self.bm["children"].append(node)
        elif zone == "group":
            if target["type"] == "folder":
                src.remove(node)
                target["children"].append(node)
                target["open"] = True
            else:
                name, ok = QInputDialog.getText(self, "북마크 폴더로 묶기", "새 폴더 이름:", text="새 폴더")
                if not ok or not name.strip():
                    return
                src.remove(node)
                tl = self._parent_list(target)
                tl[tl.index(target)] = {"type": "folder", "name": name.strip(), "open": True,
                                        "children": [target, node]}
        else:
            src.remove(node)
            tl = self._parent_list(target)
            tl.insert(tl.index(target) + (1 if zone == "after" else 0), node)
        self.bookmarks_changed()

    # ---- 빠른 이동 (사이드바) ----
    def quick_changed(self):
        self.save_session()
        self.quick.refresh(self.quick_items, self.quick_names)

    def add_quick(self, path, name=None, net=False):
        if not path:
            return
        if any(os.path.normcase(c["path"]) == os.path.normcase(path) for c in self.quick_items):
            self.say("이미 빠른 이동에 있습니다")
            return
        self.quick_items.append({"name": name or tab_title(path), "path": path, "net": net})
        self.quick_changed()
        self.say("빠른 이동에 추가: " + (name or tab_title(path)))

    def add_quick_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "빠른 이동에 추가할 폴더", self.active_view().path or HOME)
        if d:
            self.add_quick(os.path.normpath(d))

    def quick_menu(self, entry, pos):
        m = QMenu(self)
        if entry is not None:
            m.addAction("이름 변경…", lambda: self.rename_quick(entry))
            key = os.path.normcase(entry["path"])
            if entry.get("builtin") and key in self.quick_names:
                m.addAction("원래 이름으로", lambda: self.reset_quick_name(entry))
            m.addAction("열기", lambda: self.open_path(entry["path"], False))
            m.addAction("새 탭에서 열기", lambda: self.open_path(entry["path"], True))
            if not entry.get("builtin"):
                m.addAction("빠른 이동에서 제거", lambda: self.remove_quick(entry))
            m.addSeparator()
        m.addAction("현재 폴더 추가", lambda: self.add_quick(self.active_view().path))
        m.addAction("폴더 선택하여 추가…", self.add_quick_dialog)
        m.addAction("네트워크 위치 추가…", self.add_network_dialog)
        m.exec(pos)

    def rename_quick(self, entry):
        name, ok = QInputDialog.getText(self, "이름 변경", "이름:", text=entry["name"])
        if ok and name.strip():
            if entry.get("builtin"):
                self.quick_names[os.path.normcase(entry["path"])] = name.strip()
            else:
                entry["name"] = name.strip()
            self.quick_changed()

    def reset_quick_name(self, entry):
        self.quick_names.pop(os.path.normcase(entry["path"]), None)
        self.quick_changed()

    def remove_quick(self, entry):
        if entry in self.quick_items:
            self.quick_items.remove(entry)
            self.quick_changed()

    def add_network_dialog(self):
        dlg = NetworkDialog(self, credential_targets())
        if not dlg.exec():
            return
        path = dlg.path()
        if len(path) < 4:
            return
        label = dlg.name.text().strip() or (path.strip("\\").replace("\\", " / "))
        if dlg.map_chk.isChecked() and dlg.letter.currentText():
            letter = dlg.letter.currentText()
            self.say("드라이브 연결 중…")

            def run():
                r = subprocess.run(["net", "use", letter, path, "/persistent:yes"], capture_output=True, text=True,
                                   errors="ignore", creationflags=0x08000000)
                ok = r.returncode == 0

                def done():
                    self.quick.refresh(self.quick_items, self.quick_names)
                    if ok:
                        self.say(f"{letter} 연결 완료: {path}")
                    else:
                        QMessageBox.warning(self, "연결 실패", (r.stdout + r.stderr).strip()[:400])
                self._ui.emit(done)
            threading.Thread(target=run, daemon=True).start()
            return
        self.say("연결 확인 중…")

        def check():
            ok = dir_exists(path, 8)

            def done():
                if ok or QMessageBox.question(self, "접근 실패", f"{path}\n\n지금은 접근할 수 없습니다. 그래도 추가할까요?") \
                        == QMessageBox.Yes:
                    self.add_quick(path, label, net=True)
                else:
                    self.say("추가하지 않았습니다")
            self._ui.emit(done)
        threading.Thread(target=check, daemon=True).start()

    # ---- 런처 연동 ----
    def add_to_launcher(self, paths):
        cat = pick_category(self, load_json(LAUNCHER_FILE, {}).keys())
        if not cat:
            return
        n = sum(1 for p in paths if add_item_to_launcher(p, cat))
        sock = QLocalSocket()                      # 런처가 떠 있으면 목록 새로고침 요청
        sock.connectToServer(LAUNCHER_SERVER)
        if sock.waitForConnected(150):
            sock.write(b"reload")
            sock.waitForBytesWritten(300)
        self.say(f"런처에 {n}개 추가 ({cat.strip()})" if n else "이미 런처에 있습니다")

    def open_all(self, folder, other=False):
        """북마크 폴더 통째로 실행: 안의 북마크 하나하나를 각각 탭으로 (세트는 양쪽 패널에)
        other=True 면 반대편 패널의 탭으로"""
        target = self.active
        if other:
            if not self.split_btn.isChecked():
                self.split_btn.click()
            target = self.other_pane() or self.active
        leaves = list(self.bmbar._leaves(folder["children"]))
        if len(leaves) > 12 and QMessageBox.question(self, "탭 많이 열기", f"{len(leaves)}개를 각각 탭으로 엽니다. 계속할까요?") \
                != QMessageBox.Yes:
            return
        n = 0
        for c in leaves:
            if c.get("path2"):
                self.open_pair(c)
                n += 1
            elif dir_exists(c["path"]):
                target.add_tab(c["path"], activate=(n == 0))
                n += 1
        self.say(f"'{folder['name']}' — {n}개를 열었습니다")

    def open_in_other(self, path):
        if not self.split_btn.isChecked():
            self.split_btn.setChecked(True)
            self.toggle_split()
        o = self.other_pane()
        if o:
            o.view().navigate(path)

    def rename_node(self, n):
        name, ok = QInputDialog.getText(self, "이름 변경", "이름:", text=n["name"])
        if ok and name.strip():
            n["name"] = name.strip()
            self.bookmarks_changed()

    def delete_node(self, n):
        removed = list(self._all_paths([n])) if n["type"] == "folder" else [n["path"]]
        self._remove_node(n)
        self.bookmarks_changed()
        if self.sync_fav:
            still = {os.path.normcase(p) for p in self._all_paths(self.bm["children"])}
            for p in removed:
                if os.path.normcase(p) not in still:
                    threading.Thread(target=F.unpin_home, args=(p,), daemon=True).start()

    def new_bm_folder(self):
        name, ok = QInputDialog.getText(self, "새 북마크 폴더", "폴더 이름:")
        if ok and name.strip():
            self.bm["children"].append({"type": "folder", "name": name.strip(), "open": True, "children": []})
            self.bookmarks_changed()

    # ---- 설정/작업공간 메뉴 ----
    def options_menu(self):
        m = QMenu(self)
        a = m.addAction("숨김 파일 표시  (Ctrl+H)")
        a.setCheckable(True)
        a.setChecked(self.show_hidden)
        a.triggered.connect(self.toggle_hidden)
        b = m.addAction("북마크를 Windows 즐겨찾기에도 등록")
        b.setCheckable(True)
        b.setChecked(self.sync_fav)
        b.triggered.connect(self.toggle_sync)
        m.addAction("기존 북마크 전체를 Windows 즐겨찾기에 등록", self.sync_all_fav)
        m.addSeparator()
        m.addAction("Windows 탐색기 즐겨찾기 불러오기…", self.import_windows_favorites)
        m.addAction("즐겨찾기·북마크 백업하기", self.backup_now)
        m.addAction("백업에서 불러오기…", self.restore_backup)
        m.addSeparator()
        c = m.addAction("Windows 기본 우클릭 메뉴 사용 (반디집 등)")
        c.setCheckable(True)
        c.setChecked(self.data.get("shell_menu", True))
        c.triggered.connect(self.toggle_shell_menu)
        m.addSeparator()
        e = m.addAction("Win+E 로 JY Explorer 열기 / 활성화")
        e.setCheckable(True)
        e.setChecked(self.data.get("win_e", True))
        e.triggered.connect(self.toggle_win_e)
        r = m.addAction("창을 닫아도 트레이에 상주 (Win+E 로 바로 열기)")
        r.setCheckable(True)
        r.setChecked(self.data.get("resident", True))
        r.triggered.connect(self.toggle_resident)
        s = m.addAction("Windows 시작 시 자동 실행 (트레이 상주)")
        s.setCheckable(True)
        s.setChecked(startup_enabled())
        s.triggered.connect(self.toggle_startup)
        u = getattr(self, "updater", None)
        if u:
            m.addSeparator()
            m.addAction(f"업데이트 {u.available['version']} 설치…" if u.available else f"업데이트 확인  (현재 {__version__})",
                        lambda: u.prompt_install() if u.available else u.check(manual=True))
            ua = m.addAction("시작 후 업데이트 자동 확인")
            ua.setCheckable(True)
            ua.setChecked(u.auto)
            ua.triggered.connect(lambda v: u.set_auto(v))
        m.exec(self.opt_btn.mapToGlobal(self.opt_btn.rect().bottomLeft()))

    def toggle_win_e(self):
        self.data["win_e"] = not self.data.get("win_e", True)
        self.schedule_save()
        ok = self.apply_win_e()
        self.say(("Win+E → JY Explorer" if self.data["win_e"] else "Win+E → Windows 탐색기 (원래대로)")
                 + ("" if ok else "  (키보드 훅 설치 실패)"))

    def toggle_resident(self):
        self.data["resident"] = not self.data.get("resident", True)
        self.schedule_save()
        self.say("창을 닫으면 " + ("트레이에 상주" if self.data["resident"] else "프로그램 종료"))

    def toggle_startup(self):
        try:
            on = not startup_enabled()
            set_startup(on)
            self.say("시작 프로그램에 등록했습니다 (트레이 상주)" if on else "시작 프로그램에서 뺐습니다")
        except OSError as ex:
            self.say("실패: " + str(ex))

    def toggle_shell_menu(self):
        self.data["shell_menu"] = not self.data.get("shell_menu", True)
        self.schedule_save()
        self.say("Windows 기본 우클릭 메뉴 " + ("사용" if self.data["shell_menu"] else "끔 (간단 메뉴)"))

    # ---- 백업 / 복원 / Windows 즐겨찾기 가져오기 ----
    def backup_now(self, tag=""):
        """북마크·빠른 이동 설정을 오늘 날짜를 붙여 backup 폴더에 저장 (현재 설정 파일은 그대로 둠)"""
        self.save_bookmarks()
        self.save_session()
        d = backup_favorites(tag)
        if not tag:
            self.say("백업 완료: " + str(d))
        return d

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "백업에서 불러오기", str(BACKUP_DIR),
                                              "북마크 백업 (bookmarks_*.json);;모든 JSON (*.json)")
        if not path:
            return
        bm = load_json(path, None)
        if not isinstance(bm, dict) or not isinstance(bm.get("children"), list):
            QMessageBox.warning(self, "불러올 수 없음", "북마크 백업 파일(bookmarks_날짜.json)을 선택하세요.")
            return
        pair = Path(path).with_name(Path(path).name.replace("bookmarks_", "explorer_", 1))
        ex = load_json(pair, None) if pair.exists() and pair != Path(path) else None
        msg = f"현재 북마크{' 와 빠른 이동' if ex else ''} 을(를)\n{Path(path).name}{' + ' + pair.name if ex else ''}\n내용으로 교체합니다.\n\n현재 내용은 먼저 자동으로 백업됩니다. 계속할까요?"
        if QMessageBox.question(self, "백업에서 불러오기", msg) != QMessageBox.Yes:
            return
        self.backup_now("_복원전")
        self.bm["children"] = bm["children"]
        if ex:
            self.quick_items[:] = ex.get("quick", [])
            self.quick_names.clear()
            self.quick_names.update(ex.get("quick_names", {}))
            if "workspaces" in ex:
                self.data["workspaces"] = ex["workspaces"]
        self.bookmarks_changed()
        self.quick_changed()
        self.say("백업에서 불러왔습니다: " + Path(path).name)

    def _default_quick_paths(self):
        return {os.path.normcase(os.path.join(HOME, s)) for s in ("Desktop", "Downloads", "Documents", "Pictures")}

    def import_windows_favorites(self):
        self.say("Windows 즐겨찾기를 읽는 중…")

        def run():
            try:
                entries = F.windows_pinned_folders()
            except Exception as e:
                entries, err = [], str(e)
            else:
                err = ""
            self._ui.emit(lambda: self._show_import(entries, err))
        threading.Thread(target=run, daemon=True).start()

    def _show_import(self, entries, err):
        if not entries:
            QMessageBox.information(self, "Windows 즐겨찾기", err or "불러올 즐겨찾기(고정된 폴더)가 없습니다.")
            return
        have_q = {os.path.normcase(c["path"]) for c in self.quick_items} | self._default_quick_paths()
        have_b = {os.path.normcase(x) for x in self._all_paths(self.bm["children"])}
        dlg = FavImportDialog(self, entries, have_q, have_b)
        if not dlg.exec():
            return
        chosen, dest, replace = dlg.selected(), dlg.dest.currentIndex(), dlg.replace.isChecked()
        if not chosen and not replace:
            return
        self.backup_now("_가져오기전")          # 가져오기 전에 현재 내용을 항상 백업
        added = 0
        if dest == 0:                                # 빠른 이동
            if replace:
                self.quick_items.clear()
            have = {os.path.normcase(c["path"]) for c in self.quick_items} | self._default_quick_paths()
            for e in chosen:
                if os.path.normcase(e["path"]) not in have:
                    self.quick_items.append({"name": e["name"], "path": e["path"], "net": e["path"].startswith("\\\\")})
                    have.add(os.path.normcase(e["path"]))
                    added += 1
            self.quick_changed()
        else:                                        # 북마크 바
            if replace:
                self.bm["children"].clear()
            have = {os.path.normcase(x) for x in self._all_paths(self.bm["children"])}
            for e in chosen:
                if os.path.normcase(e["path"]) not in have:
                    self.bm["children"].append({"type": "bookmark", "name": e["name"], "path": e["path"]})
                    have.add(os.path.normcase(e["path"]))
                    added += 1
            self.bookmarks_changed()
        self.say(f"Windows 즐겨찾기 {added}개를 {'북마크 바' if dest else '빠른 이동'}로 가져왔습니다 (이전 내용은 backup 폴더에 백업됨)")

    def toggle_sync(self):
        self.sync_fav = not self.sync_fav
        self.data["sync_fav"] = self.sync_fav
        self.schedule_save()

    def sync_all_fav(self):
        paths = [p for p in self._all_paths(self.bm["children"]) if os.path.isdir(p)]

        def run():
            for p in paths:
                F.pin_home(p)
            self._ui.emit(lambda: self.say(f"{len(paths)}개를 Windows 즐겨찾기에 등록했습니다"))
        threading.Thread(target=run, daemon=True).start()
        self.say("등록 중…")

    def current_state(self):
        return {"split": self.split_btn.isChecked(), "panes": [p.state() for p in self.panes]}

    def apply_state(self, st):
        for p, ps in zip(self.panes, st.get("panes", [])):
            p.restore(ps)
        for p in self.panes:
            if not p.views:
                p.restore({})
        (self.split_btn if st.get("split") else self.one_btn).setChecked(True)
        self.panes[1].setVisible(self.split_btn.isChecked())
        self.active = self.panes[0]
        self.refresh_active_marks()
        self.update_status()

    def workspace_menu(self):
        ws = self.data.setdefault("workspaces", {})
        m = QMenu(self)
        m.addAction("현재 상태를 작업공간으로 저장…", self.save_workspace)
        if ws:
            m.addSeparator()
            for name in ws:
                m.addAction(name, lambda n=name: self.apply_state(ws[n]))
            d = m.addMenu("삭제")
            for name in ws:
                d.addAction(name, lambda n=name: (ws.pop(n, None), self.schedule_save()))
        m.exec(self.ws_btn.mapToGlobal(self.ws_btn.rect().bottomLeft()))

    def save_workspace(self):
        name, ok = QInputDialog.getText(self, "작업공간 저장", "이름:")
        if ok and name.strip():
            self.data.setdefault("workspaces", {})[name.strip()] = self.current_state()
            self.save_session()
            self.say(f"작업공간 저장: {name.strip()}")

    # ---- 세션 ----
    def schedule_save(self):
        self._save_t.start(800)

    def save_session(self):
        self.data["session"] = self.current_state()
        self.data["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        save_json(EXPLORER_FILE, self.data)

    def restore_session(self):
        g = self.data.get("geometry")
        if g:
            self.restoreGeometry(QByteArray.fromBase64(g.encode()))
        st = self.data.get("session")
        if st:
            self.apply_state(st)
        else:
            self.panes[0].restore({"tabs": [{"path": HOME}]})
            self.panes[1].restore({"tabs": [{"path": HOME}]})
            self.panes[1].hide()
            self.active = self.panes[0]
            self.refresh_active_marks()

    def closeEvent(self, e):
        self.save_session()
        if self.data.get("resident", True) and self.tray_ok and not self.quitting:
            e.ignore()          # 창만 닫고 트레이에 상주 → Win+E 로 즉시 다시 열림
            self.hide()
            return
        self.quitting = True
        if self.hook is not None:
            self.hook.uninstall()
        super().closeEvent(e)
        QApplication.quit()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class WinEHook:
    """Win+E 를 가로채서 callback 을 실행 (Windows 탐색기 대신 JY Explorer 를 열거나 활성화).
    Win+E 는 Windows 가 예약한 키라 일반 단축키 등록이 안 돼서 저수준 키보드 훅(WH_KEYBOARD_LL)을 사용한다.
    앱이 떠 있는 동안에만 동작하며, 종료하면 Win+E 는 원래대로 Windows 탐색기를 연다."""
    _DOWN, _UP = (0x100, 0x104), (0x101, 0x105)

    def __init__(self, callback):
        self.callback = callback
        self.hook = None
        self._swallow = False
        self._u = ctypes.windll.user32
        lresult = ctypes.c_ssize_t
        self._proto = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self._proc = self._proto(self._on_key)          # 파이썬이 콜백을 회수하지 않도록 보관
        self._u.SetWindowsHookExW.argtypes = [ctypes.c_int, self._proto, wintypes.HINSTANCE, wintypes.DWORD]
        self._u.SetWindowsHookExW.restype = wintypes.HHOOK
        self._u.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self._u.CallNextHookEx.restype = lresult
        self._u.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]

    def install(self):
        k32 = ctypes.windll.kernel32
        k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k32.GetModuleHandleW.restype = wintypes.HMODULE      # 기본(int)이면 64비트에서 핸들이 잘려 훅 설치가 실패함
        self.hook = self._u.SetWindowsHookExW(13, self._proc, k32.GetModuleHandleW(None), 0)
        return bool(self.hook)

    def uninstall(self):
        if self.hook:
            self._u.UnhookWindowsHookEx(self.hook)
            self.hook = None

    def _pressed(self, vk):
        return bool(self._u.GetAsyncKeyState(vk) & 0x8000)

    def _on_key(self, n_code, w_param, l_param):
        try:
            if n_code == 0:
                kb = _KBDLLHOOKSTRUCT.from_address(l_param)
                if kb.vkCode == 0x45:                                          # 'E'
                    if w_param in self._DOWN:
                        win = self._pressed(0x5B) or self._pressed(0x5C)
                        other = self._pressed(0x10) or self._pressed(0x11) or self._pressed(0x12)   # Shift/Ctrl/Alt
                        if win and not other:                                   # 순수 Win+E 만 가로챔
                            self._swallow = True
                            # Win 만 눌렀다 뗐을 때 시작 메뉴가 열리지 않도록 빈 키(0xE8)를 끼워 넣음
                            self._u.keybd_event(0xE8, 0, 0, 0)
                            self._u.keybd_event(0xE8, 0, 2, 0)
                            QTimer.singleShot(0, self.callback)
                            return 1
                    elif w_param in self._UP and self._swallow:
                        self._swallow = False
                        return 1
        except Exception:
            pass
        return self._u.CallNextHookEx(self.hook, n_code, w_param, l_param)


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "JYExplorer"


def startup_command():
    if FROZEN:
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


def import_favorites_cli():
    """설치 시 '기존 Windows 탐색기 즐겨찾기 불러오기'를 체크한 경우: 창 없이 빠른 이동으로 추가(기존 내용 유지)"""
    data = load_json(EXPLORER_FILE, {})
    backup_favorites("_설치전")
    quick = data.setdefault("quick", [])
    have = {os.path.normcase(c["path"]) for c in quick} | {os.path.normcase(os.path.join(HOME, s))
                                                            for s in ("Desktop", "Downloads", "Documents", "Pictures")}
    for e in F.windows_pinned_folders():
        if os.path.normcase(e["path"]) not in have:
            quick.append({"name": e["name"], "path": e["path"], "net": e["path"].startswith("\\\\")})
            have.add(os.path.normcase(e["path"]))
    save_json(EXPLORER_FILE, data)


def main():
    if "--import-favorites" in sys.argv:
        import_favorites_cli()
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(150):  # 이미 실행 중 → 그쪽 창을 활성화(경로가 있으면 새 탭으로 열기)하고 종료
        if "--background" in sys.argv and not args:
            return              # 시작 프로그램 중복 실행 등: 이미 떠 있으면 아무것도 하지 않음
        sock.write(("\n".join(["open\t" + os.path.abspath(a) for a in args]) or "show").encode("utf-8"))
        sock.waitForBytesWritten(300)
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    load_font(app)
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon("JYExplorer"))
    w = Main()
    tray = QSystemTrayIcon(app_icon("JYExplorer"), app)
    tray.setToolTip("JY Explorer  (Win+E)")
    tm = QMenu()
    tm.addAction("열기  (Win+E)", w.bring_to_front)
    tm.addAction("종료", w.quit_app)
    tray.setContextMenu(tm)
    tray.activated.connect(lambda r: w.bring_to_front() if r == QSystemTrayIcon.Trigger else None)
    tray.show()
    w.tray_ok = tray.isVisible()
    w.updater = Updater("explorer", w.quit_app)
    w.updater.attach(w, tray, tm)
    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    def on_conn():
        s = server.nextPendingConnection()

        def read():
            msg = bytes(s.readAll()).decode("utf-8", "ignore")
            if msg.startswith("quit"):          # 업데이트 설치 전에 다른 JY 프로그램이 종료를 요청
                w.quit_app()
                return
            opened = False
            for line in msg.split("\n"):
                if line.startswith("open\t"):
                    w.open_external(line[5:])
                    opened = True
            if not opened:
                w.bring_to_front()       # 이미 떠 있으면 그냥 활성화만 (새 탭을 만들지 않음)
        s.readyRead.connect(read)
    server.newConnection.connect(on_conn)

    if not (("--background" in sys.argv) and not args):     # --background: 창 없이 트레이에서 시작
        w.show()
    for a in args:
        w.open_external(os.path.abspath(a))
    w.apply_win_e()
    if "--selftest" in sys.argv:
        QTimer.singleShot(1500, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
