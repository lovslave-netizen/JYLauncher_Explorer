"""JYExplorer 파일 작업 엔진 (GUI 없음 → 단독 테스트 가능)

- 복사/이동: 작은 파일은 최대 4개 병렬, 대용량 파일은 단일 스트림(청크 복사 + 진행률)
- 충돌: resolver(src, dst) 콜백이 "overwrite" / "skip" / "rename" / "cancel" 중 하나를 돌려줌
- 삭제: Windows 셸(휴지통) 사용
- Windows 즐겨찾기(Quick access) 고정/해제
"""
import ctypes
import os
import shutil
import stat
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes

SMALL_FILE = 16 * 1024 * 1024   # 이보다 작으면 병렬 처리 대상
WORKERS = 4
DELETE_WORKERS = 8          # 삭제는 파일 내용을 읽지 않는 메타데이터 작업이라 복사보다 스레드를 더 써도 유리함
CHUNK = 4 * 1024 * 1024


class Cancelled(Exception):
    pass


def _lp(p):
    """260자가 넘는 경로도 다룰 수 있게 \\\\?\\ 접두어를 붙임"""
    p = os.path.abspath(p)
    if len(p) < 240 or p.startswith("\\\\?\\"):
        return p
    return "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p


def _is_reparse(st):
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)   # 정션/심볼릭 링크 등: 따라 들어가면 안 됨


def _unlink(p):
    """읽기 전용 파일도 지우고, 폴더 링크(정션/심볼릭)는 링크만 지움"""
    lp = _lp(p)
    try:
        os.unlink(lp)
    except OSError:
        try:
            os.chmod(lp, stat.S_IWRITE)
            os.unlink(lp)
        except OSError:
            os.rmdir(lp)


def _rmdir(p):
    lp = _lp(p)
    try:
        os.rmdir(lp)
    except PermissionError:
        os.chmod(lp, stat.S_IWRITE)
        os.rmdir(lp)


