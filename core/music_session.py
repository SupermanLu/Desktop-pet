# -*- coding: utf-8 -*-
"""媒体会话检测（Windows SMTC）+ 媒体键控制 + 播放进度外推。

- 检测：winsdk 读系统媒体会话（网易云/其他播放器都会向系统报告曲目）。
  全部 WinRT 调用收在独立 QThread 内（跨线程 WinRT 有套间风险，集中一处
  最稳），轮询结果用 Qt 信号发回主线程。
- 备用通道：网易云 3.x 不发布 SMTC 会话（实测 get_sessions() 为空），
  但它把"歌名 - 歌手"写在主窗口标题（类名 OrpheusBrowserHost）里，
  且 WASAPI 音频会话峰值表实时反映是否出声——SMTC 检不到时用这两个
  旁路信号拼出曲目/播放状态/进度。
- 会话选择：优先网易云（cloudmusic/Orpheus），其次系统"当前会话"，
  兼容其他播放器。
- 控制：SendInput 模拟媒体键（VK_MEDIA_*），网易云响应系统媒体键，
  无需任何私有接口。
- 进度：SMTC 1s 校准 + 主线程毫秒级外推（estimate_pos），供歌词同步；
  备用通道按"播放中累计时长"估算。
- 降级：winsdk 缺失/会话丢失 → 发 lost() 信号；媒体键控制不受影响。
"""
import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, QThread, QTimer, Signal

try:
    import asyncio
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _SMTC)
    _HAS_SMTC = True
except Exception:          # winsdk 未装 / WinRT 不可用
    _HAS_SMTC = False

# 音频峰值表（comtypes + pycaw，用于备用通道判断"是否在出声"）
try:
    import comtypes
    from comtypes import GUID, COMMETHOD

    class _IAudioMeterInformation(comtypes.IUnknown):
        _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
        _methods_ = [
            COMMETHOD([], ctypes.HRESULT, "GetPeakValue",
                      (["out"], ctypes.POINTER(ctypes.c_float), "pfPeak")),
            COMMETHOD([], ctypes.HRESULT, "GetMeteringChannelCount",
                      (["out"], ctypes.POINTER(ctypes.c_uint), "pnCount")),
            COMMETHOD([], ctypes.HRESULT, "GetChannelsPeakValues",
                      (["in"], ctypes.c_uint, "u32ChannelCount"),
                      (["out"], ctypes.POINTER(ctypes.c_float), "afPeakValues")),
            COMMETHOD([], ctypes.HRESULT, "QueryHardwareSupport",
                      (["out"], ctypes.POINTER(ctypes.c_uint), "pdwMask")),
        ]
    _HAS_METER = True
except Exception:
    _HAS_METER = False

# 网易云进程标识（会话 SourceAppUserModelId 特征串，小写匹配）
_NETEASE_TAGS = ("cloudmusic", "orpheus")

# 浏览器会话特征：网页媒体（如浏览器里放歌）也会报会话，但优先级最低
# （标题可能是网页标题），只在没有其他播放器时兜底选用
# 注意：Edge 的 AUMID 形如 Microsoft.MicrosoftEdge_.../"microsoftedge"，
# 不含 "msedge" 子串，必须单独列出（不能只写裸 "edge"：knowledge 也含 edge）
_BROWSER_TAGS = ("msedge", "microsoftedge", "chrome", "firefox",
                 "browser", "iexplore")

# 音乐播放器白名单：只有这些桌面播放器才认（用户只把音乐功能用于听歌）。
# 网易云单独最高优先；其余音乐播放器次之；不在名单里的一律不当音乐。
_MUSIC_PLAYER_TAGS = (
    "cloudmusic", "orpheus", "netease",      # 网易云
    "qqmusic", "kugou", "kuwo", "migu",      # QQ音乐/酷狗/酷我/咪咕
    "spotify", "foobar", "aimp", "musicbee", "itunes",
    "qianqian", "zunemusic", "groovemusic",
)

# 视频客户端特征：视频 App（B站/抖音/爱奇艺…）的媒体会话永远不算音乐
_VIDEO_APP_TAGS = (
    "bilibili", "douyin", "kuaishou", "iqiyi", "youku", "tenvideo",
    "qqlive", "mgtv", "sohu", "pptv", "miguvideo", "bilibilitv",
)

# 网页视频站点特征：浏览器会话标题命中 → 视为视频而非音乐，不触发歌词/控制栏
# （B 站/视频网站的媒体会话也会报"正在播放"，但不是听歌场景）
_VIDEO_TITLE_TAGS = (
    "bilibili", "哔哩哔哩", "youtube", "腾讯视频", "爱奇艺", "iqiyi",
    "优酷", "youku", "抖音", "douyin", "西瓜视频", "netflix", "芒果tv",
    "mgtv", "腾讯课堂", "网易公开课", "直播", "livestream", "twitch",
    "vimeo", "搜狐视频", "乐视", "pptv", "咪咕视频", "课程", "网课",
)


