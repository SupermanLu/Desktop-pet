# -*- coding: utf-8 -*-
"""本周专注时长柱状图：哆啦A梦主题背景 + 温暖奶油风图表。

- 背景：哆啦A梦天空图（与聊天窗共用 assets/chat_bg/doraemon_sky.jpg）cover 铺满
- 无边框圆角窗口，可拖动；右上角 ✕ / ESC 关闭
- 柱子用哆啦A梦蓝渐变，悬停高亮；纯本地绘制，不依赖第三方库
"""
import os

from PySide6.QtCore import Qt, QRectF, QPointF, QPoint
from PySide6.QtGui import (QPainter, QColor, QPen, QFont, QPixmap,
                           QLinearGradient, QPainterPath)
from PySide6.QtWidgets import QDialog

from core.config import ASSETS_DIR

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]
# 哆啦A梦主题背景（与聊天窗共用同一张天空图）
CHART_BG = os.path.join(ASSETS_DIR, "chat_bg", "doraemon_sky.jpg")

# 哆啦A梦配色（背景是蓝色天空，柱子用哆啦A梦蓝呼应）
_DORA_BLUE = QColor("#4a96ff")
_DORA_BLUE_DEEP = QColor("#2f7af0")
_DORA_BLUE_LIGHT = QColor("#8fc4ff")
_TITLE_BG = QColor(5, 100, 241, 178)     # 标题条（半透明深蓝）
_SUMMARY_BG = QColor(5, 100, 241, 158)   # 底部汇总条
_CARD = QColor(255, 253, 248, 240)       # 图表卡片（半透明白）
_INK = QColor("#5a3a15")                 # 深棕褐文字
_GRAY = QColor("#8a7a62")                # 次要文字
_WHITE = QColor(255, 255, 255)