def unique_path(path):
    """name.ext → name (2).ext …"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    if os.path.isdir(path):
        base, ext = path, ""
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def same_volume(a, b):
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def is_inside(child, parent):
    c, p = os.path.normcase(os.path.abspath(child)), os.path.normcase(os.path.abspath(parent))
    return c == p or c.startswith(p.rstrip("\\") + "\\")


class Job:
    """op: 'copy' | 'move'"""

    def __init__(self, op, sources, dest_dir, resolver=None):
        self.op, self.sources, self.dest_dir = op, list(sources), dest_dir
        self.resolver = resolver or (lambda s, d: "rename")
        self.cancel = threading.Event()
        self.done_bytes = 0
        self.total_bytes = 0
        self.files_done = 0
        self.errors = []
        self.current = ""
        self.total_files = 0
        self.active = {}            # 지금 복사 중인 파일들 {대상 경로: [이름, 복사한 바이트, 파일 크기]} (여러 개 동시에 보여주기용)
        self._lock = threading.Lock()
        self._ask_lock = threading.Lock()
        self.policy = None  # "모두 적용" 결과
        self.unit = "count" if op == "delete" else "bytes"   # 진행률 단위 (삭제는 개수)

    # ---- 내부 유틸 ----
    def _add(self, n, name=None):
        with self._lock:
            self.done_bytes += n
            if name:
                self.current = name

    def _err(self, path, e):
        with self._lock:
            self.errors.append((path, str(e)))

    def _resolve(self, src, dst):
        """충돌 처리: 병렬 스레드에서 동시에 물어보지 않도록 직렬화"""
        with self._ask_lock:
            if self.policy:
                return self.policy
            ans, apply_all = self.resolver(src, dst), False
            if isinstance(ans, tuple):
                ans, apply_all = ans
            if apply_all and ans != "cancel":
                self.policy = ans
            return ans

    def snapshot(self):
        """지금 복사 중인 파일 목록 [(이름, 복사한 바이트, 크기), …] (화면 표시용 복사본)"""
        with self._lock:
            return [(a[0], a[1], a[2]) for a in self.active.values()]

    def _copy_file(self, src, dst):
        """청크 복사(취소/진행률). 이미 있는 dst 는 호출 전에 처리됨."""
        try:
            size = os.path.getsize(src)
        except OSError:
            size = 0
        entry = [os.path.basename(src), 0, size]
        with self._lock:
            self.active[dst] = entry
        try:
            with open(src, "rb") as fi, open(dst, "wb") as fo:
                while True:
                    if self.cancel.is_set():
                        raise Cancelled()
                    buf = fi.read(CHUNK)
                    if not buf:
                        break
                    fo.write(buf)
                    entry[1] += len(buf)
                    self._add(len(buf))
        finally:
            with self._lock:
                self.active.pop(dst, None)
        shutil.copystat(src, dst, follow_symlinks=True)

    def _transfer_file(self, src, dst, same_vol):
        if self.cancel.is_set():
            raise Cancelled()
        self.current = os.path.basename(src)
        size = os.path.getsize(src)
        if os.path.exists(dst):
            if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
                if self.op == "move":
                    self._add(size)
                    return
                dst = unique_path(dst)  # 같은 폴더에 복사 → 자동 번호
            else:
                ans = self._resolve(src, dst)
                if ans == "cancel":
                    raise Cancelled()
                if ans == "skip":
                    self._add(size)
                    return
                if ans == "rename":
                    dst = unique_path(dst)
        try:
            if self.op == "move" and same_vol:
                os.replace(src, dst)
                self._add(size)
            else:
                self._copy_file(src, dst)
                if self.op == "move":
                    os.remove(src)
            with self._lock:
                self.files_done += 1
        except Cancelled:
            try:  # 반쪽짜리 파일 제거
                if os.path.exists(dst) and os.path.getsize(dst) != size:
                    os.remove(dst)
            except OSError:
                pass
            raise
        except OSError as e:
            self._err(src, e)

    # ---- 계획 수립 ----
    def _plan(self):
        files, dirs, moves_whole = [], [], []   # files: (src, dst), dirs: dst dirs, moves_whole: (src,dst)
        for src in self.sources:
            if not os.path.exists(src):
                self._err(src, "원본이 없습니다")
                continue
            name = os.path.basename(src.rstrip("\\/")) or src.rstrip("\\/").replace(":", "")
            dst = os.path.join(self.dest_dir, name)
            if os.path.isdir(src):
                if is_inside(self.dest_dir, src):
                    self._err(src, "폴더를 자기 자신(하위)으로 복사/이동할 수 없습니다")
                    continue
                if self.op == "move" and os.path.normcase(os.path.abspath(os.path.dirname(src))) == \
                        os.path.normcase(os.path.abspath(self.dest_dir)):
                    continue  # 같은 위치로 이동 = 아무 일 없음
                if self.op == "copy" and os.path.exists(dst) and \
                        os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
                    dst = unique_path(dst)
                if self.op == "move" and not os.path.exists(dst) and same_volume(src, self.dest_dir):
                    moves_whole.append((src, dst))  # 폴더 통째로 이름만 바꿔 이동 (즉시)
                    continue
                for root, dnames, fnames in os.walk(src):
                    rel = os.path.relpath(root, src)
                    droot = dst if rel == "." else os.path.join(dst, rel)
                    dirs.append(droot)
                    for f in fnames:
                        files.append((os.path.join(root, f), os.path.join(droot, f)))
            else:
                files.append((src, dst))
        return files, dirs, moves_whole

    def _run_delete(self, progress):
        """영구 삭제(휴지통 안 거침): 파일을 스레드 8개로 병렬 삭제 → 빈 폴더를 깊은 것부터 삭제.
        정션/심볼릭 링크는 링크만 지우고 그 안으로 들어가지 않음"""
        files, dirs = [], []
        stack = list(self.sources)
        while stack and not self.cancel.is_set():
            path = stack.pop()
            bare = path.rstrip("\\/")
            if not bare or bare.endswith(":") or (bare.startswith("\\\\") and bare.count("\\") < 4):
                self._err(path, "드라이브/네트워크 루트는 삭제할 수 없습니다")   # 실수 방지
                continue
            try:
                st = os.lstat(_lp(path))
                if stat.S_ISDIR(st.st_mode) and not _is_reparse(st):
                    dirs.append(path)
                    with os.scandir(_lp(path)) as it:
                        for e in it:
                            stack.append(os.path.join(path, e.name))
                else:
                    files.append(path)            # 파일, 링크(정션 포함)
            except OSError as ex:
                self._err(path, ex)
        self.total_bytes = max(len(files) + len(dirs), 1)
        stop = threading.Event()

        def ticker():
            while not stop.wait(0.1):
                if progress:
                    try:
                        progress(self.done_bytes, self.total_bytes, self.current)
                    except Exception:
                        pass
        threading.Thread(target=ticker, daemon=True).start()

        def rm(p):
            if self.cancel.is_set():
                return
            try:
                _unlink(p)
                with self._lock:
                    self.files_done += 1
            except OSError as ex:
                self._err(p, ex)
            self._add(1, os.path.basename(p))
        try:
            with ThreadPoolExecutor(max_workers=DELETE_WORKERS) as pool:
                list(pool.map(rm, files))
            for d in sorted(dirs, key=lambda x: x.count(os.sep), reverse=True):   # 깊은 폴더부터
                if self.cancel.is_set():
                    break
                try:
                    _rmdir(d)
                except OSError as ex:
                    self._err(d, ex)
                self._add(1, os.path.basename(d))
        finally:
            stop.set()
            if progress:
                progress(self.done_bytes, self.total_bytes, "")
        return not self.cancel.is_set()

    def run(self, progress=None):
        """progress(done_bytes, total_bytes, current_name) 는 다른 스레드에서 호출될 수 있음"""
        if self.op == "delete":
            return self._run_delete(progress)
        files, dirs, moves_whole = self._plan()
        sizes = {}
        for s, _ in files:
            try:
                sizes[s] = os.path.getsize(s)
            except OSError:
                sizes[s] = 0
        self.total_bytes = sum(sizes.values()) or 1
        self.total_files = len(files)
        stop = threading.Event()

        def ticker():
            while not stop.wait(0.1):
                if progress:
                    try:
                        progress(self.done_bytes, self.total_bytes, self.current)
                    except Exception:               # 화면 쪽 오류 때문에 진행 표시가 멈추지 않게
                        pass

        t = threading.Thread(target=ticker, daemon=True)
        t.start()
        try:
            for src, dst in moves_whole:
                self.current = os.path.basename(src)
                try:
                    os.rename(src, dst)
                except OSError as e:
                    self._err(src, e)
            for d in dirs:
                try:
                    os.makedirs(d, exist_ok=True)
                except OSError as e:
                    self._err(d, e)
            same_vol = self.op == "move" and same_volume(files[0][0], self.dest_dir) if files else False
            small = [(s, d) for s, d in files if sizes[s] < SMALL_FILE]
            large = [(s, d) for s, d in files if sizes[s] >= SMALL_FILE]
            pool = ThreadPoolExecutor(max_workers=WORKERS)
            futs = [pool.submit(self._safe, s, d, same_vol) for s, d in small]
            try:
                for s, d in large:  # 대용량은 작은 파일 병렬 처리와 겹쳐서 단일 스트림으로
                    self._safe(s, d, same_vol)
                for f in futs:
                    f.result()
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
            if self.op == "move" and not self.cancel.is_set():
                for s in self.sources:  # 이동 후 남은 빈 원본 폴더 정리
                    if os.path.isdir(s):
                        for root, _d, _f in os.walk(s, topdown=False):
                            try:
                                os.rmdir(root)
                            except OSError:
                                pass
        except Cancelled:
            self.cancel.set()
        finally:
            stop.set()
            if progress:
                progress(self.total_bytes if not self.cancel.is_set() else self.done_bytes, self.total_bytes, "")
        return not self.cancel.is_set()

    def _safe(self, src, dst, same_vol):
        try:
            self._transfer_file(src, dst, same_vol)
        except Cancelled:
            self.cancel.set()
        except Exception as e:  # noqa
            self._err(src, e)


# ───────────────────────── 삭제 (휴지통) ─────────────────────────
class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]


def delete_paths(paths, permanent=False, hwnd=None):
    """휴지통(기본) 또는 영구 삭제. 영구 삭제는 셸이 확인창을 띄움. 성공 여부 반환"""
    if not paths:
        return True
    op = SHFILEOPSTRUCTW()
    op.hwnd = hwnd
    op.wFunc = 3  # FO_DELETE
    op.pFrom = "\0".join(os.path.normpath(p) for p in paths) + "\0\0"
    op.fFlags = 0 if permanent else 0x40  # FOF_ALLOWUNDO
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return rc == 0 and not op.fAnyOperationsAborted


# ───────────────────────── Windows 즐겨찾기(Quick access) ─────────────────────────
QUICK_ACCESS = "shell:::{679f85cb-0220-4080-b29b-5540cc05aab6}"


def _ps(script):
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30, creationflags=0x08000000)  # CREATE_NO_WINDOW


def _q(s):
    return "'" + s.replace("'", "''") + "'"


def pin_home(path):
    """탐색기 '홈/빠른 실행'에 고정 (다른 프로그램의 열기창에도 보임)"""
    r = _ps(f"(New-Object -ComObject Shell.Application).Namespace({_q(path)}).Self.InvokeVerb('pintohome')")
    return r.returncode == 0


def unpin_home(path):
    p = os.path.normcase(os.path.normpath(path)).replace("'", "''")
    r = _ps(f"$q=(New-Object -ComObject Shell.Application).Namespace('{QUICK_ACCESS}');"
            f"$q.Items() | Where-Object {{ $_.Path -and ($_.Path.ToLower() -eq '{p}') }} | "
            f"ForEach-Object {{ $_.InvokeVerb('unpinfromhome') }}")
    return r.returncode == 0


def pin_many(paths):
    """여러 폴더를 PowerShell 한 번으로 '빠른 실행'에 고정 → {경로: 성공 여부}"""
    import json
    if not paths:
        return {}
    ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
          "$paths=ConvertFrom-Json $env:JY_PATHS; $sh=New-Object -ComObject Shell.Application; $res=@{};"
          "foreach($p in $paths){ try { $sh.Namespace($p).Self.InvokeVerb('pintohome'); $res[$p]=$true } catch { $res[$p]=$false } };"
          "ConvertTo-Json -InputObject $res -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           env=dict(os.environ, JY_PATHS=json.dumps(list(paths), ensure_ascii=False)),
                           timeout=60 + 3 * len(paths), creationflags=0x08000000)
        data = json.loads(r.stdout.decode("utf-8", "ignore").strip() or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {p: False for p in paths}
    return {p: bool(data.get(p, False)) for p in paths}


def unpin_many(paths):
    """여러 폴더를 PowerShell 한 번으로 '빠른 실행'에서 고정 해제 → {경로: 성공 여부} (원래 고정돼 있지 않았으면 성공으로 봄)"""
    import json
    if not paths:
        return {}
    ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
          "$paths=ConvertFrom-Json $env:JY_PATHS; $want=@{}; foreach($p in $paths){ $want[$p.ToLower()]=$p }; $res=@{};"
          f"$q=(New-Object -ComObject Shell.Application).Namespace('{QUICK_ACCESS}');"
          "foreach($i in @($q.Items())){ if($i.Path -and $want.ContainsKey($i.Path.ToLower())){ "
          "try { $i.InvokeVerb('unpinfromhome'); $res[$want[$i.Path.ToLower()]]=$true } catch { $res[$want[$i.Path.ToLower()]]=$false } } };"
          "ConvertTo-Json -InputObject $res -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           env=dict(os.environ, JY_PATHS=json.dumps(list(paths), ensure_ascii=False)),
                           timeout=60 + 3 * len(paths), creationflags=0x08000000)
        data = json.loads(r.stdout.decode("utf-8", "ignore").strip() or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {p: False for p in paths}
    return {p: bool(data.get(p, True)) for p in paths}


def is_pinned(path):
    p = os.path.normcase(os.path.normpath(path)).replace("'", "''")
    r = _ps(f"$q=(New-Object -ComObject Shell.Application).Namespace('{QUICK_ACCESS}');"
            f"($q.Items() | Where-Object {{ $_.Path -and ($_.Path.ToLower() -eq '{p}') }} | Measure-Object).Count")
    try:
        return int(r.stdout.strip() or 0) > 0
    except ValueError:
        return False


def windows_pinned_folders():
    """Windows 탐색기 '즐겨찾기(빠른 실행)'에 고정된 폴더 목록 → [{"name", "path"}]. 자주 쓰는 폴더(자동)는 제외"""
    import json
    import re
    ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
          f"$q=(New-Object -ComObject Shell.Application).Namespace('{QUICK_ACCESS}');"
          "$r=@(); foreach($i in $q.Items()){ if($i.ExtendedProperty('System.Home.IsPinned')){ "
          "$r += [pscustomobject]@{name=$i.Name; path=$i.Path} } };"
          "if($r.Count -eq 0){ '[]' } else { ConvertTo-Json -InputObject $r -Compress }")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       timeout=45, creationflags=0x08000000)
    try:
        data = json.loads(r.stdout.decode("utf-8", "ignore").strip() or "[]")
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if d.get("path") and re.match(r"^([A-Za-z]:\\|\\\\)", d["path"])]
