# -*- coding: utf-8 -*-
"""本地使用统计：按日期记录活跃/深夜/番茄钟/喝水/聊天等，供每日总结与周报曲线。

数据存 config.json 的 daily_stats: {日期: {active_min, night_min, pomodoro_done,
water_count, tip_count, chat_count}}。纯本地，不外传，仅保留最近 KEEP_DAYS 天。
"""
from datetime import datetime, timedelta

KEEP_DAYS = 60  # 只保留最近 60 天，防止无限增长


def _key(dt=None) -> str:
    return (dt or datetime.now()).strftime("%Y-%m-%d")


def _bucket(cfg, dt=None) -> dict:
    return cfg.setdefault("daily_stats", {}).setdefault(_key(dt), {})


def add(cfg, field: str, n: int = 1, dt=None) -> int:
    """给某天的某个字段累加 n，返回新值。"""
    day = _bucket(cfg, dt)
    day[field] = day.get(field, 0) + n
    return day[field]


def get(cfg, field: str, default=0, dt=None):
    return cfg.setdefault("daily_stats", {}).get(_key(dt), {}).get(field, default)


def prune(cfg):
    """清理过旧的天记录。"""
    ds = cfg.get("daily_stats")
    if not ds:
        return
    keep = {(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(KEEP_DAYS)}
    for k in list(ds):
        if k not in keep:
            del ds[k]


def day_total(cfg, field: str, days: int = 7) -> int:
    """最近 days 天（含今天）某字段累计。"""
    total = 0
    for i in range(days):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        total += cfg.setdefault("daily_stats", {}).get(day, {}).get(field, 0)
    return total


def active_days(cfg) -> int:
    """有活跃记录的天数。"""
    return sum(1 for d in (cfg.get("daily_stats") or {}).values()
               if d.get("active_min", 0) > 0)


def week_key(dt=None) -> str:
    """ISO 周 key，如 '2026-W33'，用于判断是否跨周。"""
    iso = (dt or datetime.now()).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_focus(cfg, dt=None):
    """返回本周 [日期, 活跃分钟] 列表（周一..周日），无数据的天为 0。"""
    dt = dt or datetime.now()
    monday = dt - timedelta(days=dt.weekday())
    out = []
    for i in range(7):
        day = monday + timedelta(days=i)
        d = cfg.setdefault("daily_stats", {}).get(day.strftime("%Y-%m-%d"), {})
        out.append((day.strftime("%Y-%m-%d"), d.get("active_min", 0)))
    return out


def yesterday_text(cfg) -> str:
    """生成"昨天"的一句话总结；无数据返回空串。"""
    y = datetime.now() - timedelta(days=1)
    d = cfg.setdefault("daily_stats", {}).get(y.strftime("%Y-%m-%d"), {})
    if not d:
        return ""
    parts = []
    am = int(d.get("active_min", 0))
    if am >= 60:
        parts.append(f"专注 {am // 60} 小时 {am % 60} 分钟")
    elif am > 0:
        parts.append(f"专注 {am} 分钟")
    if d.get("pomodoro_done"):
        parts.append(f"番茄钟 {d['pomodoro_done']} 个")
    if d.get("water_count"):
        parts.append(f"喝水 {d['water_count']} 次")
    if d.get("chat_count"):
        parts.append(f"聊天 {d['chat_count']} 条")
    # 心情（纯本地记录）
    try:
        from core import mood
        mv = (cfg.get("mood_records") or {}).get(y.strftime("%Y-%m-%d"))
        if mv is not None:
            emoji = mood.MOOD_EMOJI.get(int(mv), "")
            if emoji:
                parts.append(f"心情 {emoji}")
    except (ValueError, TypeError, ImportError):
        pass
    if parts:
        return "📊 昨天：" + " · ".join(parts)
    return ""
