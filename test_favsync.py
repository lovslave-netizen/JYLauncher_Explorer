"""favsync(북마크 ↔ Windows 즐겨찾기 동기화 계산) + 백업(zip, 90일 정리) 테스트.  python test_favsync.py"""
import os
import tempfile
import time
import zipfile

import favsync as S

n = S.norm
assert n("C:/Users/X/") == n("c:\\users\\x") and n("D:\\") == "d:\\"


def mk(*paths):
    return {n(p): p for p in paths}


DEF = {n(r"C:\Users\x\Desktop")}

# 처음 켤 때: 합치기만, 삭제 없음
p = S.plan(mk("W:\\a", "W:\\b"), mk("W:\\b", "W:\\c"), None, DEF)
assert p["first"] and p["to_jy"] == ["W:\\a"] and p["to_win"] == ["W:\\c"] and p["rm_jy"] == [] and p["rm_win"] == []
# 기본 폴더는 제외
p = S.plan(mk(r"C:\Users\x\Desktop", "W:\\a"), mk(), None, DEF)
assert p["to_jy"] == ["W:\\a"]

# 이후: 3방향 비교
snap = {n("W:\\a"), n("W:\\b"), n("W:\\c")}
p = S.plan(win=mk("W:\\a", "W:\\b", "W:\\new_in_win"),                # c: Windows 에서 뺌, new_in_win: Windows 에서 추가
           jy=mk("W:\\a", "W:\\c", "W:\\new_in_jy"),                  # b: 북마크에서 삭제, new_in_jy: 북마크에 추가
           snapshot=snap, excluded=DEF)
assert p["to_jy"] == ["W:\\new_in_win"], p
assert p["rm_jy"] == ["W:\\c"], p                                     # Windows 에서 사라진 c → 북마크에서 삭제
assert p["to_win"] == ["W:\\new_in_jy"], p
assert p["rm_win"] == ["W:\\b"], p                                    # 북마크에서 삭제한 b → Windows 고정 해제
# 양쪽에서 다 지운 것 / 양쪽에 다 있는 것 → 아무 일 없음
p = S.plan(mk("W:\\a"), mk("W:\\a"), {n("W:\\a"), n("W:\\gone")}, DEF)
assert p == {"to_jy": [], "rm_jy": [], "to_win": [], "rm_win": [], "first": False, "skipped_rm": False}
# 같은 경로가 대소문자만 다른 경우도 같은 것으로
p = S.plan(mk("w:\\A"), mk("W:\\a"), {n("W:\\a")}, DEF)
assert not (p["to_jy"] or p["rm_jy"] or p["to_win"] or p["rm_win"])
# 안전장치: 목록을 못 읽어 Windows 쪽이 비어 보이면 대량 삭제를 하지 않음
snap = {n(f"W:\\f{i}") for i in range(12)}
p = S.plan(win={}, jy=mk(*[f"W:\\f{i}" for i in range(12)]), snapshot=snap, excluded=())
assert p["skipped_rm"] and p["rm_jy"] == [] and p["rm_win"] == [], p
# 소수 삭제는 정상 처리
p = S.plan(win=mk(*[f"W:\\f{i}" for i in range(11)]), jy=mk(*[f"W:\\f{i}" for i in range(12)]), snapshot=snap, excluded=())
assert p["rm_jy"] == ["W:\\f11"] and not p["skipped_rm"]
# 스냅샷 갱신: 양쪽에 모두 있는 것만
assert S.new_snapshot({"a", "b"}, {"b", "c"}) == {"b"}

# ── 백업: zip 하나 + 90일 지난 것 정리 ──
tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp
import jycommon as C  # noqa: E402

C.BACKUP_DIR = C.DATA_DIR / "backup"
C.DATA_DIR.mkdir(parents=True, exist_ok=True)
C.BOOKMARKS_FILE.write_text('{"children": []}', encoding="utf-8")
C.EXPLORER_FILE.write_text('{"quick": [], "col_order": [0, 1]}', encoding="utf-8")
C.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
old = C.BACKUP_DIR / "JYExplorer_백업_2000-01-01.zip"
old.write_bytes(b"x")
legacy_old = C.BACKUP_DIR / "bookmarks_2000-01-01.json"
legacy_old.write_text("{}", encoding="utf-8")
recent = C.BACKUP_DIR / "JYExplorer_백업_recent.zip"
recent.write_bytes(b"x")
for f, days in ((old, 120), (legacy_old, 120), (recent, 10)):
    t = time.time() - days * 86400
    os.utime(f, (t, t))
z = C.backup_favorites("_테스트")
assert z.suffix == ".zip" and z.exists() and "_테스트" in z.name, z
with zipfile.ZipFile(z) as zf:
    assert sorted(zf.namelist()) == ["bookmarks.json", "explorer.json"]
    assert '"col_order"' in zf.read("explorer.json").decode("utf-8")
assert not old.exists() and not legacy_old.exists() and recent.exists()       # 90일 지난 것만 삭제
assert C.read_backup(z)[0] == {"children": []} and C.read_backup(z)[1]["col_order"] == [0, 1]
print("favsync tests OK")
