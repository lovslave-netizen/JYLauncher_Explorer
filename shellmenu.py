"""Windows 셸 우클릭 메뉴(IContextMenu)를 그대로 띄우는 모듈 — JYExplorer 용

일반 Windows 탐색기와 같은 메뉴(반디집, Notepad++, 보내기, 열기 프로그램 …)가 나오고,
맨 위에 사용자 항목(열기 / 새 탭에서 열기 / 북마크에 추가 …)을 끼워 넣을 수 있다.
메뉴 항목의 단축 글자(복사(C), 잘라내기(T) …)도 Windows 메뉴 그대로 동작한다.

사용:
    m = ShellMenu(paths, folder)                # paths 가 비어 있으면 folder 의 빈 곳 메뉴
    m.add_custom([(CUSTOM_BASE + 0, "열기"), None, (CUSTOM_BASE + 1, "새 탭에서 열기")])
    cmd = m.track(x, y)                          # 화면 픽셀 좌표, 선택한 명령 id (0 = 취소)
    if cmd >= CUSTOM_BASE: ...                   # 사용자 항목
    else: verb = m.verb(cmd); m.invoke(cmd)      # 셸 항목 (verb 로 가로채기 가능)
    m.close()
드라이브 루트 / 내 PC 등은 지원하지 않으므로 ShellMenuUnsupported 가 발생 → 호출한 쪽이 다른 메뉴로 대체.
"""
import os

import pythoncom  # noqa: F401  (COM 초기화)
import win32api
import win32con
import win32gui
from win32com.shell import shell, shellcon

CUSTOM_BASE = 0x8001      # 사용자 항목 id 시작 (셸 항목은 1..0x7FFF 를 사용)
FIRST, LAST = 1, 0x7FFF

_WM_INITMENUPOPUP, _WM_DRAWITEM, _WM_MEASUREITEM, _WM_MENUCHAR = 0x0117, 0x002B, 0x002C, 0x0120
_state = {"ctx": None, "hwnd": None}


def enable_dark_menus():
    """Windows 네이티브 팝업 메뉴를 다크 모드로 (탐색기의 어두운 색과 맞춤). Windows 10 1903+ / 11 의 비공개 uxtheme 함수
    (SetPreferredAppMode=ord 135, FlushMenuThemes=ord 136)를 사용 — 실패해도 메뉴는 기존(밝은) 모양으로 정상 동작"""
    try:
        import ctypes
        ux = ctypes.WinDLL("uxtheme")
        set_mode = ux[135]
        set_mode.argtypes = [ctypes.c_int]
        set_mode(2)                 # 2 = ForceDark
        ux[136]()                   # FlushMenuThemes
        return True
    except Exception:
        return False


class ShellMenuUnsupported(Exception):
    pass


def _wndproc(hwnd, msg, wparam, lparam):
    """'보내기', '연결 프로그램' 같은 하위 메뉴와 아이콘/그림이 있는 항목이 제대로 그려지도록 메뉴 메시지를 셸에 전달"""
    ctx = _state["ctx"]
    if ctx is not None and msg in (_WM_INITMENUPOPUP, _WM_DRAWITEM, _WM_MEASUREITEM, _WM_MENUCHAR):
        try:
            if hasattr(ctx, "HandleMenuMsg2"):
                r = ctx.HandleMenuMsg2(msg, wparam, lparam)
                if msg == _WM_MENUCHAR:
                    return r or 0
            else:
                ctx.HandleMenuMsg(msg, wparam, lparam)
            return 0 if msg == _WM_INITMENUPOPUP else 1
        except Exception:
            pass
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def _owner():
    if _state["hwnd"]:
        return _state["hwnd"]
    wc = win32gui.WNDCLASS()
    wc.hInstance = win32api.GetModuleHandle(None)
    wc.lpszClassName = "JYShellMenuOwner"
    wc.lpfnWndProc = _wndproc
    try:
        win32gui.RegisterClass(wc)
    except Exception:
        pass  # 이미 등록됨
    _state["hwnd"] = win32gui.CreateWindow(wc.lpszClassName, "", win32con.WS_POPUP, 0, 0, 0, 0, 0, 0, wc.hInstance, None)
    return _state["hwnd"]


