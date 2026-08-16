# -*- coding: utf-8 -*-
"""新增事件提醒对话框：标题 + 日期 + 时间 + 重复规则。"""
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                               QDateEdit, QTimeEdit, QComboBox, QDialogButtonBox)

REPEATS = [("不重复", "none"), ("每天", "daily"),
           ("每周", "weekly"), ("每月", "monthly")]


class EventDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增事件提醒")
        self.setMinimumWidth(320)

        lay = QVBoxLayout(self)
        # 统一白底深字，保证深色主题下可读
        self.setStyleSheet("""
            QLineEdit, QDateEdit, QTimeEdit, QComboBox {
                background: white; color: #333333;
                border: 1px solid #e6c99a; border-radius: 8px; padding: 5px 8px;
                selection-background-color: #ff9f43; selection-color: white;
            }
            QLineEdit::placeholder { color: #b0a08a; }
            QDateEdit::drop-down, QTimeEdit::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: white; color: #333333;
                selection-background-color: #ff9f43; selection-color: white;
                border: 1px solid #e6c99a; outline: none;
            }
        """)
        form = QFormLayout()

        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("例如：开会 / 喝水 / 下班")

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")

        self.time_edit = QTimeEdit(QTime.currentTime().addSecs(60))
        self.time_edit.setDisplayFormat("HH:mm")

        self.repeat_box = QComboBox()
        for label, _ in REPEATS:
            self.repeat_box.addItem(label)

        form.addRow("事件", self.edit_title)
        form.addRow("日期", self.date_edit)
        form.addRow("时间", self.time_edit)
        form.addRow("重复", self.repeat_box)
        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def event_data(self) -> dict:
        return {
            "title": self.edit_title.text().strip() or "提醒",
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "time": self.time_edit.time().toString("HH:mm"),
            "repeat": REPEATS[self.repeat_box.currentIndex()][1],
            "enabled": True,
            "last_fired": "",
        }
