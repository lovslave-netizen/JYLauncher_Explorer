"""파일 형식별 특수 열기 (예: .dxb → Duxbury).

Duxbury(dbtw.exe)는 명령줄로 받은 한글 경로를 다른 문자 코드로 읽어서 깨지므로(오류: 파일을 열 수 없음) 이렇게 연다:
  경로를 클립보드에 복사 → 프로그램 실행(이미 떠 있으면 그 창) → Ctrl+O → 파일 선택 창이 뜨면 → Ctrl+V → Enter
창이 뜰 때까지 기다리고, 키를 보내기 직전마다 '대상 프로그램의 창이 맨 앞인지' 확인해서 엉뚱한 창으로 키가 들어가지 않게 한다.
실패하면 경로를 클립보드에 남겨 두고 안내한다.  규칙은 explorer.json 의 "special_open": {".dxb": "프로그램 경로"} 로 바꿀 수 있음.
"""
import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes

DEFAULT_RULES = {".dxb": r"C:\Program Files (x86)\Duxbury\DBT 12.4\dbtw.exe"}
RULES = dict(DEFAULT_RULES)

u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
u32.GetForegroundWindow.restype = wintypes.HWND
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
k32.OpenProcess.restype = wintypes.HANDLE
VK_CONTROL, VK_MENU, VK_RETURN = 0x11, 0x12, 0x0D
KEYUP = 0x0002


def set_rules(custom):
    """사용자 규칙(확장자 → 프로그램)을 기본 규칙 위에 덮어씀 (잘못된 항목은 무시)"""
    RULES.clear()
    RULES.update(DEFAULT_RULES)
    for ext, exe in (custom or {}).items():
        if isinstance(ext, str) and isinstance(exe, str) and ext.startswith("."):
            RULES[ext.lower()] = exe


def rule_for(path):
    """이 파일을 특수하게 열어야 하면 프로그램 경로, 아니면 None (프로그램이 없으면 일반 열기로)"""
    exe = RULES.get(os.path.splitext(path)[1].lower())
    return exe if exe and os.path.exists(exe) else None


# ───────────── 창 찾기 도우미 ─────────────
def _image_of(pid):
    h = k32.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        return buf.value if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        k32.CloseHandle(h)


def _pid_of(hwnd):
    pid = wintypes.DWORD(0)
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def windows_of(exe):
    """exe 프로세스의 보이는 최상위 창들 [(hwnd, 제목)]"""
    want = os.path.normcase(os.path.abspath(exe))
    found = []
    cache = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        if u32.IsWindowVisible(hwnd):
            pid = _pid_of(hwnd)
            if pid not in cache:
                cache[pid] = os.path.normcase(_image_of(pid))
            if cache[pid] == want:
                found.append((hwnd, _title(hwnd)))
        return True
    u32.EnumWindows(cb, 0)
    return found


def _responsive(hwnd):
    r = ctypes.c_size_t(0)
    return bool(u32.SendMessageTimeoutW(hwnd, 0, 0, 0, 2, 500, ctypes.byref(r)))      # WM_NULL, SMTO_ABORTIFHUNG


def _foreground_is(exe, not_hwnd=None):
    h = u32.GetForegroundWindow()
    if not h or (not_hwnd and h == not_hwnd):
        return None
    return h if os.path.normcase(_image_of(_pid_of(h))) == os.path.normcase(os.path.abspath(exe)) else None


def _focus(hwnd, exe):
    """창을 맨 앞으로 (Windows 의 포커스 도용 방지를 Alt 키 신호로 우회). 성공하면 True"""
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)                           # SW_RESTORE
    for attempt in range(6):
        if _foreground_is(exe) == hwnd:
            return True
        if attempt >= 2:                                   # 처음 두 번은 그냥 요청, 그래도 안 되면 Alt 신호로 포커스 제한을 우회
            u32.keybd_event(VK_MENU, 0, 0, 0)
            u32.keybd_event(VK_MENU, 0, KEYUP, 0)
        u32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
    return _foreground_is(exe) == hwnd


def _chord(mod, key):
    u32.keybd_event(mod, 0, 0, 0)
    u32.keybd_event(key, 0, 0, 0)
    u32.keybd_event(key, 0, KEYUP, 0)
    u32.keybd_event(mod, 0, KEYUP, 0)


# ───────────── 클립보드 (텍스트만 보관/복원) ─────────────
def _clip_get():
    import win32clipboard
    try:
        win32clipboard.OpenClipboard()
        try:
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        except Exception:
            return None
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None


def _clip_set(text):
    import win32clipboard
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                if text is not None:
                    win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            time.sleep(0.1)
    return False


def _children(hwnd):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        buf = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(h, buf, 64)
        out.append((h, buf.value))
        return True
    u32.EnumChildWindows(hwnd, cb, 0)
    return out


