"""북마크(JY Explorer) ↔ Windows 탐색기 즐겨찾기(빠른 실행에 고정) 동기화 — 계산 부분 (화면/스레드와 무관, 테스트 가능).

규칙
  - 일반 폴더 북마크만 대상. 세트 북마크(폴더 2개)와 북마크 폴더(묶음)는 Windows 에 없는 개념이라 제외.
    Windows 로 보낼 때는 폴더 구조와 상관없이 북마크 하나하나가 고정되고(A폴더 안의 B, C → Windows 에는 B, C),
    Windows 에서 가져올 때는 폴더 없이 맨 위 단계로 들어옴 (정리는 사용자가 끌어서).
  - 기본 폴더(바탕화면/다운로드/문서/사진)는 빠른 이동에 이미 있으므로 제외.
  - '마지막으로 맞춘 목록(snapshot)'과 비교하는 3방향 비교로 추가/삭제를 구분:
        Windows 에 새로 생김 → 북마크 추가        Windows 에서 사라짐 → 북마크 삭제
        북마크에 새로 생김   → Windows 에 고정    북마크에서 사라짐   → Windows 고정 해제
    snapshot 이 없으면(처음 켤 때) 양쪽을 합치기만 하고 아무것도 지우지 않음.
  - 안전장치: 한 번에 너무 많이 지우게 되면(읽기 오류로 목록이 비어 보이는 경우 등) 삭제는 건너뜀.
"""
import os


def norm(p):
    """비교용 정규화 (대소문자/슬래시/끝 구분자 무시)"""
    k = os.path.normcase(os.path.normpath(p))
    return k if len(k) <= 3 else k.rstrip("\\")


def plan(win, jy, snapshot, excluded=()):
    """win/jy: {정규화경로: 원래경로},  snapshot: set(정규화경로) 또는 None,  excluded: 정규화경로 집합.
    돌려주는 값: {'to_jy': [원래경로], 'rm_jy': [...], 'to_win': [...], 'rm_win': [...], 'first': bool, 'skipped_rm': bool}"""
    ex = set(excluded)
    W = {k: v for k, v in win.items() if k not in ex}
    J = {k: v for k, v in jy.items() if k not in ex}
    if snapshot is None:                            # 처음: 합치기만
        return {"to_jy": [W[k] for k in W if k not in J], "rm_jy": [], "to_win": [J[k] for k in J if k not in W],
                "rm_win": [], "first": True, "skipped_rm": False}
    S = set(snapshot) - ex
    to_jy = [k for k in W if k not in S and k not in J]
    rm_jy = [k for k in S if k not in W and k in J]
    to_win = [k for k in J if k not in S and k not in W]
    rm_win = [k for k in S if k not in J and k in W]
    skipped = False
    if too_many(len(rm_jy), len(S)) or too_many(len(rm_win), len(S)):
        rm_jy, rm_win, skipped = [], [], True         # 목록을 잘못 읽었을 가능성 → 삭제는 하지 않음
    return {"to_jy": [W[k] for k in to_jy], "rm_jy": [J[k] for k in rm_jy],
            "to_win": [J[k] for k in to_win], "rm_win": [W[k] for k in rm_win], "first": False, "skipped_rm": skipped}


def too_many(n_remove, n_base):
    """한 번에 5개를 넘고 기준의 절반을 넘게 지우게 되면 의심스러움"""
    return n_remove > 5 and n_remove * 2 > n_base


def new_snapshot(win_keys, jy_keys, excluded=()):
    """동기화 후 양쪽에 모두 있는 항목 = 다음 비교의 기준 (실패해서 한쪽에만 있는 항목은 빠져서 다음에 다시 시도됨)"""
    return (set(win_keys) & set(jy_keys)) - set(excluded)
