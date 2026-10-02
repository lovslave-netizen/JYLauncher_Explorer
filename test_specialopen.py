"""특수 열기 규칙 + (메모장을 대역으로 한) 창 자동 조작 테스트. 키 입력은 대상 창이 맨 앞일 때만 보냄.  python test_specialopen.py"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import specialopen as S

# 규칙: 기본은 .dxb, 사용자 규칙은 덮어쓰기, 프로그램이 없으면 일반 열기(None)
S.set_rules(None)
assert ".dxb" in S.RULES and S.RULES[".dxb"].lower().endswith("dbtw.exe")
S.set_rules({".abc": sys.executable, ".dxb": "X:\\nope.exe", "bad": "z", 5: "q"})
assert S.rule_for("a.ABC") == sys.executable and S.rule_for("a.dxb") is None and S.rule_for("a.txt") is None
assert "bad" not in S.RULES and 5 not in S.RULES
S.set_rules(None)

# 실제 창 조작: Ctrl+O 로 '파일 선택' 창을 여는 작은 Tk 창(대역)을 pythonw 로 띄워서 한글 경로를 붙여 열어 봄.
# 화면 없는 환경(CI)이거나 이미 다른 pythonw 창이 떠 있으면(그 창으로 키가 가지 않게) 건너뜀
import subprocess

pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if os.environ.get("CI") or not os.path.exists(pyw) or S.windows_of(pyw):
    print("window automation skipped (no desktop or other pythonw window present)")
else:
    d = tempfile.mkdtemp(prefix="특수열기 ")
    app = os.path.join(d, "fakeviewer.py")
    open(app, "w", encoding="utf-8").write(
        "import tkinter as tk\nfrom tkinter import filedialog\n"
        "r = tk.Tk(); r.title('fakeviewer'); r.geometry('300x120+200+200')\n"
        "def op(e=None):\n"
        "    f = filedialog.askopenfilename(parent=r)\n"
        "    if f: r.title('OPENED:' + f)\n"
        "r.bind('<Control-o>', op); r.after(120000, r.destroy); r.mainloop()\n")
    f = os.path.join(d, "한글 파일 (테스트).txt")
    open(f, "w", encoding="utf-8").write("hello")
    keep = S._clip_get()
    titles = []
    try:
        ok, msg = S.open_with_dialog(pyw, f, args=[app])
        time.sleep(1.0)
        titles = [t for _h, t in S.windows_of(pyw)]
        print("result:", ok, msg, "| titles:", titles)
    finally:
        for pid in {S._pid_of(h) for h, _t in S.windows_of(pyw)}:       # 이 테스트가 연 프로세스만 종료
            subprocess.run(["taskkill", "/f", "/pid", str(pid)], capture_output=True)
    want = os.path.normcase(f)
    assert ok and any(t.startswith("OPENED:") and os.path.normcase(t[7:].replace("/", "\\")) == want for t in titles), (ok, msg, titles)
    assert S._clip_get() == keep                                       # 클립보드 원복
print("specialopen tests OK")
sys.stdout.flush()
os._exit(0)
