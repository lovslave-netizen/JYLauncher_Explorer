"""동영상/음악 파일의 인코딩 정보 (코덱, 비트레이트, 해상도 …) — 탐색기 '열' 용.
pymediainfo(MediaInfo 라이브러리, 약 5MB)로 읽고, 결과는 (경로, 수정시각, 크기) 기준으로 캐시한다.
폴더를 열 때 느려지지 않도록 화면에 보이는 파일만 백그라운드 스레드가 하나씩 읽고, 끝나면 Qt 신호로 알린다.
"""
import os
import threading
from collections import OrderedDict, deque

from PySide6.QtCore import QObject, Signal

try:
    from pymediainfo import MediaInfo
    AVAILABLE = MediaInfo.can_parse()
except Exception:                       # 라이브러리가 없거나 DLL 을 못 불러오면 열만 비워 둠
    MediaInfo = None
    AVAILABLE = False

VIDEO_EXT = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "ts", "mts", "m2ts", "mpg", "mpeg", "3gp", "vob",
             "ogv", "mxf", "divx", "asf", "rm", "rmvb", "f4v"}
AUDIO_EXT = {"mp3", "flac", "wav", "m4a", "aac", "ogg", "opus", "wma", "aiff", "ape", "mka", "ac3", "dts"}
MEDIA_EXT = VIDEO_EXT | AUDIO_EXT

# (키, 열 제목)  — FSModel 의 4번째 열부터 이 순서로 붙는다
COLUMNS = (("duration", "길이"), ("res", "해상도"), ("vcodec", "영상 코덱"), ("vbr", "영상 비트레이트"),
           ("br", "전체 비트레이트"), ("fps", "프레임"), ("acodec", "오디오 코덱"))

CODEC_NAMES = {"AVC": "H.264 (AVC)", "HEVC": "H.265 (HEVC)", "MPEG Video": "MPEG-2", "MPEG-4 Visual": "MPEG-4",
               "VC-1": "VC-1", "AV1": "AV1", "VP9": "VP9", "VP8": "VP8", "ProRes": "ProRes",
               "AAC": "AAC", "MPEG Audio": "MP3", "AC-3": "AC3", "E-AC-3": "E-AC3", "PCM": "PCM", "Opus": "Opus",
               "FLAC": "FLAC", "Vorbis": "Vorbis", "WMA": "WMA"}


def fmt_bitrate(bps):
    try:
        bps = float(bps)
    except (TypeError, ValueError):
        return ""
    if bps <= 0:
        return ""
    return f"{bps / 1e6:.2f} Mbps" if bps >= 1e6 else f"{bps / 1e3:.0f} kbps"


def fmt_duration(ms):
    try:
        s = int(float(ms) / 1000 + 0.5)
    except (TypeError, ValueError):
        return ""
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def summarize(tracks):
    """pymediainfo 트랙 목록 → {열 키: 표시 문자열}"""
    g = next((t for t in tracks if t.track_type == "General"), None)
    v = next((t for t in tracks if t.track_type == "Video"), None)
    a = next((t for t in tracks if t.track_type == "Audio"), None)
    out = {}
    if g is not None:
        out["duration"] = fmt_duration(getattr(g, "duration", None))
        out["br"] = fmt_bitrate(getattr(g, "overall_bit_rate", None))
    if v is not None:
        w, h = getattr(v, "width", None), getattr(v, "height", None)
        out["res"] = f"{w}×{h}" if w and h else ""
        out["vcodec"] = CODEC_NAMES.get(v.format, v.format or "")
        out["vbr"] = fmt_bitrate(getattr(v, "bit_rate", None) or getattr(v, "nominal_bit_rate", None))
        fr = getattr(v, "frame_rate", None)
        try:
            out["fps"] = f"{float(fr):.2f}".rstrip("0").rstrip(".") if fr else ""      # 29.97 / 24 / 60
        except (TypeError, ValueError):
            out["fps"] = ""
    if a is not None:
        out["acodec"] = CODEC_NAMES.get(a.format, a.format or "")
        if v is None:                                   # 음악 파일: 오디오 비트레이트를 '전체'에 표시
            out["br"] = out.get("br") or fmt_bitrate(getattr(a, "bit_rate", None))
    return out


class MediaInfoCache(QObject):
    ready = Signal(str)                 # 경로 — 정보를 읽어 캐시에 넣었음 (GUI 스레드로 전달됨)

    def __init__(self, limit=4000):
        super().__init__()
        self._cache = OrderedDict()     # 경로 → (수정시각, 크기, 정보 dict)
        self._limit = limit
        self._queue = deque()
        self._queued = set()
        self._lock = threading.Lock()
        self._worker = None

    @staticmethod
    def is_media(path):
        return os.path.splitext(path)[1][1:].lower() in MEDIA_EXT

    def get(self, path):
        """캐시된 정보 dict (없으면 None — 읽기 요청을 큐에 넣음)"""
        if not AVAILABLE:
            return {}
        try:
            st = os.stat(path)
        except OSError:
            return {}
        key = (st.st_mtime, st.st_size)
        with self._lock:
            hit = self._cache.get(path)
            if hit and hit[0] == key:
                self._cache.move_to_end(path)
                return hit[1]
            if path not in self._queued:
                self._queued.add(path)
                self._queue.append((path, key))
                if self._worker is None or not self._worker.is_alive():
                    self._worker = threading.Thread(target=self._run, daemon=True)
                    self._worker.start()
        return None

    def _run(self):
        while True:
            with self._lock:
                if not self._queue:
                    return
                path, key = self._queue.pop()      # 가장 최근에 요청된(=지금 보이는) 파일부터
            try:
                info = summarize(MediaInfo.parse(path).tracks)
            except Exception:
                info = {}
            with self._lock:
                self._queued.discard(path)
                self._cache[path] = (key, info)
                while len(self._cache) > self._limit:
                    self._cache.popitem(last=False)
            self.ready.emit(path)

    def clear_pending(self):
        with self._lock:
            self._queue.clear()
            self._queued.clear()
