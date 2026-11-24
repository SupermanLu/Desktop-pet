# -*- coding: utf-8 -*-
"""宠物主窗口：透明置顶、鼠标拖拽、屏幕内缓慢游走、点击/右键交互。

交互状态机：
- 闲置 → 打哈欠 → 睡眠动画（Zzz）
- 光标靠近 → 眼神跟随；点击抚摸 → 开心动作
- 长按拖拽自由移动；拖到屏幕边缘自动挂边待机
- 防打扰模式：鼠标穿透（不拦截任何点击），支持空闲定时自动开启
"""
import math
import os
import random
import time
from datetime import datetime

from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QTimer, Signal
from PySide6.QtGui import (QGuiApplication, QCursor, QAction, QPainter,
                           QColor, QPen, QPolygonF, QFont, QFontMetrics)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenu, QApplication, QToolTip

from core.config import ASSETS_DIR, norm_project_path
from ui.pet_animation import PetRenderer
from ui.theme import DORA


def _is_shell_window(hwnd: int) -> bool:
    """判断是否为桌面/任务栏等外壳窗口（类名 Progman / WorkerW）。

    这类窗口总是覆盖整个屏幕，但并非全屏应用；全屏检测需跳过它们，
    否则在桌面上会被误判为“全屏”而触发桌宠挂边。
    """
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(64)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 64)
        return buf.value in ("Progman", "WorkerW")
    except Exception:
        return False


def _resolve_pet_gif(cfg) -> str:
    """解析基础形象路径；配置失效时回退到 idle 素材目录的中心图。"""
    gif = norm_project_path(cfg.get("pet_gif", "") or "")
    if gif and not gif.startswith((ASSETS_DIR, "./")) and "/" not in gif \
            and "\\" not in gif:
        gif = os.path.join(ASSETS_DIR, gif)
    if gif and os.path.isfile(gif):
        return gif
    idle_dir = norm_project_path(cfg.get("idle_dir", ""))
    center = cfg.get("idle_images", {}).get("center", "")
    if idle_dir and center:
        cand = os.path.join(idle_dir, center)
        if os.path.isfile(cand):
            return cand
    return gif


class SpeechBubble(QWidget):
    """QQ 聊天式对话气泡：圆角白底 + 指向宠物的尾巴，短暂显示后自动消失。"""

    TAIL = 12  # 尾巴高度

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._text = ""
        self._pad = 12
        self.setFont(QFont("Microsoft YaHei", 10))
        self._queue = []          # 排队中的气泡 [(text, duration_ms, anchor)]
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_next)

    def _layout_size(self):
        fm = QFontMetrics(self.font())
        rect = fm.boundingRect(QRect(0, 0, 230, 1000),
                               int(Qt.TextWordWrap), self._text)
        w = max(80, rect.width() + self._pad * 2 + 8)
        h = rect.height() + self._pad * 2 + self.TAIL + 4
        self.setFixedSize(w, h)

    def popup(self, text: str, anchor_center: QPoint, duration_ms: int = 2600):
        """请求显示气泡；已有气泡在播时排队等待，避免互相抢占。

        后到的提醒不会立刻覆盖当前正在读的气泡，而是等它播完再依次显示，
        保证每条提醒都有完整的展示时间。
        """
        if self._timer.isActive():
            # 排队最多保留 5 条，防止提醒密集时无限积压
            if len(self._queue) >= 5:
                self._queue.pop(0)
            self._queue.append((text, duration_ms, anchor_center))
            return
        self._show_now(text, anchor_center, duration_ms)

    def _show_now(self, text: str, anchor_center: QPoint, duration_ms: int):
        self._text = text
        self._layout_size()
        self._place(anchor_center)
        self.show()
        # 只置顶（raise_）不激活窗口，避免提醒气泡抢占焦点打断用户当前输入
        self.raise_()
        # 统一在调用方指定时长基础上多停留 1.5s，便于读完文字
        self._timer.start(duration_ms + 1500)

    def _show_next(self):
        """当前气泡显示结束：隐藏，再显示排队的下一条（若有）。"""
        self.hide()
        if self._queue:
            text, duration_ms, anchor = self._queue.pop(0)
            self._show_now(text, anchor, duration_ms)

    def _place(self, anchor_center: QPoint):
        """按锚点（宠物窗口中心上方）计算并设置气泡位置。"""
        screen = QGuiApplication.screenAt(anchor_center)
        geo = screen.availableGeometry() if screen \
            else QGuiApplication.primaryScreen().availableGeometry()
        x = anchor_center.x() - self.width() // 2
        y = anchor_center.y() - self.height() - 6
        x = max(geo.left() + 4, min(x, geo.right() - self.width() - 4))
        y = max(geo.top() + 4, y)
        self.move(x, y)

    def follow(self, anchor_center: QPoint):
        """宠物移动时气泡跟随到新位置（仅在显示期间）。"""
        if self.isVisible():
            self._place(anchor_center)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        body = QRectF(1, 1, w - 2, h - self.TAIL - 2)
        radius = 12
        # 投影
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 45))
        painter.drawRoundedRect(body.translated(0, 2), radius, radius)
        # 气泡主体：白底 + 细蓝边框（柔和哆啦A梦风格）
        painter.setPen(QPen(QColor(DORA["blue"]), 1))
        painter.setBrush(QColor(255, 255, 255, 250))
        painter.drawRoundedRect(body, radius, radius)
        # 底部尾巴（指向宠物）：细蓝边 + 白填充
        tx = w / 2
        tail = QPolygonF([QPointF(tx - 9, body.bottom() - 2),
                          QPointF(tx + 9, body.bottom() - 2),
                          QPointF(tx, h - 4)])
        painter.setPen(QPen(QColor(DORA["blue"]), 1))
        painter.setBrush(QColor(255, 255, 255, 250))
        painter.drawPolygon(tail)
        # 文字
        painter.setPen(QColor(DORA["blue_dark"]))
        painter.setFont(self.font())
        text_rect = body.adjusted(self._pad, self._pad - 2,
                                  -self._pad, -self._pad + 2)
        painter.drawText(text_rect,
                         int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter),
                         self._text)


