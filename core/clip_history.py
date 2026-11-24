# -*- coding: utf-8 -*-
"""剪贴板历史：本地保存最近复制的文本（默认 300 条），可搜索/重新复制。

设计：
- 纯本地 JSON（PROJECT_DIR/clip_history.json），不联网、不上传；
- 只保存纯文本；单条超长截断；与最新一条相同不重复记（历史里已有则挪到最前）；
- 设置里可随时关闭（关闭后停止记录，已有历史保留）；
- 落盘防抖 1.5s，避免频繁复制时反复写盘。
"""
import json
import os
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from core.config import PROJECT_DIR

HISTORY_PATH = os.path.join(PROJECT_DIR, "clip_history.json")
MAX_ITEM_CHARS = 5000      # 单条最长保存字符（超出截断）
SAVE_DEBOUNCE_MS = 1500    # 落盘防抖


def item_kind(text: str) -> str:
    """列表图标用粗分类：url（链接）/ text（多行）/ plain（普通文字）。"""
    t = (text or "").strip()
    if "\n" in t:
        return "text"
    if t.lower().startswith(("http://", "https://")):
        return "url"
    return "plain"


class ClipHistory(QObject):
    """剪贴板历史记录：监听系统剪贴板 → 去重入栈 → 持久化。"""

    changed = Signal()          # 记录增删（UI 刷新）

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._items: list[dict] = []   # 最新在前 [{text, ts}]
        self._suppress = False         # 自己写剪贴板时置位（别记成新记录）
        self._clip = QGuiApplication.clipboard()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save)
        self._load()
        self._clip.dataChanged.connect(self._on_change)

    # ---- 配置 ----
    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("clip_history_enabled", True))

    @property
    def limit(self) -> int:
        try:
            return max(20, min(1000, int(self._cfg.get("clip_history_limit", 300))))
        except Exception:
            return 300

    # ---- 记录 ----
    def _on_change(self):
        if self._suppress:
            self._suppress = False
            return
        if not self.enabled:
            return
        try:
            text = self._clip.text() or ""
        except Exception:
            return
        self.add(text)

    def add(self, text: str):
        t = (text or "").strip()
        if not t:
            return
        if len(t) > MAX_ITEM_CHARS:
            t = t[:MAX_ITEM_CHARS] + " …"
        if self._items and self._items[0]["text"] == t:
            return                        # 与最新一条相同：不重复记
        for i, it in enumerate(self._items):
            if it["text"] == t:           # 历史里已有：旧位置删除（挪到最前）
                del self._items[i]
                break
        self._items.insert(0, {"text": t, "ts": time.time()})
        del self._items[self.limit:]
        self._save_timer.start(SAVE_DEBOUNCE_MS)
        self.changed.emit()

    def items(self) -> list[dict]:
        return list(self._items)

    def count(self) -> int:
        return len(self._items)

    def copy_text(self, text: str):
        """重新复制到系统剪贴板（不记为新记录）。"""
        self._suppress = True
        self._clip.setText(text)
        # 兜底：内容与剪贴板相同时不会触发 dataChanged，标志不能一直挂着
        QTimer.singleShot(400, self._clear_suppress)

    def _clear_suppress(self):
        self._suppress = False

    def remove(self, text: str):
        for i, it in enumerate(self._items):
            if it["text"] == text:
                del self._items[i]
                break
        self._save_timer.start(0)
        self.changed.emit()

    def clear(self):
        if not self._items:
            return
        self._items.clear()
        self._save_timer.start(0)
        self.changed.emit()

    def flush(self):
        """立即落盘（退出前调用，别丢最后几条）。"""
        if self._save_timer.isActive():
            self._save_timer.stop()
        self._save()

    # ---- 持久化 ----
    def _load(self):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("items") if isinstance(data, dict) else data
            out = []
            for it in (raw or []):
                if isinstance(it, dict) and it.get("text"):
                    out.append({"text": str(it["text"]),
                                "ts": float(it.get("ts") or 0)})
            self._items = out[:self.limit]
        except Exception:
            self._items = []

    def _save(self):
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump({"items": self._items}, f, ensure_ascii=False)
        except Exception:
            pass
