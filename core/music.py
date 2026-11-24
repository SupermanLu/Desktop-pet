# -*- coding: utf-8 -*-
"""音乐控制编排：媒体会话 + 歌词拉取 + 状态广播。

MusicController 把 MusicSession（检测/控制）与 netease_lyric（歌词）
粘起来，对 UI 提供一组简单信号：
- track_changed(title, artist)  切歌（UI 报歌名/重置歌词条）
- state_changed(playing)        播放/暂停（宠物听歌形象开关）
- lyrics_ready(lines)           歌词就绪（[{t,text,trans}]，按时间排序）
- lyric_failed(reason)          歌词拉不到（触发手动搜索兜底）
- pos_updated(pos_ms, dur_ms)   进度校准

歌词网络请求在 QThread 单发 worker 里跑（每次切歌触发，绝不进主线程）；
切歌快时旧 worker 结果按曲目比对作废，防止错歌配错词。
"""
from PySide6.QtCore import QObject, QThread, Signal

from core import netease_lyric
from core.music_session import MusicSession


class _LyricWorker(QThread):
    """后台拉歌词：缓存→搜索→拉词→解析。结束发 done 信号。"""

    done = Signal(str, str, object)   # title, artist, lines|None

    def __init__(self, title: str, artist: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._artist = artist

    def run(self):
        try:
            lines = netease_lyric.get_lyrics(self._title, self._artist)
        except Exception:
            lines = None
        self.done.emit(self._title, self._artist, lines)


class MusicController(QObject):
    track_changed = Signal(str, str)
    state_changed = Signal(bool)
    lyrics_ready = Signal(list)
    lyric_failed = Signal(str)        # 失败原因（"无匹配"/"无歌词"/"网络失败"）
    pos_updated = Signal(int, int)
    lost = Signal()                   # 播放会话消失（UI 收起控制栏）

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self.session = MusicSession(cfg, self)
        self.session.track_changed.connect(self._on_track)
        self.session.state_changed.connect(self.state_changed)
        self.session.pos_updated.connect(self.pos_updated)
        self.session.lost.connect(self._on_lost)
        self._worker = None
        self._want_title = ""          # 当前期望歌词所属曲目（作废旧结果）
        self._want_artist = ""
        self._lyric_ok = False

    # ---- 生命周期 ----
    def start(self):
        self.session.start()

    def stop(self):
        self.session.stop()
        if self._worker is not None:
            self._worker.wait(2000)
            self._worker = None

    # ---- 曲目变化 → 拉歌词 ----
    def _on_track(self, title: str, artist: str):
        self._lyric_ok = False
        self._want_title, self._want_artist = title, artist
        self.track_changed.emit(title, artist)
        self._fetch_lyrics(title, artist)

    def _fetch_lyrics(self, title: str, artist: str):
        if self._worker is not None and self._worker.isRunning():
            return   # 旧请求在跑：结果回来时按曲目比对作废即可，不再叠开线程
        self._worker = _LyricWorker(title, artist, self)
        self._worker.done.connect(self._on_lyrics)
        self._worker.start()

    def _on_lyrics(self, title: str, artist: str, lines):
        # 期间又切歌了：丢弃过期结果，立即补拉当前曲目
        # （_fetch_lyrics 在 worker 运行中会跳过请求，这里必须补上，否则漏拉）
        if title != self._want_title or artist != self._want_artist:
            self._fetch_lyrics(self._want_title, self._want_artist)
            return
        if lines:
            self._lyric_ok = True
            self.lyrics_ready.emit(lines)
        else:
            self.lyric_failed.emit("no_lyric")

    def _on_lost(self):
        self._lyric_ok = False
        self.state_changed.emit(False)
        self.lost.emit()

    # ---- 手动兜底：用户输入关键词重新搜歌词 ----
    def search_manual(self, keyword: str):
        kw = (keyword or "").strip()
        if not kw:
            return
        self._want_title, self._want_artist = kw, ""
        # 手动关键词直接走同一套链路（worker 按 title 搜索）
        self._fetch_lyrics(kw, "")

    # ---- 控制 ----
    def play_pause(self):
        self.session.play_pause()

    def next_track(self):
        self.session.next_track()

    def prev_track(self):
        self.session.prev_track()

    @property
    def has_lyrics(self) -> bool:
        return self._lyric_ok
