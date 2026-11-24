# -*- coding: utf-8 -*-
"""聊天对话框：气泡消息 + 底部输入。

支持两种回复：
- 本地规则聊天（core.chatbot.ChatBot）
- 接入 AI（core.ai_client.AIClient，OpenAI 兼容接口，异步不卡 UI）
传入 ai_client 且配置好 Key 时优先走 AI，否则回退本地聊天。

外观（哆啦A梦主题）：
- 聊天背景图（内置主题 / 手动选择本地图 / 可关闭），右上角 🎨 按钮快捷切换
- 微信式消息头像（宠物=哆啦A梦，用户=默认头像，可开关）
"""
import math
import os
import random
import re

from PySide6.QtCore import Qt, QTimer, Signal, QPoint
from PySide6.QtGui import (QFont, QPixmap, QPainter, QColor,
                           QPainterPath, QTextDocument)
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QLineEdit, QScrollArea, QWidget,
                               QFrame, QMenu, QFileDialog)

from core.chatbot import ChatBot
from core.config import ASSETS_DIR, PROJECT_DIR, save_config
from ui.pet_animation import crop_sheet_cell

PET_AVATAR = "🐱"
USER_AVATAR = "🙂"
USER_COLOR = "#4a90d9"     # 用户气泡（蓝）
PET_COLOR = "#ffb347"      # 宠物气泡（橙）
BG = "#fdf6ec"
CHAT_BG_DEFAULT = os.path.join(ASSETS_DIR, "chat_bg", "doraemon_sky.jpg")


def _resolve_asset(path: str) -> str:
    """把配置里的资源路径解析成绝对路径（支持 assets/ 前缀与相对路径）。"""
    if not path:
        return ""
    if path.startswith("assets"):
        return os.path.join(ASSETS_DIR, path[len("assets"):].lstrip("/\\"))
    if not os.path.isabs(path):
        return os.path.join(PROJECT_DIR, path)
    return path


