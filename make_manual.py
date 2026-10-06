"""JY Tools 사용설명서(PDF) 생성기.   python make_manual.py   →  docs\\JYTools_사용설명서.pdf
- 화면 캡처는 임시 데이터 폴더 + 가짜 데모 파일로 실제 프로그램을 띄워서 찍음 (내 개인 데이터는 쓰지 않음)
- 단축키 표는 프로그램의 SHORTCUT_HELP 에서 그대로 가져와서 프로그램과 어긋나지 않음
- 글은 이 파일의 HTML 에 있고, Qt(QTextDocument + QPdfWriter)로 PDF 를 만듦 (한글 글꼴은 번들 Noto Sans KR)
버전/설명이 바뀌면 이 파일을 고쳐 다시 실행하면 된다."""
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "docs" / "JYTools_사용설명서.pdf"
os.environ["APPDATA"] = tempfile.mkdtemp()                 # 실제 사용자 데이터를 건드리지 않음
os.environ["JY_INSTANCE"] = "-manual"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HERE))

from PySide6.QtCore import QCoreApplication, QEvent, QMarginsF, QSizeF, QUrl, Qt  # noqa: E402
from PySide6.QtGui import QFont, QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
import JYExplorer as J  # noqa: E402
import JYLauncher as L  # noqa: E402
from jycommon import load_font  # noqa: E402
from version import __version__  # noqa: E402

load_font(app)


def pump(ms=500):
    t = time.time()
    while time.time() - t < ms / 1000:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def wait_for(cond, timeout=20):
    t = time.time()
    while time.time() - t < timeout and not cond():
        app.processEvents()
        time.sleep(0.03)


# ───────────── 데모 데이터 + 화면 캡처 ─────────────
def make_demo():
    root = Path(r"C:\Users\Public\JYDemo") / "업무 자료"
    for d in ("2026 계획", "회의록", "점자 악보", "사진 모음"):
        (root / d).mkdir(parents=True)
    files = {"업무보고서_9월.xlsx": 48200, "회의록_정리.hwp": 31500, "발표자료.pptx": 2_400_000, "계획서_초안.docx": 86500,
             "메모.txt": 1200, "참고자료.pdf": 5_800_000}
    for n, sz in files.items():
        (root / n).write_bytes(b"x" * min(sz, 4000))
    for n in ("2026년 사업계획.hwp", "예산안.xlsx", "일정표.docx", "보고서_최종.hwp"):
        (root / "2026 계획" / n).write_bytes(b"x" * 3000)
    for n in ("1주차 회의록.hwp", "2주차 회의록.hwp"):
        (root / "회의록" / n).write_bytes(b"x" * 2000)
    (root / "점자 악보" / "Love Actually (Pf).dxb").write_bytes(b"x" * 2000)
    return root


def shots():
    out = {}
    demo = make_demo()
    w = J.Main()
    w.resize(1400, 820)
    w.show()
    pump(800)
    w.use_everything, w._guard_done = False, True
    w.bm["children"] = [
        {"type": "folder", "name": "자주 쓰는 폴더", "open": True, "children": [
            {"type": "bookmark", "name": "업무 자료", "path": str(demo), "mark": ["star", "#ffd166"], "key": 1},
            {"type": "bookmark", "name": "2026 계획", "path": str(demo / "2026 계획"), "mark": ["circle", "#4cd97b"]}]},
        {"type": "bookmark", "name": "회의록", "path": str(demo / "회의록"), "mark": ["triangle", "#ff5c5c"], "key": 2},
        {"type": "bookmark", "name": "점자 악보", "path": str(demo / "점자 악보")},
        {"type": "bookmark", "name": "양쪽 작업 세트", "path": str(demo), "path2": str(demo / "2026 계획"), "mark": ["square", "#4da3ff"]}]
    w.data["side_open"] = {"bm": True, "recent": True, "freq": False}
    w.bookmarks_changed()
    w.split_btn.click()
    pump(500)
    w.panes[0].view().navigate(str(demo))
    w.panes[1].view().navigate(str(demo / "2026 계획"))
    pump(900)
    w.rebuild_side()
    pump(300)
    out["explorer"] = w.grab().toImage()
    # 검색 탭
    w.one_btn.click()
    pump(300)
    w.active_view().navigate(str(demo))
    pump(500)
    w.open_search("folder")
    pump(300)
    pg = w.active_view().search_page
    pg.query.setText("보고")
    wait_for(lambda: pg.tree.topLevelItemCount() >= 2)
    pump(500)
    out["search"] = w.grab().toImage()
    d = J.ShortcutDialog(w)
    d.resize(760, 700)
    d.show()
    pump(500)
    out["shortcuts"] = d.grab().toImage()
    d.close()
    lw = L.Main()
    lw.resize(1280, 780)
    lw.show()
    pump(1500)
    lw.resize(1290, 790)
    pump(800)
    lw.goto(0)
    pump(1200)
    out["launcher"] = lw.grab().toImage()
    lw.goto(2)
    pump(400)
    out["launcher_search"] = lw.grab().toImage()
    lw.goto(3)
    pump(400)
    out["launcher_settings"] = lw.grab().toImage()
    import shutil
    shutil.rmtree(demo.parent, ignore_errors=True)
    return out


