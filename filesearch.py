"""전체 폴더 파일 검색 (런처 '검색' 탭 / 탐색기 '하위 폴더 포함' 공용).

1순위: voidtools Everything (SDK DLL 로 실행 중인 Everything 에 질의 → 수천만 개도 즉시).
       Everything 이 없거나 안 켜져 있거나 네트워크 경로라서 색인에 없으면
2순위: 폴더를 직접 훑는 느린 검색(백그라운드 스레드, 결과를 실시간으로 채우고 취소 가능).
Everything 이 설치돼 있지 않으면 설치를 권함(설치 옵션은 설치 프로그램/앱 안내창에서).
"""
import ctypes
import datetime
import os
import re
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from jycommon import RES_DIR

DLL_PATH = RES_DIR / "everything" / "Everything64.dll"
CREATE_NO_WINDOW = 0x08000000

# Everything SDK 상수
_REQ_FULL_PATH, _REQ_SIZE, _REQ_DATE_MODIFIED = 0x4, 0x10, 0x40
_SORT_NAME_ASC = 1
_ERR_IPC = 2


class EverythingError(Exception):
    pass


def find_everything_exe():
    """설치된 Everything.exe 경로 (없으면 None). 실행 중인 프로세스 → 흔한 설치 위치 → 레지스트리 순으로 찾음"""
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        for sub in ("Everything", r"Programs\Everything", "Everything 1.5a"):
            p = Path(base) / sub / "Everything.exe"
            if p.exists():
                return str(p)
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\voidtools\Everything", r"SOFTWARE\WOW6432Node\voidtools\Everything"):
                try:
                    with winreg.OpenKey(root, sub) as k:
                        loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                        p = Path(loc) / "Everything.exe"
                        if p.exists():
                            return str(p)
                except OSError:
                    continue
    except ImportError:
        pass
    return None


def edition_from_names(names):
    """제어판(프로그램 목록)에 등록된 이름들에서 Everything 판본을 판별: 'lite' | 'full' | None"""
    for n in names:
        low = (n or "").lower()
        if low.startswith("everything") and "toolbar" not in low:
            return "lite" if "lite" in low else "full"
    return None


_edition_cache = {"t": 0.0, "v": None}


