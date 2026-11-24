# -*- coding: utf-8 -*-
"""音效管理器：程序合成 wav + QSoundEffect 播放 + 音量控制。

所有音效在首次运行时自动合成到 assets/sfx/ 目录，无需外部素材。
"""
import math
import os
import struct
import wave

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect

from core.config import ASSETS_DIR

# ---------- 合成工具 ----------

SAMPLE_RATE = 22050  # 22050Hz 对简单音效足够


def _sine(freq: float, dur: float, amp: float = 0.4) -> list:
    """生成正弦波样本列表。"""
    n = int(SAMPLE_RATE * dur)
    return [int(amp * 32767 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
            for i in range(n)]


def _sweep(f0: float, f1: float, dur: float, amp: float = 0.4) -> list:
    """频率从 f0 线性扫到 f1 的波形。"""
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        f = f0 + (f1 - f0) * i / n
        out.append(int(amp * 32767 * math.sin(2 * math.pi * f * t)))
    return out


def _envelope(samples: list, attack: float = 0.01, decay: float = 0.05):
    """给样本包络：淡入淡出，避免爆音。"""
    n = len(samples)
    a = int(SAMPLE_RATE * attack)
    d = int(SAMPLE_RATE * decay)
    for i in range(min(a, n)):
        samples[i] = int(samples[i] * i / a)
    for i in range(max(0, n - d), n):
        samples[i] = int(samples[i] * (n - 1 - i) / d)
    return samples


def _mix(*args: list) -> list:
    """多个样本列表叠加（截断到 16 位范围）。"""
    max_len = max((len(a) for a in args), default=0)
    out = [0] * max_len
    for a in args:
        for i, v in enumerate(a):
            out[i] += v
    return [max(-32768, min(32767, v)) for v in out]


def _concat(*args: list) -> list:
    """拼接多个样本列表。"""
    out = []
    for a in args:
        out.extend(a)
    return out


def _noise(dur: float, amp: float = 0.15) -> list:
    """白噪声。"""
    import random
    n = int(SAMPLE_RATE * dur)
    return [int(amp * 32767 * (random.random() * 2 - 1)) for _ in range(n)]


def _bell(freq: float, dur: float, amp: float = 0.4, decay: float = 6.0,
          harmonics: tuple = (0.5, 0.24)) -> list:
    """钟琴/八音盒音：基频 + 小节泛音，指数衰减，听起来温暖柔和。

    想更"叮当"就把 harmonics 调大（明亮），更"闷"就把 decay 调大（短促）。
    """
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-decay * t / dur)   # 指数衰减到接近 0
        v = math.sin(2 * math.pi * freq * t) \
            + harmonics[0] * math.sin(2 * math.pi * freq * 2 * t) \
            + harmonics[1] * math.sin(2 * math.pi * freq * 3 * t)
        out.append(int(amp * 32767 * env * v))
    return _envelope(out, 0.006, 0.02)


def _write_wav(path: str, samples: list):
    """将 16-bit mono 样本列表写入 wav 文件。"""
    samples = _envelope(samples)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


# ---------- 音效定义 ----------
# 每个条目：name -> (filename, [sample_generators])
# 用函数延迟生成，避免 import 时执行

def _gen_click(p):
    """轻触，柔和小"啵"声。"""
    _write_wav(p, _bell(1046, 0.07, 0.22, decay=8))

def _gen_wave(p):
    """打招呼：温柔上行的两音钟琴 C5→E5，像"叮～叮"的问候。"""
    _write_wav(p, _concat(
        _bell(523, 0.14, 0.32),
        [0] * int(SAMPLE_RATE * 0.06),
        _bell(659, 0.16, 0.36),
    ))

def _gen_feed(p):
    """喂食：轻快归巢小琶音，柔软不吵。"""
    gap = [0] * int(SAMPLE_RATE * 0.05)
    _write_wav(p, _concat(
        _bell(392, 0.09, 0.28, decay=9),
        gap,
        _bell(440, 0.09, 0.28, decay=9),
        gap,
        _bell(523, 0.16, 0.34, decay=7),
    ))

def _gen_pocket(p):
    """魔法星星：C-E-G-C 上行琶音，八音盒般温暖明亮。"""
    gap = [0] * int(SAMPLE_RATE * 0.05)
    _write_wav(p, _concat(
        _bell(523, 0.12, 0.3, decay=7),
        gap,
        _bell(659, 0.12, 0.3, decay=7),
        gap,
        _bell(784, 0.12, 0.3, decay=7),
        gap,
        _bell(1046, 0.22, 0.38, decay=6),
    ))

