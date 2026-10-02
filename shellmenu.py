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
    def __init__(self, paths, folder, extended=False, allow_root=False):
        """paths: 같은 폴더 안의 선택 항목들 / 없으면 folder 배경 메뉴. extended: Shift+우클릭(추가 명령)"""
        self.hmenu = None
        self.ctx = None
        self._bitmaps = []
        self.workdir = folder
        desktop = shell.SHGetDesktopFolder()
        try:
            if paths:
                paths = [os.path.normpath(p) for p in paths]
                parent = os.path.dirname(paths[0])
                is_root = any(len(p) <= 3 and p[1:2] == ":" for p in paths) or not parent or parent == paths[0] \
                    or parent.startswith("\\\\") and parent.count("\\") < 4
                if is_root and not allow_root:
                    raise ShellMenuUnsupported("드라이브/네트워크 루트")
                if not is_root and len({os.path.dirname(p) for p in paths}) == 1:
                    ppidl = shell.SHParseDisplayName(parent, 0)[0]
                    pf = desktop.BindToObject(ppidl, None, shell.IID_IShellFolder)
                    children = [pf.ParseDisplayName(0, None, os.path.basename(p))[1] for p in paths]
                    self.ctx = pf.GetUIObjectOf(0, children, shell.IID_IContextMenu, 0)[1]
                else:                                   # 검색 결과처럼 폴더가 제각각이면 절대 경로 PIDL 을 데스크톱 기준으로
                    pidls = [shell.SHParseDisplayName(p, 0)[0] for p in paths]
                    self.ctx = desktop.GetUIObjectOf(0, pidls, shell.IID_IContextMenu, 0)[1]
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

    def _info(self, i):
        """(fType, 글자) — pywin32 의 GetMenuItemInfo 는 버퍼를 받아야 해서 win32gui_struct 로 풀어 씀. 실패하면 (0, '')"""
        try:
            import win32gui_struct
            buf, _extras = win32gui_struct.EmptyMENUITEMINFO(win32con.MIIM_FTYPE | win32con.MIIM_STRING)
            win32gui.GetMenuItemInfo(self.hmenu, i, True, buf)
            info = win32gui_struct.UnpackMENUITEMINFO(buf)
            return info.fType, (info.text or "")
        except Exception:
            return 0, ""

    def _is_sep(self, i):
        return bool(self._info(i)[0] & win32con.MFT_SEPARATOR)

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

    def _set_icon(self, hmenu, pos, icon):
        """메뉴 항목 앞에 아이콘을 붙임. icon = (너비, 높이, BGRA 미리곱셈 바이트) — 실패해도 글자만 나옴"""
        try:
            import ctypes
            from ctypes import wintypes

            class MII(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.UINT), ("fMask", wintypes.UINT), ("fType", wintypes.UINT), ("fState", wintypes.UINT),
                            ("wID", wintypes.UINT), ("hSubMenu", wintypes.HANDLE), ("hbmpChecked", wintypes.HANDLE),
                            ("hbmpUnchecked", wintypes.HANDLE), ("dwItemData", ctypes.c_size_t), ("dwTypeData", wintypes.LPWSTR),
                            ("cch", wintypes.UINT), ("hbmpItem", wintypes.HANDLE)]
            w, h, data = icon
            gdi = ctypes.windll.gdi32
            gdi.CreateBitmap.restype = wintypes.HANDLE
            hbmp = gdi.CreateBitmap(w, h, 1, 32, data)
            if not hbmp:
                return
            self._bitmaps.append(hbmp)
            mii = MII()
            mii.cbSize = ctypes.sizeof(MII)
            mii.fMask = 0x80                            # MIIM_BITMAP
            mii.hbmpItem = hbmp
            ctypes.windll.user32.SetMenuItemInfoW(wintypes.HANDLE(hmenu), pos, True, ctypes.byref(mii))
        except Exception:
            pass

    def remove_texts(self, names):
        """글자가 names 중 하나인 항목(하위 메뉴 포함)을 지움. 단축 글자 '(N)', 앰퍼샌드, 탭 뒤 글자는 무시하고 비교.
        예: '새 폴더(N)' → '새 폴더'. 우리 '새로 만들기' 와 겹치는 Windows 항목을 없앨 때 씀 (add_custom 보다 먼저 호출)"""
        import re
        want = {n.lower() for n in names}
        removed = 0
        for i in range(win32gui.GetMenuItemCount(self.hmenu) - 1, -1, -1):
            text = self._info(i)[1]
            key = re.sub(r"\(&?.\)\s*$", "", text.split("\t")[0].replace("&", "")).strip().lower()
            if key in want:
                win32gui.DeleteMenu(self.hmenu, i, win32con.MF_BYPOSITION)
                removed += 1
        if removed:                                       # 남은 연속/맨 앞/맨 뒤 구분선 정리
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
        """메뉴 맨 위에 사용자 항목을 넣음. items: [(id, 글자[, 아이콘]) | ("sub", 글자, [(id, 글자[, 아이콘]) …][, 아이콘]) | None(구분선)].
        ("sub" 은 하위 메뉴.) 마지막에 구분선 자동 추가"""
        pos = 0
        for it in items:
            if it is None:
                win32gui.InsertMenu(self.hmenu, pos, win32con.MF_BYPOSITION | win32con.MF_SEPARATOR, 0, None)
            elif it[0] == "sub":
                hsub = win32gui.CreatePopupMenu()
                for k, child in enumerate(it[2]):
                    win32gui.InsertMenu(hsub, k, win32con.MF_BYPOSITION | win32con.MF_STRING, child[0], child[1].replace("&", "&&"))
                    if len(child) > 2 and child[2]:
                        self._set_icon(hsub, k, child[2])
                win32gui.InsertMenu(self.hmenu, pos, win32con.MF_BYPOSITION | win32con.MF_POPUP | win32con.MF_STRING, hsub,
                                    it[1].replace("&", "&&"))
                if len(it) > 3 and it[3]:
                    self._set_icon(self.hmenu, pos, it[3])
            else:
                win32gui.InsertMenu(self.hmenu, pos, win32con.MF_BYPOSITION | win32con.MF_STRING, it[0],
                                    it[1].replace("&", "&&"))
                if len(it) > 2 and it[2]:
                    self._set_icon(self.hmenu, pos, it[2])
            pos += 1
        win32gui.InsertMenu(self.hmenu, pos, win32con.MF_BYPOSITION | win32con.MF_SEPARATOR, 0, None)

    def track(self, x, y):
        hwnd = _owner()
        _state["ctx"] = self.ctx2
        prev = win32gui.GetForegroundWindow()       # 메뉴가 끝나면 키보드 포커스를 원래 창으로 돌려줌 (안 그러면 바로 Ctrl+V 가 먹지 않음)
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
            try:
                if prev and win32gui.IsWindow(prev):
                    win32gui.SetForegroundWindow(prev)
            except Exception:
                pass
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
        for hb in self._bitmaps:
            try:
                import ctypes
                ctypes.windll.gdi32.DeleteObject(hb)
            except Exception:
                pass
        self._bitmaps = []
        if self.hmenu:
            try:
                win32gui.DestroyMenu(self.hmenu)
            except Exception:
                pass
            self.hmenu = None