# ───────────── 본문 ─────────────
def table(rows, widths=(30, 70), head=None):
    h = ""
    if head:
        h = "<tr bgcolor='#e8ebff'>" + "".join(f"<td><b>{c}</b></td>" for c in head) + "</tr>"
    body = "".join(
        "<tr>" + "".join(f"<td width='{widths[i]}%'>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<table border='1' cellspacing='0' cellpadding='5' width='100%' style='border-color:#c9cdea'>{h}{body}</table>"


def shortcut_tables():
    parts = []
    for group, rows in J.SHORTCUT_HELP:
        parts.append(f"<h3>{group}</h3>" + table([(f"<b>{k}</b>", d) for k, _reg, d in rows], widths=(34, 66)))
    return "".join(parts)


def img(name, width=620, caption=""):
    return (f"<p align='center'><img src='{name}' width='{width}'><br><span style='color:#666;font-size:8.5pt'>{caption}</span></p>")


def build_html():
    return f"""
<html><body style="font-size:10pt; color:#222;">
<h1 style="color:#3b4bd8;">JY Tools 사용설명서</h1>
<p>JY Launcher(런처) + JY Explorer(탐색기)  ·  버전 {__version__}</p>
<hr>
<h2>목차</h2>
<p>1. JY Tools 란?<br>2. 설치와 업데이트<br>3. JY Launcher (런처)<br>4. JY Explorer (탐색기) — 화면과 기본 사용<br>
5. 탐색기 — 파일 다루기<br>6. 탐색기 — 검색 (Everything)<br>7. 탐색기 — 북마크 · 빠른 이동 · 세트<br>
8. 탐색기 — Windows 즐겨찾기 동기화와 백업<br>9. 특수 열기 (.dxb → Duxbury)<br>10. 단축키 전체 목록<br>11. 데이터 위치와 문제 해결</p>

<h2>1. JY Tools 란?</h2>
<p>JY Tools 는 두 개의 프로그램을 한 번에 설치하는 묶음입니다.</p>
{table([("<b>JY Launcher</b>", "전체 화면에서 앱을 카테고리별로 크게 보여 주고 키보드/마우스로 빠르게 실행하는 런처. 파일·앱 검색 포함. 트레이에 상주하며 <b>Ctrl+Alt+L</b> 로 호출."),
        ("<b>JY Explorer</b>", "탭 + 2패널 파일 탐색기. 병렬 복사/삭제, Everything 연동 전체 검색, 북마크/빠른 이동/세트 북마크, Windows 즐겨찾기 동기화. <b>Win+E</b> 로 열림.")], widths=(22, 78))}
<p>두 프로그램은 서로 독립적으로 실행되지만 데이터(북마크 등)를 공유하고, 런처에서 폴더를 열면 JY Explorer 의 새 탭으로 열립니다.</p>

<h2>2. 설치와 업데이트</h2>
<h3>설치</h3>
<p><b>JYTools-Setup-버전.exe</b> 를 실행하면 설치됩니다. 관리자 권한이 필요 없는 <b>사용자별 설치</b>입니다. 설치 중 선택 항목:</p>
{table([("런처 / 탐색기 선택", "둘 다 설치(기본)하거나 하나만 설치할 수 있습니다."),
        ("Windows 시작 시 자동 실행", "런처 / 탐색기를 트레이에 상주시켜 시작합니다. 탐색기가 상주해야 Win+E 가 동작합니다."),
        ("우클릭 메뉴 '런처에 추가'", "Windows 우클릭 메뉴에서 파일/폴더를 런처에 추가합니다."),
        ("북마크 ↔ Windows 즐겨찾기 동기화", "처음 설치할 때 Windows 즐겨찾기를 북마크로 불러오고 동기화를 켭니다. 기존 내용은 유지되고 자동 백업됩니다."),
        ("Everything 설치", "파일 검색을 아주 빠르게 해 주는 무료 프로그램. 체크를 끄면 한 번 더 확인합니다(없어도 검색은 되지만 매우 느림).")], widths=(32, 68))}
<h3>업데이트</h3>
<p>새 버전이 GitHub 에 올라오면 프로그램을 켤 때 <b>"새 버전을 설치할까요?"</b> 확인창이 뜹니다(하루 한 번 확인, 새 버전이 있으면 켤 때마다 물어봄).
수락하면 설치 파일을 내려받아 <b>해시(sha256)를 검증</b>한 뒤 조용히 설치하고, 켜져 있던 런처/탐색기를 다시 시작합니다. 한쪽에서 업데이트해도 둘 다 같이 업데이트됩니다.
수동 확인: 런처 <b>설정 탭 → 업데이트 → 지금 확인</b>, 탐색기 <b>설정(톱니) 메뉴 → 업데이트 확인</b>. 자동 확인은 같은 곳에서 끌 수 있습니다.</p>
<p>내 데이터(북마크, 런처 목록, 설정)는 설치 폴더가 아니라 <b>%APPDATA%\\JYTools</b> 에 있어서 업데이트/재설치해도 유지됩니다.</p>

<h2>3. JY Launcher (런처)</h2>
{img("launcher", 560, "런처 메인 화면 (카테고리별 앱 카드)")}
<h3>열기와 닫기</h3>
<p><b>Ctrl+Alt+L</b> 로 어디서든 호출하고, <b>Esc</b> 로 닫습니다(트레이로 숨김, 종료 아님). 종료는 트레이 아이콘 우클릭 → 종료 또는 설정 탭의 "런처 종료".
<b>F11</b> 로 전체화면/창 모드를 바꾸고, 창 모드에서는 위쪽을 끌어 이동, 오른쪽 아래를 끌어 크기를 조절합니다.</p>
<h3>탭 구성 (Ctrl+1 ~ 4)</h3>
{table([("런처 (Ctrl+1)", "카테고리별 앱 카드. 즐겨찾기(★)는 맨 위에 모입니다."),
        ("최근 · 보관함 (Ctrl+2)", "한 화면을 반으로 나눠 왼쪽은 Windows 최근 항목(50개), 오른쪽은 보관함. 최근 항목을 우클릭 → <b>핀 꽂기</b> 하면 오른쪽 보관함으로 넘어가고, 보관함은 xlsx 는 xlsx 끼리, hwp 는 hwp 끼리 <b>확장자별로 묶여</b> 보입니다. ← → 로 왼쪽/오른쪽 이동. 최근 항목 우클릭에는 열기 / 폴더 위치 열기 / 경로 복사 / 런처에 추가 / 목록에서 지우기도 있습니다."),
        ("검색 (Ctrl+3)", "파일 검색 + 앱 검색 (아래 설명)."),
        ("설정 (Ctrl+4)", "시작 프로그램, 우클릭 메뉴, 바로가기 만들기, 업데이트 등.")], widths=(28, 72))}
<h3>앱 추가와 정리</h3>
<p>위쪽 <b>＋ 앱 추가</b> 로 카테고리를 고르고 앱을 추가합니다(카테고리 선택 창: 맨 위 "새로 추가", 맨 아래 "새 카테고리 만들기").
탐색기 우클릭 메뉴의 <b>'런처에 추가'</b> 도 같은 창이 뜹니다. 카드는 <b>마우스로 끌어서</b> 순서를 바꾸거나 다른 카테고리로 옮깁니다. 카드를 다른 카드 <b>가운데</b>에 놓으면 둘이 <b>폴더 카드</b>로 묶이고(이름 입력), 폴더 카드 위에 놓으면 그 안으로 들어갑니다.
우클릭으로 이름 변경 / 삭제 / 폴더에서 꺼내기를 합니다. 아이콘 크기는 "큰 아이콘 / 작은 아이콘(이름은 툴팁)" 중에서 고릅니다.</p>
<h3>키보드</h3>
<p>↑↓←→ 이동, <b>Enter</b> 실행, <b>Space</b> 그룹 열기/닫기, 글자를 그냥 치면 검색창으로, <b>Ctrl+F</b> 검색창 ↔ 목록, <b>Tab</b> 으로 목록 복귀.
맨 윗줄에서 <b>↑</b> 를 누르면 위쪽 버튼줄(＋ 앱 추가, ＋ 카테고리, 아이콘 크기 …)로 올라가고(보라 테두리), ← → 로 이동, Enter 로 실행, ↓ 나 Esc 로 목록으로 돌아옵니다.</p>
<h3>검색 (런처에서 그냥 입력)</h3>
{img("launcher_search", 560, "런처 검색 탭: 왼쪽 앱 검색(접힘/펼침), 오른쪽 파일 검색")}
<p>런처나 최근·보관함 화면에서 <b>아무 글자나 치면</b> 자동으로 검색 화면이 열리고, 왼쪽에는 <b>앱</b>(런처에 등록한 앱 + 시작 메뉴 앱. 예: dbt → DBT 12.4), 오른쪽에는 <b>파일 · 폴더</b>가 나뉘어 나옵니다. Enter 는 첫 번째 앱을 실행하고, ← → 로 앱/파일 목록을 오가며, 검색어를 지우면(Esc) 원래 보던 화면으로 돌아갑니다.</p>
<p><b>파일 · 폴더</b>: 맨 위 검색창에 입력하면 바로(엔터 없이) 검색됩니다. 검색 위치(전체/사용자 폴더/문서/바탕화면/다운로드/폴더 선택)와 확장자 버튼(xlsx, hwp, pdf, docx …) 또는 직접 입력(예: xlsx, hwp)으로 범위를 좁힙니다.
<b>앱</b>: 클릭하면 실행합니다. 폴더 결과는 JY Explorer 새 탭으로 열립니다. 전체 검색은 Everything 이 필요합니다(6장).</p>
<h3>설정 탭</h3>
{img("launcher_settings", 520, "런처 설정 탭")}
<p>Windows 시작 시 자동 실행(트레이 상주), 앱 실행 후 런처 숨김, 탐색기 우클릭 메뉴 '런처에 추가', 시작 메뉴/바탕화면 바로가기 만들기, 업데이트 확인을 합니다.
(작업 표시줄 고정은 Windows 규칙상 시작 메뉴에 만든 뒤 우클릭 → "작업 표시줄에 고정" 을 한 번 직접 해야 합니다.)</p>

<h2>4. JY Explorer (탐색기) — 화면과 기본 사용</h2>
{img("explorer", 650, "탐색기 메인 화면 (2개 보기)")}
<h3>화면 구성</h3>
{table([("도구줄 (오른쪽 위)", "1개 보기 / 2개 보기, ★ 현재 폴더 북마크(노랗게 채워지면 북마크됨), 돋보기: 검색 탭, [두 폴더] 세트 북마크, 톱니(설정), 검색창."),
        ("빠른 이동 (왼쪽 위)", "작은 아이콘 격자: 내 PC, 바탕화면, 다운로드, 문서, 내가 추가한 폴더/네트워크, 드라이브. 이름은 마우스를 올리면 툴팁으로, 드라이브에는 문자(C, D …) 배지가 붙습니다. ＋ 로 추가, 새로고침 버튼으로 새로고침(USB 는 자동 감지)."),
        ("북마크 · 최근 (왼쪽 아래)", "북마크(폴더 안의 폴더 가능), 최근 15개, 자주 가는 곳 10개를 접고 펼치는 트리."),
        ("패널", "각 패널에 탭, 이동 버튼(뒤로/앞으로/위로), 경로줄(폴더 이름을 눌러 그 위치로), 새로고침 버튼, ＋ 새 탭. 2개 보기에서 선택된 패널은 굵은 테두리로 표시됩니다.")], widths=(26, 74))}
<h3>이동하는 방법</h3>
<p>폴더 더블클릭 / Enter, <b>경로줄</b>의 폴더 이름 클릭(가운데 클릭 = 새 탭, 빈 곳 클릭 또는 Ctrl+L = 직접 입력), Alt+← → ↑ 또는 Backspace, 빠른 이동·북마크 클릭.
경로가 길면 <b>D: › … › 일지 › docx</b> 처럼 맨 앞 드라이브와 마지막 폴더만 보이고 가운데는 …(클릭하면 목록)로 접힙니다.</p>
<h3>탭과 2개 보기</h3>
<p><b>Ctrl+T</b> 새 탭, <b>Ctrl+W</b> 닫기, Ctrl+PgUp/PgDn 탭 이동, 탭 우클릭 → 고정/복제/반대편으로 보내기. <b>F7</b> 로 1개 ↔ 2개 보기. 2개 보기에서 <b>F5 / F6</b> 은 선택 항목을 반대편 패널로 복사 / 이동합니다.</p>
<h3>키보드로 영역 이동</h3>
<p><b>F3</b> 사이드바(빠른 이동 ↔ 북마크 번갈아), <b>F4</b> 패널(패널끼리), <b>Ctrl+Tab</b> 사이드바 ↔ 패널. 사이드바에서는 방향키로 이동하고 Enter 로 활성 패널에서 엽니다. 포커스가 있는 영역은 보라 테두리로 표시됩니다.
<b>Alt+1~9</b> = 드라이브(보이는 순서: C=1, D=2 …), <b>Alt+0</b> 내 PC, <b>Alt+-</b> 바탕화면, <b>Alt+`</b> 다운로드, <b>Alt+=</b> 문서.</p>
<h3>열(칼럼)</h3>
<p>이름 / 수정한 날짜 / 확장자 / 크기 순서이고, 헤더를 끌어 <b>순서 변경</b>, 경계를 끌어 <b>너비 조절</b>, 헤더 <b>우클릭</b>으로 열 추가/제거/초기화를 합니다(저장됨). 동영상·음악 정보 열(길이, 해상도, H.264/H.265, 비트레이트, 프레임, 오디오 코덱)도 우클릭으로 켤 수 있습니다(정렬은 기본 4개 열만 가능).
열이 넓으면 <b>Shift + 마우스 휠</b> 로 가로 스크롤합니다.</p>

<h2>5. 탐색기 — 파일 다루기</h2>
<h3>복사 · 이동 · 삭제</h3>
<p><b>Ctrl+C / X / V</b> (Windows 탐색기와 호환), 드래그 앤 드롭(같은 드라이브는 이동, 다른 드라이브는 복사, <b>Ctrl</b> = 복사, <b>Shift</b> = 이동 강제), F5/F6. 복사하면 <b>파일과 함께 경로 텍스트</b>도 클립보드에 들어가서 채팅/메모장에 붙여넣으면 경로가 나옵니다.</p>
<p>작은 파일은 최대 4개를 <b>병렬</b>로, 큰 파일은 한 줄기로 복사합니다. 하단에 <b>지금 복사 중인 파일들이 파일별 %로</b> 표시되고(WinSCP 식), 전체 진행률과 취소 버튼이 있습니다. 같은 이름이 있으면 덮어쓰기 / 건너뛰기 / 이름 변경 / 모두 적용 중에서 고릅니다. 작업이 끝나면 해당 폴더가 자동으로 새로고침됩니다(수동: 새로고침 버튼 또는 <b>Ctrl+R</b>).</p>
<p>삭제: <b>Del</b> = 휴지통(복구 가능), 파일이 3,000개를 넘으면 "휴지통(느림) / 빠르게 삭제(병렬, 복구 불가)" 를 고르게 합니다. <b>Shift+Del</b> = 확인 후 바로 빠른 삭제(복구 불가).</p>
<h3>이름 바꾸기와 새로 만들기</h3>
<p><b>F2</b>: 파일은 <b>확장자(.txt 등)를 빼고 이름만</b> 선택된 상태로 편집됩니다. <b>빈 곳 우클릭 → 새로 만들기 ▶</b>: 폴더, 바로 가기, 그리고 Windows 에 등록된 파일 형식 전부(텍스트, hwp, Word/Excel/PowerPoint, 압축, ahk 등)가 아이콘과 함께 나오고, 만들면 바로 이름 입력 상태가 됩니다.</p>
<h3>우클릭 메뉴</h3>
<p>일반 Windows 탐색기와 같은 메뉴(반디집, Notepad++ 등 포함)가 뜨고 맨 위에 JY Explorer 항목(열기, 새 탭에서 열기, 북마크에 추가, 경로 복사, 런처에 추가, 반대편으로 복사/이동)이 붙습니다. Shift+우클릭 = Windows 의 추가 명령.</p>

<h2>6. 탐색기 — 검색 (Everything)</h2>
{img("search", 650, "검색 탭: 이름 / 위치 / 수정한 날짜 / 확장자 / 크기")}
<p><b>Ctrl+F</b> = 검색 탭을 열어 <b>전체 색인 검색</b>(지금 폴더와 무관하게 C:, D:, 네트워크 드라이브까지 모두), <b>Ctrl+Shift+F</b> = 지금 폴더와 하위 폴더 안에서만 검색. 도구줄 오른쪽 위 검색창에 입력해도 같은 검색 탭이 열립니다.
입력하는 즉시 검색되고(Everything 연결 시 0.1초), 공백으로 여러 단어를 쓰면 모두 포함된 것만 나옵니다. 확장자 칸에 <b>xlsx, hwp</b> 처럼 적으면 그 형식만 나옵니다.</p>
<p>결과 목록은 일반 탐색기처럼 동작합니다: 더블클릭 = 열기(폴더는 <b>같은 검색 탭 안에서</b> 들어가고 <b>뒤로(Alt+←)</b> 로 검색 결과로 돌아옴), 우클릭 = Windows 메뉴 + "새 탭에서 열기 / 폴더 위치 열기", F2 이름 바꾸기, Ctrl+C/X, Del, 끌어서 다른 패널로 복사·이동.</p>
<h3>Everything 이 필요합니다</h3>
{table([("일반 버전이어야 함", "Everything 의 <b>Lite 버전</b>은 다른 프로그램과 연동하는 기능이 없어서 JY Tools 가 사용할 수 없습니다. Lite 가 설치돼 있으면 처음 검색할 때 '일반 버전으로 교체' 를 안내합니다."),
        ("관리자 권한 실행 주의", "Everything 이 관리자 권한으로 실행 중이면 Windows 보안상 연결할 수 없습니다. 서비스를 쓰고 '관리자로 실행' 을 끄면 해결됩니다(안내창의 '자동 설정')."),
        ("네트워크 드라이브", "Everything 이 W:\\\\, Z:\\\\ 같은 네트워크 폴더도 색인하도록 추가해야 검색됩니다. <b>탐색기 설정(톱니) → '검색 색인 (Everything)'</b> 에서 현재 색인 목록을 보고 폴더를 추가/제거할 수 있습니다(Everything 을 잠시 껐다 켜며, 설정 파일은 먼저 자동 백업)."),
        ("설치하지 않으면", "검색은 되지만 폴더를 직접 훑어서 매우 느리고, 전체 검색은 사용자 폴더 아래로 제한됩니다.")], widths=(26, 74))}

<h2>7. 탐색기 — 북마크 · 빠른 이동 · 세트</h2>
<h3>북마크</h3>
<p>현재 폴더를 북마크: <b>Ctrl+D</b> 또는 도구줄/경로줄의 ★ (이미 북마크면 노란 별, 다시 누르면 해제). 폴더를 파일 목록에서 북마크 트리로 끌어다 놓아도 추가됩니다. 북마크 트리에서 <b>폴더 안의 폴더</b>로 정리하고, 끌어서 순서를 바꿉니다.
북마크 우클릭 메뉴: 열기 / 새 탭 / 반대편 / <b>표시 지정</b>(도형 5종 × 색 6종으로 구분) / <b>단축키 지정</b> / 이름 변경 / 이동 / 삭제. 북마크 폴더 우클릭 = <b>모두 열기</b>(안의 북마크를 각각 탭으로).</p>
<p><b>북마크 단축키</b>: 우클릭 → 단축키 지정 → 1~9 번을 고르면 <b>Ctrl+1 ~ 9</b> 로 현재 패널의 현재 탭에서 엽니다(새 탭은 Ctrl+T 후 Ctrl+번호). 트리에 [Ctrl+N] 이 표시됩니다.</p>
<h3>빠른 이동</h3>
<p>자주 가는 "장소"입니다. ＋ 로 현재 폴더 / 폴더 선택 / 네트워크 위치(Windows 자격 증명에 저장된 서버 선택)를 추가하고, 우클릭 → <b>표시 이름 변경</b>, 제거. 드라이브 항목을 우클릭하면 Windows 의 드라이브 메뉴(<b>포맷, 꺼내기, 속성</b> 등)가 뜹니다. USB 를 꽂거나 빼면 3초 안에 자동으로 바뀌고, 새로고침 버튼으로 수동 새로고침도 됩니다.</p>
<h3>세트 북마크 (폴더 2개)</h3>
<p>2개 보기에서 왼쪽·오른쪽에 열어 둔 두 폴더를 <b>Ctrl+Shift+D</b> 로 저장하면, 도구줄 <b>설정 왼쪽의 [두 폴더] 버튼</b> 메뉴에 나타납니다. 클릭하면 2개 보기로 바뀌며 양쪽에 각각 엽니다. 같은 메뉴의 "세트 관리"에서 이름 변경 / 표시 / 단축키 / 순서 / 삭제를 합니다.</p>

<h2>8. 탐색기 — Windows 즐겨찾기 동기화와 백업</h2>
<h3>북마크 = Windows 즐겨찾기</h3>
<p>설정(톱니) 메뉴의 <b>"북마크 = Windows 즐겨찾기 동기화"</b> 체크 하나로 켜고 끕니다. Windows 탐색기 자체는 건드리지 않고, 즐겨찾기(빠른 실행) 고정/해제만 합니다.</p>
{table([("맞추는 시점", "프로그램 시작 4초 뒤 / 창을 닫아 트레이로 숨길 때 / 종료할 때 / 설정 메뉴 <b>'지금 동기화'</b> (결과는 알림창으로). 실시간 동기화는 없습니다."),
        ("규칙", "일반 폴더 북마크만 대상(세트·북마크 폴더 제외). Windows 로 보낼 때는 폴더 구조 없이 북마크 하나하나가 고정되고, Windows 에서 가져올 때는 폴더 없이 맨 위 단계로 들어옵니다(정리는 직접). 바탕화면/다운로드/문서/사진은 제외."),
        ("추가·삭제 판단", "'마지막으로 맞춘 목록'과 비교해서 어느 쪽에서 추가/삭제됐는지 구분해 반대쪽에 반영합니다."),
        ("안전장치", "<b>처음 켤 때는 합치기만 하고 아무것도 지우지 않습니다.</b> 삭제가 있으면 먼저 자동 백업하고, 한꺼번에 너무 많이 지우게 되면(목록 읽기 오류 의심) 삭제는 건너뜁니다. 고정하지 못한 항목은 다음에 다시 시도합니다."),
        ("끌 때", "'북마크 삭제(자동 백업 후 세트만 남김) / 유지 / 취소' 중에서 고릅니다. Windows 즐겨찾기는 어느 쪽이든 건드리지 않습니다.")], widths=(22, 78))}
<h3>백업 / 복원</h3>
<p>설정 메뉴의 <b>백업하기</b> = 북마크와 <b>모든 설정을 zip 하나</b>로 <b>%APPDATA%\\JYTools\\backup</b> 에 저장합니다(파일명에 날짜·시각). <b>백업에서 불러오기</b> = 전체를 되돌립니다(현재 상태를 먼저 자동 백업하고, 되돌린 뒤 프로그램이 다시 시작됩니다). <b>90일이 지난 백업은 자동으로 삭제</b>됩니다.
북마크 경로는 PC 마다 다르므로 이 백업은 주로 같은 PC 복구용이고, 새 PC 에서는 Windows 즐겨찾기 동기화로 채우는 편이 맞습니다.</p>

<h2>9. 특수 열기 (.dxb → Duxbury)</h2>
<p>.dxb 파일을 더블클릭 / Enter / 검색 결과 열기 / 우클릭 열기 하면 Duxbury(<b>C:\\Program Files (x86)\\Duxbury\\DBT 12.4\\dbtw.exe</b>)로 열립니다. Duxbury 가 명령줄의 <b>한글 경로를 읽지 못해서</b> 일반 방법으로는 열리지 않기 때문에 이렇게 동작합니다:
Duxbury 를 <b>새로 실행</b> → 새 창이 뜨면 <b>Ctrl+O</b> → "문서 파일 선택..." 창의 파일 이름 칸에 경로를 넣고 열기 버튼을 누름.</p>
<p>자동 조작이라서 실행 중에 <b>다른 창을 누르면 중단</b>됩니다(엉뚱한 곳에 키가 들어가지 않도록 매번 확인). 실패하면 경로가 클립보드에 남으니 Duxbury 에서 Ctrl+O 후 Ctrl+V 로 열면 됩니다. 다른 확장자도 같은 방식으로 열려면 <b>%APPDATA%\\JYTools\\explorer.json</b> 에 <code>"special_open": {{".확장자": "프로그램 경로"}}</code> 를 추가합니다.</p>

<h2>10. 단축키 전체 목록</h2>
<p>탐색기에서 <b>F1</b> (또는 설정 메뉴 → 단축키 보기)을 누르면 아래 목록이 창으로 뜨고, 검색창으로 걸러 볼 수 있습니다.</p>
{img("shortcuts", 520, "단축키 보기 창 (F1)")}
{shortcut_tables()}
<h3>런처 단축키</h3>
{table([("<b>Ctrl+Alt+L</b>", "런처 호출 / 숨김 (전역)"), ("Ctrl+1 ~ 4", "런처 / 최근·보관함 / 검색 / 설정 탭"), ("↑ ↓ ← →  ·  Enter  ·  Space", "이동 · 실행 · 그룹 열기/닫기"),
        ("↑ (맨 윗줄에서)", "위쪽 버튼줄로 (← → 이동, Enter 실행, ↓ 복귀)"), ("/ 또는 글자 입력  ·  Ctrl+F", "검색창으로  ·  검색창 ↔ 목록"), ("F11  ·  Esc", "전체화면/창 모드  ·  닫기(트레이로)")], widths=(36, 64))}

<h2>11. 데이터 위치와 문제 해결</h2>
<h3>데이터 위치 (%APPDATA%\\JYTools)</h3>
{table([("launcher.json, vault.json, settings.json", "런처 목록, 보관함, 런처 설정"), ("bookmarks.json", "북마크 (런처·탐색기 공유)"),
        ("explorer.json", "탐색기 설정, 탭 세션, 열 설정, 빠른 이동 …"), ("search.json, update.json", "검색 안내 선택, 업데이트 확인 상태"), ("backup\\\\", "백업 zip (90일 보관)")], widths=(40, 60))}
<p><b>포터블 모드</b>: 프로그램 폴더에 <code>portable.txt</code> 파일을 두면 데이터를 <code>data</code> 폴더에 저장합니다(자동 업데이트는 설치형에서만 동작).</p>
<h3>자주 겪는 문제</h3>
{table([("업데이트 안내가 안 떠요", "런처 설정 탭 → 지금 확인(탐색기: 설정 메뉴 → 업데이트 확인). 설치 안내는 설치형(포터블 아님)에서만 뜹니다."),
        ("검색이 느리고 '직접 검색' 이라고 나와요", "Everything 이 없거나 연결되지 않은 상태입니다. 검색 탭에서 안내하는 이유(Lite 버전 / 관리자 권한 / 꺼져 있음)를 확인하세요. 6장 참고."),
        ("W:\\\\ 같은 네트워크 폴더가 검색에 안 나와요", "Everything 에서 그 폴더를 색인에 추가해야 합니다(설정 → 검색 색인)."),
        ("USB 가 빠른 이동에 안 보여요", "3초 안에 자동 갱신됩니다. 안 되면 빠른 이동의 새로고침 버튼."),
        ("복사한 파일이 목록에 안 보여요", "작업이 끝나면 자동 새로고침됩니다. 안 보이면 새로고침 버튼 또는 Ctrl+R."),
        ("북마크가 사라졌어요 / 동기화가 이상해요", "backup 폴더의 최근 백업(zip)을 '백업에서 불러오기'로 복원하세요. 동기화는 삭제 전에 항상 백업합니다."),
        ("dxb 가 열리지 않아요", "실행 중 다른 창을 누르면 중단됩니다. 경로는 클립보드에 있으니 Duxbury 에서 Ctrl+O → Ctrl+V."),
        ("Win+E 가 Windows 탐색기를 열어요", "JY Explorer 가 실행 중이어야 합니다. 시작 시 자동 실행을 켜 두세요(설정 메뉴).")], widths=(32, 68))}
<h3>알려진 한계</h3>
<p>사진/영상 미리보기, 추가 열(미디어 정보)의 정렬, 폴더 3개 이상 동시 보기(패널은 최대 2개)는 지원하지 않습니다. 업데이트는 GitHub(lovslave-netizen/JYLauncher_Explorer)의 Releases 로 배포됩니다.</p>
<hr>
<p style="color:#888;font-size:8.5pt">이 문서는 make_manual.py 로 자동 생성되며 화면은 가짜 데모 파일로 찍었습니다.  JY Tools {__version__}</p>
</body></html>
"""


def main():
    images = shots()
    if "--shots" in sys.argv:                          # 캡처만 저장해서 확인할 때
        d = Path(tempfile.gettempdir()) / "manual_shots"
        d.mkdir(exist_ok=True)
        for k, im in images.items():
            im.save(str(d / f"{k}.png"))
        print("saved to", d, flush=True)
        os._exit(0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = QTextDocument()
    f = QFont(L.FONT_FAMILY if hasattr(L, "FONT_FAMILY") else "Noto Sans KR")
    f.setPointSizeF(10)
    doc.setDefaultFont(f)
    for k, im in images.items():
        doc.addResource(QTextDocument.ImageResource, QUrl(k), im)
    doc.setHtml(build_html())
    w = QPdfWriter(str(OUT))
    w.setResolution(96)
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageMargins(QMarginsF(16, 16, 16, 16), QPageLayout.Millimeter)
    w.setTitle("JY Tools 사용설명서")
    w.setCreator("JY Tools make_manual.py")
    doc.setPageSize(QSizeF(w.width(), w.height()))
    doc.print_(w)
    print("PDF:", OUT, f"{OUT.stat().st_size / 1024:.0f} KB", flush=True)
    os._exit(0)


main()




