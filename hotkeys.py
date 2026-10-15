"""런처 항목별 전역 단축키 (런처 창이 숨어 있거나 다른 프로그램이 활성이어도 동작).
Windows RegisterHotKey 를 쓰므로 런처 프로세스(트레이 상주)가 떠 있어야 한다.   예: "Ctrl+Alt+N" → notepad.exe"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, Qt
from PySide6.QtGui import QKeySequence

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000
WM_HOTKEY = 0x0312
FIRST_ID = 0x5000

_NAMED = {Qt.Key_Space: 0x20, Qt.Key_Tab: 0x09, Qt.Key_Return: 0x0D, Qt.Key_Enter: 0x0D, Qt.Key_Insert: 0x2D,
          Qt.Key_Delete: 0x2E, Qt.Key_Home: 0x24, Qt.Key_End: 0x23, Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22,
          Qt.Key_Left: 0x25, Qt.Key_Up: 0x26, Qt.Key_Right: 0x27, Qt.Key_Down: 0x28}


def _vk(key):
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        return int(key)                                   # Qt 키 코드가 ASCII 대문자/숫자와 같고, 그게 곧 VK 코드
    if Qt.Key_F1 <= key <= Qt.Key_F24:
        return 0x70 + int(key) - int(Qt.Key_F1)
    return _NAMED.get(key, 0)


def parse_hotkey(text):
    """"Ctrl+Alt+N" → (표준 표기, Windows 수정키 비트, 가상키 코드). 쓸 수 없는 조합이면 None.
    Ctrl/Alt/Win 중 하나는 반드시 포함 (글자만이나 Shift 만으로는 평소 입력을 가로채므로 거절)"""
    seq = QKeySequence(text or "", QKeySequence.PortableText)
    if seq.count() != 1:
        return None
    combo = seq[0]
    key, mods = combo.key(), combo.keyboardModifiers()
    vk = _vk(key)
    if not vk:
        return None
    bits = 0
    if mods & Qt.ControlModifier:
        bits |= MOD_CONTROL
    if mods & Qt.AltModifier:
        bits |= MOD_ALT
    if mods & Qt.MetaModifier:
        bits |= MOD_WIN
    if not bits:
        return None
    if mods & Qt.ShiftModifier:
        bits |= MOD_SHIFT
    return seq.toString(QKeySequence.PortableText), bits, vk


def normalize(text):
    p = parse_hotkey(text)
    return p[0] if p else ""


class ItemHotkeys(QAbstractNativeEventFilter):
    """항목 단축키 묶음 등록/해제. apply() 로 전체를 새로 등록하고, 눌리면 callback(payload) 호출"""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.ids = {}                                     # 등록 ID → payload

    def clear(self):
        for i in self.ids:
            ctypes.windll.user32.UnregisterHotKey(None, i)
        self.ids = {}

    def apply(self, entries, reserved=()):
        """entries: [(단축키 글자, payload)].  이미 등록된 단축키는 모두 풀고 다시 등록.
        돌려주는 값: 등록하지 못한 [(글자, payload, 이유)]  (런처 자체 키/중복/형식 오류/다른 프로그램이 사용 중)"""
        self.clear()
        used = {normalize(r) for r in reserved}
        failed = []
        for text, payload in entries:
            p = parse_hotkey(text)
            if p is None:
                failed.append((text, payload, "쓸 수 없는 조합"))
                continue
            canon, bits, vk = p
            if canon in used:
                failed.append((text, payload, "다른 항목이나 런처가 이미 사용 중"))
                continue
            hid = FIRST_ID + len(self.ids)
            if not ctypes.windll.user32.RegisterHotKey(None, hid, bits | MOD_NOREPEAT, vk):
                failed.append((text, payload, "다른 프로그램이 이미 사용 중"))
                continue
            used.add(canon)
            self.ids[hid] = payload
        return failed

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self.ids:
                self.callback(self.ids[msg.wParam])
                return True, 0
        return False, 0
