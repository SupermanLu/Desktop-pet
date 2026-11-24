# -*- coding: utf-8 -*-
"""桌面轻工具面板：从桌宠"口袋"里掏出来的极简工具集合。

- 便签 / 天气 / 待办 / 随机决定 / 计算器 —— 每个都极简，用完即走。
- 数据纯本地保存（config.json）；天气用 uapis.cn 免费接口（无需 Key，按城市名查询）。
- 工具窗无边框、可拖动、置顶；面板带淡入+上滑的"掏出来"动画。
"""
import json
import random
import re
import urllib.parse
import urllib.request

from PySide6.QtCore import Qt, Signal, QPoint, QThread, QTimer, QPropertyAnimation, \
    QEasingCurve, QRectF, QEvent
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QTextEdit, QCheckBox, QListWidget,
                               QListWidgetItem, QFrame, QApplication, QComboBox,
                               QGridLayout, QScrollArea, QInputDialog)

from core.config import save_config
from ui.theme import card_ss, DORA

_CARD_SS = card_ss()


def _place_near_pet(widget, pet_rect) -> QPoint:
    """把窗口放到桌宠头顶附近，并限制在屏幕内。"""
    screen = QGuiApplication.screenAt(pet_rect.center()) \
        or QGuiApplication.primaryScreen()
    geo = screen.availableGeometry() if screen \
        else QGuiApplication.primaryScreen().availableGeometry()
    x = pet_rect.right() - widget.width()
    y = pet_rect.top() - widget.height() - 8
    x = max(geo.left() + 4, min(x, geo.right() - widget.width() - 4))
    y = max(geo.top() + 4, y)
    return QPoint(x, y)


class ToolsPanel(QWidget):
    """工具面板：5 个极简工具入口，淡入 + 上滑"掏出来"动画。"""
    tool_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 点击面板外部 → 自动关闭，避免没选工具就关不掉
        QApplication.instance().installEventFilter(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(_CARD_SS)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 12)
        lay.setSpacing(8)
        # 标题栏：标题 + 右上角关闭按钮
        title_row = QHBoxLayout()
        title = QLabel("🧰 口袋轻工具")
        title.setObjectName("ttl")
        title_row.addWidget(title)
        title_row.addStretch(1)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("close")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setToolTip("关闭")
        btn_close.clicked.connect(self.hide)
        title_row.addWidget(btn_close)
        lay.addLayout(title_row)
        hint = QLabel("用完即走，点选一个工具")
        hint.setObjectName("hint")
        lay.addWidget(hint)
        grid = QGridLayout()
        grid.setSpacing(6)
        tools = [("📝 便签", "note"), ("🌤️ 天气", "weather"),
                 ("📋 待办", "todo"), ("🎲 随机", "random"),
                 ("🔢 计算器", "calc")]
        for i, (label, key) in enumerate(tools):
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        root.addWidget(card)
        self.adjustSize()

    def _pick(self, key: str):
        self.hide()
        self.tool_selected.emit(key)

    # 点击面板外部任意位置 → 关闭面板（返回上一级）
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            gpos = event.globalPosition().toPoint() \
                if hasattr(event, "globalPosition") else event.globalPos()
            if self.isVisible() and not self.geometry().contains(gpos) \
                    and not self.underMouse():
                self.hide()
        return super().eventFilter(obj, event)

    def show_at(self, pet_rect):
        self.move(_place_near_pet(self, pet_rect))
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        # 淡入 + 上滑 150ms，模拟"从口袋里掏出来"
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim


class _MiniWindow(QWidget):
    """极简工具窗基类：无边框、置顶、可拖动、带标题栏和关闭按钮。"""

    def __init__(self, title: str, w: int, h: int):
        super().__init__()
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(w, h)
        self._drag_pos = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._card = QFrame(self)
        self._card.setObjectName("card")
        self._card.setStyleSheet(_CARD_SS)
        self._body = QVBoxLayout(self._card)
        self._body.setContentsMargins(10, 6, 10, 10)
        self._body.setSpacing(6)

        # 标题栏（可拖动）
        self._bar = QWidget(self._card)
        self._bar.setFixedHeight(24)
        bar_lay = QHBoxLayout(self._bar)
        bar_lay.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setObjectName("ttl")
        bar_lay.addWidget(t)
        bar_lay.addStretch(1)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("close")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        bar_lay.addWidget(btn_close)
        self._body.addWidget(self._bar)

        root.addWidget(self._card)

    # ---- 拖动 ----
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def save_state(self):
        pass

    def closeEvent(self, e):
        try:
            self.save_state()
        except Exception:
            pass
        super().closeEvent(e)

    def show_near(self, pet_rect):
        self.move(_place_near_pet(self, pet_rect))
        self.show()
        self.raise_()
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(120)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim


# ---------- 📝 便签 ----------
class NoteWidget(_MiniWindow):
    def __init__(self, cfg, pet_rect):
        super().__init__("📝 便签", 300, 250)
        self._cfg = cfg
        self._edit = QTextEdit()
        self._edit.setPlainText(cfg.get("tools_note", ""))
        self._edit.textChanged.connect(self._save)
        self._body.addWidget(self._edit, 1)

        row = QHBoxLayout()
        self._chk_top = QCheckBox("窗口置顶")
        self._chk_top.setChecked(True)
        self._chk_top.toggled.connect(self._toggle_top)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(lambda: self._edit.clear())
        row.addWidget(self._chk_top)
        row.addStretch(1)
        row.addWidget(btn_clear)
        self._body.addLayout(row)
        self.show_near(pet_rect)

    def _save(self):
        self._cfg["tools_note"] = self._edit.toPlainText()
        save_config(self._cfg)

    def _toggle_top(self, on):
        flags = self.windowFlags()
        flags = flags | Qt.WindowStaysOnTopHint if on \
            else flags & ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def save_state(self):
        self._save()


# ---------- 📋 待办 ----------
class _TodoRow(QWidget):
    """单条待办行：左边小方块(点击完成/绿色√) + 文字 + 🔔提醒开关。

    通过信号把行号回传给待办窗口，由它统一读写 config。
    """
    toggled = Signal(int)        # 点击方块 → 切换完成状态
    remind_toggled = Signal(int) # 点击🔔 → 切换提醒开关
    selected = Signal(int)       # 单击文字区域 → 选中（供删除定位）
    edit_requested = Signal(int) # 双击文字区域 → 编辑内容

    def __init__(self, idx: int, text: str, done: bool,
                 remind: bool, interval_min: int):
        super().__init__()
        self._idx = idx
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(8)

        # 完成方块：未完成=空心小方框，完成=绿底+白勾
        self._chk = QPushButton()
        self._chk.setFixedSize(22, 22)
        self._chk.setCursor(Qt.PointingHandCursor)
        self._chk.setFocusPolicy(Qt.NoFocus)
        self._chk.setToolTip("点击标记完成 / 取消完成")
        self._chk.clicked.connect(lambda: self.toggled.emit(self._idx))

        # 待办文字
        self._lab = QLabel(text)
        self._lab.setWordWrap(True)

        # 提醒开关
        self._rmd = QPushButton()
        self._rmd.setFixedSize(38, 24)
        self._rmd.setCursor(Qt.PointingHandCursor)
        self._rmd.setFocusPolicy(Qt.NoFocus)
        self._rmd.setToolTip("点击开启/关闭这条待办的循环提醒（开启时设置间隔）")
        self._rmd.clicked.connect(lambda: self.remind_toggled.emit(self._idx))

        lay.addWidget(self._chk)
        lay.addWidget(self._lab, 1)
        lay.addWidget(self._rmd)
        self.refresh(done, remind, interval_min)

    def refresh(self, done: bool, remind: bool, interval_min: int):
        """刷新本行的完成态、提醒态样式。"""
        if done:
            self._chk.setText("✓")
            self._chk.setStyleSheet(
                "QPushButton{background:#4caf50;color:white;border:none;"
                "border-radius:6px;font-weight:bold;font-size:14px;}")
            self._lab.setStyleSheet(
                "color:#a99e8c; text-decoration:line-through;")
        else:
            self._chk.setText("")
            self._chk.setStyleSheet(
                "QPushButton{background:white;border:1.5px solid #c9bfa8;"
                "border-radius:6px;}")
            self._lab.setStyleSheet("color:#5a3a15;")
        if remind:
            self._rmd.setText(f"🔔{interval_min}")
            self._rmd.setStyleSheet(
                "QPushButton{background:#ffd97a;color:#7a5400;"
                "border:1px solid #e6b84d;border-radius:8px;"
                "font-size:11px;font-weight:bold;}")
        else:
            self._rmd.setText("🔕")
            self._rmd.setStyleSheet(
                "QPushButton{background:transparent;color:#b0a08a;border:none;"
                "font-size:12px;}")
        self._set_selected(False)

    def _set_selected(self, sel: bool):
        self.setStyleSheet(
            "QWidget{background:#f7ead0;border-radius:8px;}"
            if sel else "QWidget{background:transparent;}")

    def mousePressEvent(self, e):
        # 点击文字区域 → 选中该行（供"删除"定位），不拦截子控件点击
        if self._lab.geometry().contains(
                self.mapFromGlobal(e.globalPosition().toPoint())):
            self.selected.emit(self._idx)
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        # 双击文字区域 → 触发编辑
        if self._lab.geometry().contains(
                self.mapFromGlobal(e.globalPosition().toPoint())):
            self.edit_requested.emit(self._idx)
        super().mouseDoubleClickEvent(e)


