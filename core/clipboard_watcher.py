# -*- coding: utf-8 -*-
"""剪贴板助手：监控用户复制的内容，在本地做类型识别（URL/代码/命令/长文本）。

隐私设计：
- 类型判断完全在本地（正则/启发式），只把"类型"交给上层处理；
- 绝不自动把原文发给 AI，仅在用户点击"解释/摘要"时才会发送；
- 防打扰：每类"会话内首提" + 冷却间隔，避免频繁弹窗；
- 默认可由主程序关闭（默认关闭）。
"""
import re
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

COOLDOWN = 8.0  # 两次主动提示的最小间隔（秒）
TYPE_NAMES = {"url": "链接", "code": "代码", "command": "命令", "text": "长文本",
              "foreign": "外文", "amount": "金额", "unit": "单位"}

_URL_RE = re.compile(r"^https?://\S+$", re.I)
_CODE_HINTS = re.compile(
    r"(def |class |import |from |return |print\(|console\.log|=>|"
    r"function |if |for |while |const |let |var |#[^\n]|\{\}|;)",
    re.I)
_CMD_RE = re.compile(
    r"^(git|npm|pip|python|node|cd|dir|ls|cat|echo|ipconfig|netstat|tasklist|"
    r"whoami|hostname|systeminfo|date|time|ver|path|docker|kubectl|sudo|"
    r"curl|wget|setx|mkdir|rmdir|copy|del|cls|chcp)\b",
    re.I)
# 外文检测：包含英文字母且长度>=5，排除纯数字/符号
_FOREIGN_RE = re.compile(r"[a-zA-Z]{2,}")


def classify(text: str):
    """本地识别剪贴板内容类型，返回 (类型, 原文) 或 None（不处理）。"""
    t = (text or "").strip()
    if not t:
        return None
    if "\n" not in t and len(t) <= 2048 and _URL_RE.match(t):
        return ("url", t)
    if len(t) >= 200 or "\n" in t:
        if _CODE_HINTS.search(t):
            return ("code", t)
        if len(t) >= 200:
            return ("text", t)
    if "\n" not in t and len(t) <= 200 and _CMD_RE.match(t):
        return ("command", t)
    # 金额检测：1-100字符，包含数字和货币符号/代码
    if "\n" not in t and 1 <= len(t) <= 100:
        from core.exchange_rate import parse_amount
        if parse_amount(t):
            return ("amount", t)
        # 单位检测：1-50字符，包含数字和单位
        from core.unit_converter import parse_unit_value
        if parse_unit_value(t):
            return ("unit", t)
    # 外文检测：5-500字符，包含连续英文字母，排除代码/命令
    if 5 <= len(t) <= 500 and "\n" not in t and _FOREIGN_RE.search(t):
        return ("foreign", t)
    return None


class ClipboardWatcher(QObject):
    detected = Signal(dict)  # {type, content, auto}  auto=True 表示"总是允许"自动处理

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clip = QGuiApplication.clipboard()
        self._prefs = {}          # type -> "always"
        self._suppress = False    # 桌宠自己写剪贴板时置位，忽略下一次变化
        self._last_prompt = 0.0
        self._prompted = set()    # 本会话已提示过的类型
        self._clip.dataChanged.connect(self._on_change)

    def set_prefs(self, prefs: dict):
        self._prefs = {k: v for k, v in (prefs or {}).items()}

    def suppress_next(self):
        self._suppress = True

    def mark_prompted(self, ctype: str):
        self._prompted.add(ctype)

    def _on_change(self):
        if self._suppress:
            self._suppress = False
            return
        cls = classify(self._clip.text())
        if cls is None:
            return
        ctype, content = cls
        if self._prefs.get(ctype) == "always":
            self.detected.emit({"type": ctype, "content": content, "auto": True})
            return
        now = time.time()
        if now - self._last_prompt < COOLDOWN:
            return
        # 只有用户点击"忽略"后才不再提示该类型
        if ctype in self._prompted:
            return
        self._last_prompt = now
        # 不自动添加到 _prompted，让每次复制都提示
        self.detected.emit({"type": ctype, "content": content, "auto": False})
