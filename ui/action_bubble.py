# -*- coding: utf-8 -*-
"""交互式气泡：展示剪贴板检测结果和操作按钮（收藏/解释/摘要/总是允许/拒绝）。

置顶、透明、不抢焦点，跟随宠物移动；点按钮后发出 chosen(action_key) 信号。
"""
from PySide6.QtCore import Qt, QPoint, Signal, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame)

from ui.theme import DORA


class ActionBubble(QWidget):
    chosen = Signal(str)   # 用户点击的按钮 action key
    closed = Signal()      # 气泡被隐藏/关闭（用于调用方做收尾，如恢复桌宠形象）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("clipboard-bubble")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._frame = QFrame(self)
        self._frame.setObjectName("cb")
        self._frame.setStyleSheet(f"""
            QFrame#cb {{ background: {DORA['white']};
                        border: 1px solid {DORA['blue_border']}; border-radius: 12px; }}
            QLabel#title {{ color: {DORA['blue_dark']}; font-size: 13px; }}
            QPushButton {{ background: {DORA['blue_light']}; color: {DORA['blue_dark']};
                          border: 1px solid {DORA['blue_border']}; border-radius: 8px;
                          padding: 5px 10px; font-size: 12px; }}
            QPushButton:hover {{ background: #dceefb; }}
            QPushButton#primary {{ background: {DORA['blue']}; color: white;
                                  border-color: {DORA['blue']}; }}
            QPushButton#primary:hover {{ background: {DORA['blue_dark']}; }}
            QPushButton#danger {{ background: {DORA['red']}; color: white;
                                 border-color: {DORA['red']}; }}
            QPushButton#danger:hover {{ background: #c94343; }}
        """)
        lay = QVBoxLayout(self._frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        self._title = QLabel("")
        self._title.setObjectName("title")
        self._title.setWordWrap(True)
        lay.addWidget(self._title)
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(6)
        lay.addLayout(self._btn_row)
        root.addWidget(self._frame)

        # 无人操作超时自动隐藏（timeout_ms<=0 时不启用）
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self.hide)

    def _clear_buttons(self):
        while self._btn_row.count():
            it = self._btn_row.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

    def popup(self, title: str, buttons: list, anchor_center: QPoint,
              timeout_ms: int = 0):
        """buttons: [(label, action_key)]；第一个设为主按钮，dismiss 设为红色。
        timeout_ms>0 时：若用户一直不点按钮，到点自动隐藏。"""
        self._timeout_timer.stop()
        self._title.setText(title)
        self._clear_buttons()
        for i, (label, key) in enumerate(buttons):
            b = QPushButton(label)
            if i == 0:
                b.setObjectName("primary")
            elif key == "dismiss":
                b.setObjectName("danger")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._emit_choice(k))
            self._btn_row.addWidget(b)
        self.adjustSize()
        self._place(anchor_center)
        self.show()
        self.raise_()
        if timeout_ms > 0:
            self._timeout_timer.start(timeout_ms)

    def _emit_choice(self, key: str):
        self._timeout_timer.stop()
        self.hide()
        self.chosen.emit(key)

    def hideEvent(self, event):
        self._timeout_timer.stop()
        super().hideEvent(event)
        self.closed.emit()

    def _place(self, anchor_center: QPoint):
        screen = QGuiApplication.screenAt(anchor_center)
        geo = screen.availableGeometry() if screen \
            else QGuiApplication.primaryScreen().availableGeometry()
        x = anchor_center.x() - self.width() // 2
        y = anchor_center.y() - self.height() - 6
        x = max(geo.left() + 4, min(x, geo.right() - self.width() - 4))
        y = max(geo.top() + 4, y)
        self.move(x, y)

    def follow(self, anchor_center: QPoint):
        if self.isVisible():
            self._place(anchor_center)
