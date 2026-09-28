"""시작 메뉴에서 검색되는 앱 목록 (런처 '검색' 탭의 앱 검색용).
시작 메뉴 바로가기(.lnk)를 훑고, Store(UWP) 앱은 Get-StartApps 로 보충한다.
처음 펼칠 때만 백그라운드로 만들고(수십~수백 개라 가벼움) 이후에는 캐시를 쓴다."""
import json
import os
import subprocess
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
SKIP_WORDS = ("uninstall", "제거", "삭제", "언인스톨", "readme", "read me", "release notes", "사용 설명서", "도움말", "help")


def start_menu_dirs():
    dirs = []
    for base in (os.environ.get("ProgramData"), os.environ.get("APPDATA")):
        if base:
            p = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if p.exists():
                dirs.append(p)
    return dirs


def scan_shortcuts():
    """[{name, target(실행에 쓸 경로), kind:'lnk'}]"""
    out, seen = [], set()
    for d in start_menu_dirs():
        for p in d.rglob("*.lnk"):
            name = p.stem
            if any(w in name.lower() for w in SKIP_WORDS):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "target": str(p), "kind": "lnk", "folder": p.parent.name if p.parent != d else ""})
    return out


def scan_store_apps(known_names):
    """Get-StartApps 로 Store 앱 등 (이미 .lnk 로 찾은 이름은 제외). PowerShell 실행이라 1~2초 걸림"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                           capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=30)
        data = json.loads(r.stdout.decode("utf-8", "ignore") or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for a in data:
        name, appid = a.get("Name", ""), a.get("AppID", "")
        if not name or not appid or name.lower() in known_names:
            continue
        if any(w in name.lower() for w in SKIP_WORDS):
            continue
        out.append({"name": name, "target": "shell:AppsFolder\\" + appid, "kind": "store", "folder": "Store"})
    return out


def build_index():
    apps = scan_shortcuts()
    apps += scan_store_apps({a["name"].lower() for a in apps})
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def filter_apps(apps, text):
    """이름에 검색어(공백으로 여러 단어)가 모두 들어간 앱. 이름이 검색어로 시작하는 것을 앞으로"""
    words = text.lower().split()
    if not words:
        return []
    hits = [a for a in apps if all(w in a["name"].lower() for w in words)]
    hits.sort(key=lambda a: (not a["name"].lower().startswith(words[0]), a["name"].lower()))
    return hits


def launch(app):
    """앱 실행. .lnk 는 그대로, Store 앱은 explorer 로 shell:AppsFolder 를 엶"""
    t = app["target"]
    if app["kind"] == "store":
        subprocess.Popen(["explorer.exe", t], creationflags=CREATE_NO_WINDOW)
    else:
        os.startfile(t)