def _looks_like_video(title: str) -> bool:
    """浏览器会话标题是否像网页视频（视频站点名/直播/课程）。"""
    t = (title or "").lower()
    return any(tag in t for tag in _VIDEO_TITLE_TAGS)

# 播放状态枚举（GlobalSystemMediaTransportControlsSessionPlaybackStatus）
_ST_CLOSED, _ST_OPENED, _ST_CHANGING, _ST_STOPPED, _ST_PLAYING, _ST_PAUSED = \
    0, 1, 2, 3, 4, 5


# ---------- 媒体键模拟（SendInput） ----------
# 虚拟键码：PLAY/PAUSE=0xB3 PREV=0xB1 NEXT=0xB0 STOP=0xB2
_VK_MEDIA = {"play_pause": 0xB3, "prev": 0xB1, "next": 0xB0, "stop": 0xB2}

# 注意：x64 下 Windows 要求 sizeof(INPUT) == 40（union 按 MOUSEINPUT 对齐），
# 少了 MOUSEINPUT 撑尺寸时 SendInput 会被系统以参数错误静默拒绝（返回 0）。


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("_pad", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("_pad", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


def send_media_key(action: str) -> bool:
    """发送一个媒体键（按下+抬起）。action: play_pause/prev/next/stop。"""
    vk = _VK_MEDIA.get(action)
    if vk is None:
        return False
    try:
        user32 = ctypes.windll.user32
        inputs = (_INPUT * 2)()
        inputs[0].type = 1                       # INPUT_KEYBOARD
        inputs[0].union.ki.wVk = vk
        inputs[1].type = 1
        inputs[1].union.ki.wVk = vk
        inputs[1].union.ki.dwFlags = 0x0002     # KEYEVENTF_KEYUP
        n = user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(_INPUT))
        return n == 2
    except Exception:
        return False


# ---------- 网易云备用检测（SMTC 缺席时） ----------
# 网易云 3.x 不发布 SMTC 会话，但两个旁路信号可靠：
#   1) 主窗口（类名 OrpheusBrowserHost）标题实时等于"歌名 - 歌手"
#   2) WASAPI 音频会话峰值表 GetPeakValue：出声 >0，暂停立即归 0

_NE_IDLE_TITLES = ("", "网易云音乐", "netease cloud music", "cloudmusic")


def _netease_window_title() -> str:
    """取网易云主窗口标题；没有则返回空串。"""
    u32 = ctypes.windll.user32
    found = []
    cls_buf = ctypes.create_unicode_buffer(64)
    txt_buf = ctypes.create_unicode_buffer(512)
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                         wintypes.LPARAM)

    def cb(hwnd, _l):
        u32.GetClassNameW(hwnd, cls_buf, 64)
        if cls_buf.value == "OrpheusBrowserHost":
            u32.GetWindowTextW(hwnd, txt_buf, 512)
            found.append(txt_buf.value)
        return True

    u32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0].strip() if found else ""


def _parse_netease_title(raw: str) -> tuple:
    """'歌名 - 歌手' → (歌名, 歌手)；空闲标题返回 ('', '')。"""
    t = (raw or "").strip()
    for suf in (" - 网易云音乐", " - 网易云"):
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
    if not t or t.lower() in _NE_IDLE_TITLES:
        return "", ""
    if " - " in t:
        name, artist = t.split(" - ", 1)
        return name.strip(), artist.strip()
    return t, ""


class _NeteaseMeter:
    """网易云音频会话峰值表：>0 = 正在出声（暂停立即归零）。"""

    def __init__(self):
        self._meter = None
        self._last_find = 0.0
        self._last_peak_ts = 0.0    # 最近一次峰值>0 的时刻（静音段黏滞用）

    def playing(self) -> bool:
        peak = self._peak()
        now = time.monotonic()
        if peak > 0.005:
            self._last_peak_ts = now
            return True
        # 弱音段（前奏渐强/间奏静默）黏滞 8 秒，防止进度冻结导致歌词
        # 忽快忽慢；真暂停时峰值瞬时归零（实测），8 秒后歌词跟停
        return (now - self._last_peak_ts) < 8.0

    def _peak(self) -> float:
        if self._meter is None:
            now = time.monotonic()
            if now - self._last_find < 5.0:
                return 0.0            # 找不到就 5 秒重试一次
            self._last_find = now
            self._meter = self._find_meter()
        if self._meter is None:
            return 0.0
        try:
            return float(self._meter.GetPeakValue())
        except Exception:
            self._meter = None        # 会话失效 → 立即重建（别等 5s）
            self._last_find = 0.0
            return 0.0

    @staticmethod
    def _find_meter():
        if not _HAS_METER:
            return None
        try:
            comtypes.CoInitialize()
            from pycaw.pycaw import AudioUtilities
        except Exception:
            return None
        try:
            for s in AudioUtilities.GetAllSessions():
                try:
                    proc = s.Process
                    if proc and "cloudmusic" in (proc.name() or "").lower():
                        ctl = getattr(s, "_ctl", None)
                        if ctl is not None:
                            return ctl.QueryInterface(_IAudioMeterInformation)
                except Exception:
                    continue
        except Exception:
            pass
        return None


