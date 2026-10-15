"""런처 항목 전역 단축키 / 경로 변경 / 탐색기 이름 바꾸기 → 키 테스트.   python test_hotkeys.py"""
import ctypes
import os
import sys
import tempfile
import time
import traceback
from ctypes import wintypes

tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp
os.environ["JY_INSTANCE"] = "-hktest"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QStandardItem, QStandardItemModel  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QTreeView  # noqa: E402

app = QApplication([])


def pump(ms=200):
    t = time.time()
    while time.time() - t < ms / 1000:
        app.processEvents()


def fake_hotkey(filt, hid):
    msg = wintypes.MSG()
    msg.message, msg.wParam = 0x0312, hid
    return filt.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))


def main():
    import hotkeys as HK
    # 형식 검사
    assert HK.parse_hotkey("Ctrl+Alt+N") == ("Ctrl+Alt+N", HK.MOD_CONTROL | HK.MOD_ALT, ord("N"))
    assert HK.parse_hotkey("ctrl+alt+shift+f12")[2] == 0x7B
    for bad in ("", "N", "Shift+N", "Ctrl+;", "Ctrl+A, Ctrl+B"):
        assert HK.parse_hotkey(bad) is None, bad
    # 실제 등록/중복/예약/해제 (눈에 띄지 않는 조합으로 잠깐만 등록)
    called = []
    f = HK.ItemHotkeys(called.append)
    a, b = {"name": "a"}, {"name": "b"}
    failed = f.apply([("Ctrl+Alt+Shift+F23", a), ("ctrl+alt+shift+f23", b), ("Ctrl+Alt+L", b)], reserved=("Ctrl+Alt+L",))
    assert len(f.ids) == 1 and len(failed) == 2, failed
    hid = next(iter(f.ids))
    assert fake_hotkey(f, hid) == (True, 0) and called == [a]        # 눌림 → 해당 항목 콜백
    assert fake_hotkey(f, hid + 99) == (False, 0)
    f.clear()
    assert not f.ids

    # 런처: 단축키/경로 변경 데이터 흐름
    import JYLauncher as L
    w = L.Main()
    w.show()
    pump()
    tdir = tempfile.mkdtemp()
    real = os.path.join(tdir, "real.txt")
    open(real, "w").write("x")
    it = {"name": "T", "path": os.path.join(tdir, "gone.txt"), "hotkey": "Ctrl+Alt+Shift+F22"}
    w.launcher.data = {"테스트": [it, {"type": "folder", "name": "F", "items": [{"name": "U", "path": real, "hotkey": "Ctrl+Alt+Shift+F22"}]}]}
    failed = w.apply_hotkeys()
    assert len(failed) == 1 and failed[0][1]["name"] == "U", failed       # 두 번째(중복)만 실패
    assert w.launcher.all_apps() == [it, w.launcher.data["테스트"][1]["items"][0]]
    ran = []
    w.hotkey_launch = lambda x: ran.append(x)
    w.item_hotkeys.callback = w.hotkey_launch
    assert fake_hotkey(w.item_hotkeys, next(iter(w.item_hotkeys.ids))) == (True, 0) and ran == [it]
    # 경로 변경 (대화창은 건너뛰고 결과 주입)
    class FakeDlg:
        result_path = real
        def __init__(self, *a): pass
        def exec(self): return True
    L.PathDialog = FakeDlg
    w.launcher.change_path(it)
    assert it["path"] == os.path.normpath(real)
    L.PathDialog.result_path = os.path.join(tdir, "nope")
    shown = []
    L.QMessageBox.warning = lambda *a, **k: shown.append(a[2])
    w.launcher.change_path(it)
    assert it["path"] == os.path.normpath(real) and shown                  # 없는 경로는 거절
    w.launcher.clear_hotkey(it)
    assert "hotkey" not in it
    w.item_hotkeys.clear()
    print("launcher hotkeys OK", flush=True)

    # 탐색기: F2 이름 바꾸기에서 → 키는 확장자 앞에서 멈춤
    import search_ui as SUI
    m = QStandardItemModel()
    for n in ("파일명.mp4", "폴더", "noext", ".gitignore", "a.b.mkv"):
        m.appendRow(QStandardItem(n))
    for row, exp in ((0, 3), (1, 2), (2, 5), (3, 10), (4, 3)):
        tv = QTreeView()
        tv.setModel(m)
        tv.setItemDelegate(SUI.StemDelegate(lambda ix: ix.row() == 1, tv))
        tv.show()
        pump(100)
        idx = m.index(row, 0)
        tv.setCurrentIndex(idx)
        tv.edit(idx)
        pump(200)
        ed = tv.findChild(QLineEdit)
        QTest.keyClick(ed, Qt.Key_Right)
        assert ed.cursorPosition() == exp and not ed.hasSelectedText(), (row, ed.cursorPosition())
        QTest.keyClick(ed, Qt.Key_Right)                                    # 두 번째 → 부터는 평소처럼 한 칸씩
        assert ed.cursorPosition() == min(exp + 1, len(ed.text()))
        tv.close()
    print("rename right-key OK", flush=True)

    # 탐색기: 새 폴더 → 바로 이름 입력, 자동 새로고침이 입력을 끊지 않음, 도구줄 버튼
    import JYExplorer as J
    from PySide6.QtWidgets import QAbstractItemView
    ew = J.Main()
    ew.show()
    pump(500)
    root = tempfile.mkdtemp()
    for i in range(20):
        open(os.path.join(root, f"f{i}.txt"), "w").write("x")
    v = ew.active_view()
    v.navigate(root)
    pump(1200)
    n0 = len(os.listdir(root))
    ew.active.btn_newfolder.click()
    pump(800)
    assert len(os.listdir(root)) == n0 + 1 and v.state() == QAbstractItemView.EditingState
    v.refresh_if_changed()                                                   # 창 복귀 때의 자동 새로고침
    pump(300)
    assert v.state() == QAbstractItemView.EditingState
    print("new folder rename OK", flush=True)


