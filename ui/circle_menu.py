# -*- coding: utf-8 -*-
"""圆形快捷菜单（哆啦A梦主题）：应用图标环绕排列，中心为红色鼻子关闭按钮，
点击外部自动关闭。整体风格贴近哆啦A梦：蓝色圆盘 + 白色描边圆环 + 白脸/黄铃铛按钮。
"""
import math

from PySide6.QtCore import Qt, QPoint, QRectF, Signal, QEvent, QFileInfo
from PySide6.QtGui import (QPainter, QColor, QFont, QIcon, QBrush,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import (QWidget, QPushButton, QApplication,
                               QFileIconProvider)

# ---- 尺寸（比旧版更紧凑） ----
MENU_RADIUS = 102    # 菜单面板半径（旧 130）
BTN_RADIUS = 22      # 图标按钮半径（旧 30）
CENTER_BTN = 24      # 中心关闭按钮半径（旧 34）

# ---- 哆啦A梦配色 ----
_BLUE_LIGHT = (45, 181, 253)     # 体色亮蓝 #2DB5FD
_BLUE_DEEP = (5, 100, 241)       # 体色深蓝 #0564F1
_RING_WHITE = (255, 255, 255)

# 应用按钮样式（白脸蓝边）
APP_QSS = """
    QPushButton {
        background: qradialgradient(cx:0.35, cy:0.35, radius:1,
            stop:0 rgba(255,255,255,255), stop:0.75 rgba(238,247,255,255),
            stop:1 rgba(198,226,255,255));
        border: 2px solid #2DB5FD;
        border-radius: %dpx;
        color: #0564F1;
        font-weight: bold;
    }
    QPushButton:hover {
        background: qradialgradient(cx:0.35, cy:0.35, radius:1,
            stop:0 rgba(255,255,255,255), stop:0.7 rgba(255,244,200,255),
            stop:1 rgba(255,213,90,255));
        border: 2px solid #FFCB00;
        color: #7a5a00;
    }
    QPushButton:pressed {
        background: qradialgradient(cx:0.35, cy:0.35, radius:1,
            stop:0 rgba(235,244,255,255), stop:1 rgba(120,175,255,255));
        border: 2px solid #0564F1;
    }
"""

# 动作按钮样式（黄色铃铛渐变）
ACTION_QSS = """
    QPushButton {
        background: qradialgradient(cx:0.35, cy:0.35, radius:1,
            stop:0 rgba(255,255,255,255), stop:0.55 rgba(255,238,170,255),
            stop:1 rgba(255,203,0,255));
        border: 2px solid #FFCB00;
        border-radius: %dpx;
        color: #7a5a00;
        font-weight: bold;
    }
    QPushButton:hover {
        background: qradialgradient(cx:0.35, cy:0.35, radius:1,
            stop:0 rgba(255,255,255,255), stop:0.6 rgba(255,224,120,255),
            stop:1 rgba(255,190,0,255));
        border: 2px solid #FFCB00;
    }
    QPushButton:pressed {
        background: qradialgradient(cx:0.35, cy:0.35, radius:1,
            stop:0 rgba(255,244,205,255), stop:1 rgba(230,165,0,255));
        border: 2px solid #b8860b;
    }
"""


class _MenuItem(QPushButton):
    """圆形图标按钮。kind='app' 优先用系统图标；kind='action' 用 emoji+黄色铃铛。"""

    def __init__(self, app: dict, kind: str = "app", radius=BTN_RADIUS, parent=None):
        super().__init__(parent)
        self.app = app
        self.setFixedSize(radius * 2, radius * 2)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(app.get("name", ""))

        path = app.get("path") or ""
        if kind == "app" and path and QFileInfo(path).isFile():
            icon = QFileIconProvider().icon(QFileInfo(path))
            self.setIcon(icon)
            self.setIconSize(self.size())
        else:
            self.setText(app.get("icon", "❓"))
            self.setFont(QFont("Segoe UI Emoji", radius // 2))

        self.setStyleSheet((ACTION_QSS if kind == "action" else APP_QSS) % radius)


class CircleMenu(QWidget):
    """应用与动作按钮环绕排列的圆形菜单，点击外部区域自动关闭。"""
    item_clicked = Signal(dict)      # 发射 app 字典
    action_triggered = Signal(str)   # 发射动作 key，如 "feed"

    def __init__(self, apps: list, actions: list | None = None, parent=None):
        super().__init__(parent)
        self._items = []
        self._bottom_free = False     # 底部正中是否有空间画微笑弧线（仅 n=3/5 时成立）
        d = MENU_RADIUS * 2
        self.setFixedSize(d, d)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)

        # 点击外部关闭的全局事件过滤
        QApplication.instance().installEventFilter(self)

        # 中心关闭按钮 = 哆啦A梦的红鼻子
        close = QPushButton("✕", self)
        close.setFixedSize(CENTER_BTN * 2, CENTER_BTN * 2)
        close.move(d // 2 - CENTER_BTN, d // 2 - CENTER_BTN)
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet("""
            QPushButton {
                background: qradialgradient(cx:0.35, cy:0.35, radius:1,
                    stop:0 rgba(255,120,120,255), stop:0.5 rgba(255,60,60,255),
                    stop:1 rgba(205,22,30,255));
                border: 2px solid rgba(255,255,255,220);
                border-radius: %dpx;
                color: white; font-size: 15px; font-weight: bold;
            }
            QPushButton:hover {
                background: qradialgradient(cx:0.35, cy:0.35, radius:1,
                    stop:0 rgba(255,150,150,255), stop:0.5 rgba(255,90,90,255),
                    stop:1 rgba(230,40,48,255));
            }
        """ % CENTER_BTN)
        close.clicked.connect(self.close)

        # 环绕排列：先应用、后动作
        entries = [("app", app) for app in apps]
        entries += [("action", a) for a in (actions or [])]
        n = len(entries)
        if n == 0:
            return
        # 微笑弧线需要底部正中有空隙：n=3 或 n=5 时底部两按钮正好让开正中
        self._bottom_free = n in (3, 5)
        angle_step = 2 * math.pi / n
        for i, (kind, data) in enumerate(entries):
            btn = _MenuItem(data, kind=kind, parent=self)
            # 从正上方开始，逆时针排列
            a = angle_step * i - math.pi / 2
            cx = d // 2 + int((MENU_RADIUS - BTN_RADIUS * 1.3) * math.cos(a))
            cy = d // 2 + int((MENU_RADIUS - BTN_RADIUS * 1.3) * math.sin(a))
            btn.move(cx - BTN_RADIUS, cy - BTN_RADIUS)
            if kind == "app":
                btn.clicked.connect(lambda checked=False, a_=data: self._click(a_))
            else:
                btn.clicked.connect(lambda checked=False, a_=data: self._action(a_))
            self._items.append(btn)

    def _click(self, app: dict):
        self.item_clicked.emit(app)
        self.close()

    def _action(self, action: dict):
        self.action_triggered.emit(action.get("key", ""))
        self.close()

    def show_at(self, pet_rect):
        """把圆盘放到宠物附近，避开宠物不遮挡。

        优先显示在宠物上方居中；上方空间不足时移到宠物下方，
        尽量完整显示在屏幕内，避免圆盘压住/盖住桌宠。
        pet_rect 为宠物窗口矩形（QRect），anchor 取其中心。
        """
        screen = QApplication.screenAt(pet_rect.center())
        geo = screen.availableGeometry() if screen \
            else QApplication.primaryScreen().availableGeometry()
        mw, mh = self.width(), self.height()
        gap = 8
        # 水平居中于宠物
        x = pet_rect.center().x() - mw // 2
        x = max(geo.left(), min(x, geo.right() - mw))
        # 优先放宠物上方（圆盘底边贴近宠物顶边）
        y = pet_rect.top() - mh - gap
        if y < geo.top():
            # 上方放不下 → 移到宠物下方
            y = pet_rect.bottom() + gap
            if y + mh > geo.bottom():
                # 上下都不够（屏幕极矮）：夹紧屏幕内，尽量完整显示
                y = max(geo.top(), min(y, geo.bottom() - mh))
        self.move(x, y)
        self.show()
        self.raise_()
        # 只置顶不激活：菜单是临时浮层，抢焦点会导致全屏视频底下弹出任务栏
        self._no_activate()

    def _no_activate(self):
        """Win32 设置 WS_EX_NOACTIVATE：点击菜单按钮时不激活窗口，避免打断全屏。"""
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            hwnd = int(self.winId())
            styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, styles | WS_EX_NOACTIVATE)
        except Exception:
            pass

    # ---------- 绘制哆啦A梦蓝色圆盘 + 白色描边 + 微笑弧线 ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # 蓝色身体（径向渐变，左上有高光）
        grad = QRadialGradient(cx * 0.4, cy * 0.4, w * 0.62)
        grad.setColorAt(0.0, QColor(*_BLUE_LIGHT, 235))
        grad.setColorAt(0.72, QColor(*_BLUE_LIGHT, 228))
        grad.setColorAt(1.0, QColor(*_BLUE_DEEP, 222))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(3, 3, w - 6, h - 6))

        # 白色描边圆环（像哆啦A梦脸部轮廓）
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(*_RING_WHITE, 235), 3))
        painter.drawEllipse(QRectF(5, 5, w - 10, h - 10))

        # 底部微笑弧线（白色小嘴，仅在底部无按钮时绘制）
        if self._bottom_free:
            pen = QPen(QColor(*_RING_WHITE, 235), 3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            smile_w = 40
            smile_y = h - 46
            painter.drawArc(QRectF(cx - smile_w / 2, smile_y,
                                   smile_w, smile_w),
                            180 * 16, 180 * 16)

    # ---------- 点击外部自动关闭 ----------
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            gpos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") \
                else event.globalPos()
            if self.isVisible() and not self.geometry().contains(gpos) \
                    and not self.underMouse():
                self.close()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