class PetWindow(QWidget):
    # 左键单击（未发生拖拽）→ 弹出圆形菜单
    clicked = Signal()
    # 请求打开设置
    settings_requested = Signal()
    # 请求退出
    quit_requested = Signal()
    # 全屏挂起状态变化：True=进入挂起（桌宠已隐藏），False=恢复显示
    fullscreen_paused = Signal(bool)
    # 鼠标悬停在宠物身上变化（音乐控制栏等据此显隐）
    hover_changed = Signal(bool)
    # 键盘工作联动状态变化（边工作边听音乐形象据此切换）
    work_changed = Signal(bool)
    # 请求重启（右键菜单 → main.py 另起新实例后退出）
    restart_requested = Signal()

    MOVE_THRESHOLD = 8  # px，超过视为拖拽而非点击
    SNAP_VISIBLE = 60   # 挂边后露出的像素（便于点回来）
    WORK_ACTIVE_SECONDS = 5  # 停止输入超过此时长(秒)后，退出“工作”状态
    FAINT_SPEED = 1500  # px/s，拖拽速度超过此值 → 晕倒
    FAINT_DIST = 500    # px，累计拖动距离超过此值 → 晕倒

    def __init__(self, cfg: dict, sfx=None):
        super().__init__()
        self._cfg = cfg
        self._sfx = sfx             # 音效管理器（可空）
        self._drag_offset = None
        self._press_gpos = QPoint()
        self._moved_dist = 0
        self._faint = False          # 晕倒中（快速/大范围拖动）
        self._last_move_ts = None    # 拖拽速度检测：上次移动时刻
        self._last_move_pos = None   # 拖拽速度检测：上次移动位置
        self._wander_enabled = bool(cfg.get("wander", True))
        self._wandering = False
        self._bubble = SpeechBubble()
        self._follow_bubbles = []   # 额外随宠物移动的气泡（如剪贴板助手按钮气泡）
        self._music_hover = False   # 悬停广播去重（hover_changed）

        # ---- 交互状态机状态 ----
        self._energy_state = "normal"      # 体力系统状态（happy/normal/hungry）
        self._display_state = None         # 实际渲染状态
        self._overlay = None               # 临时状态（yawn/pet）
        self._sleeping = False             # 睡眠动画中
        self._hanging = False              # 挂边待机中
        self._hang_side = None             # 挂边方向：left / right / bottom
        self._press_was_hang = False       # 本次点击是否从挂边状态开始（点出来不弹圆盘）
        self._hang_restore = None          # 挂边提醒跳出后待回归的 (side, pos)
        self._yawned = False               # 本次闲置是否已打过哈欠
        self._working = False              # 敲键盘工作联动中
        self._reading = False              # 长时间不理 → 看书待机中
        self._gaze_enabled = bool(cfg.get("interact_gaze", True))
        self._gaze_dist = int(cfg.get("interact_gaze_dist", 160))
        self._gaze_active = False          # 光标是否处于眼神跟随范围（靠近时优先跟随）
        self._hang_snap = int(cfg.get("interact_hang_snap", 24))  # 挂边触发距离(px)
        # ---- 局部点击：双击宠物 → 触发翻口袋交互 ----
        self._pocket_enabled = bool(cfg.get("pocket_click_enabled", False))
        self._pocket_active = False        # 口袋交互播放中（用于结束后的收尾）
        # 单击菜单延迟判定：等待可能到来的双击（双击=翻口袋，不弹菜单）
        self._pending_click = False
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._emit_pending_click)
        # ---- 悬停 3 秒显示体力/彩蛋提示 ----
        self._hover_since = None           # 悬停起始时刻（time.monotonic）
        self._tip_shown = False            # 3 秒体力提示是否已显示
        self._tip_text = "体力：100/100   🥚 彩蛋：0"
        self.setToolTip("")                # 关闭系统默认悬停提示（改为 3 秒触发）
        # ---- 防打扰（鼠标穿透） ----
        self._dnm = bool(cfg.get("dnm_enabled", False))
        self._dnm_auto_min = int(cfg.get("dnm_auto_min", 0))
        self._dnm_auto_active = False      # 是否为“空闲自动开启”的穿透

        # ---- 窗口基础属性 ----
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("桌宠")
        # 设置 WS_EX_NOACTIVATE：点击桌宠时不激活窗口，避免打断全屏视频的焦点。
        # 鼠标事件（点击/拖拽/右键菜单）正常接收，但窗口不会夺取输入焦点，
        # 从而全屏视频底下的任务栏不会弹出。
        self._apply_noactivate()

        # ---- 宠物渲染 ----
        size = int(cfg.get("pet_size", 120))
        gif = _resolve_pet_gif(cfg)
        self._renderer = PetRenderer(
            gif_path=gif if gif.startswith(("assets", "./")) or "/" in gif or "\\" in gif
                        else f"{ASSETS_DIR}/{gif}",
            size=size,
            skin=cfg.get("pet_skin", "哆啦A梦"),
            action_dir=norm_project_path(cfg.get("action_img_dir", "")),
            action_images=cfg.get("action_images", {}),
            props=cfg.get("props", {}),
            idle_dir=norm_project_path(cfg.get("idle_dir", "")),
            idle_images=cfg.get("idle_images", {}),
            emotion_keys=cfg.get("hover_emotions"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._renderer)

        # 尺寸：渲染尺寸 + 底部一点留白
        self.setFixedSize(size, size + 8)

        # ---- 游走逻辑 ----
        # 速度与跑步双帧动画匹配：双腿摆动时身体要明显前进，才有真实跑步感。
        # 横向 50~100px/s（2~4px/40ms 帧），纵向缓降保持自然。
        self._vx = random.choice([-1, 1]) * random.uniform(2.0, 4.0)
        self._vy = random.uniform(0.3, 0.9)
        self._wander_timer = QTimer(self)
        self._wander_timer.timeout.connect(self._wander_step)
        if self._wander_enabled:
            self._wander_timer.start(40)

        # ---- 交互状态机定时器 ----
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._cursor_step)
        self._cursor_timer.start(50)            # 光标跟随
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._idle_step)
        self._idle_timer.start(1000)            # 闲置检测
        # ---- 键盘工作联动：敲键盘 → 显示"敲键盘工作"素材 ----
        self._work_timer = QTimer(self)
        self._work_timer.timeout.connect(self._work_step)
        self._work_timer.start(500)             # 键盘活动轮询

        # ---- 全屏检测：前台窗口全屏 → 挂边待机（挂起） ----
        self._fs_paused = False          # 当前是否处于全屏挂起状态
        self._fs_prev_pos = None         # 挂起前的位置（退出全屏恢复用）
        self._fs_suspend_hang = False    # 挂起时是否动了挂边位置
        self._fs_hidden = False          # 挂起方式为 hide 时是否已隐藏
        self._fs_pause_enabled = bool(cfg.get("fullscreen_pause_enabled", True))
        self._fs_mode = cfg.get("fullscreen_pause_mode", "hang")  # hang / hide
        self._fs_timer = QTimer(self)
        self._fs_timer.timeout.connect(self._fullscreen_check)
        self._fs_timer.start(1000)       # 每秒检测一次

        # 初始同步一次渲染状态
        self._update_display()

    def _apply_noactivate(self):
        """Win32 设置 WS_EX_NOACTIVATE：点击不激活窗口，不打断全屏应用焦点。

        必须在窗口句柄创建后再调用才有效，因此 __init__ 与 showEvent 各调一次。
        """
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            hwnd = int(self.winId())
            styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, styles | WS_EX_NOACTIVATE)
        except Exception:
            pass   # 非 Windows 或句柄未就绪时静默跳过

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_noactivate()            # 句柄就绪后再应用一次
        self._set_passthrough(self._dnm)    # 窗口创建后应用鼠标穿透

    # ---------- 全屏检测（前台窗口全屏 → 自动隐藏桌宠，不影响观影） ----------
    def _fullscreen_check(self):
        """每秒检测前台窗口是否全屏。是则隐藏桌宠并暂停提醒，退出全屏自动恢复。

        检测原理：取前台窗口的客户区，与屏幕工作区对比。当客户区占据整个
        工作区（或更大）时视为全屏。此方法不依赖系统托盘，视频/游戏/浏览器
        全屏均可检测。
        """
        if not self._fs_pause_enabled:
            return
        if self._drag_offset is not None:
            return   # 正在拖拽桌宠时不触发挂起，避免拖拽被中断
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return
            # 桌面外壳窗口（Progman / WorkerW）本身就覆盖整个屏幕，
            # 需排除，否则在桌面上会被误判为“全屏”而触发挂边。
            if _is_shell_window(hwnd):
                return
            rect = wintypes.RECT()
            ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
            # 客户区宽高
            cw = rect.right - rect.left
            ch = rect.bottom - rect.top
            # 前台窗口所在屏幕的完整区域（含任务栏）。
            # 用完整屏幕而非工作区：最大化窗口客户区==工作区（不含任务栏），
            # 不会被误判成全屏；只有真正覆盖整个屏幕（含任务栏）才算全屏。
            screen = QGuiApplication.screenAt(self.geometry().center()) \
                or QGuiApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.geometry()
            # 全屏：客户区宽 >= 屏幕宽 且 客户区高 >= 屏幕高
            is_fullscreen = cw >= geo.width() and ch >= geo.height()
        except Exception:
            return

        if is_fullscreen == self._fs_paused:
            return   # 状态无变化
        self._fs_paused = is_fullscreen
        if is_fullscreen:
            self._fs_suspend()
            self.fullscreen_paused.emit(True)
        else:
            self._fs_resume()
            self.fullscreen_paused.emit(False)
            self.raise_()                   # 重新置顶

    def _fs_suspend(self):
        """全屏挂起：按挂起方式处理——hang=挂边待机，hide=完全隐藏。"""
        self._bubble.hide()
        for b in self._follow_bubbles:
            b.hide()
        self.pause_wander(True)
        if self._fs_mode == "hide":
            # 完全隐藏：不遮挡画面，退出全屏后恢复显示
            self._fs_hidden = True
            self.hide()
            return
        # 挂边待机：与手动拖拽挂边完全一致（_hanging 状态 + hang 挂边形象 +
        # SNAP_VISIBLE 露出像素），保证形象完整可见、点击可恢复，
        # 且闲置的哈欠/睡觉/看书不会覆盖挂边形象。
        if self._hanging:
            # 已在手动挂边：保持位置不动，仅暂停游走
            return
        self._fs_prev_pos = self.pos()
        self._fs_suspend_hang = True
        # 先置为挂边状态再叫醒：_wake 因 _hanging=True 不会误恢复游走，
        # 且能清掉入睡/哈欠等旧形象，确保挂边形象稳定显示
        self._hanging = True
        self._hang_side = "right"
        if self._sleeping:
            self._wake()
        screen = QGuiApplication.screenAt(self.geometry().center()) \
            or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        y = min(max(self.y(), geo.top()), geo.bottom() - self.height())
        self.move(geo.right() - self.SNAP_VISIBLE, y)
        # 与手动挂边一致：重置镜像，走状态机，再挂 hang_right 形象
        self._renderer.set_mirrored(False)
        self._update_display()
        self._renderer.set_persistent_action("hang_right")

    def _fs_resume(self):
        """退出全屏：按挂起方式恢复挂起前的显示状态。"""
        if self._fs_mode == "hide":
            if self._fs_hidden:
                self._fs_hidden = False
                self.show()
                self.raise_()
                if not self._hanging:
                    self.pause_wander(False)
            return
        if getattr(self, "_fs_suspend_hang", False):
            # 解除全屏挂边产生的挂边状态，恢复挂起前位置（与手动解挂一致）
            self._fs_suspend_hang = False
            self._hanging = False
            self._hang_side = None
            self._renderer.clear_persistent_action()
            self._renderer.set_mirrored(False)
            if self._fs_prev_pos is not None:
                self.move(self._fs_prev_pos)
            self._update_display()
            if self._wander_enabled:
                self.pause_wander(False)
        elif not self._hanging:
            # 常规状态（未挂边）：恢复正常游走
            self.pause_wander(False)
        # 手动挂边（_hanging 仍为 True）：保持挂边不动，不恢复游走

    def moveEvent(self, event):
        """桌宠移动（拖动/游走/挂边等）时，让头顶气泡跟随。"""
        super().moveEvent(event)
        anchor = QPoint(self.geometry().center().x(), self.geometry().top())
        if self._bubble.isVisible():
            self._bubble.follow(anchor)
        for b in self._follow_bubbles:
            b.follow(anchor)

    def register_follow_bubble(self, bubble):
        """注册一个随宠物移动的悬浮气泡（如剪贴板助手按钮气泡）。"""
        if bubble not in self._follow_bubbles:
            self._follow_bubbles.append(bubble)

    # ---------- 动作图片 ----------
    def play_action(self, key: str, seconds: float = 3.0):
        """临时切换为动作图片，seconds 秒后自动恢复。"""
        self._renderer.play_action(key, seconds)

    @property
    def is_hanging(self) -> bool:
        """当前是否处于挂边待机状态（主程序据此决定提醒时是否跳出挂边）。"""
        return self._hanging

    def remind_while_hanging(self, action_key: str, seconds: float):
        """挂边待机时的提醒：暂时跳出挂边、完整显示提醒动作，seconds 后自动回归挂边。

        挂边时只露出 60px，提醒动作图显示不全，因此提示时把桌宠移回屏幕内
        完整展示，结束后再挂回边缘。非挂边状态返回 False（不跳出）。
        """
        if not self._hanging:
            return False
        side = self._hang_side or "right"
        self._hang_restore = (side, self.pos())
        # 解除挂边显示（游走保持暂停），移到屏幕内露出完整形象
        self._hanging = False
        self._hang_side = None
        self._renderer.clear_persistent_action()
        screen = QGuiApplication.screenAt(self.geometry().center()) \
            or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x, y, w, h = self.x(), self.y(), self.width(), self.height()
        if side == "left":
            x = geo.left() + 12
        elif side == "bottom":
            y = geo.bottom() - h - 12
        else:
            x = geo.right() - w - 12
        self.move(x, y)
        self._update_display()
        self.play_action(action_key, seconds)
        # 动作播放结束（留一点余量）后回归挂边
        QTimer.singleShot(int(seconds * 1000) + 300, self._restore_hang_after_remind)
        return True

    def _restore_hang_after_remind(self):
        """提醒动作播放结束后，把桌宠挂回原边缘位置与挂边形象。"""
        restore = getattr(self, "_hang_restore", None)
        if restore is None:
            return
        # 用户正在拖拽/接管桌宠，或已不在原挂边场景：放弃自动回归
        if self._drag_offset is not None or self._dnm:
            return
        self._hang_restore = None
        side, hang_pos = restore
        self._hanging = True
        self._hang_side = side
        self.end_action()
        self._renderer.set_mirrored(False)
        self.move(hang_pos)
        self._update_display()
        self._renderer.set_persistent_action(f"hang_{side}")

    def end_action(self):
        """立即结束临时动作图片。"""
        self._renderer.end_action()

    def set_persistent_action(self, key: str):
        """常驻显示动作图片（如睡觉/工作），直到 clear_persistent_action。"""
        self._renderer.set_persistent_action(key)

    def clear_persistent_action(self):
        self._renderer.clear_persistent_action()

    def set_festival_idle(self, key: str):
        """设置节日待机形象（替换静止待机图；空串=恢复默认）。"""
        self._renderer.set_festival_idle(key)

    def clear_festival_idle(self):
        self._renderer.clear_festival_idle()

    def set_reading(self, on: bool):
        """长时间不理 → 看书待机形象（有互动自动恢复）。"""
        self._renderer.set_reading(on)

    # ---------- 小道具叠加 ----------
    def show_prop(self, key: str, seconds: float = 1.5):
        """在宠物旁边临时叠加一个道具（爱心/闪光/…）。"""
        self._renderer.show_prop(key, seconds)

    def clear_prop(self):
        self._renderer.clear_prop()

    # ---------- 播放音乐音符特效 ----------
    def set_music_notes(self, on: bool):
        """播放音乐时两侧飘音符（♪♫ 升起摇曳）。"""
        self._renderer.set_music_notes(on)

    # ---------- 交互形象（脸红/拖动） ----------
    def set_blush(self, on: bool):
        """鼠标悬停 → 脸红。"""
        self._renderer.set_blush(on)

    def set_drag(self, on: bool):
        """按住拖动 → 独立形象。"""
        self._renderer.set_drag(on)

    # ---------- 位置初始化 ----------
    def place_default(self):
        """默认放到屏幕右下角，像悬浮球。"""
        screen = QGuiApplication.screenAt(QGuiApplication.primaryScreen().availableGeometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 40, geo.bottom() - self.height() - 60)

    # ---------- 游走 ----------
    def _can_wander(self) -> bool:
        """游走优先级最低：只有完全空闲（无事件占用）时才允许移动。

        任何交互/动作（拖拽、挂边、睡觉、防打扰、临时动作、工作联动、
        看书、眼神跟随）发生时都停止游走，事件结束自动恢复。
        """
        if not self._wander_enabled:
            return False
        if self._drag_offset is not None:    # 拖拽中
            return False
        if self._hanging or self._sleeping or self._dnm:  # 挂边/睡觉/防打扰
            return False
        if self._overlay is not None:        # 临时动作（点击/打哈欠/提醒）
            return False
        if self._working:                    # 敲键盘工作联动
            return False
        if self._reading:                    # 看书待机
            return False
        if self._gaze_active:                # 眼神跟随（光标靠近）
            return False
        return True

    def _wander_step(self):
        """屏幕游走：仅在完全空闲时移动并显示跑步双帧动画。

        无事件时按速度前进（碰到屏幕边缘反弹）；任何事件占用或位置未变时
        停止游走并恢复静止形象（idle），事件结束自动继续。
        """
        if not self._can_wander():
            self._renderer.set_running(False)   # 事件占用 → 恢复静止形象
            return
        geo = QGuiApplication.screenAt(self.geometry().center()).availableGeometry()
        x, y = self.x(), self.y()
        nx, ny = x + self._vx, y + self._vy
        if nx <= geo.left():
            nx, self._vx = geo.left(), abs(self._vx)
        elif nx + self.width() >= geo.right():
            nx, self._vx = geo.right() - self.width(), -abs(self._vx)
        if ny <= geo.top():
            ny, self._vy = geo.top(), abs(self._vy)
        elif ny + self.height() >= geo.bottom():
            ny, self._vy = geo.bottom() - self.height(), -abs(self._vy)
        if (nx, ny) == (x, y):
            self._renderer.set_running(False)   # 位置未变（贴边）→ 不跑步
            return
        self._renderer.set_running(True, "left" if self._vx < 0 else "right")
        self.move(nx, ny)

    def pause_wander(self, paused: bool):
        if paused:
            self._wander_timer.stop()
            self._renderer.set_running(False)   # 停止游走 → 恢复正常形象
        elif self._wander_enabled:
            self._wander_timer.start(40)

    # ---------- 鼠标交互 ----------
    def _play_pocket(self):
        """翻口袋交互（双击触发）：伸手套口袋 → 展示道具 → 掏出小星星 + 星星道具。"""
        self._renderer.play_action("pocket_reach", 0.9)
        QTimer.singleShot(900,
                          lambda: self._renderer.play_action("pocket_show", 0.9))
        QTimer.singleShot(1800, lambda: (
            self._renderer.play_action("pocket_star", 1.5),
            self._renderer.show_prop("star", 1.5)))
        QTimer.singleShot(1900,
                          lambda: self.show_bubble("✨ 从口袋里掏出颗小星星～", 1800))
        QTimer.singleShot(3400, self._end_pocket)   # 序列结束恢复游走

    def _end_pocket(self):
        self._pocket_active = False
        if self._drag_offset is None:
            self.pause_wander(False)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._pocket_enabled \
                and not self._dnm:
            # 双击 → 翻口袋交互（替代原先的局部点击热区，位置不再难定位）
            self._pending_click = False
            self._single_click_timer.stop()
            if self._sleeping:
                self._wake()
            self._pocket_active = True
            self.pause_wander(True)
            if self._sfx is not None:
                self._sfx.play("pocket")
            self._play_pocket()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._sfx is not None:
                self._sfx.play("click")
            # 记录本次点击是否从挂边状态开始：挂边点出来只恢复桌宠、不弹圆盘
            self._press_was_hang = self._hanging
            # 从挂边状态恢复，进入常规拖拽/点击
            self._restore_from_hang()
            # 睡眠中被触碰 → 叫醒
            if self._sleeping and not self._dnm:
                self._wake()
            # 点击/抚摸 → 进入拖动形象（开心欢呼）+ 飘爱心道具
            self._play_overlay("pet", 1.2)
            self._renderer.play_feed_effect()
            self._renderer.set_drag(True)
            self._renderer.show_prop("heart", 1.4)
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_gpos = event.globalPosition().toPoint()
            self._moved_dist = 0
            # 以按下时刻/位置为速度基准，第一次移动即可估算速度
            self._last_move_ts = time.monotonic()
            self._last_move_pos = event.globalPosition().toPoint()
            self._set_faint(False)
            self.pause_wander(True)

    def _set_faint(self, on: bool):
        """切换晕倒形象（拖拽中快速/大范围移动时显示晕倒，覆盖开心拖动图）。"""
        if on == self._faint:
            return
        self._faint = on
        self._renderer.set_faint(on)

    def _check_faint(self, pos: QPoint):
        """拖拽速度/距离检测：快速移动或大范围拖动 → 晕倒。

        速度用相邻两次鼠标事件的位移/时间差估算；大范围用累计拖动距离。
        速度放缓且距离不大时恢复开心拖动形象（衔接）。
        """
        now = time.monotonic()
        speed = 0.0
        if self._last_move_ts is not None:
            dt = now - self._last_move_ts
            if dt > 0:
                speed = (pos - self._last_move_pos).manhattanLength() / dt
        self._last_move_ts = now
        self._last_move_pos = pos
        if speed > self.FAINT_SPEED or self._moved_dist > self.FAINT_DIST:
            self._set_faint(True)
        elif self._faint and speed < self.FAINT_SPEED * 0.5 \
                and self._moved_dist <= self.FAINT_DIST:
            self._set_faint(False)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            pos = event.globalPosition().toPoint()
            self.move(pos - self._drag_offset)
            dist = (pos - self._press_gpos).manhattanLength()
            if dist > self._moved_dist:
                self._moved_dist = dist
            self._renderer.set_mirrored(self.x() + self.width() / 2 <
                                        self._press_gpos.x())
            # 快速/大范围拖动 → 晕倒
            self._check_faint(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            was_faint = self._faint
            self._set_faint(False)           # 结束拖拽中的晕倒层
            self.pause_wander(False)
            self._renderer.set_drag(False)   # 结束拖动形象
            if was_faint:
                # 释放后维持晕倒 3 秒再恢复（快速/大范围拖动后“晕”一会儿）
                self._renderer.play_action("faint", 3.0)
                self._renderer.show_prop("sparkle", 3.0)
                # 大范围拖到边缘时不立即挂边，避免晕倒形象被挂边图覆盖
                return
            if self._moved_dist <= self.MOVE_THRESHOLD:
                # 单击互动 → 挥手打招呼 + 爱心（完整播完再回待机，避免像一闪而过）
                self._renderer.play_action("wave", 2.2)
                self._renderer.show_prop("heart", 1.2)
                # 圆盘菜单延迟弹出，等待可能到来的双击（双击=翻口袋，不弹菜单）。
                # 从挂边点出来：只打招呼恢复桌宠，不弹圆盘菜单
                # （取回桌宠与打开菜单是两种意图，不应绑定在同一次点击上）
                if not self._press_was_hang:
                    self._pending_click = True
                    self._single_click_timer.start(
                        QApplication.doubleClickInterval() + 30)
            else:
                # 拖拽结束：靠近屏幕边缘则挂边待机
                self._maybe_hang()

    def _emit_pending_click(self):
        """延迟判定结束：确认是单击（未出现双击），弹出圆盘菜单。"""
        if not self._pending_click:
            return
        self._pending_click = False
        if not self.isVisible():   # 宠物被隐藏时不再弹菜单
            return
        self.clicked.emit()

    # ---------- 交互状态机 ----------
    @staticmethod
    def _system_idle_seconds() -> float:
        """Windows 键盘/鼠标空闲秒数（GetLastInputInfo）。"""
        try:
            import ctypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(lii)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
        except Exception:
            return 0.0

    def _cursor_step(self):
        """光标靠近 → 眼神跟随；悬停 → 脸红；靠近睡眠中的宠物会把它叫醒。"""
        pos = QCursor.pos()
        center = self.frameGeometry().center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        dist = math.hypot(dx, dy)
        # 鼠标悬停在宠物身上 → 脸红（睡觉/挂边/拖动时不脸红）
        on_pet = self.frameGeometry().contains(pos)
        # 悬停状态广播（音乐控制栏据此显隐）：隐藏/勿扰/拖动中不算
        hover = on_pet and self.isVisible() and not self._dnm \
            and self._drag_offset is None
        if hover != self._music_hover:
            self._music_hover = hover
            self.hover_changed.emit(hover)
        self._renderer.set_blush(
            on_pet and not self._sleeping and not self._hanging
            and not self._dnm and self._drag_offset is None)
        # 悬停满 3 秒 → 显示体力/彩蛋提示
        self._update_hover_tip(on_pet)
        # 光标凑近宠物 → 立即叫醒（不依赖系统空闲判断，避免长时间空闲后"没反应"）
        if self._sleeping and not self._dnm and dist < self._gaze_dist:
            self._wake()
        if self._sleeping or self._hanging or self._overlay is not None \
                or not self._gaze_enabled:
            self._gaze_active = False
            self._set_gaze(0.0, 0.0)
            return
        if on_pet:
            # 光标在宠物身上：保留脸红，眼神回正（不按方向切换）
            self._gaze_active = True
            self._renderer.set_work(False)   # 靠近/悬停 → 优先眼神跟随，暂停工作图
            self._set_gaze(0.0, 0.0)
        elif 0 < dist < self._gaze_dist:
            # 光标靠近宠物 → 眼神跟随（暂停工作图，避免被 GetLastInputInfo 触发的工作图盖住）
            self._gaze_active = True
            self._renderer.set_work(False)
            self._set_gaze(dx / self._gaze_dist, dy / self._gaze_dist)
        else:
            self._gaze_active = False
            self._set_gaze(0.0, 0.0)

    def _set_gaze(self, lx: float, ly: float):
        self._renderer.set_look(lx, ly)

    def _update_hover_tip(self, on_pet: bool):
        """悬停满 3 秒才显示体力/彩蛋提示；移开立即隐藏。"""
        if self._dnm or self._drag_offset is not None:
            on_pet = False          # 鼠标穿透 / 拖动中不算悬停
        now = time.monotonic()
        if on_pet:
            if self._hover_since is None:
                self._hover_since = now
            elif not self._tip_shown and now - self._hover_since >= 3.0:
                self._tip_shown = True
                QToolTip.showText(QCursor.pos(), self._tip_text, self)
        else:
            if self._hover_since is not None:
                self._hover_since = None
                if self._tip_shown:
                    self._tip_shown = False
                    QToolTip.hideText()

    def _idle_step(self):
        """闲置检测：打哈欠 → 睡眠动画；空闲定时开启防打扰。"""
        idle = self._system_idle_seconds()
        # 自动防打扰：用户恢复操作即退出穿透
        if self._dnm_auto_active:
            if idle < 5:
                self._dnm_auto_active = False
                self.set_dnm(False)
            return
        if self._dnm:
            return  # 手动穿透常驻，等用户手动关闭
        if idle < 3:
            if self._sleeping:
                self._wake()
            self._yawned = False
            if self._reading:
                self._reading = False
                self._renderer.set_reading(False)
            return
        yawn_at = int(self._cfg.get("interact_yawn_sec", 90))
        sleep_at = int(self._cfg.get("interact_sleep_sec", 300))
        if not self._yawned and not self._sleeping and not self._hanging \
                and idle >= yawn_at:
            self._yawned = True
            if self._sfx is not None:
                self._sfx.play("yawn")
            self._play_overlay("yawn", 3.5)
            # 图片/GIF 形象没有嘴巴动画，用气泡提示打哈欠
            if self._renderer.using_image:
                self.show_bubble("哈欠～ 😪", 1600)
        # 夜间模式：过了深夜时段，空闲 1 分钟就入睡
        now_min = datetime.now().hour * 60 + datetime.now().minute
        late_at = int(float(self._cfg.get("late_hour", 22.5)) * 60)
        night = now_min >= late_at
        threshold = 60 if night else sleep_at
        if not self._sleeping and not self._hanging and idle >= threshold:
            self._sleep()
        # 长时间不理 → 看书待机（早于睡眠的过渡形象，有互动自动恢复）
        reading_at = int(self._cfg.get("reading_idle_sec", 150))
        # 看书必须早于睡眠出现：睡眠阈值太短时自动收窄，避免配置被覆盖后永不触发。
        # 默认配置下 reading(420s) << sleep(900s)，看书会一直显示到切换睡眠。
        reading_at = min(reading_at, max(0, threshold - 5))
        want_read = (self._cfg.get("reading_enabled", True)
                     and not self._sleeping and not self._hanging
                     and self._overlay is None and idle >= reading_at)
        if want_read != self._reading:
            self._reading = want_read
            self._renderer.set_reading(want_read)
        # 空闲达到设定时长 → 自动开启鼠标穿透
        if self._dnm_auto_min > 0 and idle >= self._dnm_auto_min * 60:
            self._dnm_auto_active = True
            self.set_dnm(True)

    def _play_overlay(self, name: str, seconds: float):
        self._overlay = name
        self._update_display()
        QTimer.singleShot(int(seconds * 1000),
                          lambda: self._clear_overlay(name))

    def _clear_overlay(self, name: str):
        if self._overlay == name:
            self._overlay = None
            self._update_display()

    def _update_display(self):
        """按优先级合成实际渲染状态：临时动作 > 挂边 > 睡眠 > 体力状态。"""
        if self._overlay is not None:
            st = self._overlay
        elif self._hanging:
            st = "hang"
        elif self._sleeping:
            st = "sleep"
        else:
            st = self._energy_state or "normal"
        if st != self._display_state:
            self._display_state = st
            self._renderer.set_state(st)

    def _sleep(self):
        self._sleeping = True
        self.pause_wander(True)
        if self._sfx is not None:
            self._sfx.play("sleep")
        self._update_display()

    def _wake(self):
        """叫醒宠物：清睡眠、清 overlay、恢复游走。"""
        self._sleeping = False
        if self._sfx is not None:
            self._sfx.play("wake")
        if self._overlay is not None:
            self._clear_overlay(self._overlay)
        if self._wander_enabled and not self._hanging:
            self.pause_wander(False)
        self._update_display()

    # ---------- 键盘工作联动（检测系统输入活动 → 显示"敲键盘工作"素材） ----------
    def _work_step(self):
        """轮询系统输入空闲（GetLastInputInfo，键盘/鼠标均可）：
        有输入活动则显示工作图，空闲超过阈值则恢复。
        光标靠近宠物（眼神跟随中）时暂停工作图，优先眼神跟随。
        """
        if not self._cfg.get("work_sync_enabled", True):
            if self._working:
                self._working = False
                self.work_changed.emit(False)
                self._renderer.set_work(False)
            return
        active = self._system_idle_seconds() < self.WORK_ACTIVE_SECONDS
        if active != self._working:
            self._working = active
            self.work_changed.emit(active)
        # 光标靠近宠物时眼神跟随优先，不覆盖工作图
        if active and not self._gaze_active:
            self._renderer.set_work(True)
        else:
            self._renderer.set_work(False)

    def _maybe_hang(self):
        """拖拽结束时宠物边缘已接触屏幕边框（部分出屏）→ 吸附挂边待机。"""
        if not self._cfg.get("interact_hang", True) or self._dnm:
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) \
            or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x, y, w, h = self.x(), self.y(), self.width(), self.height()
        side = None
        if x <= geo.left():
            self.move(geo.left() - (w - self.SNAP_VISIBLE), y)
            side = "left"
        elif x + w >= geo.right():
            self.move(geo.right() - self.SNAP_VISIBLE, y)
            side = "right"
        elif y + h >= geo.bottom():
            self.move(x, geo.bottom() - self.SNAP_VISIBLE)
            side = "bottom"
        else:
            return
        self._hanging = True
        self._hang_side = side
        self.pause_wander(True)
        # 挂边图本身已含正确朝向 → 重置拖拽残留的镜像，避免左右挂边图被翻转
        self._renderer.set_mirrored(False)
        if self._sfx is not None:
            self._sfx.play("notify")
        self._update_display()
        # 挂边形象：左/右挂边显示对应挂边图；底部挂边无专用图则保持待命形象
        if side in ("left", "right"):
            self._renderer.set_persistent_action(f"hang_{side}")
        self.show_bubble("挂边待机啦～点我回来 👋", 1600)

    def _restore_from_hang(self):
        """点击宠物时从挂边状态恢复为常规位置。"""
        if not self._hanging:
            return
        self._hanging = False
        self._hang_side = None
        # 若当前是全屏挂起产生的挂边，用户点击接管后不再恢复原位，
        # 避免退出全屏时桌宠突然跳回挂起前的位置
        self._fs_suspend_hang = False
        self._renderer.clear_persistent_action()
        # 恢复后重置镜像，朝向由后续游走/拖拽逻辑重新决定
        self._renderer.set_mirrored(False)
        # 挂边时窗口中心可能落在屏幕外，screenAt 会返回 None → 用主屏兜底
        screen = QGuiApplication.screenAt(self.geometry().center()) \
            or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        w, h = self.width(), self.height()
        x = max(geo.left() + 4, min(self.x(), geo.right() - w - 4))
        y = max(geo.top() + 4, min(self.y(), geo.bottom() - h - 4))
        self.move(x, y)
        if self._wander_enabled:
            self.pause_wander(False)
        self._update_display()

    # ---------- 防打扰（鼠标穿透） ----------
    @property
    def dnm(self) -> bool:
        return self._dnm

    def set_dnm(self, on: bool):
        """开启/关闭鼠标穿透。开启时宠物进入睡眠动画，不拦截任何点击。"""
        on = bool(on)
        self._cfg["dnm_enabled"] = on
        self._dnm = on
        self._set_passthrough(on)
        if on:
            self._sleeping = True
            self.pause_wander(True)
        else:
            self._sleeping = False
            self._yawned = False
            if self._wander_enabled and not self._hanging:
                self.pause_wander(False)
        self._update_display()

    def _set_passthrough(self, on: bool):
        """Win32 运行时切换鼠标穿透（WS_EX_TRANSPARENT），失败则退回 Qt 属性。"""
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            hwnd = int(self.winId())
            styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            styles = (styles | WS_EX_TRANSPARENT) if on \
                else (styles & ~WS_EX_TRANSPARENT)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, styles)
        except Exception:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, on)

    # ---------- 喂食 / 状态 / 气泡 ----------
    def show_bubble(self, text: str, duration_ms: int = 1600):
        """在宠物头顶上方弹气泡提示（不遮挡宠物本体）。"""
        center = self.geometry().center()
        top = QPoint(center.x(), self.geometry().top())
        self._bubble.popup(text, top, duration_ms)

    def set_pet_state(self, state: str):
        """同步宠物表情状态：happy / normal / hungry。"""
        self._energy_state = state if state in ("happy", "hungry", "normal") \
            else "normal"
        self._update_display()

    def play_feed_effect(self):
        """播放喂食特效：弹跳 + 爱心粒子。"""
        self._renderer.play_feed_effect()

    def set_energy_tooltip(self, energy: int, eggs: int = 0,
                           level: int = 1, streak: int = 0):
        """记录成长/体力/彩蛋文本；悬停满 3 秒时显示（已显示则同步刷新）。"""
        self._tip_text = (f"Lv.{level}  体力：{energy}/100  🥚 彩蛋：{eggs}"
                          + (f"  🔥 连续{streak}天" if streak else ""))
        if self._tip_shown:
            QToolTip.showText(QCursor.pos(), self._tip_text, self)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_settings = QAction("设置…", menu)
        act_restart = QAction("重启", menu)
        act_quit = QAction("退出", menu)
        act_settings.triggered.connect(self.settings_requested.emit)
        act_restart.triggered.connect(self.restart_requested.emit)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_settings)
        menu.addAction(act_restart)
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.exec(event.globalPos())

    # ---------- 配置同步 ----------
    def apply_config(self, cfg: dict):
        self._cfg = cfg
        size = int(cfg.get("pet_size", 120))
        self.setFixedSize(size, size + 8)
        self._renderer.setFixedSize(size, size)
        self._renderer.set_source(_resolve_pet_gif(cfg))
        self._renderer.set_skin(cfg.get("pet_skin", "哆啦A梦"))
        self._renderer.set_action_config(norm_project_path(cfg.get("action_img_dir", "")),
                                         cfg.get("action_images", {}),
                                         cfg.get("props", {}),
                                         norm_project_path(cfg.get("idle_dir", "")),
                                         cfg.get("idle_images", {}))
        # 置顶
        on_top = bool(cfg.get("always_on_top", True))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on_top)
        self.show()
        # 游走开关
        self._wander_enabled = bool(cfg.get("wander", True))
        if self._wander_enabled:
            self._wander_timer.start(40)
        else:
            self._wander_timer.stop()
        # 全屏挂起开关与模式：关闭时若正处于挂起（挂边/隐藏），立即恢复原位
        self._fs_pause_enabled = bool(cfg.get("fullscreen_pause_enabled", True))
        self._fs_mode = cfg.get("fullscreen_pause_mode", "hang")
        if not self._fs_pause_enabled and self._fs_paused:
            self._fs_paused = False
            self._fs_resume()
        # 交互与防打扰配置
        self._gaze_enabled = bool(cfg.get("interact_gaze", True))
        self._gaze_dist = int(cfg.get("interact_gaze_dist", 160))
        self._dnm_auto_min = int(cfg.get("dnm_auto_min", 0))
        if bool(cfg.get("dnm_enabled", False)) != self._dnm:
            self.set_dnm(bool(cfg.get("dnm_enabled", False)))
        else:
            self._set_passthrough(self._dnm)
        # 音效配置同步
        if self._sfx is not None:
            self._sfx.apply_config(cfg)
        self._update_display()
