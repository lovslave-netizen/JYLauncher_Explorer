"""복사 진행/새로고침/빠른 이동/런처 키 이동 테스트 (임시 데이터 폴더 사용).  python test_ops.py"""
import os
import sys
import tempfile
import threading
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["JY_INSTANCE"] = "-ops"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

app = QApplication([])


def pump(ms=300):
    t = time.time()
    while time.time() - t < ms / 1000:
        app.processEvents()


def wait_for(cond, what, timeout=40):
    t = time.time()
    while time.time() - t < timeout:
        app.processEvents()
        if cond():
            return
        time.sleep(0.03)
    raise AssertionError("timeout: " + what)


def main():
    import fileops as F
    import JYExplorer as J

    # 1) 2GB 를 넘는 진행률이 넘치지 않고 그대로 전달됨 (150GB 파일에서 용량이 '-' 로 뜨고 0% 에 멈추던 문제)
    r = J.JobRunner()
    got = []
    r.progress.connect(lambda d, t, n: got.append((d, t, n)))
    big = 150 * 1024 ** 3
    r.progress.emit(100 * 1024 ** 3, big, "huge.bin")
    pump(100)
    assert got == [(100 * 1024 ** 3, big, "huge.bin")], got
    assert J.fmt_size(100 * 1024 ** 3).endswith("GB") and not J.fmt_size(100 * 1024 ** 3).startswith("-")

    # 2) 복사 중 파일별 진행 정보(동시에 여러 개) + 끝난 폴더 알림
    src = tempfile.mkdtemp()
    dst = tempfile.mkdtemp()
    for i in range(6):
        with open(os.path.join(src, f"f{i}.bin"), "wb") as f:
            f.write(os.urandom(3 * 1024 * 1024))
    F.CHUNK = 256 * 1024                              # 진행 중 상태를 잡을 수 있게 조각을 작게
    job = F.Job("copy", [os.path.join(src, f"f{i}.bin") for i in range(6)], dst)
    seen = []
    orig_add = job._add

    def slow_add(n, name=None):
        time.sleep(0.004)
        orig_add(n, name)
    job._add = slow_add
    t = threading.Thread(target=lambda: job.run(lambda d, tot, n: seen.append(job.snapshot())))
    t.start()
    t.join(60)
    most = max((len(s) for s in seen), default=0)
    assert most >= 2, most                            # 동시에 2개 이상 진행되는 순간이 있음
    assert job.total_files == 6 and job.files_done == 6 and not job.active
    assert all(0 <= d <= s for snap in seen for _n, d, s in snap)
    assert sorted(os.listdir(dst)) == sorted(f"f{i}.bin" for i in range(6))

    # 3) 폴더 새로고침: 모델 감시가 놓친 변경도 refresh() 로 보임 + 선택/정렬 유지
    w = J.Main()
    w.show()
    pump()
    v = w.active_view()
    folder = tempfile.mkdtemp()
    open(os.path.join(folder, "a.txt"), "w").write("x")
    v.navigate(folder)
    wait_for(lambda: v.model_.rowCount(v.rootIndex()) == 1, "첫 목록")
    old_model = v.model_
    v.model_.setOption(J.QFileSystemModel.DontWatchForChanges, True)      # 감시를 꺼서 '변경을 놓친' 상태를 만듦
    pump(200)
    open(os.path.join(folder, "b.txt"), "w").write("y")
    pump(600)
    v.refresh()
    wait_for(lambda: v.model_.rowCount(v.rootIndex()) == 2, "refresh 후 2개")
    assert v.model_ is not old_model
    assert v.header().isSectionHidden(5) and not v.header().isSectionHidden(1)      # 열 설정 유지
    # 작업이 끝난 폴더를 다시 읽는 연결
    w.runner.touched.emit([folder])
    pump(1200)
    # 새 파일은 목록에 없어도 select_path 가 새로 읽어서 찾음
    open(os.path.join(folder, "c.txt"), "w").write("z")
    v.select_path(os.path.join(folder, "c.txt"))
    wait_for(lambda: v.model_.index(os.path.join(folder, "c.txt")).isValid(), "c.txt 표시")

    # 4) 빠른 이동: 드라이브 이름 + 새로고침
    name = J.drive_display("C:\\")
    assert name.endswith("(C:)") and len(name) > 4, name
    texts = [w.quick.item(i).data(Qt.UserRole + 2) for i in range(w.quick.count())]
    assert any(x.endswith("(C:)") and len(x) > 4 for x in texts), texts
    mask = w._drive_mask
    w._drive_mask = 0
    w._check_drives()                                  # 드라이브 구성이 바뀐 것으로 보고 목록 갱신
    assert w._drive_mask == mask
    assert w.quick.count() == len(texts)

    # 4-2) 화면 구성: 빠른 이동 = 아이콘 격자(글자 없음, 툴팁), 세트 북마크 = 설정 왼쪽 버튼, 배지/세트 바 숨김, 기본 접힘
    assert all(w.quick.item(i).text() == "" and w.quick.item(i).toolTip() for i in range(w.quick.count()))
    assert w.quick.height() <= w.quick.GRID.height() * 6 + 8, w.quick.height()          # 열 개 남짓 → 몇 줄이면 끝
    assert w.sets_btn.x() > w.search_btn.x() and w.sets_btn.x() < w.opt_btn.x()
    assert not w.bmbar.isVisible()
    w.split_btn.click()
    pump(200)
    assert all(not p.badge.isVisible() for p in w.panes)
    w.one_btn.click()
    assert not w.side_tree.topLevelItem(1).isExpanded() and not w.side_tree.topLevelItem(2).isExpanded()
    assert w.side_tree.topLevelItem(0).isExpanded()
    icon = J.drive_icon("C:\\")
    assert not icon.isNull() and isinstance(J.special_drive_letters(), set)

    # 4-3) 경로줄: 길면 맨 앞 드라이브는 남기고 가운데를 … 로 접어 마지막 폴더가 보임
    pb = J.PathBar()
    pb.resize(330, 34)
    pb.show()
    pb.set_path("D:\\aa\\bbbbbbbbbbbb\\cccccccccccc\\dddddddddddd\\eeeeeeeeeeee\\last")
    pump(200)
    vis = [b.text() for b, _s in pb._items if b.isVisible()]
    assert vis[0] == "D:" and vis[-1] == "last" and pb.ell.isVisible() and len(vis) < 7, vis
    assert [n for n, _p in pb._segs[1:pb._start]] and all(n not in vis for n, _p in pb._segs[1:pb._start])
    pb.resize(2000, 34)
    pump(200)
    assert all(b.isVisible() for b, _s in pb._items) and not pb.ell.isVisible()
    pb.close()

    # 4-4) 키보드: F3/F4/Ctrl+Tab 영역 이동, Alt+숫자, Ctrl+숫자 북마크 단축키
    from PySide6.QtGui import QKeySequence, QShortcut
    keys = {sc.key().toString() for sc in w.findChildren(QShortcut)}
    for k in ["F3", "F4", "F7", "Ctrl+Tab", "Alt+`", "Alt+-", "Alt+=", "Alt+0"] + [f"Alt+{i}" for i in range(1, 10)] + [f"Ctrl+{i}" for i in range(1, 10)]:
        assert k in keys, k
    w.activateWindow()
    pump(300)
    w.focus_sidebar()
    pump(100)
    assert w.quick.hasFocus() and w.quick.currentItem() is not None and w.quick_panel.property("kfocus") is True
    w.key_f3()                                         # 빠른 이동 → 북마크 트리
    pump(100)
    assert w.side_tree.hasFocus() and w._last_side == "tree" and w.tree_panel.property("kfocus") is True and w.quick_panel.property("kfocus") is False
    w.key_f3()                                         # 다시 → 빠른 이동
    pump(100)
    assert w.quick.hasFocus()
    w.toggle_area()                                    # Ctrl+Tab → 패널
    pump(100)
    assert not w.in_sidebar() and w.active_view().hasFocus()
    w.toggle_area()                                    # 다시 → 마지막 사이드바 위치(빠른 이동)
    pump(100)
    assert w.quick.hasFocus()
    w.key_f4()                                         # F4 → 패널
    pump(100)
    assert not w.in_sidebar()
    # Enter 로 열기: 빠른 이동 / 북마크 트리
    opened = []
    w.open_path = lambda p, nt: opened.append((p, nt))
    from PySide6.QtGui import QKeyEvent
    w.focus_sidebar("quick")
    w.quick.setCurrentRow(1)
    QApplication.sendEvent(w.quick, QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert opened and opened[-1][0] == w.quick.item(1).data(Qt.UserRole) and not opened[-1][1], opened
    # Alt+숫자: 드라이브(보이는 순서), 장소
    drv = [w.quick.item(r).data(Qt.UserRole) for r in range(w.quick.count()) if w.quick.item(r).data(Qt.UserRole + 3) == "drive"]
    w.alt_drive(1)
    assert opened[-1] == (drv[0], False)
    w.alt_drive(len(drv))
    assert opened[-1] == (drv[-1], False)
    w.alt_place("Downloads")
    assert opened[-1] == (os.path.join(J.HOME, "Downloads"), False)
    w.alt_place("")
    assert opened[-1] == ("", False)
    assert "Alt+1" in w.quick.item([r for r in range(w.quick.count()) if w.quick.item(r).data(Qt.UserRole + 3) == "drive"][0]).toolTip()
    # Ctrl+숫자: 북마크 단축키 지정/중복 이동/열기/해제
    fa, fb = tempfile.mkdtemp(), tempfile.mkdtemp()
    w.bm["children"] = [{"type": "bookmark", "name": "A북마크", "path": fa},
                        {"type": "folder", "name": "묶음", "open": True, "children": [{"type": "bookmark", "name": "B북마크", "path": fb}]}]
    w.bookmarks_changed()
    w.set_key(w.bm["children"][0], 1)
    w.set_key(w.bm["children"][1]["children"][0], 2)
    w.open_key(1)
    assert opened[-1] == (fa, False)
    w.open_key(2)
    assert opened[-1] == (fb, False)
    w.set_key(w.bm["children"][1]["children"][0], 1)                   # 1번을 B 가 가져가면 A 는 해제
    assert w.bm["children"][0].get("key") is None and w._node_with_key(1)["name"] == "B북마크"
    labels = []
    w.side_tree.build(w.bm, [], [], {})
    assert any("[Ctrl+1]" in w.side_tree.topLevelItem(0).child(i).text(0) or
               any("[Ctrl+1]" in w.side_tree.topLevelItem(0).child(i).child(j).text(0) for j in range(w.side_tree.topLevelItem(0).child(i).childCount()))
               for i in range(w.side_tree.topLevelItem(0).childCount()))
    w.set_key(w._node_with_key(1), None)
    assert w._node_with_key(1) is None
    w.open_key(5)                                                      # 지정 안 된 번호는 안내만
    opened.clear()
    w.open_key(5)
    assert not opened

    # 4-5) 단축키 보기: 등록된 모든 단축키가 목록에 있고, 목록의 키가 실제로 등록돼 있음
    listed = {k for _g, rows in J.SHORTCUT_HELP for _key, reg, _d in rows for k in reg}
    assert keys <= listed, sorted(keys - listed)                 # 등록은 됐는데 목록에 없는 키
    assert listed <= keys, sorted(listed - keys)                 # 목록에는 있는데 등록 안 된 키 (오타)
    dlg = J.ShortcutDialog(w)
    assert dlg.tree.topLevelItemCount() == len(J.SHORTCUT_HELP)
    dlg.q.setText("북마크")
    shown = [dlg.tree.topLevelItem(i).text(0) for i in range(dlg.tree.topLevelItemCount()) if not dlg.tree.topLevelItem(i).isHidden()]
    assert "북마크" in shown and "탭" not in shown, shown
    dlg.q.setText("f4")
    assert any(not dlg.tree.topLevelItem(i).child(j).isHidden() and dlg.tree.topLevelItem(i).child(j).text(0) == "F4"
               for i in range(dlg.tree.topLevelItemCount()) for j in range(dlg.tree.topLevelItem(i).childCount()))
    dlg.q.setText("zzzz없는키")
    assert all(dlg.tree.topLevelItem(i).isHidden() for i in range(dlg.tree.topLevelItemCount()))
    dlg.close()

    # 5) 드라이브 루트 Windows 메뉴 (포맷/속성 등): 셸을 쓸 수 있는 환경에서만
    try:
        import shellmenu as SM
        m = SM.ShellMenu(["C:\\"], "C:\\", allow_root=True)
    except Exception as e:                             # noqa: BLE001
        print("shell unavailable - skipped:", type(e).__name__)
    else:
        verbs = set(m.command_ids().values())
        n = m.remove_verbs({"open", "rename", "delete", "cut", "paste"})
        left = set(m.command_ids().values())
        assert "properties" in verbs and not (left & {"delete", "cut", "rename"}), (verbs, left)
        m.close()
        try:
            SM.ShellMenu(["C:\\"], "C:\\")             # 기본(허용 안 함)은 예전처럼 거부
            raise AssertionError("root must be rejected by default")
        except SM.ShellMenuUnsupported:
            pass
    # 6) 폴더 통째 이동이 권한으로 막혀도(이름 바꾸기 거부) 복사 후 삭제로 이동됨
    base = tempfile.mkdtemp()
    sdir = os.path.join(base, "src", "folder")
    os.makedirs(os.path.join(sdir, "sub"))
    for rel in ("a.txt", os.path.join("sub", "b.txt")):
        open(os.path.join(sdir, rel), "w").write("data")
    ddir = os.path.join(base, "dst")
    os.makedirs(ddir)
    real_rename = os.rename

    def denied(a, b, *x, **k):
        if os.path.isdir(a):
            raise PermissionError(5, "액세스가 거부되었습니다")
        return real_rename(a, b, *x, **k)
    os.rename = denied
    try:
        j = F.Job("move", [sdir], ddir)
        assert j.run() and not j.errors, j.errors
    finally:
        os.rename = real_rename
    assert open(os.path.join(ddir, "folder", "sub", "b.txt")).read() == "data" and not os.path.exists(sdir)

    # 7) F2 이름 바꾸기: 확장자 앞까지만 선택
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import QLineEdit
    import search_ui as SUI

    def stem_selection(name, is_dir):
        mdl = QStandardItemModel()
        mdl.appendRow(QStandardItem(name))
        ed = QLineEdit()
        SUI.StemDelegate(lambda ix: is_dir).setEditorData(ed, mdl.index(0, 0))
        pump(100)
        return ed.selectedText()
    assert stem_selection("보고서.최종.txt", False) == "보고서.최종"
    assert stem_selection("폴더.v2", True) == "폴더.v2"
    assert stem_selection(".gitignore", False) == ".gitignore"          # 점으로 시작하는 파일은 전체 선택
    assert stem_selection("noext", False) == "noext"
    assert isinstance(w.active_view().itemDelegate(), SUI.StemDelegate)
    print("explorer ops OK", flush=True)

    # 8) 런처: 맨 위에서 ↑ → 위쪽 버튼줄, ← → 이동, ↓ 복귀
    import JYLauncher as L
    lw = L.Main()
    lw.show()
    pump()
    lw.goto(0)
    pg = lw.launcher
    if pg.rows:
        pg.select(pg.rows[0][0])
        assert pg.at_top()

    def key(k):
        lw.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, k, Qt.NoModifier))
    key(Qt.Key_Up)
    assert lw._hdr == 0 and lw.header_widgets()[0].property("kb") is True
    key(Qt.Key_Right)
    assert lw._hdr == 1
    key(Qt.Key_Left)
    key(Qt.Key_Left)
    assert lw._hdr == len(lw.header_widgets()) - 1          # 처음에서 ← 는 끝으로 순환
    # 버튼 실행: 크기 토글 버튼(= '작은 아이콘' 등)을 Enter 로 누르면 눌림
    ws = lw.header_widgets()
    target = next(i for i, wd in enumerate(ws) if wd.isCheckable() and not wd.isChecked())
    lw.set_header(target)
    key(Qt.Key_Return)
    assert ws[target].isChecked()
    key(Qt.Key_Down)
    assert lw._hdr == -1 and all(w2.property("kb") in (False, None) for w2 in ws)
    lw.goto(1)
    assert lw._hdr == -1
    print("launcher header keys OK", flush=True)


try:
    main()
    code = 0
except Exception:
    import traceback
    traceback.print_exc()
    code = 1
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
