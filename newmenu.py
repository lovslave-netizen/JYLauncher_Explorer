"""'새로 만들기' 목록 — 일반 탐색기처럼 빈 곳 우클릭 → 새로 만들기 → (폴더 / 바로 가기 / 텍스트 문서 / hwp / ahk …).

Windows 는 새로 만들 수 있는 파일 형식을 레지스트리 HKCR\\.확장자\\ShellNew (또는 .확장자\\ProgID\\ShellNew)에 등록해 둔다.
  NullFile  = 빈 파일을 만듦            FileName = 템플릿 파일을 복사            Data = 이 바이트를 파일로 씀
  (Command = 프로그램 실행 방식은 지원하지 않음)
이름은 그 확장자의 파일 형식 설명(예: '텍스트 문서')을 쓰고, 만든 뒤 바로 이름을 바꿀 수 있게 한다.
"""
import ctypes
import os
import shutil
import threading
import winreg

SKIP_EXT = {".lnk", ".library-ms", ".searchconnector-ms", ".zfsendtarget", ".mapimail", ".website", ".url"}
_cache = {"types": None}
_lock = threading.Lock()


def _indirect(s):
    """'@%SystemRoot%\\\\system32\\\\notepad.exe,-470' 같은 리소스 문자열을 실제 글자로"""
    if not s or not s.startswith("@"):
        return s
    try:
        buf = ctypes.create_unicode_buffer(512)
        if ctypes.windll.shlwapi.SHLoadIndirectString(s, buf, 512, None) == 0:
            return buf.value
    except Exception:
        pass
    return ""


def _values(key):
    out, i = {}, 0
    while True:
        try:
            name, val, typ = winreg.EnumValue(key, i)
        except OSError:
            return out
        out[name.lower()] = (val, typ)
        i += 1


def _shellnew(path):
    """레지스트리 경로의 ShellNew 키 → {'kind','template','data','itemname'} 또는 None"""
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, path) as k:
            v = _values(k)
    except OSError:
        return None
    item = v.get("itemname", ("", 0))[0]
    if "nullfile" in v:
        return {"kind": "null", "itemname": item}
    if "filename" in v and v["filename"][0]:
        return {"kind": "file", "template": v["filename"][0], "itemname": item}
    if "data" in v:
        d = v["data"][0]
        return {"kind": "data", "data": d if isinstance(d, bytes) else str(d).encode("utf-8"), "itemname": item}
    return None


def _description(ext):
    """확장자의 파일 형식 설명 (예: .txt → 텍스트 문서). 없으면 '.EXT 파일'"""
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as k:
            progid = winreg.QueryValueEx(k, "")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid) as k:
            desc = _indirect(winreg.QueryValueEx(k, "")[0])
        if desc:
            return desc
    except OSError:
        pass
    return f"{ext[1:].upper()} 파일"


def list_types(force=False):
    """[{'ext': '.txt', 'desc': '텍스트 문서', 'base': '새 텍스트 문서', 'kind', 'template', 'data'}, …] (설명 순). 한 번 읽고 캐시"""
    with _lock:
        if _cache["types"] is not None and not force:
            return _cache["types"]
        found = {}
        try:
            n = winreg.QueryInfoKey(winreg.HKEY_CLASSES_ROOT)[0]
            for i in range(n):
                try:
                    name = winreg.EnumKey(winreg.HKEY_CLASSES_ROOT, i)
                except OSError:
                    continue
                if not name.startswith(".") or name.lower() in SKIP_EXT:
                    continue
                sn = _shellnew(name + "\\ShellNew")
                if sn is None:                                   # .확장자\\ProgID\\ShellNew 형태
                    try:
                        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name) as k:
                            for j in range(winreg.QueryInfoKey(k)[0]):
                                sub = winreg.EnumKey(k, j)
                                sn = _shellnew(f"{name}\\{sub}\\ShellNew")
                                if sn:
                                    break
                    except OSError:
                        pass
                if sn is None:
                    continue
                desc = _description(name)
                item = _indirect(sn.get("itemname", "")) if sn.get("itemname") else ""
                base = item.replace("%s", desc) if "%s" in item else (item or f"새 {desc}")
                found[name.lower()] = {"ext": name.lower(), "desc": desc, "base": base, **sn}
        except OSError:
            pass
        if ".ahk" not in found:                                  # AutoHotkey 는 등록이 없는 PC 가 많아 기본 제공
            found[".ahk"] = {"ext": ".ahk", "desc": "AutoHotkey 스크립트", "base": "새 AutoHotkey 스크립트", "kind": "null"}
        types = sorted(found.values(), key=lambda t: t["desc"].lower())
        _cache["types"] = types
        return types


def _template_path(name):
    if os.path.isabs(name) and os.path.exists(name):
        return name
    for base in (os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Templates"),
                 os.path.join(os.environ.get("ProgramData", ""), "Microsoft", "Windows", "Templates"),
                 os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "ShellNew")):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


def _unique(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def create_file(folder, item):
    """folder 에 item(list_types 의 항목) 형식의 새 파일을 만들고 경로를 돌려줌"""
    dest = _unique(os.path.join(folder, item["base"] + item["ext"]))
    if item["kind"] == "file":
        tpl = _template_path(item["template"])
        if tpl:
            shutil.copyfile(tpl, dest)
            return dest
    if item["kind"] == "data":
        with open(dest, "wb") as f:
            f.write(item["data"])
        return dest
    open(dest, "wb").close()
    return dest


def create_shortcut(folder, target):
    """바로 가기 만들기: 웹 주소면 .url, 그 밖은 .lnk. 만든 경로를 돌려줌 (실패하면 None)"""
    import jycommon
    target = target.strip().strip('"')
    if not target:
        return None
    if target.lower().startswith(("http://", "https://", "ftp://")):
        host = target.split("//", 1)[1].split("/", 1)[0] or "웹 바로 가기"
        dest = _unique(os.path.join(folder, host + ".url"))
        with open(dest, "w", encoding="utf-8") as f:
            f.write(f"[InternetShortcut]\r\nURL={target}\r\n")
        return dest
    target = os.path.normpath(target)
    name = os.path.basename(target.rstrip("\\")) or target.rstrip(":\\") + " 드라이브"
    dest = _unique(os.path.join(folder, f"{name} - 바로 가기.lnk"))
    workdir = target if os.path.isdir(target) else os.path.dirname(target)
    return dest if jycommon.make_shortcut(dest, target, "", workdir, name) else None