def everything_edition():
    """설치된 Everything 판본. 'lite' 는 IPC/SDK 가 제거된 버전이라 다른 프로그램이 연동할 수 없음(voidtools 문서).
    'full' 은 일반(다국어/영어) 버전, 설치 안 됐으면 None. (레지스트리 조회가 느리므로 1분 캐시)"""
    now = time.monotonic()
    if now - _edition_cache["t"] < 60:
        return _edition_cache["v"]
    names = []
    try:
        import winreg
        for root, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                          (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
            try:
                with winreg.OpenKey(root, sub) as k:
                    for i in range(winreg.QueryInfoKey(k)[0]):
                        try:
                            with winreg.OpenKey(k, winreg.EnumKey(k, i)) as ik:
                                names.append(winreg.QueryValueEx(ik, "DisplayName")[0])
                        except OSError:
                            continue
            except OSError:
                continue
    except ImportError:
        pass
    v = edition_from_names(names) or ("full" if find_everything_exe() else None)      # 포터블 등 등록이 없으면 일반 버전으로 가정
    _edition_cache.update(t=now, v=v)
    return v


class EverythingClient:
    """Everything SDK 래퍼. DLL 은 전역 상태를 쓰므로 질의는 lock 으로 한 번에 하나씩"""

    def __init__(self):
        self._lock = threading.Lock()
        self.dll = None
        try:
            d = ctypes.WinDLL(str(DLL_PATH))
            d.Everything_SetSearchW.argtypes = [wintypes.LPCWSTR]
            d.Everything_SetRequestFlags.argtypes = [wintypes.DWORD]
            d.Everything_SetSort.argtypes = [wintypes.DWORD]
            d.Everything_SetMax.argtypes = [wintypes.DWORD]
            d.Everything_SetOffset.argtypes = [wintypes.DWORD]
            d.Everything_QueryW.argtypes = [wintypes.BOOL]
            d.Everything_QueryW.restype = wintypes.BOOL
            d.Everything_GetLastError.restype = wintypes.DWORD
            d.Everything_GetNumResults.restype = wintypes.DWORD
            d.Everything_GetTotResults.restype = wintypes.DWORD
            d.Everything_IsDBLoaded.restype = wintypes.BOOL
            d.Everything_IsFolderResult.argtypes = [wintypes.DWORD]
            d.Everything_IsFolderResult.restype = wintypes.BOOL
            d.Everything_GetResultFullPathNameW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD]
            d.Everything_GetResultFullPathNameW.restype = wintypes.DWORD
            d.Everything_GetResultSize.argtypes = [wintypes.DWORD, ctypes.POINTER(ctypes.c_longlong)]
            d.Everything_GetResultSize.restype = wintypes.BOOL
            d.Everything_GetResultDateModified.argtypes = [wintypes.DWORD, ctypes.POINTER(ctypes.c_longlong)]
            d.Everything_GetResultDateModified.restype = wintypes.BOOL
            self.dll = d
        except (OSError, AttributeError):
            self.dll = None

    @staticmethod
    def ipc_window():
        """Everything 의 IPC 창 (검색 창 'EVERYTHING' 이 아니라 트레이 알림 창 'EVERYTHING_TASKBAR_NOTIFICATION' 이 SDK 요청을 받음)"""
        try:
            u = ctypes.WinDLL("user32")
            u.FindWindowW.restype = wintypes.HWND
            return u.FindWindowW("EVERYTHING_TASKBAR_NOTIFICATION", None) or 0
        except Exception:
            return 0

    def is_running(self):
        return bool(self.ipc_window())

    def blocked_by_elevation(self):
        """Everything 이 관리자 권한으로 떠 있어 일반 권한인 이 프로그램이 검색 요청(WM_COPYDATA)을 보낼 수 없는 상태.
        판별: IPC 창 소유 프로세스를 열 수 없고(접근 거부) 우리는 관리자가 아님"""
        try:
            hwnd = self.ipc_window()
            if not hwnd or ctypes.windll.shell32.IsUserAnAdmin():
                return False
            pid = wintypes.DWORD(0)
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid.value)          # PROCESS_QUERY_INFORMATION
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return False
            return ctypes.GetLastError() == 5
        except Exception:
            return False

    def available(self):
        """DLL 이 있고 Everything 이 실행 중이며 색인 DB 가 로드됨"""
        if self.dll is None:
            return False
        with self._lock:
            return bool(self.dll.Everything_IsDBLoaded())

    def query(self, text, max_results=2000):
        """검색어(Everything 문법 그대로) → [{path, name, is_dir, size, mtime}], 전체 개수"""
        d = self.dll
        if d is None:
            raise EverythingError("Everything SDK DLL 을 불러오지 못했습니다")
        with self._lock:
            d.Everything_SetSearchW(text)
            d.Everything_SetRequestFlags(_REQ_FULL_PATH | _REQ_SIZE | _REQ_DATE_MODIFIED)
            d.Everything_SetSort(_SORT_NAME_ASC)
            d.Everything_SetMax(max_results)
            d.Everything_SetOffset(0)
            if not d.Everything_QueryW(True):
                raise EverythingError("Everything 이 응답하지 않습니다 (실행 중인지 확인)" if d.Everything_GetLastError() == _ERR_IPC
                                      else f"Everything 질의 오류 {d.Everything_GetLastError()}")
            out = []
            buf = ctypes.create_unicode_buffer(4096)
            for i in range(d.Everything_GetNumResults()):
                n = d.Everything_GetResultFullPathNameW(i, buf, 4096)
                if not n:
                    continue
                path = buf.value
                is_dir = bool(d.Everything_IsFolderResult(i))
                size, ft = ctypes.c_longlong(-1), ctypes.c_longlong(0)
                d.Everything_GetResultSize(i, ctypes.byref(size))
                d.Everything_GetResultDateModified(i, ctypes.byref(ft))
                mtime = (ft.value / 1e7 - 11644473600) if ft.value > 0 else 0
                out.append({"path": path, "name": os.path.basename(path.rstrip("\\")) or path, "is_dir": is_dir,
                            "size": -1 if is_dir else size.value, "mtime": mtime})
            return out, d.Everything_GetTotResults()


def build_query(text, root=None, exts=()):
    """사용자가 친 검색어 + (선택) 폴더 범위 + 확장자 필터 → Everything 검색식"""
    parts = []
    if root:
        parts.append('path:"%s"' % root.rstrip("\\/").replace('"', ""))
    if exts:
        parts.append("ext:" + ";".join(e.lstrip(".") for e in exts))
    if text.strip():
        parts.append(text.strip())
    return " ".join(parts)


def is_network_path(path):
    if not path:
        return False
    if path.startswith("\\\\"):
        return True
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(path[:3]) == 4      # DRIVE_REMOTE
    except Exception:
        return False


