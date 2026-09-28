"""화면 스모크 테스트: 두 프로그램의 메인 창을 실제로 만들고 검색 탭/검색 페이지까지 열어 봄 (임시 데이터 폴더 사용).
빌드 전에 돌려서 '지연 생성되는 화면'(검색 탭 등)의 누락/오타를 잡는다.   python test_smoke.py"""
import os
import sys
import tempfile
import time

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


# ── 탐색기: 검색 탭 (Ctrl+F / Ctrl+Shift+F), 결과 복사, 클립보드 ──
import JYExplorer as J  # noqa: E402

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
w.open_search("folder")
pump()
page = w.active_view().search_page
assert page is not None and page.tree is not None
page.query.setText("report")
pump(1500)
assert page.tree.topLevelItemCount() == 2, page.tree.topLevelItemCount()
page.tree.setCurrentItem(page.tree.topLevelItem(0))
page.tree.selectAll()
page.tree.copyRequested.emit([r[0] for r in page.tree.selected_results()])   # Ctrl+C 경로
assert len(app.clipboard().mimeData().urls()) == 2 and "report" in app.clipboard().mimeData().text()
w.open_search("all")
pump()
assert w.active_view().search_page is page              # 이미 검색 탭이면 재사용
w.save_session()
print("explorer smoke OK")

# ── 런처: 검색 탭 (파일 + 앱) ──
import JYLauncher as L  # noqa: E402

lw = L.Main()
lw.show()
pump()
sp = lw.search_page
sp._guard_done, sp._use_everything = True, False
i = sp.scope.count() - 1
sp.scope.setItemData(i, root)
sp.scope.setCurrentIndex(i)
lw.goto(3)
lw.search.setText("report")
pump(1500)
assert sp.tree.topLevelItemCount() == 2, sp.tree.topLevelItemCount()
sp.app_btn.setChecked(True)
pump(3500)
assert sp.apps is not None                               # 앱 색인이 만들어짐 (개수는 PC 마다 다름)
print("launcher smoke OK")

# 종료 시 백그라운드 스레드(검색/앱 색인)와 Qt 객체 파괴 순서 때문에 나는 접근 위반(0xC0000005)을 피하려고 바로 종료
sys.stdout.flush()
os._exit(0)
