"""새로 만들기(newmenu) + 윈도우 메뉴 하위 메뉴/아이콘 테스트. PC 마다 등록된 파일 형식이 달라서 형식 개수에는 의존하지 않음.  python test_newmenu.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import newmenu

types = newmenu.list_types()
assert types and any(t["ext"] == ".ahk" for t in types), types          # 등록된 형식이 없어도 .ahk 는 기본 제공
print("new-menu types:", len(types), ", ".join(t["ext"] for t in types))
root = tempfile.mkdtemp()
for t in types[:3] + [next(t for t in types if t["ext"] == ".ahk")]:
    a = newmenu.create_file(root, t)
    b = newmenu.create_file(root, t)
    assert os.path.exists(a) and os.path.exists(b) and a != b and a.endswith(t["ext"]), (a, b)   # 이름 겹치면 (2)
url = newmenu.create_shortcut(root, "https://example.com/a")
assert url and url.endswith(".url") and "URL=https://example.com/a" in open(url, encoding="utf-8").read()
lnk = newmenu.create_shortcut(root, root)
assert lnk is None or lnk.endswith(".lnk")                                # .lnk 는 PowerShell 이 있어야 만들어짐 (없으면 None)

# 윈도우 우클릭 메뉴: 하위 메뉴 + 아이콘 만들기, 중복 항목 제거 (셸을 못 쓰는 환경이면 건너뜀)
try:
    import win32gui
    import shellmenu as SM
    m = SM.ShellMenu([], root)
except Exception as e:                                                    # noqa: BLE001
    print("shell menu unavailable here - submenu check skipped:", type(e).__name__)
else:
    icon = (16, 16, bytes(16 * 16 * 4))
    m.remove_texts({"새 폴더", "새로 만들기", "new folder", "new"})
    m.add_custom([("sub", "새로 만들기", [(SM.CUSTOM_BASE, "폴더", icon), (SM.CUSTOM_BASE + 1, "텍스트", None)])])
    assert win32gui.GetSubMenu(m.hmenu, 0) != 0
    m.close()
print("newmenu tests OK")
sys.stdout.flush()
os._exit(0)
