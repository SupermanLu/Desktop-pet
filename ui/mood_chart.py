# -*- coding: utf-8 -*-
"""情绪曲线（极简版）：用 QPainter 画本周 7 天的心情折线 + 图例 + 一句话总结。

纯本地渲染，不联网、不生成文件。
"""
from datetime import datetime

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QDialog

MOOD_COLORS = {1: QColor("#7f8c9a"), 2: QColor("#f0a500"), 3: QColor("#2ecc71")}
# 温暖奶油风主题色
_TITLE = QColor("#5a3a15")
_LINE = QColor("#c07a2d")
_DOT_EMPTY = QColor("#d4c8a8")
_LABEL = QColor("#8a7a62")
WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


class MoodChartDialog(QDialog):
    """展示一周心情曲线的小窗口。records: [(date_str, value), ...]"""

    def __init__(self, records, summary: str = "", parent=None):
        super().__init__(parent)
        self._records = records
        self._summary = summary
        self.setWindowTitle("本周情绪曲线")
        self.setFixedSize(340, 250)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        # 按星期（周一=0..周日=6）建索引，便于画完整一周
        self._by_weekday = {}
        for d, v in records:
            try:
                day = datetime.strptime(d, "%Y-%m-%d")
                self._by_weekday[day.weekday()] = int(v)
            except (ValueError, TypeError):
                continue

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 标题
        p.setPen(_TITLE)
        p.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        p.drawText(QRectF(0, 8, w, 24), Qt.AlignCenter, "本周情绪曲线")

        # 图表区域
        x0, x1 = 36, w - 36
        y0, y1 = 52, h - 58
        step = (x1 - x0) / 6.0
        prev_x, prev_y = None, None
        for i in range(7):
            x = x0 + i * step
            if i in self._by_weekday:
                v = self._by_weekday[i]
                y = y1 - (v - 1) / 2.0 * (y1 - y0)
                # 与前一个有记录的天连线
                if prev_x is not None:
                    pen = QPen(_LINE, 2)
                    p.setPen(pen)
                    p.drawLine(int(prev_x), int(prev_y), int(x), int(y))
                p.setPen(Qt.NoPen)
                p.setBrush(MOOD_COLORS[v])
                p.drawEllipse(QRectF(x - 6, y - 6, 12, 12))
                prev_x, prev_y = x, y
            else:
                p.setPen(QPen(_DOT_EMPTY, 1))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QRectF(x - 3.5, (y0 + y1) / 2 - 3.5, 7, 7))
            # 星期标签
            p.setPen(_LABEL)
            p.setFont(QFont("Microsoft YaHei", 9))
            p.drawText(QRectF(x - 18, h - 34, 36, 18), Qt.AlignCenter,
                       WEEKDAY_CN[i])

        # 图例 + 计数
        counts = {1: 0, 2: 0, 3: 0}
        for _d, v in self._records:
            counts[v] = counts.get(v, 0) + 1
        legend = f"😔 {counts[1]}    😐 {counts[2]}    😊 {counts[3]}"
        p.setFont(QFont("Microsoft YaHei", 10))
        p.drawText(QRectF(0, h - 52, w, 20), Qt.AlignCenter, legend)

        # 一句话总结
        if self._summary:
            p.setPen(_TITLE)
            p.setFont(QFont("Microsoft YaHei", 9))
            p.drawText(QRectF(14, h - 26, w - 28, 18), Qt.AlignCenter,
                       self._summary)