class ShellMenu:
    def __init__(self, paths, folder, extended=False):
        """paths: 같은 폴더 안의 선택 항목들 / 없으면 folder 배경 메뉴. extended: Shift+우클릭(추가 명령)"""
        self.hmenu = None
        self.ctx = None
        self.workdir = folder
        desktop = shell.SHGetDesktopFolder()
        try:
            if paths:
                paths = [os.path.normpath(p) for p in paths]
                parent = os.path.dirname(paths[0])
                if any(len(p) <= 3 and p[1:2] == ":" for p in paths) or not parent or parent == paths[0] \
                        or parent.startswith("\\\\") and parent.count("\\") < 4:
                    raise ShellMenuUnsupported("드라이브/네트워크 루트")
                ppidl = shell.SHParseDisplayName(parent, 0)[0]
                pf = desktop.BindToObject(ppidl, None, shell.IID_IShellFolder)
                children = [pf.ParseDisplayName(0, None, os.path.basename(p))[1] for p in paths]
                self.ctx = pf.GetUIObjectOf(0, children, shell.IID_IContextMenu, 0)[1]
                self.workdir = parent
            else:
                if not folder:
                    raise ShellMenuUnsupported("내 PC")
                fpidl = shell.SHParseDisplayName(folder, 0)[0]
                f = desktop.BindToObject(fpidl, None, shell.IID_IShellFolder)
                self.ctx = f.CreateViewObject(0, shell.IID_IContextMenu)
        except ShellMenuUnsupported:
            raise
        except Exception as e:
            raise ShellMenuUnsupported(str(e))
        self.hmenu = win32gui.CreatePopupMenu()
        flags = shellcon.CMF_NORMAL | (shellcon.CMF_CANRENAME if paths else 0)
        if extended:
            flags |= shellcon.CMF_EXTENDEDVERBS
        self.ctx.QueryContextMenu(self.hmenu, 0, FIRST, LAST, flags)
        self.ctx2 = None
        for iid in (shell.IID_IContextMenu3, shell.IID_IContextMenu2):
            try:
                self.ctx2 = self.ctx.QueryInterface(iid)
                break
            except Exception:
                continue

    def _is_sep(self, i):
        try:
            return bool(win32gui.GetMenuItemInfo(self.hmenu, i, True)[0] & win32con.MFT_SEPARATOR)
        except Exception:
            return False

    def remove_verbs(self, verbs):
        """셸 메뉴에서 verb 가 verbs 에 있는 항목을 지움 (우리 항목과 겹치는 '열기', '런처에 추가' 등).
        지운 뒤 맨 앞/맨 뒤/연속된 구분선은 정리. 반드시 add_custom 보다 먼저 호출"""
        removed = 0
        for i in range(win32gui.GetMenuItemCount(self.hmenu) - 1, -1, -1):
            try:
                cid = win32gui.GetMenuItemID(self.hmenu, i)
            except Exception:
                continue
            if FIRST <= cid < CUSTOM_BASE and self.verb(cid) in verbs:
                win32gui.DeleteMenu(self.hmenu, i, win32con.MF_BYPOSITION)
                removed += 1
        i, prev_sep = 0, True
        while i < win32gui.GetMenuItemCount(self.hmenu):
            sep = self._is_sep(i)
            if sep and prev_sep:
                win32gui.DeleteMenu(self.hmenu, i, win32con.MF_BYPOSITION)
                continue
            prev_sep = sep
            i += 1
        n = win32gui.GetMenuItemCount(self.hmenu)
        if n and self._is_sep(n - 1):
            win32gui.DeleteMenu(self.hmenu, n - 1, win32con.MF_BYPOSITION)
        return removed

    def add_custom(self, items):
        """메뉴 맨 위에 사용자 항목을 넣음. items: [(id, 글자) | None(구분선)]. 마지막에 구분선 자동 추가"""
        pos = 0
        for it in items:
            if it is None:
                win32gui.InsertMenu(self.hmenu, pos, win32con.MF_BYPOSITION | win32con.MF_SEPARATOR, 0, None)
            else:
                cid, text = it
                win32gui.InsertMenu(self.hmenu, pos, win32con.MF_BYPOSITION | win32con.MF_STRING, cid,
                                    text.replace("&", "&&"))
            pos += 1
        win32gui.InsertMenu(self.hmenu, pos, win32con.MF_BYPOSITION | win32con.MF_SEPARATOR, 0, None)

    def track(self, x, y):
        hwnd = _owner()
        _state["ctx"] = self.ctx2
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            cmd = win32gui.TrackPopupMenu(self.hmenu, win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON
                                          | win32con.TPM_RETURNCMD, int(x), int(y), 0, hwnd, None)
        finally:
            _state["ctx"] = None
            win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        return cmd or 0

    def verb(self, cmd):
        """선택한 셸 명령의 표준 이름(copy, cut, paste, delete, rename, open, properties …). 없으면 ''"""
        try:
            v = self.ctx.GetCommandString(cmd - FIRST, shellcon.GCS_VERBW)
            return (v or "").lower() if isinstance(v, str) else (v.decode("utf-8", "ignore").lower() if v else "")
        except Exception:
            return ""

    def command_ids(self):
        """(테스트용) 메뉴에 들어 있는 모든 셸 명령 id → verb"""
        out = {}
        for i in range(win32gui.GetMenuItemCount(self.hmenu)):
            try:
                cid = win32gui.GetMenuItemID(self.hmenu, i)
            except Exception:
                continue
            if FIRST <= cid < CUSTOM_BASE:
                out[cid] = self.verb(cid)
        return out

    def invoke(self, cmd, hwnd=0):
        # 주의: 문자열 verb 로 호출하면 프로세스가 죽으므로 항상 명령 오프셋(정수) + hIcon=0 으로 호출
        self.ctx.InvokeCommand((0, hwnd or _owner(), cmd - FIRST, None, self.workdir, win32con.SW_SHOWNORMAL, 0, 0))

    def close(self):
        if self.hmenu:
            try:
                win32gui.DestroyMenu(self.hmenu)
            except Exception:
                pass
            self.hmenu = None