def scan_search(root, text, exts, cancel, on_batch, limit=2000):
    """Everything 이 없을 때의 느린 검색: root 아래를 훑으며 이름에 모든 검색어가 들어간 항목을 모음.
    on_batch(list) 로 결과를 조금씩 넘김. 돌려주는 값: (개수, 잘렸는지)"""
    words = text.lower().split()
    want = {e.lstrip(".").lower() for e in exts}
    stack, batch, total = [root], [], 0
    last = time.monotonic()
    while stack and not cancel.is_set():
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if cancel.is_set():
                        break
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        stack.append(e.path)
                    low = e.name.lower()
                    if words and not all(w in low for w in words):
                        continue
                    if want and (is_dir or low.rpartition(".")[2] not in want):
                        continue
                    try:
                        st = e.stat(follow_symlinks=False)
                        size, mtime = (-1 if is_dir else st.st_size), st.st_mtime
                    except OSError:
                        size, mtime = -1, 0
                    batch.append({"path": e.path, "name": e.name, "is_dir": is_dir, "size": size, "mtime": mtime})
                    total += 1
                    if total >= limit:
                        on_batch(batch)
                        return total, True
        except OSError:
            continue
        if batch and (len(batch) >= 50 or time.monotonic() - last > 0.3):
            on_batch(batch)
            batch, last = [], time.monotonic()
    if batch:
        on_batch(batch)
    return total, False


class Searcher(QObject):
    """비동기 검색기. search() 를 부르면 이전 검색은 취소되고 결과가 results 신호로 조금씩 옴, 끝나면 done"""
    results = Signal(int, list)          # 검색 번호, 결과 목록(dict)
    done = Signal(int, dict)             # 검색 번호, {backend, total, truncated, error, note}

    _client = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gen = 0
        self._cancel = threading.Event()

    @classmethod
    def client(cls):
        if cls._client is None:
            cls._client = EverythingClient()
        return cls._client

    @staticmethod
    def status():
        """'ready'(사용 가능) | 'elevated'(관리자 권한으로 실행 중이라 접속 불가) | 'loading'(실행 중이지만 색인을 불러오는 중)
        | 'not_running'(설치됐지만 꺼져 있음) | 'missing'(설치 안 됨)"""
        c = Searcher.client()
        if everything_edition() == "lite":
            return "lite"
        if c.blocked_by_elevation():
            return "elevated"
        if c.available():
            return "ready"
        if c.is_running():
            return "loading"
        return "not_running" if find_everything_exe() else "missing"

    REASONS = {"missing": "Everything 이 설치돼 있지 않습니다",
               "lite": "설치된 Everything 이 Lite 버전이라 다른 프로그램이 검색할 수 없습니다 (Lite 는 외부 연동 기능이 없음 → 일반 버전으로 교체 필요)",
               "elevated": "Everything 이 관리자 권한으로 실행 중이라 연결할 수 없습니다 (설정 → 검색 색인 에서 확인)",
               "loading": "Everything 이 색인을 불러오는 중입니다 (잠시 뒤 다시 검색해 보세요)",
               "not_running": "Everything 이 실행 중이 아닙니다"}

    @staticmethod
    def reason():
        """Everything 을 못 쓰는 이유 (사용자에게 보여줄 문구). 쓸 수 있으면 빈 문자열"""
        st = Searcher.status()
        return "" if st == "ready" else Searcher.REASONS.get(st, "")

    def cancel(self):
        self._cancel.set()

    def search(self, text, root=None, exts=(), limit=2000, use_everything=True):
        """새 검색 시작. 검색 번호를 돌려줌 (오래된 번호의 신호는 무시할 것)"""
        self._cancel.set()
        self._gen += 1
        gen = self._gen
        cancel = self._cancel = threading.Event()
        threading.Thread(target=self._run, args=(gen, cancel, text, root, tuple(exts), limit, use_everything),
                         daemon=True).start()
        return gen

    def _run(self, gen, cancel, text, root, exts, limit, use_everything):
        info = {"backend": "", "total": 0, "truncated": False, "error": "", "note": ""}
        try:
            if not text.strip() and not exts:
                self.done.emit(gen, info)
                return
            client = self.client()
            tried_everything = False
            if use_everything and client.available():
                tried_everything = True
                try:
                    rows, tot = client.query(build_query(text, root, exts), limit)
                    if not cancel.is_set():
                        if rows:
                            self.results.emit(gen, rows)
                        info.update(backend="everything", total=len(rows), truncated=tot > len(rows))
                        if rows or not (root and is_network_path(root)):
                            self.done.emit(gen, info)
                            return
                        info["note"] = "Everything 색인에 없는 네트워크 경로라서 직접 검색합니다"
                except EverythingError as e:
                    info["error"] = str(e)
            if cancel.is_set():
                return
            if not root:
                info.update(backend="", error=info["error"] or "Everything 이 없으면 전체 검색은 폴더를 지정해야 합니다")
                self.done.emit(gen, info)
                return
            info["backend"] = "scan"
            total, trunc = scan_search(root, text, exts, cancel, lambda rows: (not cancel.is_set()) and self.results.emit(gen, rows), limit)
            info.update(total=total, truncated=trunc)
            if not cancel.is_set():
                self.done.emit(gen, info)
        except Exception as e:                       # 검색 스레드의 어떤 오류도 UI 를 멈추지 않게
            info["error"] = str(e)
            self.done.emit(gen, info)