class _NeteaseFallback:
    """网易云备用检测：标题(曲目) + 峰值(播放中) + 播放累计(进度)。"""

    def __init__(self):
        self._meter = _NeteaseMeter()
        self._title = ""
        self._artist = ""
        self._acc = 0.0               # 播放累计毫秒
        self._last = time.monotonic()

    def probe(self):
        """返回 (title, artist, playing, pos_ms, dur_ms)；无曲目返回 None。"""
        name, artist = _parse_netease_title(_netease_window_title())
        now = time.monotonic()
        if not name:
            self._title = self._artist = ""
            self._acc = 0.0
            self._last = now
            return None
        if name != self._title or artist != self._artist:
            self._acc = 0.0           # 切歌 → 进度清零
        playing = self._meter.playing()
        if playing:
            self._acc += (now - self._last) * 1000.0
        self._last = now
        self._title, self._artist = name, artist
        return (name, artist, playing, int(self._acc), 0)


# ---------- SMTC 轮询线程 ----------

class _SmtcThread(QThread):
    """独立线程内 asyncio 轮询媒体会话，结果用信号发回主线程。"""

    got_session = Signal(str, str, bool, int, int)  # title, artist, playing, pos_ms, dur_ms
    lost = Signal()
    ready = Signal(bool)                            # SMTC 可用性

    def __init__(self, parent=None, cfg=None):
        super().__init__(parent)
        self._running = True
        self._cfg = cfg or {}

    def stop(self):
        self._running = False

    def run(self):
        self.ready.emit(_HAS_SMTC)
        try:
            asyncio.run(self._poll_loop())
        except Exception:
            self.lost.emit()

    async def _poll_loop(self):
        mgr = None
        if _HAS_SMTC:
            try:
                mgr = await _SMTC.request_async()
            except Exception:
                mgr = None
        had_session = False
        fallback = _NeteaseFallback()
        while self._running:
            try:
                allow_browser = bool(
                    self._cfg.get("browser_session_enabled", False))
                session = self._pick_session(mgr, allow_browser)
                fb = fallback.probe()
                # 通道优先级：网易云正在播放（备用）> SMTC 会话 >
                #             网易云暂停有曲目（备用）> 丢失
                use_fb = fb is not None and (fb[2] or session is None)
                if use_fb:
                    self.got_session.emit(*fb)
                    had_session = True
                elif session is not None:
                    info = await session.try_get_media_properties_async()
                    title = (info.title or "").strip()
                    artist = (info.artist or "").strip()
                    if not title:
                        await asyncio.sleep(2.0)
                        continue
                    # 浏览器里放网页视频（B 站/课程/直播等）不算音乐：
                    # 标题像视频站点就跳过，避免弹歌词/控制栏干扰
                    if self._is_browser(session) and _looks_like_video(title):
                        if had_session:
                            self.lost.emit()
                            had_session = False
                        await asyncio.sleep(2.0)
                        continue
                    pb = session.get_playback_info()
                    playing = pb.playback_status == _ST_PLAYING
                    tl = session.get_timeline_properties()
                    pos_ms = int(tl.position.total_seconds() * 1000)
                    dur_ms = int(tl.end_time.total_seconds() * 1000)
                    self.got_session.emit(title, artist, playing,
                                          pos_ms, dur_ms)
                    had_session = True
                else:
                    if had_session:
                        self.lost.emit()
                        had_session = False
                    await asyncio.sleep(3.0)     # 完全无源：降频
                    continue
            except Exception:
                if had_session:
                    self.lost.emit()
                    had_session = False
            await asyncio.sleep(1.0)

    @staticmethod
    def _app_id(s) -> str:
        try:
            return (s.source_app_user_model_id or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _is_browser(s) -> bool:
        app_id = _SmtcThread._app_id(s)
        return any(tag in app_id for tag in _BROWSER_TAGS)

    @staticmethod
    def _is_video_app(s) -> bool:
        """视频客户端（B站/抖音/爱奇艺等）：永远不算音乐。"""
        app_id = _SmtcThread._app_id(s)
        return any(tag in app_id for tag in _VIDEO_APP_TAGS)

    @staticmethod
    def _is_music_player(s) -> bool:
        """音乐播放器白名单（网易云/QQ音乐/酷狗/Spotify…）。"""
        app_id = _SmtcThread._app_id(s)
        return any(tag in app_id for tag in _MUSIC_PLAYER_TAGS)

    @staticmethod
    def _pick_session(mgr, allow_browser: bool = False):
        """选会话（只认音乐来源）：
        1) 网易云
        2) 其他音乐播放器白名单（QQ音乐/酷狗/Spotify…）
        3) 视频客户端（B站/抖音…）永远不选
        4) 浏览器/未知来源：默认不选；仅设置开启识别浏览器时兜底
        """
        if mgr is None:
            return None
        try:
            sessions = list(mgr.get_sessions())
        except Exception:
            sessions = []
        try:
            cur = mgr.get_current_session()
        except Exception:
            cur = None

        # 1) 网易云会话（无论播放/暂停）
        for s in sessions:
            if any(tag in _SmtcThread._app_id(s) for tag in _NETEASE_TAGS):
                return s
        # 2) 其他音乐播放器（当前会话优先）
        if cur is not None and _SmtcThread._is_music_player(cur):
            return cur
        for s in sessions:
            if _SmtcThread._is_music_player(s):
                return s
        # 3) 浏览器/未知来源：仅在设置开启时兜底；视频客户端始终拒绝
        if not allow_browser:
            return None
        if cur is not None and not _SmtcThread._is_video_app(cur):
            return cur
        for s in sessions:
            if not _SmtcThread._is_video_app(s):
                return s
        return None


# ---------- 对外封装 ----------

class MusicSession(QObject):
    """播放状态检测 + 媒体键控制（主线程使用）。"""

    track_changed = Signal(str, str)      # title, artist（曲目变化时发）
    state_changed = Signal(bool)          # 播放/暂停
    pos_updated = Signal(int, int)        # pos_ms, dur_ms（每次轮询）
    lost = Signal()                       # 会话消失（播放器关闭/停止）
    smtc_ready = Signal(bool)             # winsdk 可用性

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self._thread = None
        self._cfg = cfg or {}
        self._title = ""
        self._artist = ""
        self._playing = False
        # 进度外推基准：上次校准的位置/时刻
        self._base_pos = 0
        self._base_ts = 0.0
        self._dur_ms = 0
        # 1s 校准兜底：若线程信号停摆（异常），主线程不再盲推
        self._last_seen = 0.0

    # ---- 生命周期 ----
    def start(self):
        if self._thread is not None:
            return
        self._thread = _SmtcThread(self, self._cfg)
        self._thread.got_session.connect(self._on_session)
        self._thread.lost.connect(self._on_lost)
        self._thread.ready.connect(self.smtc_ready)
        self._thread.start()

    def stop(self):
        if self._thread is not None:
            self._thread.stop()
            self._thread.wait(3000)
            self._thread = None

    # ---- 轮询结果（来自工作线程信号，已在主线程执行） ----
    def _on_session(self, title: str, artist: str, playing: bool,
                    pos_ms: int, dur_ms: int):
        self._last_seen = time.monotonic()
        self._base_pos = pos_ms
        self._base_ts = time.monotonic()
        self._dur_ms = dur_ms
        if title != self._title or artist != self._artist:
            self._title, self._artist = title, artist
            self.track_changed.emit(title, artist)
        if playing != self._playing:
            self._playing = playing
            self.state_changed.emit(playing)
        self.pos_updated.emit(pos_ms, dur_ms)

    def _on_lost(self):
        self._title = ""
        self._artist = ""
        if self._playing:
            self._playing = False
            self.state_changed.emit(False)
        self.lost.emit()

    # ---- 进度外推（毫秒级，供歌词同步） ----
    def estimate_pos(self) -> int:
        """当前位置估计：校准点 + 经过时间×播放状态；暂停冻结。"""
        if self._last_seen <= 0:
            return 0
        if not self._playing:
            return self._base_pos
        elapsed = (time.monotonic() - self._base_ts) * 1000
        return int(self._base_pos + elapsed)

    def snap_pos(self, pos_ms: int):
        """收到外部校准（如系统时间跳变）时重设基准。"""
        self._base_pos = pos_ms
        self._base_ts = time.monotonic()

    # ---- 信息查询 ----
    @property
    def track(self) -> tuple[str, str]:
        return self._title, self._artist

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def duration_ms(self) -> int:
        return self._dur_ms

    @property
    def available(self) -> bool:
        return _HAS_SMTC

    # ---- 控制 ----
    @staticmethod
    def play_pause():
        send_media_key("play_pause")

    @staticmethod
    def next_track():
        send_media_key("next")

    @staticmethod
    def prev_track():
        send_media_key("prev")