def main2():
    import JYExplorer as J
    ew = J.Main()
    ew.show()
    pump(500)

    # 탭 끌기 표시: 반대편 패널 위에서만 켜지고, 놓으면 꺼짐
    ew.split_btn.click()
    pump(400)
    a, b = ew.panes
    a._press_vid = next(iter(a.views))
    a._hint_drop_target(b.mapToGlobal(b.rect().center()))
    assert b._drop_hint.isVisible()
    a._hint_drop_target(a.mapToGlobal(a.rect().center()))
    assert not b._drop_hint.isVisible()
    a._hint_drop_target(b.mapToGlobal(b.rect().center()))
    a._press_vid = None
    a._hint_drop_target(b.mapToGlobal(b.rect().center()))
    assert not b._drop_hint.isVisible()
    print("tab drop hint OK", flush=True)

    # 이동 팔레트
    import palette as PAL
    docs, docs_lower, photos = "C:\\Users\\x\\Documents", "c:\\users\\x\\documents", "D:\\사진"
    ents = PAL.build_entries([("탭", [("문서", docs)]), ("북마크", [("문서2", docs_lower), ("사진", photos)])])
    assert [e[2] for e in ents] == [docs, photos]                           # 같은 경로는 먼저 나온 것 하나만
    assert [e[1] for e in PAL.filter_entries(ents, "사진")] == ["사진"]
    assert PAL.filter_entries(ents, "users docu") and not PAL.filter_entries(ents, "없는것")
    pal = PAL.Palette(ents)
    got = []
    pal.chosen.connect(lambda p, nt: got.append((p, nt)))
    pal.show()
    pump(100)
    pal.q.setText("사진")
    QTest.keyClick(pal.q, Qt.Key_Return, Qt.ControlModifier)
    assert got == [(photos, True)], got
    opened = []
    ew.open_path = lambda p, nt: opened.append((p, nt))
    orig = PAL.Palette.exec
    PAL.Palette.exec = lambda self: (self.q.setText("바탕화면"), self.pick(False))
    ew.open_palette()
    PAL.Palette.exec = orig
    assert opened and opened[0][0].endswith("Desktop") and opened[0][1] is False, opened
    print("palette OK", flush=True)

    # 특수 열기 설정: 기본 규칙과 같으면 저장 안 함, 지운 기본 규칙은 ""(끔)
    import specialopen as SO
    import specialopen_ui as SOU
    dxb = SO.DEFAULT_RULES[".dxb"]
    npad = "C:\\Windows\\notepad.exe"
    assert SOU.normalize_ext(" DXB ") == ".dxb" and SOU.normalize_ext(".") == ""
    assert SOU.rules_to_save([(".dxb", dxb), ("abc", npad)]) == {".abc": npad}
    assert SOU.rules_to_save([("abc", npad)]) == {".dxb": "", ".abc": npad}
    SO.set_rules({".dxb": "", ".abc": npad})
    assert SO.rule_for("x.dxb") is None and SO.rule_for("x.abc")
    SO.set_rules(None)
    dlg = SOU.SpecialOpenDialog(ew, {".abc": npad})
    assert (".abc", npad) in dlg.rows() and any(r[0] == ".dxb" for r in dlg.rows())
    print("special open settings OK", flush=True)

    # 사진 미리보기
    import imgpreview as IMG
    from PySide6.QtGui import QColor, QImage
    d = tempfile.mkdtemp()
    names = []
    for n, (w_, h_) in (("a.png", (400, 200)), ("b.png", (100, 300))):
        im = QImage(w_, h_, QImage.Format_RGB32)
        im.fill(QColor("steelblue"))
        im.save(os.path.join(d, n))
        names.append(os.path.join(d, n))
    open(os.path.join(d, "c.txt"), "w").write("x")
    assert IMG.is_image("X.JPG") and not IMG.is_image("c.txt")
    prev = IMG.ImagePreview(names, 0)
    prev.show()
    pump(100)
    assert prev.img.pixmap().width() == 400
    QTest.keyClick(prev, Qt.Key_Right)
    assert prev.i == 1 and prev.img.pixmap().height() == 300
    QTest.keyClick(prev, Qt.Key_Right)
    assert prev.i == 0                                                       # 끝에서 처음으로
    QTest.keyClick(prev, Qt.Key_Escape)
    assert not prev.isVisible()
    v = ew.panes[0].view()
    v.navigate(d)
    pump(1500)
    shown = []
    IMG.ImagePreview.exec = lambda self: shown.append([os.path.basename(x) for x in self.paths])      # 러너 임시 경로는 8.3 짧은 이름일 수 있어 이름만 비교
    v.select_path(names[1])
    pump(300)
    QTest.keyClick(v, Qt.Key_Space)
    assert shown == [[os.path.basename(x) for x in names]], shown
    v.select_path(os.path.join(d, "c.txt"))
    pump(300)
    QTest.keyClick(v, Qt.Key_Space)
    assert len(shown) == 1                                                   # 사진이 아니면 미리보기 안 함
    print("image preview OK", flush=True)

    # 최근 항목 → 끌면 실제 파일 URL (보관함에 놓으면 핀), 이미 있는 파일은 중복 추가 안 함
    import JYLauncher as L
    from PySide6.QtWidgets import QTreeWidgetItem
    lw = L.Main()
    lw.show()
    pump(200)
    real = os.path.join(d, "a.png")
    L.lnk_target = lambda p: real if p.endswith("ok.lnk") else ""
    t = lw.recent.tree
    it1, it2 = QTreeWidgetItem(["ok"]), QTreeWidgetItem(["gone"])
    it1.setData(0, Qt.UserRole, "ok.lnk")
    it2.setData(0, Qt.UserRole, "gone.lnk")
    mime = t.mimeData([it1, it2])
    assert [u.toLocalFile() for u in mime.urls()] == [real.replace("\\", "/")], [u.toLocalFile() for u in mime.urls()]
    n0 = len(lw.vault.root["children"])
    lw.vault.on_files([real], None)
    assert len(lw.vault.root["children"]) == n0 + 1
    lw.vault.on_files([real], None)
    assert len(lw.vault.root["children"]) == n0 + 1
    print("recent drag to vault OK", flush=True)


try:
    main()
    main2()
    code = 0
except Exception:
    traceback.print_exc()
    code = 1
sys.stdout.flush()
sys.stderr.flush()
_k = ctypes.WinDLL("kernel32")
_k.GetCurrentProcess.restype = ctypes.c_void_p
_k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_k.TerminateProcess(_k.GetCurrentProcess(), code)
os._exit(code)
