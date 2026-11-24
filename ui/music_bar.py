# -*- coding: utf-8 -*-
"""音乐 UI：悬停控制栏 + 宠物下方常驻歌词行（网易云官方音乐宠物同款）。

交互（参考官方设计）：
- 平时 / 未检测到播放：只有桌宠本体，碰它也不弹任何控件（保持纯净交互）
- 检测到播放会话后，鼠标碰到桌宠：控制栏浮现在宠物下方
    歌名 - 歌手
    ♡ |◀ ▶(红) ▶| 词
- "词"键（/ 快捷键 M）开关常驻歌词行：直接浮在宠物正下方——
    当前行大字亮白（卡拉OK 扫色：未唱灰白 → 已唱亮白）
    下一行/翻译小字暗灰
  无背景、带阴影（浅色壁纸可读）、点击穿透（WS_EX_TRANSPARENT）。
- 移开鼠标（宠物和控制栏都不在）：约 1s 后控制栏收起；歌词行常驻
- 控制栏/歌词行随宠物移动（挂边/拖动/游走都跟），屏幕边缘自动翻转，
  全屏时随气泡一起隐藏

视觉：控制栏深色半透明圆角条、白色图标、大红播放键（自绘 QPainter 图标 +
命中测试，不依赖 emoji 字体）。歌词两遍绘制做卡拉OK扫色（灰白全文 +
按进度裁剪的亮白叠画）。
"""
from bisect import bisect_right
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import (QPainter, QColor, QFont, QFontMetrics, QPen,
                           QPainterPath, QGuiApplication)
from PySide6.QtWidgets import QWidget

_W = 340                     # 控制栏宽度
_H_CTRL = 112                # 控制区高度（歌名 + 按钮行）
_BG = QColor(18, 18, 20, 216)        # 深色半透明底（近网易官方黑）
_ICON = QColor(238, 236, 232)        # 图标白
_PLAY_RED = QColor(236, 65, 55)      # 播放键红

_HOVER_HIDE_MS = 1000       # 离开后延迟收起（滑向按钮不闪断）

# ---- 常驻歌词行（宠物正下方） ----
_LY_W = 320                  # 歌词行宽度（长句走马灯滚动，不撑宽）
_LY_H = 48                   # 歌词行高度（当前行 + 预览行）
_LY_CUR_HOT = QColor(255, 255, 255)      # 当前行已唱（亮白）
_LY_CUR_DIM = QColor(198, 195, 191)      # 当前行未唱（灰白）
_LY_SUB = QColor(168, 164, 160)          # 下一行/翻译小字（暗灰）
_LY_SHADOW = QColor(0, 0, 0, 150)        # 文字阴影（浅色壁纸上也可读）


def _apply_win_style(widget, extra=0):
    """WS_EX_NOACTIVATE（不抢焦点）+ 可选额外扩展样式。"""
    try:
        import ctypes
        GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
        hwnd = int(widget.winId())
        u32 = ctypes.windll.user32
        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                           style | WS_EX_NOACTIVATE | extra)
    except Exception:
        pass


