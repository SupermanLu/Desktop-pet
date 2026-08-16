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
    _write_wav(p, _sine(1000, 0.08))

def _gen_wave(p):
    _write_wav(p, _sweep(500, 700, 0.25))

def _gen_feed(p):
    """快速咀嚼声：4 个短脉冲。"""
    parts = []
    for _ in range(4):
        parts.append(_sine(200 + 100 * (_ % 2), 0.04, 0.3))
        parts.append([0] * int(SAMPLE_RATE * 0.03))
    _write_wav(p, _concat(*parts))

def _gen_pocket(p):
    """魔法星星：4 个上升音阶。"""
    parts = []
    for f in (400, 600, 800, 1000):
        parts.append(_sine(f, 0.1, 0.35))
        parts.append([0] * int(SAMPLE_RATE * 0.04))
    _write_wav(p, _concat(*parts))

def _gen_wake(p):
    _write_wav(p, _sweep(300, 600, 0.3))

def _gen_sleep(p):
    _write_wav(p, _sweep(400, 200, 0.5))

def _gen_yawn(p):
    _write_wav(p, _sweep(300, 150, 0.7))

def _gen_chat_in(p):
    _write_wav(p, _concat(
        _sine(600, 0.08, 0.3),
        [0] * int(SAMPLE_RATE * 0.04),
        _sine(800, 0.08, 0.3),
    ))

def _gen_chat_out(p):
    _write_wav(p, _sine(500, 0.1, 0.3))

def _gen_reminder(p):
    """三连短促提醒音。"""
    parts = []
    for _ in range(3):
        parts.append(_sine(500, 0.06, 0.35))
        parts.append([0] * int(SAMPLE_RATE * 0.05))
    _write_wav(p, _concat(*parts))

def _gen_achievement(p):
    """胜利号角：4 个上升音符。"""
    parts = []
    for f in (300, 500, 700, 900):
        parts.append(_sine(f, 0.15, 0.35))
        parts.append([0] * int(SAMPLE_RATE * 0.04))
    _write_wav(p, _concat(*parts))

def _gen_heart(p):
    _write_wav(p, _sine(400, 0.3, 0.25))

def _gen_error(p):
    _write_wav(p, _sweep(400, 200, 0.3))

def _gen_happy(p):
    _write_wav(p, _sweep(500, 800, 0.3))

def _gen_sad(p):
    _write_wav(p, _sweep(500, 200, 0.4))

def _gen_proud(p):
    _write_wav(p, _sweep(400, 600, 0.3))

def _gen_faint(p):
    """晕眩：交替音。"""
    parts = []
    for _ in range(5):
        parts.append(_sine(200, 0.05, 0.3))
        parts.append(_sine(300, 0.05, 0.3))
    _write_wav(p, _concat(*parts))

def _gen_thinking(p):
    _write_wav(p, _sine(300, 0.2, 0.25))

def _gen_notify(p):
    _write_wav(p, _concat(
        _sine(700, 0.1, 0.3),
        [0] * int(SAMPLE_RATE * 0.03),
        _sine(900, 0.1, 0.3),
    ))

def _gen_app_launch(p):
    _write_wav(p, _sweep(500, 700, 0.2))

def _gen_pomodoro(p):
    """番茄钟：三个短促的高音。"""
    parts = []
    for _ in range(3):
        parts.append(_sine(800, 0.08, 0.35))
        parts.append([0] * int(SAMPLE_RATE * 0.04))
    _write_wav(p, _concat(*parts))

def _gen_rps_ready(p):
    _write_wav(p, _concat(
        _sine(400, 0.08, 0.3),
        _sine(600, 0.08, 0.3),
        _sine(800, 0.08, 0.3),
    ))

def _gen_rps_win(p):
    _write_wav(p, _concat(
        _sine(600, 0.1, 0.3),
        _sine(900, 0.1, 0.3),
        _sine(1200, 0.15, 0.35),
    ))

def _gen_rps_lose(p):
    _write_wav(p, _sweep(400, 200, 0.4))


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