# -*- coding: utf-8 -*-
"""剪贴板历史窗口：卡片式列表，搜索 / 双击复制 / 右键删除 / 一键清空。

交互（贴手机习惯）：
- 双击一条记录 → 复制回剪贴板（底部提示"已复制"）
- 顶部搜索框实时过滤（按内容包含匹配）
- 右键单条 → 复制 / 删除；底部"清空"需二次确认
"""
import time
from datetime import datetime

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QListWidget,
                               QListWidgetItem, QFrame, QMenu, QMessageBox)

from core.clip_history import item_kind
from ui.theme import card_ss

_CARD_SS = card_ss()

_KIND_ICON = {"url": "🔗", "text": "📄", "plain": "📝"}


def _preview(text: str, limit: int = 80) -> str:
    """单行预览：换行压成 ⏎ 记号，压缩空白，超长截断。"""
    s = " ⏎ ".join(ln.strip() for ln in text.splitlines() if ln.strip())
    s = " ".join(s.split())
    return s if len(s) <= limit else s[:limit] + "…"


def _fmt_ts(ts: float) -> str:
    """时间显示：今天只看时分，跨天带月日。"""
    try:
        dt = datetime.fromtimestamp(ts)
    except Exception:
        return ""
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%m-%d %H:%M")


class ClipHistoryWindow(QWidget):
    """剪贴板历史（卡片窗，随桌宠位置弹出）。"""

    def __init__(self, hist, parent=None):
        super().__init__(parent)
        self._hist = hist
        self._drag_pos = None
        self._hint_ts = 0.0

        self.setWindowTitle("剪贴板历史")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(360, 430)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(_CARD_SS)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 6, 10, 10)
        lay.setSpacing(6)

        # ---- 标题栏（可拖动） ----
        self._bar = QWidget(card)
        self._bar.setFixedHeight(24)
        bar_lay = QHBoxLayout(self._bar)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("📋 剪贴板历史")
        title.setObjectName("ttl")
        self._count = QLabel("")
        self._count.setObjectName("hint")
        btn_close = QPushButton("✕")
        btn_close.setObjectName("close")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setToolTip("关闭")
        btn_close.clicked.connect(self.hide)
        bar_lay.addWidget(title)
        bar_lay.addWidget(self._count)
        bar_lay.addStretch(1)
        bar_lay.addWidget(btn_close)
        lay.addWidget(self._bar)

        # ---- 搜索 ----
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索记录…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh)
        lay.addWidget(self._search)

        # ---- 列表 ----
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setWordWrap(True)
        self._list.setStyleSheet(
            "QListWidget::item { padding: 5px 6px; }"
            "QListWidget::item:selected { background:#f7ecd7; color:#5a3a15; }")
        self._list.itemDoubleClicked.connect(self._on_copy)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_menu)
        lay.addWidget(self._list, 1)

        # ---- 底部 ----
        bottom = QHBoxLayout()
        self._hint = QLabel("双击复制 · 隐私仅存本机")
        self._hint.setObjectName("hint")
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._on_clear)
        bottom.addWidget(self._hint, 1)
        bottom.addWidget(btn_clear)
        lay.addLayout(bottom)

        root.addWidget(card)
        self._hist.changed.connect(self._refresh)
        self._refresh()

    # ---- 数据 → 列表 ----
    def _refresh(self):
        kw = (self._search.text() or "").strip().lower()
        self._list.clear()
        items = self._hist.items()
        for it in items:
            text = it.get("text", "")
            if kw and kw not in text.lower():
                continue
            icon = _KIND_ICON.get(item_kind(text), "📝")
            row = QListWidgetItem(
                f"{icon} {_preview(text)}\n     {_fmt_ts(it.get('ts', 0))}")
            row.setData(Qt.UserRole, text)
            row.setToolTip(text[:800])
            self._list.addItem(row)
        total = len(items)
        shown = self._list.count()
        self._count.setText(f"  {shown}/{total} 条" if kw else f"  {total} 条")
        if total == 0:
            self._hint.setText("还没有记录～去复制点东西吧")

    # ---- 操作 ----
    def _on_copy(self, item: QListWidgetItem):
        text = item.data(Qt.UserRole) or ""
        if not text:
            return
        self._hist.copy_text(text)
        self._hint.setText("✓ 已复制到剪贴板")
        self._hint_ts = time.monotonic()
        self._restore_hint_later()

    def _restore_hint_later(self):
        """2 秒后恢复默认提示（避免"已复制"一直挂着）。"""
        stamp = self._hint_ts

        def _restore():
            if self._hint_ts == stamp:
                self._hint.setText("双击复制 · 隐私仅存本机")
        QTimer.singleShot(2000, _restore)

    def _on_menu(self, pos: QPoint):
        item = self._list.itemAt(pos)
        if item is None:
            return
        text = item.data(Qt.UserRole) or ""
        menu = QMenu(self)
        act_copy = menu.addAction("复制")
        act_del = menu.addAction("删除这条")
        act = menu.exec(self._list.mapToGlobal(pos))
        if act == act_copy:
            self._on_copy(item)
        elif act == act_del:
            self._hist.remove(text)

    def _on_clear(self):
        if self._hist.count() == 0:
            return
        ok = QMessageBox.question(
            self, "清空剪贴板历史",
            f"确定清空全部 {self._hist.count()} 条记录吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok == QMessageBox.Yes:
            self._hist.clear()

    # ---- 位置 / 拖动 ----
    def show_near(self, pet_rect):
        """弹到桌宠头顶附近（放不下就下移），限制在屏幕内。"""
        screen = QGuiApplication.screenAt(pet_rect.center()) \
            or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = pet_rect.right() - self.width()
        y = pet_rect.top() - self.height() - 8
        x = max(geo.left() + 4, min(x, geo.right() - self.width() - 4))
        if y < geo.top() + 4:                 # 头顶放不下 → 放到宠物下方
            y = pet_rect.bottom() + 8
        y = min(y, geo.bottom() - self.height() - 4)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() \
                - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(e)