class LyricLine(QWidget):
    """宠物正下方的常驻歌词（网易云官方音乐宠物样式）。

    "词"键由 MusicBar.toggle_lyric 开关；随宠物移动、全屏随气泡隐藏。
    """

    def __init__(self, cfg: dict, controller, pet, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._ctrl = controller
        self._pet = pet
        self._enabled = bool(cfg.get("lyric_bar_enabled", True))
        self._has_track = False
        self._lines: list[dict] = []   # [{t, text, trans}]
        self._times: list[int] = []
        self._cur = -1
        self._hint = ""
        self._line_ts = time.monotonic()   # 当前行开始展示时刻（走马灯用）

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(_LY_W, _LY_H)
        self.setWindowTitle("歌词")

        self._timer = QTimer(self)     # 100ms 推进卡拉OK扫色
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)

        controller.track_changed.connect(self.set_track)
        controller.lyrics_ready.connect(self.set_lyrics)
        controller.lyric_failed.connect(self._on_lyric_failed)
        controller.lost.connect(self.on_lost)

    # ---------- 状态 ----------
    def set_enabled(self, on: bool):
        self._enabled = bool(on)
        self._update_visibility()

    def set_track(self, title: str, artist: str):
        if not title:
            self.on_lost()
            return
        self._has_track = True
        self._lines, self._times, self._cur = [], [], -1
        self._hint = "歌词加载中…"
        self._line_ts = time.monotonic()
        self._update_visibility()
        self.update()

    def set_lyrics(self, lines: list):
        self._lines = list(lines or [])
        self._times = [ln["t"] for ln in self._lines]
        self._cur = 0 if self._lines else -1   # 防 -1 负索引误取末行
        self._hint = "" if self._lines else "🎵 纯音乐～没有歌词"
        self._line_ts = time.monotonic()
        self.update()

    def _on_lyric_failed(self, _reason: str):
        self._hint = "暂无歌词"
        self.update()

    def on_lost(self):
        """播放会话消失：清歌词并隐藏。"""
        self._has_track = False
        self._lines, self._times, self._cur = [], [], -1
        self._hint = ""
        self._update_visibility()

    def _update_visibility(self):
        want = self._enabled and self._has_track
        if want and not self.isVisible():
            self.follow_pet()
            self.show()
            self.raise_()
            _apply_win_style(self, extra=0x00000020)  # WS_EX_TRANSPARENT 点击穿透
        elif not want and self.isVisible():
            self.hide()

    # ---------- 定位（register_follow_bubble 契约） ----------
    def follow_pet(self):
        pg = self._pet.geometry()
        x = pg.center().x() - _LY_W // 2
        y = pg.bottom() + 4
        screen = QGuiApplication.screenAt(pg.center()) \
            or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        if y + self.height() > geo.bottom():
            y = pg.top() - self.height() - 4
        # 水平限位放宽：允许窗口最多探出屏幕 30%，尽量贴住宠物不"钉死"
        overflow = int(_LY_W * 0.3)
        x = max(geo.left() - overflow,
                min(x, geo.right() - _LY_W + overflow))
        self.move(x, y)

    def follow(self, anchor):
        self.follow_pet()

    @property
    def below_pet(self) -> bool:
        """歌词当前是否排在宠物下方（控制栏布局参考）。"""
        return self.isVisible() and self.y() >= self._pet.geometry().bottom()

    def showEvent(self, e):
        super().showEvent(e)
        _apply_win_style(self, extra=0x00000020)

    # ---------- 歌词推进 ----------
    def _tick(self):
        if not (self.isVisible() and self._lines):
            return
        pos = self._ctrl.session.estimate_pos()
        i = bisect_right(self._times, pos) - 1
        i = max(0, min(i, len(self._lines) - 1))
        if i != self._cur:
            self._cur = i
            self._line_ts = time.monotonic()   # 换行 → 走马灯重新起播
        self.update()                  # 扫色渐进也刷（100ms 足够轻）

    def _line_progress(self) -> float:
        """当前行内进度 0~1（卡拉OK扫色宽度）。"""
        if not self._lines or self._cur < 0:
            return 0.0
        pos = self._ctrl.session.estimate_pos()
        t0 = self._times[self._cur]
        t1 = (self._times[self._cur + 1]
              if self._cur + 1 < len(self._times)
              else max(self._ctrl.session.duration_ms, t0 + 4000))
        if t1 <= t0:
            return 1.0
        return max(0.0, min(1.0, (pos - t0) / (t1 - t0)))

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        if not self._lines:
            f = QFont()
            f.setPixelSize(13)
            p.setFont(f)
            self._draw_scrolling(p, self._hint or "🎵 …", QFontMetrics(f),
                                 QRectF(0, 0, w, _LY_H), -1.0, 40.0)
            p.end()
            return

        # 当前行：大字，卡拉OK 扫色（放不下时走马灯滚动）
        cur = self._lines[self._cur]
        f = QFont()
        f.setPixelSize(18)
        f.setBold(True)
        fm = QFontMetrics(f)
        text = cur.get("text", "") or "……"
        p.setFont(f)
        self._draw_scrolling(p, text, fm, QRectF(0, 2, w, 26),
                             self._line_progress(), 60.0)

        # 预览行：翻译（设置开启且有）否则下一行（同样走马灯）
        show_trans = self._cfg.get("lyric_translate", True)
        trans = cur.get("trans", "") if show_trans else ""
        if trans:
            sub = trans
        elif self._cur + 1 < len(self._lines):
            sub = self._lines[self._cur + 1].get("text", "")
        else:
            sub = ""
        if sub:
            f2 = QFont()
            f2.setPixelSize(12)
            fms = QFontMetrics(f2)
            p.setFont(f2)
            self._draw_scrolling(p, sub, fms, QRectF(0, 30, w, 16), -1.0, 40.0)
        p.end()

    def _draw_scrolling(self, p: QPainter, text: str, fm: QFontMetrics,
                        rect: QRectF, prog: float, speed: float):
        """一行文字：放得下居中；放不下走马灯左右滚动（prog<0 = 无扫色）。

        走马灯：先停 1.5s 亮出句首，再匀速左移直到句尾露出后定格，
        换行时重置——长句完整可读又不占宽度。
        """
        w = self.width()
        pad = 14
        tw = fm.horizontalAdvance(text)
        if tw <= w - pad * 2:                    # 放得下：居中
            self._draw_line_pair(p, text, (w - tw) / 2, rect, prog, tw)
            return
        t = max(0.0, time.monotonic() - self._line_ts)
        x = pad - speed * max(0.0, t - 1.5)      # 1.5s 后开始滚动
        x = max(w - pad - tw, x)                 # 句尾露出即定格
        p.save()
        p.setClipRect(QRectF(pad, rect.y(), w - pad * 2, rect.height()))
        self._draw_line_pair(p, text, x, rect, prog, tw)
        p.restore()

    @staticmethod
    def _draw_line_pair(p: QPainter, text: str, x: float, rect: QRectF,
                        prog: float, tw: float):
        """暗色全文 +（prog>=0 时）亮色卡拉OK扫色叠画；带阴影。"""
        r = QRectF(x, rect.y(), tw + 8, rect.height())
        align = int(Qt.AlignLeft | Qt.AlignVCenter)
        p.setPen(_LY_SHADOW)
        p.drawText(r.translated(1, 1), align, text)
        p.setPen(_LY_CUR_DIM)
        p.drawText(r, align, text)
        if prog is not None and prog >= 0:
            p.save()
            p.setClipRect(QRectF(x - 2, rect.y(), tw * prog + 4,
                                 rect.height()), Qt.IntersectClip)
            p.setPen(_LY_CUR_HOT)
            p.drawText(r, align, text)
            p.restore()


