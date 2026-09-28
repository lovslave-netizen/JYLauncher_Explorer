"""JYLauncher_Ico.png / JYExplorer_Ico.png (가로형 원본) → 정사각형으로 잘라 둥근 모서리 .ico 생성.
아이콘 원본을 바꿨을 때만 다시 실행:  python make_icons.py   (Pillow 필요)"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]

# 원본에서 엠블럼 주변 정사각형 영역 (left, top, right, bottom) — 오른쪽 아래 반짝이 로고는 제외
CROPS = {
    "JYLauncher": (357, 24, 1077, 744),
    "JYExplorer": (385, 45, 1025, 685),
}


def make(name, box):
    src = Image.open(HERE / f"{name}_Ico.png").convert("RGBA").crop(box).resize((512, 512), Image.LANCZOS)
    mask = Image.new("L", (512, 512), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 511, 511), radius=96, fill=255)
    src.putalpha(mask)
    src.save(HERE / f"{name}.ico", sizes=SIZES)
    print("saved", f"{name}.ico")


if __name__ == "__main__":
    for n, b in CROPS.items():
        make(n, b)
