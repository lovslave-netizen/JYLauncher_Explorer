"""Everything.ini 읽기/수정 — 색인에 들어 있는 볼륨/폴더를 보고, 폴더 색인을 추가·제거한다.
형식은 voidtools INI 문서 기준: 목록 값은 쉼표로 구분, 따옴표 안에서는 \\ 가 이스케이프 문자.
폴더 색인은 `folders=` 목록 + 같은 길이의 보조 목록(folder_monitor_changes, folder_update_types …)으로 저장되므로
추가/제거할 때 모든 보조 목록의 길이를 함께 맞춘다.
파일을 쓰기 전에는 항상 백업을 만들고, Everything 이 종료된 상태에서만 수정해야 한다(종료 때 ini 를 다시 쓰기 때문)."""
import os
import re
import shutil
import time
from pathlib import Path

FOLDER_LISTS = ("folder_monitor_changes", "folder_buffer_size_list", "folder_rescan_if_full_list", "folder_update_types",
                "folder_update_days", "folder_update_ats", "folder_update_intervals", "folder_update_interval_types")
DEFAULTS = {"folder_monitor_changes": "1", "folder_buffer_size_list": "65536", "folder_rescan_if_full_list": "0",
            "folder_update_types": "2", "folder_update_days": "0", "folder_update_ats": "3",
            "folder_update_intervals": "6", "folder_update_interval_types": "1"}


def parse_list(v):
    """쉼표로 구분된 목록 (따옴표 항목은 \\ 이스케이프 해석, 따옴표 없는 항목은 그대로)"""
    v = v.strip()
    if v == "":
        return []
    out, i, n = [], 0, len(v)
    while i <= n:
        if i < n and v[i] == '"':
            i += 1
            buf = ""
            while i < n and v[i] != '"':
                if v[i] == "\\" and i + 1 < n:
                    buf += v[i + 1]
                    i += 2
                else:
                    buf += v[i]
                    i += 1
            i += 1                                   # 닫는 따옴표
            out.append(buf)
            while i < n and v[i] != ",":
                i += 1
            i += 1
        else:
            j = v.find(",", i)
            j = n if j < 0 else j
            out.append(v[i:j])
            i = j + 1
    return out


def format_paths(items):
    return ",".join('"' + it.replace("\\", "\\\\").replace('"', '\\"') + '"' for it in items)


def normalize_folder(path):
    """Everything 이 저장하는 모양으로: 드라이브 루트는 'X:\\', 그 밖은 끝 백슬래시 없이"""
    p = os.path.normpath(path)
    if len(p) == 2 and p[1] == ":":
        p += "\\"
    return p if len(p) <= 3 else p.rstrip("\\")


class IniText:
    """ini 텍스트를 줄 단위로 다루는 얇은 래퍼 (다른 줄은 그대로 보존)"""

    def __init__(self, text):
        self.nl = "\r\n" if "\r\n" in text else "\n"
        self.lines = text.splitlines()

    def _find(self, key):
        pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=", re.I)
        for i, ln in enumerate(self.lines):
            if pat.match(ln):
                return i
        return -1

    def get(self, key, default=""):
        i = self._find(key)
        return default if i < 0 else self.lines[i].split("=", 1)[1]

    def set(self, key, value):
        i = self._find(key)
        line = f"{key}={value}"
        if i >= 0:
            self.lines[i] = line
        else:                                       # [Everything] 구역 끝(다음 구역 앞, 없으면 파일 끝)에 추가
            end = len(self.lines)
            seen = False
            for j, ln in enumerate(self.lines):
                if ln.strip().lower() == "[everything]":
                    seen = True
                elif seen and ln.strip().startswith("["):
                    end = j
                    break
            self.lines.insert(end, line)

    def text(self):
        return self.nl.join(self.lines) + self.nl


def read_ini(path):
    """(IniText, BOM 여부). Everything 은 보통 UTF-8"""
    raw = Path(path).read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("mbcs", "replace")
    return IniText(text), bom


def write_ini(path, ini, bom):
    """백업(Everything.ini.jy-백업-시각) 을 만든 뒤 저장. 백업 경로를 돌려줌"""
    path = Path(path)
    backup = path.with_name(path.name + ".jy-backup-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    data = ini.text().encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" + data) if bom else data)
    return backup


def find_ini():
    """사용 중인 Everything.ini (APPDATA 설정이 있으면 그것, 없으면 Everything.exe 옆). 없으면 None"""
    cands = []
    if os.environ.get("APPDATA"):
        cands.append(Path(os.environ["APPDATA"]) / "Everything" / "Everything.ini")
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            cands.append(Path(base) / "Everything" / "Everything.ini")
    for c in cands:
        try:
            if c.exists() and "ntfs_volume_paths" in c.read_text(encoding="utf-8-sig", errors="ignore"):
                return c
        except OSError:
            continue
    for c in cands:
        if c.exists():
            return c
    return None


def read_index(ini):
    """색인 현황: {'volumes': [(경로, 포함여부, 감시여부)], 'folders': [(경로, 감시여부)]}"""
    vols = []
    for kind in ("ntfs", "refs"):
        paths = parse_list(ini.get(f"{kind}_volume_paths"))
        inc = parse_list(ini.get(f"{kind}_volume_includes"))
        mon = parse_list(ini.get(f"{kind}_volume_monitors"))
        for k, p in enumerate(paths):
            vols.append((p, (inc[k] if k < len(inc) else "1") == "1", (mon[k] if k < len(mon) else "1") == "1"))
    folders = parse_list(ini.get("folders"))
    fmon = parse_list(ini.get("folder_monitor_changes"))
    return {"volumes": vols, "folders": [(p, (fmon[k] if k < len(fmon) else "1") == "1") for k, p in enumerate(folders)]}


def covered_by_volume(ini, path):
    """path 가 이미 색인되는 NTFS/ReFS 볼륨 안에 있으면 그 볼륨 경로 (없으면 None)"""
    drive = os.path.splitdrive(os.path.normpath(path))[0].upper()
    for p, included, _m in read_index(ini)["volumes"]:
        if included and p.upper().rstrip("\\") == drive:
            return p
    return None


def add_folder(ini, path):
    """폴더 색인 추가. 이미 있으면 False. 모든 보조 목록 길이를 folders 와 맞춰 새 항목을 덧붙임"""
    path = normalize_folder(path)
    folders = parse_list(ini.get("folders"))
    if any(f.lower().rstrip("\\") == path.lower().rstrip("\\") for f in folders):
        return False
    folders.append(path)
    ini.set("folders", format_paths(folders))
    n = len(folders)
    for key in FOLDER_LISTS:
        vals = parse_list(ini.get(key))
        fill = vals[-1] if vals else DEFAULTS[key]         # 기존 항목과 같은 값으로 채워 사용자 설정을 따름
        vals = (vals + [fill] * n)[:n - 1] + [fill]
        ini.set(key, ",".join(vals))
    return True


def remove_folder(ini, path):
    """폴더 색인 제거 (모든 보조 목록에서 같은 위치 항목 삭제). 없으면 False"""
    key = normalize_folder(path).lower().rstrip("\\")
    folders = parse_list(ini.get("folders"))
    idx = next((i for i, f in enumerate(folders) if f.lower().rstrip("\\") == key), -1)
    if idx < 0:
        return False
    del folders[idx]
    ini.set("folders", format_paths(folders))
    for k in FOLDER_LISTS:
        vals = parse_list(ini.get(k))
        if idx < len(vals):
            del vals[idx]
        ini.set(k, ",".join(vals))
    return True