class TodoWidget(_MiniWindow):
    completed = Signal(int)   # 参数：已完成的件数

    def __init__(self, cfg, pet_rect):
        super().__init__("📋 待办", 340, 360)
        self._cfg = cfg
        self._rows = []          # [_TodoRow,...]
        self._selected_idx = -1

        self._input = QLineEdit()
        self._input.setPlaceholderText("加一件待办，回车确认…")
        self._input.returnPressed.connect(self._add)
        self._body.addWidget(self._input)

        # 待办列表（可滚动）。滚动区视口与内容容器用与卡片一致的暖白实底，
        # 既避免系统暗夜模式下的默认深色背景（黑块），也不依赖透明导致露桌面。
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea{{background:{DORA['white']};border:none;}}")
        self._scroll.viewport().setStyleSheet(
            f"background:{DORA['white']};")
        self._list_host = QWidget()
        self._list_host.setStyleSheet(f"background:{DORA['white']};")
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(2)
        self._list_lay.addStretch(1)
        self._scroll.setWidget(self._list_host)
        self._body.addWidget(self._scroll, 1)

        row = QHBoxLayout()
        btn_add = QPushButton("添加")
        btn_add.clicked.connect(self._add)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._del)
        row.addWidget(btn_add)
        row.addWidget(btn_del)
        row.addStretch(1)
        self._body.addLayout(row)

        self._reload()
        self.show_near(pet_rect)

    # ---------- 数据与显示 ----------
    def _reload(self):
        while self._list_lay.count() > 1:
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._rows = []
        self._selected_idx = -1
        for idx, t in enumerate(self._cfg.get("tools_todos", [])):
            rw = _TodoRow(idx, t.get("text", ""), bool(t.get("done")),
                          bool(t.get("remind")),
                          int(t.get("remind_interval_min", 60) or 60))
            rw.toggled.connect(self._toggle)
            rw.remind_toggled.connect(self._toggle_remind)
            rw.selected.connect(self._select)
            rw.edit_requested.connect(self._edit)
            self._list_lay.insertWidget(self._list_lay.count() - 1, rw)
            self._rows.append(rw)

    def _refresh_row(self, idx: int):
        if not (0 <= idx < len(self._rows)):
            return
        todos = self._cfg.get("tools_todos", [])
        if idx >= len(todos):
            return
        t = todos[idx]
        self._rows[idx].refresh(bool(t.get("done")), bool(t.get("remind")),
                                int(t.get("remind_interval_min", 60) or 60))

    def _select(self, idx: int):
        self._selected_idx = idx
        for i, rw in enumerate(self._rows):
            rw._set_selected(i == idx)

    # ---------- 操作 ----------
    def _add(self):
        text = self._input.text().strip()
        if not text:
            return
        self._cfg.setdefault("tools_todos", []).append(
            {"text": text, "done": False, "remind": False,
             "remind_interval_min": 60})
        self._input.clear()
        self._reload()
        save_config(self._cfg)

    def _del(self):
        idx = self._selected_idx
        todos = self._cfg.get("tools_todos", [])
        if 0 <= idx < len(todos):
            del todos[idx]
            self._reload()
            save_config(self._cfg)

    def _edit(self, idx: int):
        """双击某行 → 弹出输入框修改内容，空输入视为删除。"""
        todos = self._cfg.get("tools_todos", [])
        if not (0 <= idx < len(todos)):
            return
        old_text = todos[idx].get("text", "")
        new_text, ok = QInputDialog.getText(
            self, "修改待办", "修改内容：", text=old_text)
        if not ok:
            return
        new_text = new_text.strip()
        if not new_text:
            # 空输入 → 删除这条
            del todos[idx]
            self._reload()
            save_config(self._cfg)
            return
        todos[idx]["text"] = new_text
        self._reload()
        save_config(self._cfg)

    def _toggle(self, idx: int):
        todos = self._cfg.get("tools_todos", [])
        if not (0 <= idx < len(todos)):
            return
        t = todos[idx]
        t["done"] = not t.get("done")
        self._refresh_row(idx)
        save_config(self._cfg)
        if t["done"]:
            done_count = sum(1 for x in todos if x.get("done"))
            self.completed.emit(done_count)

    def _toggle_remind(self, idx: int):
        todos = self._cfg.get("tools_todos", [])
        if not (0 <= idx < len(todos)):
            return
        t = todos[idx]
        if t.get("remind"):
            t["remind"] = False
        else:
            interval = self._pick_interval(t)
            if interval is None:
                return
            t["remind"] = True
            t["remind_interval_min"] = interval
        save_config(self._cfg)
        self._refresh_row(idx)

    def _pick_interval(self, t) -> int | None:
        items = [("30 分钟", 30), ("45 分钟", 45), ("60 分钟", 60),
                 ("90 分钟", 90), ("120 分钟", 120), ("180 分钟", 180)]
        labels = [k for k, _ in items]
        vals = dict(items)
        cur = int(t.get("remind_interval_min", 60) or 60)
        cur_ix = 2
        for i, (_, v) in enumerate(items):
            if v == cur:
                cur_ix = i
                break
        text, ok = QInputDialog.getItem(
            self, "⏰ 提醒间隔",
            "每隔多久提醒一次这条待办？（未完成前循环提醒）",
            labels, cur_ix, False)
        if not ok or not text:
            return None
        return vals.get(text, 60)

    def save_state(self):
        pass