def _gen_wake(p):
    """醒来：温柔上行的滑音，轻快朝气。"""
    _write_wav(p, _concat(
        _bell(330, 0.14, 0.28),
        [0] * int(SAMPLE_RATE * 0.04),
        _bell(523, 0.18, 0.32),
    ))

def _gen_sleep(p):
    """睡觉：柔和下行两音，像轻轻道晚安。"""
    _write_wav(p, _concat(
        _bell(523, 0.2, 0.3),
        [0] * int(SAMPLE_RATE * 0.06),
        _bell(392, 0.26, 0.28),
    ))

def _gen_yawn(p):
    """打哈欠：很低很柔的下行拖音，慵懒。"""
    _write_wav(p, _sweep(280, 130, 0.7, 0.22))

def _gen_chat_in(p):
    """来消息：柔和清脆的一声"叮"。"""
    _write_wav(p, _bell(880, 0.16, 0.34, decay=6))

def _gen_chat_out(p):
    """发消息：更轻的一声"提"。"""
    _write_wav(p, _bell(659, 0.1, 0.3, decay=8))

def _gen_reminder(p):
    """提醒：三连温柔"叮咚～叮咚～叮咚"，下行三度，微信门铃的温柔版。"""
    gap = [0] * int(SAMPLE_RATE * 0.1)
    _write_wav(p, _concat(
        _bell(784, 0.16, 0.34, decay=7),
        _bell(659, 0.22, 0.32, decay=7),
        gap,
        _bell(784, 0.16, 0.34, decay=7),
        _bell(659, 0.22, 0.32, decay=7),
        gap,
        _bell(784, 0.16, 0.34, decay=7),
        _bell(659, 0.24, 0.32, decay=7),
    ))

def _gen_achievement(p):
    """完成：明亮欢快的上行琶音 C-E-G-C，有成就感又不突兀。"""
    gap = [0] * int(SAMPLE_RATE * 0.05)
    _write_wav(p, _concat(
        _bell(523, 0.12, 0.3, decay=7),
        gap,
        _bell(659, 0.12, 0.3, decay=7),
        gap,
        _bell(784, 0.12, 0.3, decay=7),
        gap,
        _bell(1046, 0.26, 0.4, decay=5),
        [0] * int(SAMPLE_RATE * 0.05),
        _bell(784, 0.2, 0.28, decay=6),
    ))

def _gen_heart(p):
    """爱心：缓慢柔和的低音"咚"，像贴心的心跳。"""
    _write_wav(p, _bell(262, 0.34, 0.3, decay=5))

def _gen_error(p):
    """出错：柔和的下行"嚸～嘟"，不太刺耳。"""
    _write_wav(p, _concat(
        _bell(440, 0.14, 0.3, decay=7),
        [0] * int(SAMPLE_RATE * 0.04),
        _bell(330, 0.22, 0.28, decay=6),
    ))

def _gen_happy(p):
    """开心：轻快上行 D-F#-A 三连，像雀跃。"""
    gap = [0] * int(SAMPLE_RATE * 0.045)
    _write_wav(p, _concat(
        _bell(587, 0.1, 0.3, decay=8),
        gap,
        _bell(740, 0.1, 0.3, decay=8),
        gap,
        _bell(880, 0.2, 0.34, decay=6),
    ))

def _gen_sad(p):
    """难过：柔和下行 A→F，温度低一些但不刺耳。"""
    _write_wav(p, _concat(
        _bell(440, 0.18, 0.28),
        [0] * int(SAMPLE_RATE * 0.05),
        _bell(349, 0.24, 0.24),
    ))

def _gen_proud(p):
    """得意：上扬的一小段，轻点"叮~滴"。"""
    _write_wav(p, _bell(660, 0.14, 0.32, decay=8))

def _gen_faint(p):
    """晕眩：轻轻高低交替，像飘忽。"""
    gap = [0] * int(SAMPLE_RATE * 0.04)
    _write_wav(p, _concat(
        _bell(392, 0.08, 0.24, decay=9),
        _bell(294, 0.08, 0.24, decay=9),
        gap,
        _bell(392, 0.08, 0.24, decay=9),
        _bell(294, 0.08, 0.24, decay=9),
    ))

def _gen_thinking(p):
    """思考：一声轻柔拉长的"叮～"。"""
    _write_wav(p, _bell(440, 0.28, 0.3, decay=5))

def _gen_notify(p):
    """通知：双音"叮叮"G5→C6，清晰轻快。"""
    _write_wav(p, _concat(
        _bell(784, 0.12, 0.3, decay=8),
        [0] * int(SAMPLE_RATE * 0.05),
        _bell(1046, 0.16, 0.32, decay=7),
    ))

def _gen_app_launch(p):
    """应用启动：两音上行 C5→G5，欢快。"""
    _write_wav(p, _concat(
        _bell(523, 0.11, 0.3, decay=8),
        [0] * int(SAMPLE_RATE * 0.05),
        _bell(784, 0.16, 0.32, decay=7),
    ))

