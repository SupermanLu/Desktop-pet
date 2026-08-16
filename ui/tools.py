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
                               QGridLayout)

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
class TodoWidget(_MiniWindow):
    completed = Signal(int)   # 参数：已完成的件数

    def __init__(self, cfg, pet_rect):
        super().__init__("📋 待办", 320, 320)
        self._cfg = cfg
        self._loading = False
        self._input = QLineEdit()
        self._input.setPlaceholderText("加一件待办，回车确认…")
        self._input.returnPressed.connect(self._add)
        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_toggled)
        self._body.addWidget(self._input)
        self._body.addWidget(self._list, 1)

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

    def _reload(self):
        # 用 _loading 标志屏蔽重建列表期间的 itemChanged，避免反复重连
        self._loading = True
        self._list.clear()
        # 注意：PySide6 对 setData 的 Python dict 取出时会拷贝，
        # 所以这里只存行号，勾选时再按行号取真实对象修改。
        for idx, t in enumerate(self._cfg.get("tools_todos", [])):
            text = t.get("text", "")
            item = QListWidgetItem(("☑ " if t.get("done") else "☐ ") + text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if t.get("done") else Qt.Unchecked)
            item.setData(Qt.UserRole, idx)
            self._list.addItem(item)
        self._loading = False

    def _add(self):
        text = self._input.text().strip()
        if not text:
            return
        self._cfg.setdefault("tools_todos", []).append(
            {"text": text, "done": False})
        self._input.clear()
        self._reload()
        save_config(self._cfg)

    def _del(self):
        row = self._list.currentRow()
        todos = self._cfg.get("tools_todos", [])
        if 0 <= row < len(todos):
            del todos[row]
            self._reload()
            save_config(self._cfg)

    def _on_toggled(self, item):
        if self._loading:
            return
        idx = item.data(Qt.UserRole)
        todos = self._cfg.get("tools_todos", [])
        if idx is None or not (0 <= idx < len(todos)):
            return
        t = todos[idx]
        done = item.checkState() == Qt.Checked
        if done and not t.get("done"):
            t["done"] = True
            item.setText("☑ " + t.get("text", ""))
            save_config(self._cfg)
            done_count = sum(1 for x in todos if x.get("done"))
            self.completed.emit(done_count)
        elif not done and t.get("done"):
            t["done"] = False
            item.setText("☐ " + t.get("text", ""))
            save_config(self._cfg)

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