# ---------- 🎲 随机决定 ----------
class RandomWidget(_MiniWindow):
    def __init__(self, cfg, pet_rect):
        super().__init__("🎲 随机决定", 320, 280)
        self._cfg = cfg
        self._result = QLabel("点一下，让桌宠替你决定 👇")
        self._result.setAlignment(Qt.AlignCenter)
        self._result.setWordWrap(True)
        self._result.setStyleSheet(
            "color:#5a3a15; font-size:20px; font-weight:bold; padding:8px;")
        self._body.addWidget(self._result)

        btn = QPushButton("🎲 随机！")
        btn.setStyleSheet(_CARD_SS + "QPushButton{font-size:14px; padding:8px;}")
        btn.clicked.connect(self._pick)
        self._body.addWidget(btn)

        self._input = QLineEdit()
        self._input.setPlaceholderText("加一个选项，回车添加")
        self._input.returnPressed.connect(self._add)
        self._list = QListWidget()
        self._list.setMaximumHeight(90)
        self._body.addWidget(self._input)
        self._body.addWidget(self._list)

        row = QHBoxLayout()
        btn_del = QPushButton("删选中")
        btn_del.clicked.connect(self._del)
        hint = QLabel("（中午吃什么？就用这个！）")
        hint.setObjectName("hint")
        row.addWidget(btn_del)
        row.addStretch(1)
        row.addWidget(hint)
        self._body.addLayout(row)
        self._reload()
        self.show_near(pet_rect)

    def _reload(self):
        self._list.clear()
        for opt in self._cfg.get("tools_random_options", []):
            self._list.addItem(opt)

    def _pick(self):
        opts = [o.strip() for o in self._cfg.get("tools_random_options", [])
                if o.strip()]
        if not opts:
            self._result.setText("列表空啦，先加点选项～")
            return
        self._result.setText("🍽️ " + random.choice(opts))

    def _add(self):
        text = self._input.text().strip()
        if not text:
            return
        self._cfg.setdefault("tools_random_options", []).append(text)
        self._input.clear()
        self._reload()
        save_config(self._cfg)

    def _del(self):
        row = self._list.currentRow()
        opts = self._cfg.get("tools_random_options", [])
        if 0 <= row < len(opts):
            del opts[row]
            self._reload()
            save_config(self._cfg)

    def save_state(self):
        pass