def _gen_pomodoro(p):
    """番茄钟结束：三下柔和高音"叮叮叮"，提醒但不吵。"""
    gap = [0] * int(SAMPLE_RATE * 0.09)
    _write_wav(p, _concat(
        _bell(880, 0.14, 0.3, decay=8),
        gap,
        _bell(988, 0.14, 0.3, decay=8),
        gap,
        _bell(1046, 0.22, 0.34, decay=6),
    ))

def _gen_rps_ready(p):
    """猜拳预备：阶梯三音 C5-D5-E5，期待感。"""
    gap = [0] * int(SAMPLE_RATE * 0.04)
    _write_wav(p, _concat(
        _bell(523, 0.1, 0.28, decay=9),
        gap,
        _bell(587, 0.1, 0.28, decay=9),
        gap,
        _bell(659, 0.1, 0.28, decay=9),
    ))

def _gen_rps_win(p):
    """猜拳胜利：欢快上行 G5-C6-E6。"""
    gap = [0] * int(SAMPLE_RATE * 0.05)
    _write_wav(p, _concat(
        _bell(784, 0.12, 0.3, decay=8),
        gap,
        _bell(1046, 0.12, 0.3, decay=8),
        gap,
        _bell(1318, 0.2, 0.34, decay=6),
    ))

def _gen_rps_lose(p):
    """猜拳输：柔和下行，轻轻鼓励。"""
    _write_wav(p, _concat(
        _bell(440, 0.14, 0.26),
        [0] * int(SAMPLE_RATE * 0.04),
        _bell(330, 0.22, 0.24),
    ))


# 音效注册表：name -> 生成函数
SOUND_DEFS = {
    "click": _gen_click,
    "wave": _gen_wave,
    "feed": _gen_feed,
    "eat": _gen_feed,         # 喂食吃食物复用餐
    "pocket": _gen_pocket,
    "wake": _gen_wake,
    "sleep": _gen_sleep,
    "yawn": _gen_yawn,
    "chat_in": _gen_chat_in,
    "chat_out": _gen_chat_out,
    "reminder": _gen_reminder,
    "achievement": _gen_achievement,
    "heart": _gen_heart,
    "error": _gen_error,
    "happy": _gen_happy,
    "sad": _gen_sad,
    "proud": _gen_proud,
    "faint": _gen_faint,
    "thinking": _gen_thinking,
    "notify": _gen_notify,
    "app_launch": _gen_app_launch,
    "pomodoro": _gen_pomodoro,
    "rps_ready": _gen_rps_ready,
    "rps_win": _gen_rps_win,
    "rps_lose": _gen_rps_lose,
}


# ---------- SoundManager ----------

class SoundManager(QObject):
    """音效管理器：合成 wav 文件 + QSoundEffect 播放 + 音量控制。"""

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._sfx_dir = os.path.join(ASSETS_DIR, "sfx")
        self._effects = {}          # name -> QSoundEffect
        self._enabled = True
        self._volume = 0.8

        # 按当前配置初始化
        self._ensure_sounds()
        self._preload()
        self.apply_config(cfg)

    # ---- 音效文件生成 ----

    def _ensure_sounds(self):
        """首次运行：生成所有 wav 文件到 assets/sfx/。"""
        os.makedirs(self._sfx_dir, exist_ok=True)
        for name, gen in SOUND_DEFS.items():
            path = os.path.join(self._sfx_dir, f"{name}.wav")
            if not os.path.isfile(path):
                try:
                    gen(path)
                except Exception:
                    pass   # 生成失败不阻塞

    # ---- 加载/播放 ----

    def _preload(self):
        """预创建所有 QSoundEffect 实例并加载。"""
        for name in SOUND_DEFS:
            path = os.path.join(self._sfx_dir, f"{name}.wav")
            if not os.path.isfile(path):
                continue
            try:
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(path))
                effect.setVolume(self._volume)
                self._effects[name] = effect
            except Exception:
                pass

    def play(self, name: str):
        """播放指定音效（静音时不播放）。"""
        if not self._enabled:
            return
        effect = self._effects.get(name)
        if effect is not None:
            try:
                effect.play()
            except Exception:
                pass

    def apply_config(self, cfg: dict):
        """从配置同步音效开关和音量。"""
        self._enabled = bool(cfg.get("sfx_enabled", True))
        vol = int(cfg.get("sfx_volume", 80))
        self._volume = max(0.0, min(1.0, vol / 100.0))
        for effect in self._effects.values():
            try:
                effect.setVolume(self._volume)
            except Exception:
                pass

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = bool(value)