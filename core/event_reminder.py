# -*- coding: utf-8 -*-
"""自定义事件提醒：按"日期 + 时间 + 重复规则"定时触发。

事件存于 config.json 的 events 列表：
    {title, date:"YYYY-MM-DD", time:"HH:MM",
     repeat:"none/daily/weekly/monthly", enabled:True, last_fired:"YYYY-MM-DD HH:MM"}

- 单次事件触发后自动置为完成（enabled=False）
- 周期事件按重复规则（每天/每周/每月）继续触发
- last_fired 记录上次触发分钟，避免同一分钟重复弹提醒
"""
from datetime import datetime

from PySide6.QtCore import QObject, Signal, QTimer

REPEAT_LABELS = {"none": "不重复", "daily": "每天", "weekly": "每周", "monthly": "每月"}


class EventReminder(QObject):
    remind = Signal(str)  # 发射事件标题

    def __init__(self, cfg: dict, save_fn, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._save = save_fn
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(20_000)  # 每 20 秒检查一次

    def _tick(self):
        if not self._cfg.get("reminder_enabled", True):
            return
        now = datetime.now()
        now_key = now.strftime("%Y-%m-%d %H:%M")
        now_time = now.strftime("%H:%M")
        changed = False

        events = self._cfg.get("events", [])
        for ev in events:
            if not ev.get("enabled", True):
                continue
            if ev.get("time") != now_time:
                continue
            if ev.get("last_fired") == now_key:
                continue
            if not self._date_ok(ev, now):
                continue
            # 触发
            ev["last_fired"] = now_key
            if ev.get("repeat", "none") == "none":
                ev["enabled"] = False  # 单次事件完成
            changed = True
            self.remind.emit(ev.get("title", "提醒"))
        if changed:
            self._save(self._cfg)

    @staticmethod
    def _date_ok(ev: dict, now: datetime) -> bool:
        rep = ev.get("repeat", "none")
        try:
            ev_date = datetime.strptime(ev.get("date", ""), "%Y-%m-%d")
        except ValueError:
            return False
        if rep == "daily":
            return True
        if rep == "weekly":
            return ev_date.strftime("%A") == now.strftime("%A")
        if rep == "monthly":
            return ev_date.day == now.day
        return ev_date.strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d")
