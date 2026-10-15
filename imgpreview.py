"""이미지 미리보기: 파일 목록에서 사진을 고르고 Space → 큰 화면으로 보기.
← → = 같은 폴더의 이전/다음 사진, Space·Esc·클릭 = 닫기. 휴대폰 사진의 회전 정보(EXIF)를 반영."""
import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QImageReader, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico", ".jfif"}


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def load_scaled(path, max_w, max_h):
    """화면에 들어가는 크기로 줄여서 읽음 (큰 사진을 통째로 읽지 않아 빠름). (QPixmap 또는 None, 원본 크기)"""
    r = QImageReader(path)
    r.setAutoTransform(True)
    size = r.size()
    if not size.isValid():
        return None, QSize()
    # 회전 정보로 가로/세로가 바뀌는 사진도 있어서, 읽은 뒤 한 번 더 맞춤
    if size.width() > max_w * 2 or size.height() > max_h * 2:
        sc = size.scaled(max_w * 2, max_h * 2, Qt.KeepAspectRatio)
        r.setScaledSize(sc)
    img = r.read()
    if img.isNull():
        return None, size
    return QPixmap.fromImage(img), size


class ImagePreview(QDialog):
    def __init__(self, paths, index, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setObjectName("imgpreview")
        self.paths, self.i = list(paths), index
        scr = (parent.screen() if parent is not None else QGuiApplication.primaryScreen()).availableGeometry()
        self.max_w, self.max_h = int(scr.width() * 0.86), int(scr.height() * 0.80)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        self.img = QLabel()
        self.img.setAlignment(Qt.AlignCenter)
        self.cap = QLabel()
        self.cap.setAlignment(Qt.AlignCenter)
        self.cap.setStyleSheet("color:#c9cdea; font-size:13px;")
        lay.addWidget(self.img, 1)
        lay.addWidget(self.cap)
        self.setStyleSheet("QDialog#imgpreview { background: #0d0f1a; border: 1px solid #3a3f66; border-radius: 10px; }")
        self.show_index(index)

    def show_index(self, i):
        self.i = i % len(self.paths)
        p = self.paths[self.i]
        pm, size = load_scaled(p, self.max_w, self.max_h)
        if pm is None:
            self.img.setPixmap(QPixmap())
            self.img.setText("이미지를 읽을 수 없습니다")
            self.img.setMinimumSize(420, 240)
        else:
            pm = pm.scaled(self.max_w, self.max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation) \
                if pm.width() > self.max_w or pm.height() > self.max_h else pm
            self.img.setText("")
            self.img.setPixmap(pm)
            self.img.setMinimumSize(pm.size())
        try:
            kb = os.path.getsize(p) / 1024
            info = f"{size.width()}×{size.height()}   {kb / 1024:.1f} MB" if kb >= 1024 else \
                   f"{size.width()}×{size.height()}   {kb:.0f} KB"
        except OSError:
            info = ""
        self.cap.setText(f"{os.path.basename(p)}   ({self.i + 1}/{len(self.paths)})   {info}   ← → 이동 · Space/Esc 닫기")
        self.adjustSize()
        self._center()

    def _center(self):
        p = self.parentWidget()
        scr = (p.screen() if p is not None else QGuiApplication.primaryScreen()).availableGeometry()
        self.move(scr.center().x() - self.width() // 2, scr.center().y() - self.height() // 2)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Space, Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        elif k in (Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown):
            self.show_index(self.i + 1)
        elif k in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp):
            self.show_index(self.i - 1)
        elif k == Qt.Key_Home:
            self.show_index(0)
        elif k == Qt.Key_End:
            self.show_index(len(self.paths) - 1)
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        self.accept()