def fill_dialog(dlg, path):
    """표준 '파일 열기' 창의 파일 이름 칸(Edit)에 경로를 넣고 확인(IDOK=1) 버튼을 누름. 성공하면 True"""
    WM_SETTEXT, WM_GETTEXT, BM_CLICK = 0x000C, 0x000D, 0x00F5
    for h, cls in _children(dlg):
        if cls.lower() != "edit" or not u32.IsWindowVisible(h):
            continue
        u32.SendMessageW(h, WM_SETTEXT, 0, ctypes.c_wchar_p(path))
        buf = ctypes.create_unicode_buffer(len(path) + 16)
        u32.SendMessageW(h, WM_GETTEXT, len(path) + 16, buf)
        if buf.value != path:
            continue
        ok_btn = u32.GetDlgItem(dlg, 1)
        if not ok_btn:
            return False
        u32.PostMessageW(ok_btn, BM_CLICK, 0, 0)
        return True
    return False


# ───────────── 본체 ─────────────
def open_with_dialog(exe, path, log=None, wait_main=40.0, wait_dialog=12.0, args=()):
    """exe 를 띄우고 Ctrl+O 창에 path 를 붙여 열기. (성공 여부, 안내 문구). 작업 스레드에서 호출"""
    def say(m):
        if log:
            log(m)
    old = _clip_get()
    if not _clip_set(path):
        return False, "클립보드를 사용할 수 없습니다"
    try:
        wins = windows_of(exe)
        if not wins:
            say("프로그램을 시작하는 중…")
            try:
                subprocess.Popen([exe, *args], cwd=os.path.dirname(exe))
            except OSError as e:
                return False, f"프로그램을 실행하지 못했습니다: {e}"
            end = time.monotonic() + wait_main
            while time.monotonic() < end and not wins:
                time.sleep(0.25)
                wins = windows_of(exe)
        if not wins:
            return False, "프로그램 창이 나타나지 않았습니다 (경로는 클립보드에 있습니다: Ctrl+O 후 Ctrl+V)"
        main = max(wins, key=lambda w: len(w[1]))[0]
        end = time.monotonic() + 10
        while time.monotonic() < end and not _responsive(main):      # 시작 중에는 키를 받을 수 없음
            time.sleep(0.2)
        time.sleep(0.6)
        if not _focus(main, exe):
            return False, "프로그램 창을 맨 앞으로 가져오지 못했습니다 (경로는 클립보드에 있습니다: Ctrl+O 후 Ctrl+V)"
        before = {h for h, _t in windows_of(exe)}
        if _foreground_is(exe) is None:
            return False, "다른 창이 앞으로 와서 중단했습니다 (경로는 클립보드에 있습니다)"
        _chord(VK_CONTROL, ord("O"))
        dlg = None
        end = time.monotonic() + wait_dialog
        while time.monotonic() < end:                                   # '파일 선택' 창: Ctrl+O 뒤에 이 프로그램에 새로 생긴 창
            time.sleep(0.2)
            new = [h for h, _t in windows_of(exe) if h not in before and h != main]
            if new:
                dlg = new[0]
                break
        if dlg is None:
            return False, "파일 선택 창이 뜨지 않았습니다 (경로는 클립보드에 있습니다: Ctrl+O 후 Ctrl+V)"
        time.sleep(0.4)
        if not _focus(dlg, exe) or _foreground_is(exe) != dlg:         # 그 사이 다른 창이 앞으로 왔으면 다시 앞으로 가져오고, 안 되면 중단
            return False, "파일 선택 창을 앞으로 가져오지 못해 중단했습니다 (경로는 클립보드에 있습니다)"
        if not fill_dialog(dlg, path):                                  # 입력 칸을 못 찾는 특수한 창이면 붙여넣기 + Enter 로
            _chord(VK_CONTROL, ord("V"))
            time.sleep(0.35)
            if _foreground_is(exe) != dlg:
                return False, "다른 창이 앞으로 와서 중단했습니다 (경로는 클립보드에 있습니다)"
            u32.keybd_event(VK_RETURN, 0, 0, 0)
            u32.keybd_event(VK_RETURN, 0, KEYUP, 0)
        end = time.monotonic() + 8
        while time.monotonic() < end:
            if not u32.IsWindow(dlg) or not u32.IsWindowVisible(dlg):
                return True, "열었습니다"
            time.sleep(0.2)
        return False, "파일 선택 창이 닫히지 않았습니다 (경로가 잘못됐거나 파일을 열 수 없을 수 있습니다. 경로는 클립보드에 있습니다)"
    finally:
        time.sleep(0.4)
        _clip_set(old)                                                   # 클립보드 원래 텍스트로 (실패했을 땐 아래에서 다시 경로를 남김)


def open_special(path, notify=None):
    """특수 열기 대상이면 백그라운드로 열고 True. 아니면 False (호출한 쪽이 일반 열기)"""
    exe = rule_for(path)
    if not exe:
        return False

    def work():
        ok, msg = open_with_dialog(exe, path, log=notify)
        if not ok:
            _clip_set(path)                                              # 실패하면 직접 붙여넣을 수 있게 경로를 클립보드에 남김
        if notify:
            notify(("열기: " if ok else "! 열기 실패: ") + os.path.basename(path) + ("" if ok else "  —  " + msg))
    threading.Thread(target=work, daemon=True).start()
    return True