def _round_pixmap(pm: QPixmap, size: int = 36) -> QPixmap:
    """把图片裁剪成圆形（微信头像样式）。"""
    pm = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding,
                   Qt.SmoothTransformation)
    pm = pm.copy((pm.width() - size) // 2, (pm.height() - size) // 2,
                 size, size)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def _md_to_html(text: str) -> str:
    """把常见 markdown 子集转成 QLabel 可渲染的 HTML。

    支持：`**粗体**`、`*斜体*`、`- 列表项`、`# 标题`、`> 引用`、
    `---` 分割线、行内代码 `` ` ``、换行。
    纯文本会原样显示，不会破坏原有气泡。
    """
    if not text:
        return ""
    lines = text.split("\n")
    html_parts = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        # 分割线
        if stripped in ("---", "***", "___"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append('<hr style="border:none;border-top:1px solid #ccc;margin:6px 0;">')
            continue
        # 标题
        m = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if m:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            level = len(m.group(1))
            sizes = {1: 18, 2: 16, 3: 15}
            html_parts.append(f'<p style="font-weight:bold;font-size:{sizes[level]}px;margin:4px 0;">{m.group(2)}</p>')
            continue
        # 引用
        if stripped.startswith("> "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p style="color:#888;border-left:3px solid #ccc;padding-left:8px;margin:4px 0;">{stripped[2:]}</p>')
            continue
        # 列表项
        if stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:]
            if not in_list:
                html_parts.append('<ul style="margin:4px 0;padding-left:20px;">')
                in_list = True
            html_parts.append(f"<li>{_inline_md(item)}</li>")
            continue
        # 普通行
        if in_list and stripped == "":
            html_parts.append("</ul>")
            in_list = False
        if stripped == "":
            html_parts.append("<br>")
        else:
            html_parts.append(f'<p style="margin:2px 0;">{_inline_md(stripped)}</p>')
    if in_list:
        html_parts.append("</ul>")
    return "".join(html_parts)


def _inline_md(text: str) -> str:
    """处理行内 markdown：`**粗体**`、`*斜体*`、`` `代码` ``。"""
    # 先转义 HTML 特殊字符（但保留后续插入的标签）
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 行内代码
    text = re.sub(r"`([^`]+)`", r'<code style="background:#eee;padding:1px 4px;border-radius:3px;font-family:monospace;">\1</code>', text)
    # 粗体
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # 斜体
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text


class _Bubble(QLabel):
    """圆角消息气泡（自绘文本切片）。

    - 支持 markdown 渲染（粗体/列表/标题/引用/代码），AI 回复不再暴露原始符号
    - 用 QTextDocument 按"实际渲染字体"精确测量换行后的宽高并 setFixedSize，
      不依赖布局自动换行（嵌套布局里 QLabel 的 wordWrap 高度不可靠）。
      测量与绘制共用同一文档实例，保证结果一致。
    - 超长消息自动折叠（微信式）：高度超过折叠线时只显示顶部内容 +
      "展开全文"按钮。巨型 QLabel（数千像素高）是 Qt 渲染故障重灾区
      （文字消失、视觉重叠、布局被撑爆后各行互相叠画成"满屏聊天信息"），
      因此控件高度永远封顶 SAFE_MAX：展开后若内容仍超高，用滚轮在
      气泡内部滚动浏览，绝不把控件撑成巨型。
    - 文本用 drawContents 画切片：顶部对齐、按钮区不画文字。不再用
      嵌套 QPainter 裁剪（Qt 6.12 下 super().paintEvent 里的内建 painter
      与外层 painter 冲突，裁剪失效，文字会溢出盖住按钮）。
    - 代价：放弃鼠标选中文字（自绘接管后 QLabel 内建选区失效）。
    """

    COLLAPSE_LIMIT = 340   # 折叠高度上限（像素）
    SAFE_MAX = 1500        # 展开后控件高度上限（防巨型 QLabel 渲染故障）

    def __init__(self, text: str, color: str, text_color: str,
                 max_width: int, parent=None):
        super().__init__(parent)
        self._max_width = max_width
        self._color = color
        self._text_color = text_color
        # 显式指定字体（像素级确定），测量与渲染用同一字体，避免 QSS 生效
        # 前后字体不一致导致高度算少。
        font = QFont()
        font.setPixelSize(14)
        self.setFont(font)
        self._font = font
        # 自绘接管绘制，不再走 QLabel 的 setText / QSS 背景
        self.setStyleSheet("")
        self._doc = QTextDocument()
        self._doc.setDefaultFont(self._font)
        self._full_h = 0            # 完整内容高度（含内边距）
        self._w = 0                 # 测量得到的宽度（不依赖 self.width()）
        self._expanded = False      # 是否处于展开状态
        self._scroll_y = 0          # 展开后气泡内部滚动偏移（px）
        self._btn = None            # 展开/收起按钮（超长消息才有）
        self._raw_text = text       # 保存原始文本（含 markdown）
        self._set_content(text)

    # ---------- 尺寸测量与折叠 ----------
    def _measure(self, text: str):
        """返回 (宽, 完整高)。复用渲染同一文档，测量即渲染。"""
        pad_x, pad_y = 24, 16          # 与绘制内边距 12px/8px 对应
        text_w = max(self._max_width - pad_x, 20)
        doc = self._doc
        # 先取"不换行"的理想宽度：短文本气泡收窄，长文本限宽换行
        ideal = doc.idealWidth()
        used_w = min(ideal, text_w)
        doc.setTextWidth(used_w)
        h = math.ceil(doc.size().height())
        return math.ceil(used_w) + pad_x, h + pad_y + 2   # +2 防末行被裁

    def _apply_size(self):
        """按折叠/展开状态应用气泡尺寸，并管理按钮。

        任何状态下控件高度都不超过 SAFE_MAX，杜绝巨型 QLabel。
        """
        if self._full_h <= self.COLLAPSE_LIMIT:
            self.setFixedSize(self._w, max(self._full_h, 36))
            if self._btn is not None:
                self._btn.hide()
        else:
            h = min(self._full_h, self.SAFE_MAX) if self._expanded \
                else self.COLLAPSE_LIMIT
            self.setFixedSize(self._w, h)
            self._ensure_btn()
            self._btn.setText("收起 ▴" if self._expanded else "展开全文 ▾")
            self._btn.show()
            self._move_btn()
        self.update()

    def _ensure_btn(self):
        if self._btn is not None:
            return
        self._btn = QPushButton(self)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setAutoDefault(False)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,0,0,28);
                color: {self._text_color};
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                padding: 4px 0;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(0,0,0,55); }}
        """)
        self._btn.clicked.connect(self._toggle_expand)

    def _move_btn(self):
        """通栏按钮贴住气泡底部，占满宽度。"""
        if self._btn is None:
            return
        self._btn.setGeometry(2, self.height() - 24, self.width() - 4, 22)

    def _toggle_expand(self):
        if self._btn is None or self._full_h <= self.COLLAPSE_LIMIT:
            return   # 非超长消息无需展开
        self._expanded = not self._expanded
        self._scroll_y = 0
        self._apply_size()
        # 尺寸变化后通知对话框滚到该消息，避免展开后视野丢失
        dlg = self.window()
        if hasattr(dlg, "_scroll_bottom"):
            dlg._scroll_bottom(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._btn is not None and self._btn.isVisible():
            self._move_btn()

    def wheelEvent(self, event):
        """展开且内容超高时：滚轮在气泡内部滚动浏览，不冒泡给聊天列表。"""
        doc_h = max(self._full_h - 18, 0)          # 文档高（去掉内边距）
        visible_h = max(self.height() - 16 - 24, 1)  # 文本可视高（预留按钮）
        max_scroll = max(0, doc_h - visible_h)
        if self._expanded and max_scroll > 0:
            self._scroll_y = max(0.0, min(float(max_scroll),
                                self._scroll_y - event.angleDelta().y() / 2.0))
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def paintEvent(self, event):
        """自绘：圆角背景 + 文本切片（顶部对齐，按滚动偏移取窗）。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 圆角背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._color))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        # 文本切片：painter 裁剪出可视窗，translate 实现内部滚动。
        # 不用 drawContents(painter, rect) 取景窗语义（PySide6 下不生效）。
        pad_x, pad_y = 12, 8
        btn_h = 24 if (self._btn is not None and self._btn.isVisible()) else 0
        text_w = max(self.width() - 2 * pad_x, 20)
        visible_h = max(self.height() - 2 * pad_y - btn_h, 1)
        painter.setClipRect(pad_x, pad_y, text_w, visible_h)
        painter.translate(pad_x, pad_y - self._scroll_y)
        self._doc.setTextWidth(text_w)
        self._doc.drawContents(painter)
        painter.end()

    def _set_content(self, text: str):
        """设置文本：测量完整宽高并应用折叠规则（重置展开状态）。

        直接落到最终尺寸，绝不停留在"全高"状态——setFixedSize 对布局内
        子控件是立即生效的，瞬时数万像素的巨型尺寸会让布局/滚动条震荡，
        绘制帧被固化后就是"满屏叠画"的乱象。
        """
        self._raw_text = text
        # 外包一层 div 统一文字色（自绘后 QSS color 不再生效）
        html = f'<div style="color:{self._text_color}">{_md_to_html(text)}</div>'
        self._doc.setHtml(html)
        self._w, self._full_h = self._measure(text)
        self._expanded = False
        self._scroll_y = 0
        self._apply_size()
        # 触发父布局更新，确保 AI 回复替换"…"后布局正确刷新
        if self.parent():
            self.parent().updateGeometry()


