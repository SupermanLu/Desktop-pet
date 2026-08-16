# -*- coding: utf-8 -*-
"""成长系统（经验/等级/连续天数）：补全 energy → growth → achievements 的中间链路。

经验值：各种互动行为获得经验，累积升级。
连续天数：连续活跃天数，每日零点自动检测，断签重置。

经验规则（设重上限，防刷屏）：
  - 聊天发消息 +5 XP（每天最多 20 次）
  - 喂食 +10 XP（每次）
  - 完成待办 +10 XP（每天最多 10 次）
  - 番茄钟完成 +15 XP（每次）
  - 使用口袋工具 +3 XP（每天最多 10 次）
  - 猜拳获胜 +10 XP、参与（平/负） +2 XP（每天最多 10 次）
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

# ---- 经验值常量 ----
XP_RULES = {
    "chat":       {"xp": 5,  "daily_cap": 20},
    "feed":       {"xp": 10, "daily_cap": 999},
    "todo":       {"xp": 10, "daily_cap": 10},
    "pomodoro":   {"xp": 15, "daily_cap": 999},
    "tool":       {"xp": 3,  "daily_cap": 10},
    "rps_win":    {"xp": 10, "daily_cap": 10},   # 猜拳获胜
    "rps_play":   {"xp": 2,  "daily_cap": 10},   # 猜拳参与（平/负）
}

# 升级所需经验 = base + level * step（Lv.1→2 需 80，2→3 需 110…）
XP_BASE = 50    # 基础量
XP_STEP = 30    # 每升一级递增量
MAX_LEVEL = 50

# 连续天数检测
STREAK_KEY = "growth_streak_ts"     # 上次活跃日期（YYYY-MM-DD）
STREAK_COUNT_KEY = "growth_streak"  # 当前连续天数


def xp_for_level(level: int) -> int:
    """从 level 升到 level+1 所需经验。"""
    return XP_BASE + level * XP_STEP


def calc_level(total_xp: int) -> int:
    """根据累计经验值计算当前等级。"""
    lv = 1
    while lv < MAX_LEVEL:
        need = xp_for_level(lv)
        if total_xp < need:
            break
        total_xp -= need
        lv += 1
    return lv


def calc_level_progress(total_xp: int) -> tuple:
    """返回 (level, current_xp, need_xp, 0~1 progress)。"""
    lv = 1
    while lv < MAX_LEVEL:
        need = xp_for_level(lv)
        if total_xp < need:
            return (lv, total_xp, need, total_xp / max(need, 1))
        total_xp -= need
        lv += 1
    return (MAX_LEVEL, total_xp, xp_for_level(MAX_LEVEL), 0.0)


def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class GrowthManager(QObject):
    """成长管理器：管理经验/等级/连续天数，发射升级信号。"""

    leveled_up = Signal(int)    # 升级了：新等级
    streaked = Signal(int)      # 连续天数更新了：当前天数

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._total_xp = int(cfg.get("growth_total_xp", 0))
        self._today = today_key()
        # 按天重置计数：上次记录日期不是今天 → 清空
        xp_day = str(cfg.get("growth_xp_day", ""))
        self._xp_today = {}
        if xp_day == self._today:
            raw = cfg.get("growth_xp_today", {})
            if isinstance(raw, dict):
                self._xp_today = raw
        cfg["growth_xp_day"] = self._today
        cfg["growth_xp_today"] = self._xp_today

    # ---- 经验 ----
    def add_xp(self, source: str, n: int = 1) -> int:
        """给指定来源加经验，返回本次实际获得值（受 daily cap 限制）。"""
        rule = XP_RULES.get(source)
        if not rule:
            return 0
        cap = rule["daily_cap"]
        xp = rule["xp"] * n
        if cap < 999:
            used = self._xp_today.get(source, 0)
            if used >= cap:
                return 0
            allowed = cap - used
            if xp > allowed:
                xp = allowed
            self._xp_today[source] = used + xp
        self._total_xp += xp
        self._cfg["growth_total_xp"] = self._total_xp
        # 检查是否升级
        old_lv = calc_level(self._total_xp - xp)
        new_lv = calc_level(self._total_xp)
        if new_lv > old_lv:
            self.leveled_up.emit(new_lv)
        return xp

    def xp(self) -> int:
        return self._total_xp

    def level(self) -> int:
        return calc_level(self._total_xp)

    def progress(self) -> tuple:
        return calc_level_progress(self._total_xp)

    def summary(self) -> str:
        lv, cur, need, _ = calc_level_progress(self._total_xp)
        return f"Lv.{lv} 经验 {cur}/{need}"

    # ---- 连续天数 ----
    def check_streak(self) -> int:
        """检查并更新连续天数（每日一次）。"""
        last = str(self._cfg.get(STREAK_KEY, ""))
        today = today_key()
        if last == today:
            return int(self._cfg.get(STREAK_COUNT_KEY, 0))
        count = int(self._cfg.get(STREAK_COUNT_KEY, 0))
        if not last:
            count = 1
        elif last == _yesterday():
            count += 1
        else:
            count = 1
        self._cfg[STREAK_KEY] = today
        self._cfg[STREAK_COUNT_KEY] = count
        self.streaked.emit(count)
        return count

    def streak(self) -> int:
        return int(self._cfg.get(STREAK_COUNT_KEY, 0))


def _yesterday() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")