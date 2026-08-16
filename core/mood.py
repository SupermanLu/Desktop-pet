# -*- coding: utf-8 -*-
"""情绪日记（极简版）：纯本地记录每天心情，不做原因分析、不追问。

心情值：1=😔 难过, 2=😐 一般, 3=😊 开心。
记录存到 config.json 的 mood_records: {日期: 值}。
"""
from datetime import datetime

MOOD_EMOJI = {1: "😔", 2: "😐", 3: "😊"}
MOOD_LABEL = {1: "难过", 2: "一般", 3: "开心"}


def _week_key(d: datetime) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def today_str(dt: datetime | None = None) -> str:
    return (dt or datetime.now()).strftime("%Y-%m-%d")


def has_asked_today(cfg: dict, dt: datetime | None = None) -> bool:
    """今天是否已经问过心情了。"""
    return cfg.get("mood_asked", "") == today_str(dt)


def set_mood(cfg: dict, value: int, dt: datetime | None = None):
    """记录今天的心情，并标记今天已问过。"""
    cfg.setdefault("mood_records", {})[today_str(dt)] = int(value)
    cfg["mood_asked"] = today_str(dt)


def week_records(cfg: dict, dt: datetime | None = None):
    """返回本周（ISO 周）的 [(日期, 心情值)]，按日期升序。"""
    dt = dt or datetime.now()
    wk = _week_key(dt)
    out = []
    for d, v in (cfg.get("mood_records") or {}).items():
        try:
            day = datetime.strptime(d, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        if _week_key(day) == wk:
            out.append((d, int(v)))
    return sorted(out)


def summary_text(records) -> str:
    """根据一组记录生成一句陪伴式总结（不分析原因）。"""
    counts = {1: 0, 2: 0, 3: 0}
    for _d, v in records:
        counts[v] = counts.get(v, 0) + 1
    sad, mid, happy = counts[1], counts[2], counts[3]
    n = len(records)
    if n == 0:
        return ""
    if happy > 0 and happy >= sad and happy >= mid:
        return (f"这周你有 {happy} 天选了😊，心情很不错呀，"
                f"继续保持这种好状态～")
    if sad > 0 and sad >= happy:
        return (f"这周你有 {sad} 天选了😔，周末要不要好好放松一下？"
                f"我陪着你，别太勉强自己 ☕")
    return (f"这周 {n} 天里，开心 {happy} 天、一般 {mid} 天、难过 {sad} 天，"
            f"整体挺平稳的，真棒 👍")