class ChatDialog(QDialog):
    # AI 生成期间发出的信号（桌宠据此切换“敲键盘工作”素材）
    ai_started = Signal()
    ai_finished = Signal()
    # 用户在输入框打字时发出（桌宠据此显示“倾听姿势”）
    user_typing = Signal()
    # 用户发出消息时发出（主程序据此偶尔问心情）
    message_sent = Signal()

    def __init__(self, bot: ChatBot, ai_client=None, parent=None,
                 avatar_sheet: str = "", cfg: dict | None = None):
        super().__init__(parent)
        self.bot = bot
        self.ai = ai_client
        self._cfg = cfg or {}
        self._history = []        # 发给 AI 的对话历史 [{role,content}, ...]
        self._messages = []       # 界面展示记录 [(role,text), ...]（不含等待“…”）
        self._ai_bubble = None    # 兼容引用（同 _pending_bubbles[0]）
        self._pending_bubbles = []  # 等待回复的"…"气泡队列（连发消息时不丢回复）
        self._pending = False     # 是否正在等待 AI 回复
        self._last_role = None    # 上一条消息角色（连续同角色合并头像）
        self.setWindowTitle(f"{bot.pet_name} 的聊天室")
        self.setFixedSize(360, 480)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        # 背景图层（哆啦A梦主题），垫在所有控件下方
        self._bg_label = QLabel(self)
        self._bg_label.setStyleSheet("background: transparent;")
        self._bg_label.setGeometry(self.rect())

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # 顶部标题栏
        title_row = QHBoxLayout()
        avatar = QLabel()
        # 优先用素材表里的哆啦A梦形象（1行1列 = 全身正立）作头像
        dora = crop_sheet_cell(avatar_sheet, 1, 1, 40) if avatar_sheet else None
        if dora is not None:
            avatar.setPixmap(dora)
            avatar.setFixedSize(40, 40)
            avatar.setScaledContents(True)
        else:
            avatar.setText(PET_AVATAR)
            avatar.setFont(QFont("Segoe UI Emoji", 20))
        ai_ready = self.ai is not None and self.ai.is_ready()
        mode = "AI 模式" if ai_ready else "陪伴模式"
        name = QLabel(f"<b>{bot.pet_name}</b>  ·  {mode}")
        name.setStyleSheet("font-size:15px; color:#5a3a15;")
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton { background: rgba(200,80,80,200); color:white;
                          border:none; border-radius:14px; font-size:14px; }
            QPushButton:hover { background: rgba(220,60,60,235); }
        """)
        btn_close.clicked.connect(self.close)
        btn_close.setAutoDefault(False)
        btn_bg = QPushButton("🎨")
        btn_bg.setFixedSize(28, 28)
        btn_bg.setCursor(Qt.PointingHandCursor)
        btn_bg.setToolTip("聊天外观（背景 / 头像）")
        btn_bg.setStyleSheet("""
            QPushButton { background: rgba(90,160,250,200); color:white;
                          border:none; border-radius:14px; font-size:13px; }
            QPushButton:hover { background: rgba(60,140,240,235); }
        """)
        btn_bg.clicked.connect(lambda: self._bg_menu.exec(
            btn_bg.mapToGlobal(QPoint(0, btn_bg.height()))))
        btn_bg.setAutoDefault(False)
        title_row.addWidget(avatar)
        title_row.addWidget(name)
        title_row.addStretch(1)
        title_row.addWidget(btn_bg)
        title_row.addWidget(btn_close)
        root.addLayout(title_row)

        # 中间消息区（背景透明，露出下面的主题图）
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.scroll.viewport().setAutoFillBackground(False)
        container = QWidget()
        container.setAttribute(Qt.WA_TranslucentBackground, True)
        container.setAutoFillBackground(False)
        self.msg_layout = QVBoxLayout(container)
        self.msg_layout.setContentsMargins(4, 4, 4, 4)
        self.msg_layout.setSpacing(2)   # 行间距交给各消息行上边距控制
        self.msg_layout.addStretch(1)
        self.scroll.setWidget(container)
        root.addWidget(self.scroll, 1)

        # 底部输入
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("和" + bot.pet_name + "说点什么…")
        self.input.setStyleSheet("""
            QLineEdit {
                background: white;
                color: #333333;
                border: 1px solid #e6c99a;
                border-radius: 14px;
                padding: 8px 12px;
                font-size: 14px;
                selection-background-color: #ff9f43;
                selection-color: white;
            }
            QLineEdit:focus { border-color: #ff9f43; }
            QLineEdit::placeholder { color: #b0a08a; }
        """)
        self.input.returnPressed.connect(self._send)
        self.input.textChanged.connect(self._on_input_changed)
        btn_send = QPushButton("发送")
        btn_send.setCursor(Qt.PointingHandCursor)
        btn_send.setStyleSheet("""
            QPushButton { background: #ff9f43; color: white; border: none;
                          border-radius: 14px; padding: 8px 16px; font-size: 14px; }
            QPushButton:hover { background: #ff8c22; }
        """)
        btn_send.clicked.connect(self._send)
        btn_send.setAutoDefault(False)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(btn_send)
        root.addLayout(input_row)

        # 外观快捷菜单
        self._bg_menu = QMenu(self)
        act_theme = self._bg_menu.addAction("⭐ 内置哆啦A梦主题")
        act_pick = self._bg_menu.addAction("🖼 选择本地图片…")
        act_off = self._bg_menu.addAction("🚫 关闭背景")
        self._bg_menu.addSeparator()
        self.act_avatar = self._bg_menu.addAction("👤 聊天头像")
        self.act_avatar.setCheckable(True)
        self.act_avatar.setChecked(bool(self._cfg.get("chat_avatar_enabled", True)))
        act_theme.triggered.connect(lambda: self._set_bg(""))
        act_pick.triggered.connect(self._pick_bg)
        act_off.triggered.connect(self._off_bg)
        self.act_avatar.toggled.connect(self._toggle_avatar)

        # 消息头像素材
        self._pet_avatar_pm = None
        if avatar_sheet:
            self._pet_avatar_pm = _round_pixmap(
                crop_sheet_cell(avatar_sheet, 1, 1, 40), 36)
        self._user_avatar_pm = self._load_user_avatar()

        self._bg_label.lower()
        self._apply_bg()
        self._greeting()

    # ---------- 背景与头像 ----------
    def _load_user_avatar(self):
        path = _resolve_asset(self._cfg.get("chat_user_avatar") or "")
        if path and os.path.isfile(path):
            pm = QPixmap(path)
            if not pm.isNull():
                return _round_pixmap(pm, 36)
        return None

    def _bg_path(self) -> str:
        p = (self._cfg.get("chat_bg_path") or "").strip()
        if not p:
            return CHAT_BG_DEFAULT
        return _resolve_asset(p)

    def _apply_bg(self):
        """按配置加载背景图（cover 裁剪），失败或关闭则隐藏。"""
        if not self._cfg.get("chat_bg_enabled", True):
            self._bg_label.hide()
            return
        pm = QPixmap(self._bg_path())
        if pm.isNull():
            self._bg_label.hide()
            return
        w, h = self._bg_label.width(), self._bg_label.height()
        if w <= 0 or h <= 0:
            return
        scaled = pm.scaled(w, h, Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
        scaled = scaled.copy((scaled.width() - w) // 2, (scaled.height() - h) // 2,
                             w, h)
        self._bg_label.setPixmap(scaled)
        self._bg_label.show()

    def _set_bg(self, path: str):
        """应用指定背景图路径（空=内置主题），并写回配置。"""
        self._cfg["chat_bg_path"] = path or ""
        self._cfg["chat_bg_enabled"] = True
        save_config(self._cfg)
        self._apply_bg()

    def _pick_bg(self):
        fd = QFileDialog(self, "选择聊天背景图片", "",
                         "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        fd.setWindowModality(Qt.WindowModal)
        if fd.exec() and fd.selectedFiles():
            self._set_bg(fd.selectedFiles()[0])

    def _off_bg(self):
        self._cfg["chat_bg_enabled"] = False
        save_config(self._cfg)
        self._apply_bg()

    def _toggle_avatar(self, checked: bool):
        self._cfg["chat_avatar_enabled"] = bool(checked)
        save_config(self._cfg)
        self._refresh_messages()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg_label.setGeometry(self.rect())
        self._apply_bg()

    # ---------- 消息展示 ----------
    def _greeting(self):
        QTimer.singleShot(300, lambda: self.add_pet(
            f"你好呀～我是{self.bot.pet_name}！写代码累了就跟我说说话，"
            f"我也会提醒你吃饭喝水休息的 😊"))

    def _avatar_widget(self, role: str, show: bool = True) -> QLabel | None:
        """返回微信式头像控件。

        show=False（连续同角色消息）时返回同宽透明占位，保持气泡对齐；
        关闭头像功能时返回 None。
        """
        if not self._cfg.get("chat_avatar_enabled", True):
            return None
        lab = QLabel()
        lab.setFixedSize(36, 36)
        if not show:
            lab.setStyleSheet("background: transparent;")
            return lab
        if role == "pet":
            pm, emoji = self._pet_avatar_pm, PET_AVATAR
        else:
            pm, emoji = self._user_avatar_pm, USER_AVATAR
        if pm is not None and not pm.isNull():
            lab.setPixmap(pm)
            lab.setScaledContents(True)
        else:
            lab.setAlignment(Qt.AlignCenter)
            lab.setText(emoji)
            lab.setFont(QFont("Segoe UI Emoji", 16))
        return lab

    def add_user(self, text: str):
        self._render_message("user", text)

    def add_pet(self, text: str):
        return self._render_message("pet", text)

    def _bubble_max_width(self) -> int:
        """气泡最大宽度：随窗口宽度与头像开关自适应，保证长文本正常换行。"""
        base = max(self.width() - 28, 160)   # 去掉窗口 + 滚动区左右边距
        if self._cfg.get("chat_avatar_enabled", True):
            base -= 36 + 6                   # 头像宽 + 间距
        return max(140, int(base * 0.82))

    def _render_message(self, role: str, text: str, record: bool = True):
        """渲染一条消息：微信式头像 + 气泡（连续同角色合并头像）。返回气泡控件。"""
        if record:
            self._messages.append((role, text))
        pet_side = role == "pet"
        color = PET_COLOR if pet_side else USER_COLOR
        text_color = "#5a3a15" if pet_side else "white"
        new_group = role != self._last_role   # 角色切换 → 新一组消息
        avatar = self._avatar_widget(role, show=new_group)
        self._last_role = role

        row = QHBoxLayout()
        row.setSpacing(6)
        # 新一组消息顶部留更大间距，组内消息贴近，提升可读性
        row.setContentsMargins(0, 12 if new_group else 4, 0, 0)
        bubble = _Bubble(text, color, text_color, self._bubble_max_width())
        if pet_side:
            if avatar is not None:
                row.addWidget(avatar, 0, Qt.AlignTop)
            row.addWidget(bubble, 0, Qt.AlignTop)
            row.addStretch(1)
        else:
            row.addStretch(1)
            row.addWidget(bubble, 0, Qt.AlignTop)
            if avatar is not None:
                row.addWidget(avatar, 0, Qt.AlignTop)
        # 插到 stretch 之前
        self.msg_layout.insertLayout(self.msg_layout.count() - 1, row)
        self._last_bubble = bubble
        self._scroll_bottom(bubble)
        return bubble

    def _refresh_messages(self):
        """重建消息列表（头像开关切换后刷新已有消息）。"""
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                lay = item.layout()
                while lay.count():
                    it = lay.takeAt(0)
                    if it.widget() is not None:
                        it.widget().deleteLater()
                lay.deleteLater()
        self._last_role = None   # 重建时重新按组显示头像
        for role, text in self._messages:
            self._render_message(role, text, record=False)
        # 重建等待中的"…"气泡队列
        self._pending_bubbles = [
            self._render_message("pet", "…", record=False)
            for _ in range(len(self._pending_bubbles))
        ]
        self._ai_bubble = self._pending_bubbles[0] if self._pending_bubbles else None

    def _scroll_bottom(self, widget=None):
        """滚到消息区底部。

        单纯 setValue(maximum()) 在布局尚未重算时会拿到旧值，导致滚不到位。
        这里强制处理一次布局请求，再滚动，并额外用 ensureWidgetVisible
        把最后一条消息气泡定位到可视区域，双保险。
        """

        def do():
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()   # 强制完成布局重算，刷新 maximum()
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
            if widget is not None:
                self.scroll.ensureWidgetVisible(widget)

        QTimer.singleShot(0, do)
        QTimer.singleShot(120, do)

    # ---------- 发送与回复 ----------
    def _on_input_changed(self, _text):
        """用户在输入框打字时通知桌宠显示“倾听姿势”。"""
        if self.input.text().strip():
            self.user_typing.emit()

    def _send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.add_user(text)
        self._history.append({"role": "user", "content": text})
        self.message_sent.emit()

        if self.ai is not None and self.ai.is_ready():
            # AI 异步回复，显示"…"等待（队列管理：连发消息不丢单）
            self._pending = True
            bub = self._render_message("pet", "…", record=False)
            self._pending_bubbles.append(bub)
            self._ai_bubble = self._pending_bubbles[0]
            self.ai_started.emit()
            self.ai.finished.connect(self._on_ai_reply, Qt.UniqueConnection)
            self.ai.ask_async(self._history)
        else:
            # 本地规则聊天
            delay = random.randint(400, 800)
            QTimer.singleShot(delay, self._reply_local)

    def _reply_local(self):
        reply = self.bot.reply(self._history[-1]["content"])
        self._history.append({"role": "assistant", "content": reply})
        self.add_pet(reply)

    def _on_ai_reply(self, reply: str):
        self._history.append({"role": "assistant", "content": reply})
        self._messages.append(("pet", reply))   # 记录展示历史，刷新重建不丢
        self.ai_finished.emit()
        # 按发送顺序填充等待气泡（连发消息时逐个消费，不丢单）
        if self._pending_bubbles:
            bub = self._pending_bubbles.pop(0)
            bub._set_content(reply)
            self._last_bubble = bub
            self._scroll_bottom(bub)
        self._pending = bool(self._pending_bubbles)
        self._ai_bubble = self._pending_bubbles[0] if self._pending_bubbles else None

    # ---------- 键盘事件：回车发送、ESC 关闭 ----------
    def keyPressEvent(self, event):
        # QDialog 默认会把回车当作"确定"关窗，这里拦截掉
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.input.text().strip():
                self._send()
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)
