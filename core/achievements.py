# -*- coding: utf-8 -*-
"""成就/称号系统：根据本地使用统计与心情记录解锁称号，纯本地，不弹窗打扰。

解锁记录存 config.json 的 achievements: {key: "解锁日期"}。
"""
from datetime import datetime

from core import stats
from core import growth


def _max_day(cfg, field, default=0) -> int:
    return max((d.get(field, 0) for d in (cfg.get("daily_stats") or {}).values()),
               default=default)


# 定义顺序即展示顺序
ACHIEVEMENTS = [
    {"key": "first_step",   "name": "初来乍到",  "icon": "🎉",
     "desc": "开始使用桌宠",
     "check": lambda cfg: stats.active_days(cfg) >= 1},
    {"key": "mood_keeper",  "name": "情绪记录员", "icon": "📔",
     "desc": "累计记录 7 天心情",
     "check": lambda cfg: len(cfg.get("mood_records") or {}) >= 7},
    {"key": "focus_beast",  "name": "专注狂魔",   "icon": "🔥",
     "desc": "单日活跃满 4 小时",
     "check": lambda cfg: _max_day(cfg, "active_min") >= 240},
    {"key": "water_king",   "name": "水王",       "icon": "💧",
     "desc": "单日喝水提醒满 5 次",
     "check": lambda cfg: any(d.get("water_count", 0) >= 5
                              for d in (cfg.get("daily_stats") or {}).values())},
    {"key": "tomato_master","name": "番茄达人",   "icon": "🍅",
     "desc": "累计完成 20 个番茄钟",
     "check": lambda cfg: stats.day_total(cfg, "pomodoro_done", 600) >= 20},
    {"key": "persistent",   "name": "坚持不懈",   "icon": "💪",
     "desc": "累计使用满 7 天",
     "check": lambda cfg: stats.active_days(cfg) >= 7},
    {"key": "level_5",      "name": "成长小达人", "icon": "⭐",
     "desc": "等级达到 5 级",
     "check": lambda cfg: growth.calc_level(
         int(cfg.get("growth_total_xp", 0))) >= 5},
    {"key": "streak_7",     "name": "七日伙伴",   "icon": "🔥",
     "desc": "连续陪伴满 7 天",
     "check": lambda cfg: int(cfg.get("growth_streak", 0)) >= 7},
    {"key": "night_watch",  "name": "深夜守望者", "icon": "🌙",
     "desc": "深夜活跃累计 60 分钟",
     "check": lambda cfg: stats.day_total(cfg, "night_min", 600) >= 60},
    {"key": "best_friend",  "name": "桌宠挚友",   "icon": "❤️",
     "desc": "累计使用满 30 天",
     "check": lambda cfg: stats.active_days(cfg) >= 30},
]


def unlocked(cfg) -> dict:
    return cfg.setdefault("achievements", {})


def is_unlocked(cfg, key) -> bool:
    return key in cfg.setdefault("achievements", {})


def check_and_unlock(cfg):
    """检查并解锁新成就，返回本次新解锁的 [achievement, ...]。"""
    done = cfg.setdefault("achievements", {})
    today = datetime.now().strftime("%Y-%m-%d")
    new = []
    for a in ACHIEVEMENTS:
        if a["key"] in done:
            continue
        try:
            if a["check"](cfg):
                done[a["key"]] = today
                new.append(a)
        except Exception:
            pass
    return new


def summary_line(cfg) -> str:
    """已解锁成就的一句话概览（供设置页展示）。"""
    names = [f"{a['icon']}{a['name']}"
             for a in ACHIEVEMENTS if a["key"] in cfg.setdefault("achievements", {})]
    return "、".join(names) if names else "（还没有解锁成就，多陪陪它吧～）"