# ---------- 🔢 计算器 ----------
class CalcWidget(_MiniWindow):
    def __init__(self, pet_rect):
        super().__init__("🔢 计算器", 250, 320)
        self._expr = ""
        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setAlignment(Qt.AlignRight)
        self._display.setStyleSheet(
            "QLineEdit{background:white;color:#333;border:1px solid #e6c99a;"
            "border-radius:8px;font-size:20px;padding:6px 8px;}")
        self._body.addWidget(self._display)

        keys = ["C", "(", ")", "⌫",
                "7", "8", "9", "÷",
                "4", "5", "6", "×",
                "1", "2", "3", "-",
                "0", ".", "=", "+"]
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, k in enumerate(keys):
            b = QPushButton(k)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, kk=k: self._press(kk))
            grid.addWidget(b, i // 4, i % 4)
        self._body.addLayout(grid)

        row = QHBoxLayout()
        btn_copy = QPushButton("📋 复制结果")
        btn_copy.clicked.connect(self._copy)
        row.addWidget(btn_copy)
        row.addStretch(1)
        self._body.addLayout(row)
        self.show_near(pet_rect)

    def _press(self, key):
        if key == "C":
            self._expr = ""
        elif key == "⌫":
            self._expr = self._expr[:-1]
        elif key == "=":
            self._evaluate()
            return
        else:
            self._expr += key
        self._display.setText(self._expr)

    def _evaluate(self):
        expr = self._expr.replace("×", "*").replace("÷", "/")
        if not expr:
            return
        if not re.fullmatch(r"[0-9+\-*/().\s]*", expr):
            self._display.setText("表达式有误")
            self._expr = ""
            return
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            text = str(result)
            self._display.setText(text)
            self._expr = text
        except Exception:
            self._display.setText("错误")
            self._expr = ""

    def _copy(self):
        QApplication.clipboard().setText(self._display.text())
        self.setWindowTitle("🔢 计算器 · 已复制")

    def save_state(self):
        pass


# ---------- 🌤️ 天气 ----------
class _WeatherFetch(QThread):
    done = Signal(str, str, str, str, str, str)   # city, weather, temp, humidity, wind, time
    failed = Signal(str)

    def __init__(self, city: str, parent=None):
        super().__init__(parent)
        self._city = city

    def run(self):
        try:
            # uapis.cn 免费天气接口：按城市名查询，无需 Key，支持全国 3000+ 城市
            url = "https://uapis.cn/api/v1/misc/weather?city=" \
                + urllib.parse.quote(self._city)
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                text = r.read().decode("utf-8", errors="ignore")
            d = json.loads(text)
            city = d.get("city", self._city)
            weather = d.get("weather", "")
            temp = d.get("temperature", "")
            humidity = d.get("humidity", "")
            wind = (str(d.get("wind_direction", ""))
                    + str(d.get("wind_power", ""))).strip()
            report = str(d.get("report_time", ""))[:16]
            self.done.emit(city, weather, temp, humidity, wind, report)
        except Exception as e:
            self.failed.emit(str(e))


class WeatherWidget(_MiniWindow):
    def __init__(self, cfg, pet_rect):
        super().__init__("🌤️ 天气", 280, 200)
        self._cfg = cfg
        self._thread = None
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("输入城市名，回车查询，如：成都")
        self._edit.setText(cfg.get("tools_weather_city", "北京"))
        self._edit.returnPressed.connect(self._fetch)
        self._info = QLabel("点「查询」获取天气")
        self._info.setAlignment(Qt.AlignCenter)
        self._info.setWordWrap(True)
        self._info.setStyleSheet(
            f"color:{DORA['blue_dark']}; font-size:16px; padding:10px;")
        row = QHBoxLayout()
        row.addWidget(self._edit, 1)
        btn = QPushButton("查询")
        btn.clicked.connect(self._fetch)
        row.addWidget(btn)
        self._body.addWidget(self._info, 1)
        self._body.addLayout(row)
        self.show_near(pet_rect)
        self._fetch()

    def _fetch(self):
        city = self._edit.text().strip()
        if not city:
            self._info.setText("请输入城市名")
            return
        self._cfg["tools_weather_city"] = city
        save_config(self._cfg)
        self._info.setText("获取中…")
        if self._thread is not None and self._thread.isRunning():
            self._thread.terminate()
        self._thread = _WeatherFetch(city)
        self._thread.done.connect(self._on_done)
        self._thread.failed.connect(self._on_fail)
        self._thread.start()

    def _on_done(self, city, weather, temp, humidity, wind, _report):
        parts = []
        if temp:
            parts.append(f"{temp} ℃")
        if wind:
            parts.append(wind)
        if humidity:
            parts.append(f"湿度{humidity}%")
        line1 = city or self._edit.text().strip()
        if weather:
            line1 += f"  {weather}"
        self._info.setText(line1 + "\n" + ("  ".join(parts) if parts else "暂无数据"))

    def _on_fail(self, _err):
        self._info.setText("天气获取失败，请检查网络")

    def save_state(self):
        pass