class FocusChartDialog(QDialog):
    """本周专注柱状图。week_data: [(date_str, active_min), ...]（周一..周日）。"""

    RADIUS = 16

    def __init__(self, week_data, parent=None):
        super().__init__(parent)
        self._data = week_data
        self._bars = []          # 柱子矩形列表（paintEvent 中构建，供悬停命中）
        self._drag_offset = None
        self._hover = -1         # 悬停的柱子下标（-1=无）
        self.setWindowTitle("本周专注")
        self.setFixedSize(360, 300)
        # 无边框圆角 + 置顶 + 不抢焦点
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

    # ---------- 无边框窗口交互（拖动 / 关闭 / ESC） ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if self._in_close_btn(pos):
                self.close()
                return
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            self._update_hover(event.position().toPoint())

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _in_close_btn(self, pos: QPoint) -> bool:
        w = self.width()
        cx, cy = w - 26, 20
        return (pos.x() - cx) ** 2 + (pos.y() - cy) ** 2 <= 15 * 15

    def _update_hover(self, pos: QPoint):
        idx = -1
        for i, r in enumerate(self._bars):
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                idx = i
                break
        if idx != self._hover:
            self._hover = idx
            self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 投影（不裁剪，落在透明边缘内）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 42))
        p.drawRoundedRect(QRectF(3, 7, w - 6, h - 6), self.RADIUS, self.RADIUS)

        # 圆角裁剪，保证背景图/卡片都收进圆角
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), self.RADIUS, self.RADIUS)
        p.setClipPath(clip)

        # ---- 背景：哆啦A梦主题图（cover 铺满）----
        bg = QPixmap(CHART_BG)
        if not bg.isNull() and bg.width() > 0 and bg.height() > 0:
            scale = max(w / bg.width(), h / bg.height())
            sw, sh = int(bg.width() * scale), int(bg.height() * scale)
            p.drawPixmap(QPoint(int((w - sw) / 2), int((h - sh) / 2)),
                         bg.scaled(sw, sh, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation))
        else:
            p.fillRect(QRectF(0, 0, w, h), QColor("#cfe6ff"))

        # ---- 顶部标题条（半透明深蓝，顶部圆角）----
        title_path = QPainterPath()
        title_path.moveTo(0, self.RADIUS)
        title_path.arcTo(QRectF(0, 0, self.RADIUS * 2, self.RADIUS * 2),
                         90, 90)
        title_path.lineTo(w - self.RADIUS, 0)
        title_path.arcTo(QRectF(w - self.RADIUS * 2, 0,
                                self.RADIUS * 2, self.RADIUS * 2), 0, 90)
        title_path.lineTo(w, 46)
        title_path.lineTo(0, 46)
        title_path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(_TITLE_BG)
        p.drawPath(title_path)
        # 标题文字：白色，带轻微阴影增强可读性
        p.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        p.setPen(QColor(0, 0, 0, 70))
        p.drawText(QRectF(0, 2, w - 4, 30), Qt.AlignCenter, "📊 本周专注时长")
        p.setPen(_WHITE)
        p.drawText(QRectF(0, 0, w - 4, 30), Qt.AlignCenter, "📊 本周专注时长")
        # 标题底部分隔线
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        p.drawLine(0, 46, w, 46)
        # 右上角关闭按钮（红鼻风格 ✕）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(220, 78, 78, 225))
        p.drawEllipse(QPointF(w - 26, 20), 13, 13)
        p.setPen(QPen(_WHITE, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(w - 30, 16), QPointF(w - 22, 24))
        p.drawLine(QPointF(w - 30, 24), QPointF(w - 22, 16))

        # ---- 图表卡片（半透明白圆角）----
        card = QRectF(14, 58, w - 28, h - 58 - 44)
        p.setPen(QPen(QColor(255, 255, 255, 190), 1))
        p.setBrush(_CARD)
        p.drawRoundedRect(card, 12, 12)

        # ---- 柱状图 ----
        self._bars = []
        x0, x1 = card.left() + 18, card.right() - 18
        y0 = card.top() + 18          # 为满值柱顶的数值标签留出空间
        y1 = card.bottom() - 30       # 星期标签区
        n = max(1, len(self._data))
        step = (x1 - x0) / n
        bw = min(step * 0.52, 34)
        max_v = max((v for _, v in self._data), default=1) or 1
        total = sum(v for _, v in self._data)
        for i, (_d, v) in enumerate(self._data):
            x = x0 + i * step + step / 2
            bh = (y1 - y0) * (v / max_v)
            r = QRectF(x - bw / 2, y1 - bh, bw, bh)
            self._bars.append(r)
            if v > 0:
                # 柱子：哆啦A梦蓝渐变，悬停提亮
                grad = QLinearGradient(r.topLeft(), r.bottomLeft())
                if i == self._hover:
                    grad.setColorAt(0, QColor("#b5daff"))
                    grad.setColorAt(1, QColor("#4a96ff"))
                else:
                    grad.setColorAt(0, _DORA_BLUE_LIGHT)
                    grad.setColorAt(1, _DORA_BLUE_DEEP)
                p.setPen(Qt.NoPen)
                p.setBrush(grad)
                p.drawRoundedRect(r, 4, 4)
                if i == self._hover:
                    p.setPen(QPen(QColor(255, 255, 255, 220), 1.2))
                    p.drawLine(QPointF(r.left() + 2, r.top() + 1),
                               QPointF(r.right() - 2, r.top() + 1))
                # 数值标签（柱顶上方）
                label = f"{v}m" if v < 60 else f"{v // 60}h{v % 60:02d}m"
                p.setFont(QFont("Microsoft YaHei", 9))
                p.setPen(_INK)
                p.drawText(QRectF(r.left() - 14, r.top() - 16, bw + 28, 14),
                           Qt.AlignCenter, label)
            else:
                # 无记录的星期：画一条浅基线占位
                p.setPen(QPen(QColor(226, 210, 172, 190), 1))
                p.drawLine(QPointF(r.left(), r.bottom() - 1),
                           QPointF(r.right(), r.bottom() - 1))
            # 星期标签
            p.setFont(QFont("Microsoft YaHei", 10))
            p.setPen(_GRAY)
            p.drawText(QRectF(x - step / 2, y1 + 5, step, 18),
                       Qt.AlignCenter, "周" + WEEKDAY_CN[i])

        # ---- 底部汇总条（半透明深蓝）----
        sum_rect = QRectF(14, h - 36, w - 28, 26)
        p.setPen(Qt.NoPen)
        p.setBrush(_SUMMARY_BG)
        p.drawRoundedRect(sum_rect, 12, 12)
        if total > 0:
            text = (f"本周共专注 {total // 60} 小时 {total % 60} 分钟"
                    if total >= 60 else f"本周共专注 {total} 分钟")
        else:
            text = "本周还没有专注记录，开始一个番茄钟吧 🍅"
        p.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        p.setPen(_WHITE)
        p.drawText(sum_rect, Qt.AlignCenter, text)
