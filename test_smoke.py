"""화면 스모크 테스트: 두 프로그램의 메인 창을 실제로 만들고 검색 탭/검색 페이지까지 열어 봄 (임시 데이터 폴더 사용).
빌드 전에 돌려서 '지연 생성되는 화면'(검색 탭 등)의 누락/오타를 잡는다.   python test_smoke.py
(느린 PC/CI 러너에서도 안정적이도록 시간 고정 대기 대신 '조건이 될 때까지 최대 N초' 로 기다림)"""
import os
import sys
import tempfile
import time
import traceback

tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp                       # 실제 사용자 데이터를 건드리지 않음
os.environ["JY_INSTANCE"] = "-smoke"              # 실행 중인 설치본과 부딪히지 않음
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])


def pump(ms=300):
    t = time.time()
    while time.time() - t < ms / 1000:
        app.processEvents()


def wait_for(cond, what, timeout=60.0):
    t = time.time()
    while time.time() - t < timeout:
        app.processEvents()
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError(f"시간 초과({timeout:.0f}초): {what}")


def main():
    # ── 탐색기: 검색 탭 (Ctrl+F / Ctrl+Shift+F), 결과 복사, 클립보드 ──
    import JYExplorer as J

    w = J.Main()
    w.show()
    pump()
    w.use_everything, w._guard_done = False, True           # Everything 없이 직접 검색 경로로
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "a", "deep"))
    for f in ("a/report.txt", "a/deep/report2.docx"):
        open(os.path.join(root, f), "w").write("x")
    w.active_view().navigate(os.path.join(root, "a"))
    pump()
    # 일반 파일 목록에서 Ctrl+C → 클립보드 텍스트의 경로 구분자는 항상 \\ (Qt 기본은 /)
    fv = w.active_view()
    pump(800)
    fv.selectAll()
    wait_for(lambda: len(fv.selected_paths()) >= 1, "파일 목록 선택")
    w.key_action("copy", w.active, fv)
    txt = app.clipboard().mimeData().text()
    assert txt and "/" not in txt and "\\" in txt, repr(txt)
    w.open_search("folder")
    pump()
    page = w.active_view().search_page
    assert page is not None and page.tree is not None
    page.query.setText("report")
    wait_for(lambda: page.tree.topLevelItemCount() == 2, "탐색기 검색 결과 2개")
    page.tree.selectAll()
    page.tree.copyRequested.emit([r[0] for r in page.tree.selected_results()])   # Ctrl+C 경로
    mime = app.clipboard().mimeData()
    assert len(mime.urls()) == 2 and "report" in mime.text()
    # 결과 목록은 탐색기처럼: 열 순서, 이름 바꾸기(F2 경로), 잘못된 이름은 되돌림
    assert [page.tree.headerItem().text(i) for i in range(5)] == ["이름", "위치", "수정한 날짜", "확장자", "크기"]
    it = page.tree.topLevelItem(0)
    from PySide6.QtCore import Qt
    old_path = it.data(0, Qt.UserRole)[0]
    new_path = w.rename_path(old_path, "smoke_renamed" + os.path.splitext(old_path)[1])
    assert new_path and os.path.exists(new_path) and not os.path.exists(old_path)
    assert w.rename_path(new_path, "bad:name") is None
    w.open_search("all")
    pump()
    assert w.active_view().search_page is page              # 이미 검색 탭이면 재사용

    # 검색 결과의 폴더는 같은 탭 안에서 들어가고, ◀ 뒤로 = 검색 결과로 복귀 (탭이 늘어나지 않음)
    page.query.setText("deep")

    def deep_row():
        for i in range(page.tree.topLevelItemCount()):
            it = page.tree.topLevelItem(i)
            if it.text(0) == "deep":                              # 이전 검색(report)의 남은 결과가 아니라 실제 'deep' 폴더 행
                return it.data(0, 0x100)
        return None
    wait_for(lambda: deep_row() is not None, "'deep' 폴더 검색 결과")
    n_tabs = w.active.tabbar.count()
    folder_row = deep_row()
    w.open_search_result(w.active, folder_row[0], True)
    pump(300)
    v = w.active_view()
    assert w.active.tabbar.count() == n_tabs and v.search_page is None and v.suspended_search is page
    assert os.path.normcase(v.path) == os.path.normcase(folder_row[0])
    v.back()                                                # ◀
    pump(300)
    assert v.search_page is page and v.suspended_search is None and page.query.text() == "deep"
    assert w.search_box.text() == "deep"                    # 도구줄 검색창이 검색 탭과 같은 검색어를 보여줌
    # 도구줄 검색창에 입력 → 검색 탭에서 바로 검색
    w.search_box.setText("report")
    wait_for(lambda: page.query.text() == "report" and page.tree.topLevelItemCount() >= 1, "도구줄 검색창 입력 반영")
    assert w.active.tabbar.count() == n_tabs

    w.save_session()
    print("explorer smoke OK", flush=True)

    # ── 런처: 검색 탭 (파일 + 앱) ──
    import JYLauncher as L

    lw = L.Main()
    lw.show()
    pump()
    sp = lw.search_page
    sp._guard_done, sp._use_everything = True, False
    i = sp.scope.count() - 1
    sp.scope.setItemData(i, root)
    sp.scope.setCurrentIndex(i)
    lw.goto(2)
    lw.search.setText("report")
    wait_for(lambda: sp.tree.topLevelItemCount() == 1, "런처 파일 검색 결과 1개 (하나는 위에서 이름을 바꿨음)")
    wait_for(lambda: sp.apps is not None, "앱 색인 생성 (PowerShell Get-StartApps)", timeout=90)
    print("launcher smoke OK", flush=True)


try:
    main()
    code = 0
except Exception:
    traceback.print_exc()
    code = 1
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)          # 종료 시 백그라운드 스레드(검색/앱 색인)와 Qt 객체 파괴 순서 때문에 나는 접근 위반을 피하려고 바로 종료