# ───────────────────────── Everything 설치 / 실행 ─────────────────────────
def service_running():
    """Everything 서비스(관리자 권한 없이 NTFS 전체를 색인해 주는 서비스)가 실행 중인지"""
    try:
        r = subprocess.run(["sc", "query", "Everything"], capture_output=True, text=True, errors="ignore",
                           creationflags=CREATE_NO_WINDOW, timeout=10)
        return "RUNNING" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def start_everything(wait=8.0):
    """설치돼 있지만 꺼져 있으면 백그라운드(-startup)로 켜고 DB 가 로드될 때까지 기다림. 성공 여부"""
    exe = find_everything_exe()
    if not exe:
        return False
    c = Searcher.client()
    if c.available():
        return True
    if not user_everything_pids():                 # 이미 떠 있는데 아직 준비 중/응답 없음이면 또 실행하지 않고 기다리기만 함
        try:
            subprocess.Popen([exe, "-startup"], creationflags=CREATE_NO_WINDOW)
        except OSError:
            return False
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if c.available():
            return True
        time.sleep(0.4)
    return c.available()


def user_everything_pids():
    """사용자 세션에서 실행 중인 Everything.exe 프로세스 id (서비스는 세션 0 이라 제외)"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='Everything.exe'\" | "
                            "Where-Object { $_.SessionId -ne 0 } | ForEach-Object { $_.ProcessId }"],
                           capture_output=True, text=True, errors="ignore", creationflags=CREATE_NO_WINDOW, timeout=30)
        return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def stop_everything(wait=20.0):
    """Everything 을 종료하고 프로세스가 사라질 때까지 기다림. 관리자 권한으로 떠 있어 종료할 수 없으면 False"""
    exe = find_everything_exe()
    if not exe:
        return True
    if not user_everything_pids():
        return True
    try:
        subprocess.run([exe, "-exit"], creationflags=CREATE_NO_WINDOW, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if not user_everything_pids():
            return True
        time.sleep(0.7)
    return False


def change_index(mutate, log=None):
    """Everything.ini 의 색인 설정을 안전하게 바꿈: 종료 → (백업 후) mutate(IniText) 로 수정 → 다시 시작.
    mutate 는 성공 메시지(str)를 돌려주거나, 바꿀 게 없으면 None, 실패면 예외(ValueError). (성공 여부, 메시지) 를 돌려줌"""
    import everything_ini as EI

    def say(m):
        if log:
            log(m)
    exe, path = find_everything_exe(), EI.find_ini()
    if not exe or not path:
        return False, "Everything 이 설치돼 있지 않습니다"
    say("Everything 을 잠시 종료합니다…")
    if not stop_everything():
        return False, ("Everything 을 종료하지 못했습니다. 관리자 권한으로 실행 중이면 작업 표시줄 트레이의 Everything 아이콘 → "
                       "Exit(종료) 로 직접 끈 뒤 다시 시도해 주세요")
    result = (True, "")
    try:
        ini, bom = EI.read_ini(path)
        msg = mutate(ini)
        if msg is None:
            result = (True, "변경할 내용이 없습니다")
        else:
            backup = EI.write_ini(path, ini, bom)
            result = (True, f"{msg}  (이전 설정은 {Path(backup).name} 로 백업됨)")
    except (ValueError, OSError) as e:
        result = (False, str(e))
    finally:
        say("Everything 을 다시 시작합니다…")
        start_everything(30)
    return result


def replace_lite_with_full(log=None):
    """Lite 를 제거하고 일반 버전(winget voidtools.Everything)을 설치한 뒤 서비스/시작 설정 후 실행. 색인 설정(ini)과 DB 는 사용자 폴더에 있어 유지됨.
    관리자 권한 확인창이 뜸. 성공하면 True"""
    def say(m):
        if log:
            log(m)
    say("Everything 을 종료하는 중…")
    stop_everything(8)
    say("Lite 버전을 제거하는 중… (관리자 권한 확인창이 뜨면 '예')")
    try:
        subprocess.run(["winget", "uninstall", "--id", "voidtools.Everything.Lite", "-e", "--silent",
                        "--accept-source-agreements"], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=300)
    except (OSError, subprocess.SubprocessError):
        pass
    _edition_cache["t"] = 0.0
    if find_everything_exe():
        return False                                   # 제거되지 않음 (직접 제거 필요)
    return install_everything(log)


def install_everything(log=None):
    """Everything 을 설치하고(winget, 없으면 voidtools 에서 내려받아 조용히 설치) 서비스 등록 + 시작 프로그램 등록 + 실행.
    관리자 권한 확인창(UAC)이 한두 번 뜸. 성공하면 True"""
    def say(m):
        if log:
            log(m)
    if find_everything_exe():
        say("이미 설치돼 있습니다")
    else:
        say("Everything 설치 중…")
        ok = False
        try:
            r = subprocess.run(["winget", "install", "--id", "voidtools.Everything", "-e", "--silent",
                                "--accept-package-agreements", "--accept-source-agreements"],
                               capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=600)
            ok = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if not ok and not find_everything_exe():
            ok = _install_from_voidtools(say)
        if not find_everything_exe():
            return False
    exe = find_everything_exe()
    say("색인 서비스 등록 중… (관리자 권한 확인창이 뜨면 '예')")
    # 서비스를 설치해야 관리자 권한 없이도 NTFS 전체를 즉시 색인함. 한 번의 UAC 로 서비스 + 시작 프로그램 + 실행
    ps = (f"& '{exe}' -install-service; Start-Sleep -Milliseconds 800; "
          f"& '{exe}' -install-run-on-system-startup; Start-Process -FilePath '{exe}' -ArgumentList '-startup'")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile','-Command',\"{ps}\""],
                       creationflags=CREATE_NO_WINDOW, timeout=120)
    except (OSError, subprocess.SubprocessError):
        pass
    return start_everything(20) and service_running()


def repair_everything_access(log=None):
    """Everything 이 관리자 권한으로 실행 중이라 접속이 막힌 경우: (관리자 확인창 1회) 서비스 설치 + '관리자로 실행' 해제 후
    일반 권한으로 다시 시작. 서비스가 있으면 관리자 권한 없이도 NTFS 전체를 색인하고 다른 프로그램(우리 앱)이 접속할 수 있음"""
    exe = find_everything_exe()
    if not exe:
        return False
    if log:
        log("Everything 설정 변경 중… (관리자 권한 확인창이 뜨면 '예')")
    ps = f"& '{exe}' -exit -wait; & '{exe}' -install-service; Start-Sleep -Milliseconds 800; & '{exe}' -disable-run-as-admin"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile','-Command',\"{ps}\""],
                       creationflags=CREATE_NO_WINDOW, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return False
    return start_everything(30) and service_running()      # 서비스가 없으면 색인이 비어 검색 결과가 나오지 않으므로 실패로 봄


def _install_from_voidtools(say):
    """winget 이 없을 때: voidtools 다운로드 페이지에서 x64 설치 파일을 찾아 조용히 설치(/S)"""
    import tempfile
    import urllib.request
    try:
        with urllib.request.urlopen("https://www.voidtools.com/downloads/", timeout=20) as r:
            html = r.read().decode("utf-8", "ignore")
        m = re.search(r'href="([^"]*Everything-[\d.]+\.x64-Setup\.exe)"', html)
        if not m:
            return False
        url = m.group(1)
        if url.startswith("/"):
            url = "https://www.voidtools.com" + url
        elif not url.startswith("http"):
            url = "https://www.voidtools.com/" + url
        dest = Path(tempfile.gettempdir()) / "Everything-Setup.exe"
        say("Everything 내려받는 중…")
        urllib.request.urlretrieve(url, dest)
        subprocess.run([str(dest), "/S"], creationflags=CREATE_NO_WINDOW, timeout=300)
        return find_everything_exe() is not None
    except Exception:
        return False
