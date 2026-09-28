"""everything_ini 테스트: 사용자 ini 와 같은 모양의 텍스트로 읽기/추가/제거 (실제 Everything 설정은 건드리지 않음).  python test_everything_ini.py"""
import os
import tempfile

import everything_ini as E

SAMPLE = """[Everything]
run_as_admin=0
ntfs_volume_paths="C:","D:","E:","F:"
ntfs_volume_includes=1,1,0,1
ntfs_volume_monitors=1,1,1,1
filelists=
folders="G:\\\\","W:\\\\","Z:\\\\"
folder_monitor_changes=1,1,1
folder_buffer_size_list=65536,65536,65536
folder_rescan_if_full_list=0,0,0
folder_update_types=2,2,2
folder_update_days=0,0,0
folder_update_ats=3,3,3
folder_update_intervals=6,6,6
folder_update_interval_types=1,1,1
exclude_folders=
other_setting=keep me
"""

# 목록 파싱
assert E.parse_list('"G:\\\\","W:\\\\"') == ["G:\\", "W:\\"]
assert E.parse_list("1,1,0") == ["1", "1", "0"]
assert E.parse_list('c:\\program files,"c:\\\\a,folder,with,commas",\\\\server\\share,"\\\\\\\\server\\\\share2"') == \
    ["c:\\program files", "c:\\a,folder,with,commas", "\\\\server\\share", "\\\\server\\share2"]
assert E.parse_list("") == []
assert E.format_paths(["G:\\", "\\\\srv\\a b"]) == '"G:\\\\","\\\\\\\\srv\\\\a b"'
assert E.parse_list(E.format_paths(["G:\\", "\\\\srv\\a b", 'x"y'])) == ["G:\\", "\\\\srv\\a b", 'x"y']

ini = E.IniText(SAMPLE)
idx = E.read_index(ini)
assert idx["volumes"] == [("C:", True, True), ("D:", True, True), ("E:", False, True), ("F:", True, True)], idx["volumes"]
assert idx["folders"] == [("G:\\", True), ("W:\\", True), ("Z:\\", True)], idx["folders"]
assert E.covered_by_volume(ini, r"C:\Users\x") == "C:"
assert E.covered_by_volume(ini, r"E:\a") is None          # E: 는 포함 안 됨
assert E.covered_by_volume(ini, r"W:\a") is None

# 추가: 모든 보조 목록이 같이 늘어남, 다른 줄은 보존
assert E.add_folder(ini, r"\\172.16.100.77\학습지원센터") is True
assert E.add_folder(ini, "w:\\") is False                  # 이미 있음 (대소문자 무시)
t = ini.text()
assert t.count("\n") == SAMPLE.count("\n") and "other_setting=keep me" in t and "run_as_admin=0" in t
after = E.read_index(E.IniText(t))
assert [p for p, _ in after["folders"]] == ["G:\\", "W:\\", "Z:\\", "\\\\172.16.100.77\\학습지원센터"], after["folders"]
for k in E.FOLDER_LISTS:
    assert len(E.parse_list(E.IniText(t).get(k))) == 4, (k, E.IniText(t).get(k))
# 제거
ini2 = E.IniText(t)
assert E.remove_folder(ini2, "w:\\") is True and E.remove_folder(ini2, "W:\\") is False
r = E.read_index(E.IniText(ini2.text()))
assert [p for p, _ in r["folders"]] == ["G:\\", "Z:\\", "\\\\172.16.100.77\\학습지원센터"]
for k in E.FOLDER_LISTS:
    assert len(E.parse_list(E.IniText(ini2.text()).get(k))) == 3
# folders 키가 없던 ini
bare = E.IniText("[Everything]\nntfs_volume_paths=\"C:\"\n")
assert E.add_folder(bare, r"D:\data") is True
assert E.read_index(E.IniText(bare.text()))["folders"] == [("D:\\data", True)]
assert E.normalize_folder("D:/data/") == "D:\\data" and E.normalize_folder("W:") == "W:\\"

# 파일 저장: 백업 생성, BOM/줄바꿈 보존
d = tempfile.mkdtemp()
p = os.path.join(d, "Everything.ini")
open(p, "wb").write(b"\xef\xbb\xbf" + SAMPLE.replace("\n", "\r\n").encode("utf-8"))
i3, bom = E.read_ini(p)
assert bom is True and i3.nl == "\r\n"
E.add_folder(i3, r"D:\새 폴더")
backup = E.write_ini(p, i3, bom)
raw = open(p, "rb").read()
assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw and os.path.exists(backup)
assert open(backup, "rb").read().count(b"D:") == SAMPLE.encode().count(b"D:")       # 백업은 원본 그대로
assert E.read_index(E.read_ini(p)[0])["folders"][-1] == ("D:\\새 폴더", True)

# change_index 순서 검증 (Everything 을 실제로 끄지 않도록 함수들을 가짜로 바꿈): 종료 → 백업+수정 → 재시작
import filesearch as FS  # noqa: E402

calls = []
FS.find_everything_exe = lambda: "X:\\fake\\Everything.exe"
E.find_ini = lambda: p
FS.stop_everything = lambda wait=20.0: (calls.append("stop") or True)
FS.start_everything = lambda wait=8.0: (calls.append("start") or True)
ok, m = FS.change_index(lambda ini: "추가함" if E.add_folder(ini, r"D:\또 다른 폴더") else None)
assert ok and "추가함" in m and "백업" in m and calls == ["stop", "start"], (ok, m, calls)
assert E.read_index(E.read_ini(p)[0])["folders"][-1][0] == "D:\\또 다른 폴더"
calls.clear()
ok, m = FS.change_index(lambda ini: None)                            # 바꿀 게 없어도 다시 켬
assert ok and calls == ["stop", "start"] and "없습니다" in m
calls.clear()


def boom(ini):
    raise ValueError("나쁜 경로")


ok, m = FS.change_index(boom)                                        # 수정 실패해도 Everything 은 다시 켬
assert (not ok) and m == "나쁜 경로" and calls == ["stop", "start"]
calls.clear()
FS.stop_everything = lambda wait=20.0: False                         # 종료 못 하면(관리자 권한) 아무것도 바꾸지 않고 안내
before = open(p, "rb").read()
ok, m = FS.change_index(lambda ini: E.add_folder(ini, r"D:\x") and "x")
assert (not ok) and "종료하지 못했" in m and open(p, "rb").read() == before and calls == []
print("everything_ini tests OK")
