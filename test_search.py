"""filesearch / appsearch 오프라인 테스트 (Everything 없이 도는 부분).  python test_search.py"""
import os
import tempfile
import threading

import appsearch
import filesearch as FS

# 검색식 만들기
assert FS.build_query("report", r"D:\a b\c", ("xlsx", ".hwp")) == 'path:"D:\\a b\\c" ext:xlsx;hwp report'
assert FS.build_query("", None, ("pdf",)) == "ext:pdf"
assert FS.build_query("  x  ") == "x"

# 직접 훑기 (폴백)
root = tempfile.mkdtemp()
for sub, files in (("a", ["Report_2024.xlsx", "img.png"]), ("a/deep", ["report-final.docx", "budget.xlsx"]), ("b", ["REPORT.pdf"])):
    os.makedirs(os.path.join(root, sub), exist_ok=True)
    for f in files:
        open(os.path.join(root, sub, f), "w").write("x")


def scan(text, exts=()):
    got = []
    FS.scan_search(root, text, exts, threading.Event(), got.extend)
    return sorted(os.path.relpath(r["path"], root).replace("\\", "/") for r in got)


assert scan("report") == ["a/Report_2024.xlsx", "a/deep/report-final.docx", "b/REPORT.pdf"], scan("report")
assert scan("REPORT final") == ["a/deep/report-final.docx"]
assert scan("", ("xlsx",)) == ["a/Report_2024.xlsx", "a/deep/budget.xlsx"]
assert scan("deep") == ["a/deep"]                                   # 폴더도 검색됨
cancel = threading.Event()
cancel.set()
got = []
FS.scan_search(root, "report", (), cancel, got.extend)
assert got == []                                                    # 취소하면 즉시 중단
_, trunc = FS.scan_search(root, "", ("xlsx", "pdf", "png", "docx"), threading.Event(), lambda r: None, limit=2)
assert trunc is True                                                # 개수 제한

# 앱 목록 필터
apps = [{"name": n, "target": n, "kind": "lnk", "folder": ""} for n in ("Google Chrome", "Chrome Remote", "계산기", "메모장", "Notepad++")]
assert [a["name"] for a in appsearch.filter_apps(apps, "chrome")] == ["Chrome Remote", "Google Chrome"]   # 앞글자 일치 우선
assert [a["name"] for a in appsearch.filter_apps(apps, "google chr")] == ["Google Chrome"]
assert appsearch.filter_apps(apps, "") == []
print("search tests OK")