class MusicBar(QWidget):
    """悬停式音乐控制栏（"词"键开关宠物下方的常驻歌词行）。"""

    heart_toggled = Signal(bool)      # 喜欢按钮

    def __init__(self, cfg: dict, controller, pet, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._ctrl = controller
        self._pet = pet               # 桌宠窗口（取位置/尺寸跟随）
        self._lyric = None            # 常驻歌词行（布局参考，set_lyric_layer 注入）
        self._title = ""
        self._artist = ""
        self._playing = False
        self._active = False           # 检测到播放会话才准弹控制栏
        self._on_pet = False           # 鼠标当前是否停在宠物上
        self._hover_bar = False        # 鼠标当前是否停在控制栏上（停留期间永不收起）
        self._liked = False
        self._lyric_on = bool(cfg.get("lyric_bar_enabled", True))
        self._hover = None            # 悬停按钮 key

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(_W, _H_CTRL)
        self.setWindowTitle("音乐控制栏")
        self.setMouseTracking(True)

        # 离开延时收起
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_if_idle)

        controller.track_changed.connect(self.set_track)
        controller.state_changed.connect(self.set_state)
        controller.lost.connect(self.on_lost)

    def set_lyric_layer(self, lyric):
        """注入常驻歌词行（"词"键开关它；控制栏排在它下面）。"""
        self._lyric = lyric
        self._lyric_on = bool(lyric._enabled)

    # ---------- 对外接口 ----------
    def set_track(self, title: str, artist: str):
        if not title:
            self.on_lost()
            return
        self._title, self._artist = title, artist
        self._active = True            # 有曲目 = 检测到播放，允许弹出
        self.update()
        if self._on_pet:               # 鼠标正停在宠物上：立即弹出
            self.notify_hover(True)

    def on_lost(self):
        """播放会话消失：收起控制栏并回到"未检测"状态（碰宠物不再弹）。"""
        self._active = False
        self._title, self._artist = "", ""
        self._playing = False
        self._hide_timer.stop()
        self.hide()
        self.update()

    def set_state(self, playing: bool):
        self._playing = playing
        self.update()

    def toggle_lyric(self):
        """开关常驻歌词行（"词"键 / 快捷键 M）。"""
        self._lyric_on = not self._lyric_on
        self._cfg["lyric_bar_enabled"] = self._lyric_on
        if self._lyric is not None:
            self._lyric.set_enabled(self._lyric_on)
        self.update()

    def sync_lyric_from_cfg(self):
        """设置页改动后同步歌词行开关（即时生效）。"""
        self._lyric_on = bool(self._cfg.get("lyric_bar_enabled", True))
        if self._lyric is not None:
            self._lyric.set_enabled(self._lyric_on)
        self.update()

    def notify_hover(self, on_pet: bool):
        """桌宠悬停状态变化（PetWindow.hover_changed 接入）。

        只有检测到播放会话（_active）时才弹控制栏——没放歌时碰到宠物
        完全无感，不干扰拖拽/点击等日常交互。
        进入宠物 → 立即显示并跟随定位；离开 → 延时收起
        （给鼠标从宠物滑到控制栏留时间）。
        """
        if on_pet:
            self._on_pet = True
            if not self._active:
                return               # 未检测到播放：不弹任何控件
            self._hide_timer.stop()
            self.follow_pet()
            if not self.isVisible():
                self.show()
                self.raise_()
            _apply_win_style(self)
        else:
            self._on_pet = False
            # 迟到的 hover=False 信号可能晚于 enterEvent 到达（悬停检测是
            # 轮询的），若鼠标已在控制栏上就不再排收起，防止“人在栏上却收起”
            if not self._hover_bar:
                self._hide_timer.start(_HOVER_HIDE_MS)

    def _hide_if_idle(self):
        """收起前最后确认：鼠标还在控制栏上就不收（双保险）。"""
        if self._hover_bar or self.underMouse():
            return
        self.hide()

    def follow_pet(self):
        """定位到宠物正下方；歌词行开着时排在歌词下面。"""
        pg = self._pet.geometry()
        x = pg.center().x() - _W // 2
        y = pg.bottom() + 6
        if self._lyric is not None and self._lyric.below_pet:
            y = self._lyric.y() + self._lyric.height() + 4
        screen = QGuiApplication.screenAt(pg.center()) \
            or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        if y + self.height() > geo.bottom():   # 屏幕底部放不下 → 放宠物上方
            y = pg.top() - self.height() - 6
        x = max(geo.left() + 4, min(x, geo.right() - _W - 4))
        self.move(x, y)

    # register_follow_bubble 契约：桌宠移动时调用（anchor=宠物顶部中心）
    def follow(self, anchor):
        self.follow_pet()

    # ---------- 悬停进出（鼠标滑到控制栏上不收起） ----------
    def enterEvent(self, e):
        self._hover_bar = True
        self._hide_timer.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover_bar = False
        self._hide_timer.start(_HOVER_HIDE_MS)
        super().leaveEvent(e)

    # ---------- 按钮几何（命中测试与绘制共用） ----------
    def _btns(self):
        """[(key, 中心QPointF, 半径)]：heart/prev/play/next/lyric。"""
        cy = _H_CTRL - 44
        cx = _W / 2
        return [
            ("heart", QPointF(cx - 92, cy), 15),
            ("prev", QPointF(cx - 46, cy), 15),
            ("play", QPointF(cx, cy), 28),
            ("next", QPointF(cx + 46, cy), 15),
            ("lyric", QPointF(cx + 92, cy), 15),
        ]

    @staticmethod
    def _hit(key: str, c: QPointF, r: float, pos: QPointF) -> bool:
        if key == "lyric":
            return (abs(pos.x() - c.x()) <= r and abs(pos.y() - c.y()) <= r)
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        return dx * dx + dy * dy <= (r + 4) * (r + 4)

    # ---------- 鼠标 ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        for key, c, r in self._btns():
            if self._hit(key, c, r, pos):
                self._click(key)
                return

    def mouseMoveEvent(self, e):
        pos = e.position()
        hov = None
        for key, c, r in self._btns():
            if self._hit(key, c, r, pos):
                hov = key
                break
        if hov != self._hover:
            self._hover = hov
            self.setCursor(Qt.PointingHandCursor if hov else Qt.ArrowCursor)
            self.update()

    def _click(self, key: str):
        if key == "play":
            self._ctrl.play_pause()
        elif key == "next":
            self._ctrl.next_track()
        elif key == "prev":
            self._ctrl.prev_track()
        elif key == "lyric":
            self.toggle_lyric()
        elif key == "heart":
            self._liked = not self._liked
            self.heart_toggled.emit(self._liked)
            self.update()

    def showEvent(self, event):
        super().showEvent(event)
        _apply_win_style(self)

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 深色圆角底
        p.setPen(Qt.NoPen)
        p.setBrush(_BG)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)

        # 歌名 - 歌手
        f = QFont()
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor(245, 243, 240))
        text = f"{self._title} - {self._artist}" if self._title and self._artist \
            else (self._title or "等待播放…")
        fm = p.fontMetrics()
        text = fm.elidedText(text, Qt.ElideRight, _W - 32)
        p.drawText(QRectF(16, 12, _W - 32, 22),
                   int(Qt.AlignHCenter | Qt.AlignVCenter), text)

        # 按钮行
        for key, c, r in self._btns():
            self._draw_btn(p, key, c, r)
        p.end()

    def _draw_btn(self, p: QPainter, key: str, c: QPointF, r: float):
        hover = (self._hover == key)
        if key == "play":
            # 大红圆播放/暂停键
            p.setPen(Qt.NoPen)
            p.setBrush(_PLAY_RED.lighter(115) if hover else _PLAY_RED)
            p.drawEllipse(c, r, r)
            p.setBrush(QColor(255, 255, 255))
            if self._playing:      # 暂停图标（两竖条）
                bw = r * 0.22
                gap = r * 0.20
                p.drawRect(QRectF(c.x() - gap - bw, c.y() - r * 0.42,
                                  bw, r * 0.84))
                p.drawRect(QRectF(c.x() + gap, c.y() - r * 0.42,
                                  bw, r * 0.84))
            else:                  # 播放三角
                path = QPainterPath()
                path.moveTo(c.x() - r * 0.28, c.y() - r * 0.44)
                path.lineTo(c.x() + r * 0.48, c.y())
                path.lineTo(c.x() - r * 0.28, c.y() + r * 0.44)
                path.closeSubpath()
                p.drawPath(path)
            return

        # 其余小键：悬停浅底圆
        if hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 36))
            p.drawEllipse(c, r + 3, r + 3)

        pen = QPen(_ICON, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        if key == "heart":
            if self._liked:        # 喜欢 → 红色实心
                p.setPen(Qt.NoPen)
                p.setBrush(_PLAY_RED)
                self._draw_heart(p, c, r * 0.95)
            else:
                self._draw_heart(p, c, r * 0.95)
        elif key == "prev":
            self._draw_skip(p, c, r * 0.62, left=True)
        elif key == "next":
            self._draw_skip(p, c, r * 0.62, left=False)
        elif key == "lyric":
            # 圆角方框 + "词"（开启时反白）
            rect = QRectF(c.x() - r, c.y() - r, r * 2, r * 2)
            f = QFont()
            f.setPixelSize(13)
            f.setBold(True)
            p.setFont(f)
            if self._lyric_on:
                p.setPen(Qt.NoPen)
                p.setBrush(_ICON)
                p.drawRoundedRect(rect, 5, 5)
                p.setPen(QColor(18, 18, 20))
            else:
                p.drawRoundedRect(rect, 5, 5)
                p.setPen(_ICON)
            p.drawText(rect, int(Qt.AlignCenter), "词")

    @staticmethod
    def _draw_heart(p: QPainter, c: QPointF, s: float):
        path = QPainterPath()
        x, y = c.x(), c.y()
        path.moveTo(x, y + s * 0.42)
        path.cubicTo(x - s * 0.9, y - s * 0.12, x - s * 0.48, y - s * 0.72,
                     x, y - s * 0.28)
        path.cubicTo(x + s * 0.48, y - s * 0.72, x + s * 0.9, y - s * 0.12,
                     x, y + s * 0.42)
        path.closeSubpath()
        p.drawPath(path)

    @staticmethod
    def _draw_skip(p: QPainter, c: QPointF, s: float, left: bool):
        """上一首/下一首：双三角 + 竖条（prev=|◀◀ 在左，next=▶▶| 在右）。"""
        d = 1 if left else -1
        p.setBrush(_ICON)
        p.setPen(Qt.NoPen)
        path = QPainterPath()
        path.moveTo(c.x() + d * s * 0.15, c.y() - s * 0.55)
        path.lineTo(c.x() - d * s * 0.55, c.y())
        path.lineTo(c.x() + d * s * 0.15, c.y() + s * 0.55)
        path.closeSubpath()
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(c.x() + d * s * 0.75, c.y() - s * 0.55)
        path2.lineTo(c.x() + d * s * 0.05, c.y())
        path2.lineTo(c.x() + d * s * 0.75, c.y() + s * 0.55)
        path2.closeSubpath()
        p.drawPath(path2)
        bar_x = c.x() - d * s * 0.92
        p.drawRect(QRectF(bar_x - 1.5, c.y() - s * 0.55, 3, s * 1.1))
