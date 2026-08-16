# -*- coding: utf-8 -*-
"""桌宠入口：加载配置 → 创建宠物窗口 → 体力系统 → 系统托盘 → 事件循环。

运行：python main.py
打包：pyinstaller -F -w -i assets/icon.ico main.py -n TraeDeskPet
"""
import os
import re
import sys
import random
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QPoint, QEvent, QObject
from PySide6.QtGui import QIcon, QAction, QPixmap, QGuiApplication
from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu,
                               QMessageBox, QInputDialog)

from core.config import load_config, save_config, ASSETS_DIR, norm_project_path
from core.app_launcher import launch
from core.energy import EnergyManager
from core.chatbot import ChatBot
from core.reminder import ReminderManager
from core.event_reminder import EventReminder
from core.ai_client import AIClient
from core import sandbox
from core import mood
from core import web_ai
from core import stats
from core import achievements
from core.growth import GrowthManager
from core.clipboard_watcher import ClipboardWatcher, TYPE_NAMES
from core.key_hook import GlobalHotkey, DEFAULT_MAP
from core.sound_manager import SoundManager
from ui.action_bubble import ActionBubble
from ui.mood_chart import MoodChartDialog
from ui.focus_chart import FocusChartDialog
from ui.tools import (ToolsPanel, NoteWidget, TodoWidget, RandomWidget,
                      CalcWidget, WeatherWidget)
from ui.pet_animation import pet_pixmap, strip_white_bg
from ui.pet_window import PetWindow
from ui.circle_menu import CircleMenu
from ui.chat_dialog import ChatDialog
from ui.settings_dialog import SettingsDialog


class _EscCloseFilter(QObject):
    """应用级 ESC 关闭：按下 ESC 时关闭可见的浮层（气泡/工具面板/小工具窗）。

    这些浮层为"不抢焦点"设计，默认收不到按键，统一在这里拦截最稳妥。
    仅当有目标浮层可见时才吞掉 ESC，否则放行给 QDialog（聊天/设置等原生支持 ESC）。
    """

    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self._targets = targets   # 返回当前应关闭的浮层列表的可调用对象

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            for w in self._targets():
                if w is not None and w.isVisible():
                    w.close()
                    return True
        return super().eventFilter(obj, event)


def build_tray_icon(cfg):
    """托盘图标：优先用当前宠物图片（失效则回退 idle 中心图），否则程序绘制形象。"""
    gif = norm_project_path(cfg.get("pet_gif", "") or "")
    if gif and not gif.startswith((ASSETS_DIR, "./")) and "/" not in gif \
            and "\\" not in gif:
        gif = os.path.join(ASSETS_DIR, gif)
    if not gif or not os.path.isfile(gif):
        # pet_gif 失效 → 用 idle 素材目录里的中心图
        idle_dir = norm_project_path(cfg.get("idle_dir", ""))
        center = cfg.get("idle_images", {}).get("center", "")
        if idle_dir and center:
            cand = os.path.join(idle_dir, center)
            if os.path.isfile(cand):
                gif = cand
    if gif and os.path.isfile(gif):
        pm = strip_white_bg(QPixmap(gif))
        if not pm.isNull():
            return QIcon(pm.scaled(64, 64, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation))
    return QIcon(pet_pixmap(64, skin=cfg.get("pet_skin", "哆啦A梦")))


def dock_chat_beside_pet(dlg, pet, gap: int = 8):
    """把聊天窗停靠在桌宠旁边，保证宠物形象不被遮挡。

    横向：优先放桌宠右侧，放不下放左侧；左右都放不下再考虑正上方/正下方。
    纵向：优先顶部对齐，放不下则底部对齐（如桌宠贴屏幕底部时，聊天窗会
    垂直铺开在桌宠旁边，而不是越界或落到右下角盖住桌宠）。
    用客户区尺寸做定位，最终 move 时补偿窗口边框偏移，保证客户区落点精确。
    """
    pw = pet.geometry()
    screen = QGuiApplication.screenAt(pw.center()) or QGuiApplication.primaryScreen()
    geo = screen.availableGeometry() if screen else QGuiApplication.primaryScreen().availableGeometry()

    client = dlg.geometry()
    fg = dlg.frameGeometry()
    dx = fg.left() - client.left()   # 窗口左边框宽度
    dy = fg.top() - client.top()     # 顶部边框 + 标题栏高度
    w, h = client.width(), client.height()

    # 横向：优先右，其次左
    if pw.right() + gap + w <= geo.right():
        x = pw.right() + gap
    elif pw.left() - gap - w >= geo.left():
        x = pw.left() - gap - w
    else:
        # 左右都放不下：先正上方、再正下方，最后屏幕内居中
        x = max(geo.left(), min(pw.center().x() - w // 2, geo.right() - w))
        if pw.top() - gap - h >= geo.top():
            dlg.move(x - dx, pw.top() - gap - h - dy)
        elif pw.bottom() + gap + h <= geo.bottom():
            dlg.move(x - dx, pw.bottom() + gap - dy)
        else:
            dlg.move(x - dx, max(geo.top(), (geo.height() - h) // 2) - dy)
        return

    # 纵向：顶部对齐放不下时改底部对齐，并始终限制在屏幕内
    y = pw.top()
    if y + h > geo.bottom():
        y = pw.bottom() - h
    y = max(geo.top(), min(y, geo.bottom() - h))
    dlg.move(x - dx, y - dy)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TraeDeskPet")

    cfg = load_config()

    # ---- 启动状态重置（临时场景开关不跨重启保留） ----
    # 免打扰（鼠标穿透）：重启后自动恢复正常交互，避免点击无反应被误认为桌宠坏了
    cfg["dnm_enabled"] = False
    # 番茄钟：重启后不延续上次的计时。否则若上次关闭前还在计时、end_ts 已过期，
    # 启动后 30 秒内 _check_pomodoro 会立即触发阶段切换气泡，看起来像"自己开启"
    cfg["pomodoro_running"] = False
    cfg["pomodoro_end_ts"] = 0.0
    cfg["pomodoro_phase"] = "work"

    # 托盘图标：用当前宠物图片
    tray_icon = build_tray_icon(cfg)

    # 音效管理器：程序合成音效（交互/聊天/提醒/彩蛋），带开关与音量
    sfx = SoundManager(cfg)

    pet = PetWindow(cfg, sfx=sfx)
    pet.place_default()
    pet.show()

    # 启动欢迎：挥手打招呼 + 气泡
    QTimer.singleShot(900, lambda: (
        sfx.play("wave"),
        pet.play_action("wave", 2.5),
        pet.show_bubble(f"嗨～{cfg.get('pet_name', '小团子')}来啦！今天也要元气满满哦 💪", 2400)))

    # ---- 聊天机器人 ----
    bot = ChatBot(cfg.get("pet_name", "小团子"))
    ai = AIClient(cfg)  # 未配置 Key 时聊天自动回退本地规则
    # 长期记忆：AI 提炼出的新信息写回 config.json
    def save_new_memory(facts):
        mem = cfg.setdefault("ai_memory", [])
        for f in facts:
            if f not in mem:
                mem.append(f)
        save_config(cfg)
    ai.memory_new.connect(save_new_memory)
    chat_ref = {"dlg": None}

    # 聊天/菜单等暂停游走后的统一恢复：聊天还开着时保持暂停
    def resume_wander():
        if chat_ref["dlg"] is None or not chat_ref["dlg"].isVisible():
            pet.pause_wander(False)

    # 聊天头像素材：取道具合集表里的哆啦A梦（1行1列 = 全身正立）
    avatar_sheet = ""
    for _v in cfg.get("props", {}).values():
        if _v and len(_v) == 3:
            avatar_sheet = os.path.join(norm_project_path(cfg.get("action_img_dir", "")), _v[0])
            break

    # ---- 关怀提醒 ----
    def on_remind(text: str):
        # 只在宠物头顶弹气泡提示，不打断聊天窗口；提示音可在设置里开关
        pet.show_bubble(text, 4000)
        _refresh_tooltip()
        if cfg.get("reminder_sound_enabled", True):
            sfx.play("reminder")

    reminder = ReminderManager(cfg)
    reminder.remind.connect(on_remind)

    def on_fullscreen_paused(paused: bool):
        """全屏挂起：暂停所有提醒，避免观影时被气泡打扰；退出全屏自动恢复。"""
        reminder.set_paused(paused)
    pet.fullscreen_paused.connect(on_fullscreen_paused)

    def on_festival_idle(key: str):
        """节日形象：节日当天把静止待机图换成节日形象；空串恢复默认。"""
        pet.set_festival_idle(key)
    reminder.festival_idle.connect(on_festival_idle)
    reminder.refresh_festival_idle()   # 启动时立即评估一次今天的节日形象

    def on_reminder_action(k: str):
        """提醒 → 按类型切换对应形象素材。

        挂边待机时提醒：暂时跳出挂边完整显示提醒动作，结束后自动回归挂边；
        非挂边则照常播放动作。
        """
        if pet.remind_while_hanging(k, 3.0):
            return
        pet.play_action(k, 3.0)
    reminder.action.connect(on_reminder_action)

    def on_reminder_prop(p: str):
        """提醒 → 叠加对应道具（爱心/零食/水滴/星星等）。"""
        pet.show_prop(p, 2.5)
    reminder.prop.connect(on_reminder_prop)

    def on_egg_hatched(reward: dict):
        """彩蛋攒满自动孵化 → 放烟花庆祝 + 弹出随机小惊喜。"""
        sfx.play("achievement")
        pet.play_action("fireworks", 3.0)
        pet.show_prop("sparkle", 3.0)
        kind = reward.get("type", "word")
        if kind == "food":
            gained = energy.feed({"gain": reward.get("gain", 20)})
            pet.show_bubble(
                f"🥚 彩蛋孵出啦！送你一份{reward.get('name', '美食')}"
                f"{reward.get('icon', '🍗')} 体力+{gained}", 3200)
        elif kind == "extra_egg":
            cfg["eggs"] = int(cfg.get("eggs", 0)) + reward.get("gain", 1)
            save_config(cfg)
            pet.show_bubble(
                f"🥚 惊喜加倍！彩蛋里又孵出一颗蛋，现在共 {cfg['eggs']} 颗～", 3200)
        else:
            pet.show_bubble(
                f"🥚 彩蛋破壳！{reward.get('text', '来个小惊喜～')}", 3200)
        energy.snapshot()
        _refresh_tooltip()
    reminder.egg_hatched.connect(on_egg_hatched)

    # ---- 自定义事件提醒 ----
    event_reminder = EventReminder(cfg, save_config)
    event_reminder.remind.connect(on_remind)

    def on_event_remind(_t):
        pet.play_action("worry", 3.0)
        pet.show_prop("exclaim", 2.5)
    event_reminder.remind.connect(on_event_remind)

    # ---- AI 工具调用（轻量安全版：设提醒 / 开番茄钟 / 打开应用） ----
    # 只允许 AI 控制桌宠已有功能，不做文件修改、鼠标键盘等高危操作
    def dispatch_tool(name: str, args: dict) -> str:
        """主线程执行 AI 请求的工具，返回结果文本喂回给 AI。"""
        try:
            if name == "set_reminder":
                text = str(args.get("text") or "").strip() or "该休息啦"
                try:
                    minutes = max(1, min(120, int(args.get("minutes", 10))))
                except (TypeError, ValueError):
                    minutes = 10
                QTimer.singleShot(minutes * 60_000,
                                  lambda: on_remind(f"⏰ 小团子提醒：{text}"))
                pet.play_action("tomato", 3.0)
                return f"已设置提醒，{minutes} 分钟后提醒：{text}"
            if name == "open_app":
                app_name = str(args.get("name") or "").strip()
                if not app_name:
                    return "请告诉我要打开哪个应用"
                app = next((a for a in cfg.get("apps", [])
                            if a.get("name") == app_name), None)
                if app is None:
                    app = {"name": app_name, "path": ""}   # 未配置时走 KNOWN_APPS 探测
                ok, err = launch(app)
                if ok:
                    pet.play_action("wave", 2.0)
                    return f"已打开 {app_name}"
                return err
            if name == "start_pomodoro":
                try:
                    work = max(1, min(180, int(args.get("work_min", 25))))
                except (TypeError, ValueError):
                    work = 25
                try:
                    brk = max(1, min(60, int(args.get("break_min", 5))))
                except (TypeError, ValueError):
                    brk = 5
                cfg["pomodoro_enabled"] = True
                cfg["pomodoro_running"] = True
                cfg["pomodoro_phase"] = "work"
                cfg["pomodoro_work_min"] = work
                cfg["pomodoro_break_min"] = brk
                cfg["pomodoro_end_ts"] = time.time() + work * 60
                save_config(cfg)
                pet.play_action("tomato", 3.0)
                pet.show_prop("tomato", 3.0)
                # 3 秒开始动画后进入专注形象轮换
                QTimer.singleShot(3000, _start_focus_rotation)
                pet.show_bubble(f"🍅 番茄钟开始！专注 {work} 分钟，加油～", 2600)
                return f"番茄钟已启动：专注 {work} 分钟、休息 {brk} 分钟"
            if name == "sandbox_write":
                rel = str(args.get("rel_path") or "").strip()
                if not rel:
                    return "请提供沙盒内的相对路径"
                try:
                    return sandbox.sandbox_write(rel, str(args.get("content") or ""))
                except ValueError as e:
                    return str(e)
            if name == "sandbox_read":
                try:
                    return sandbox.sandbox_read(str(args.get("rel_path") or ""))
                except ValueError as e:
                    return str(e)
            if name == "sandbox_list":
                return sandbox.sandbox_list()
            if name == "run_command":
                return sandbox.run_whitelisted(str(args.get("command") or ""))
        except Exception as e:
            return f"执行出错：{e}"
        return "我不太会做这个操作"

    def on_tool_request(req: dict):
        """worker 线程请求执行工具 → 主线程执行后把结果交回。"""
        result = dispatch_tool(req.get("name", ""), req.get("args") or {})
        ai.tool_result(req.get("id", ""), result)
    ai.tool_request.connect(on_tool_request)

    # ---- 剪贴板助手（隐私沙盒·主动层，默认关闭） ----
    clip_watcher = ClipboardWatcher()
    clip_watcher.set_prefs(cfg.get("clipboard_prefs", {}))
    clip_bubble = ActionBubble()
    pet.register_follow_bubble(clip_bubble)   # 气泡随宠物移动
    clip_pending = {"type": None, "content": ""}

    def _clip_anchor() -> QPoint:
        return QPoint(pet.geometry().center().x(), pet.geometry().top())

    def _code_ext(content: str) -> str:
        if re.search(r"\b(def |import |print\(|class )", content):
            return "py"
        if re.search(r"\b(console\.log|function |=>|const |let |var )", content):
            return "js"
        return "txt"

    def do_clip_save(ctype: str, content: str, name: str = "") -> str:
        """按类型收藏/保存到沙盒（纯本地），返回提示文本。
        name 非空时用于命名代码/笔记文件（URL/命令为追加式，不适用命名）。"""
        if ctype == "url":
            return sandbox.append_bookmark(content)
        if ctype == "code":
            return sandbox.save_code(content, _code_ext(content), name=name)
        if ctype == "command":
            return sandbox.append_command(content)
        return sandbox.save_note(content, name=name)

    def ask_ai_about_content(ctype: str, content: str):
        """用户在剪贴板气泡点了"解释/摘要"：打开聊天并自动发送问题（此时才把原文给 AI）。"""
        if ctype == "command":
            q = f"请解释这条命令是干什么的、有没有安全隐患：\n{content}"
        elif ctype == "code":
            q = f"请帮我解释一下这段代码的功能和要点：\n{content}"
        else:
            q = f"请帮我给这段文字写一个简洁摘要：\n{content}"
        open_chat()
        dlg = chat_ref["dlg"]
        if dlg is not None:
            dlg.input.setText(q)
            dlg._send()

    def on_clip_choice(action: str):
        ctype, content = clip_pending["type"], clip_pending["content"]
        if not ctype:
            return
        if action == "save":
            name = ""
            # 代码/笔记是按文件保存：保存前让用户命名；取消命名则放弃保存
            if ctype in ("code", "note"):
                kind = "代码" if ctype == "code" else "笔记"
                ext = _code_ext(content) if ctype == "code" else "txt"
                name, ok = QInputDialog.getText(
                    pet, f"保存{kind}",
                    f"给{kind}起个名字（留空用默认名）\n"
                    f"将存到 沙盒/{kind} 目录，代码会自动加 .{ext} 后缀",
                    text="")
                if not ok:
                    clip_pending["type"] = None
                    clip_pending["content"] = ""
                    return   # 取消命名 → 不保存
            pet.show_bubble(do_clip_save(ctype, content, name), 2600)
            sfx.play("proud")
            pet.play_action("happy", 2.0)
        elif action == "always":
            cfg.setdefault("clipboard_prefs", {})[ctype] = "always"
            clip_watcher.set_prefs(cfg["clipboard_prefs"])
            save_config(cfg)
            pet.show_bubble(do_clip_save(ctype, content), 2600)
            sfx.play("proud")
            pet.play_action("proud", 2.0)
        elif action in ("explain", "summarize"):
            ask_ai_about_content(ctype, content)
        elif action == "dismiss":
            clip_watcher.mark_prompted(ctype)
        clip_pending["type"] = None
        clip_pending["content"] = ""

    clip_bubble.chosen.connect(on_clip_choice)

    def on_clip_detected(info: dict):
        if not cfg.get("clipboard_assistant_enabled", False):
            return
        ctype, content = info.get("type"), info.get("content", "")
        if info.get("auto"):   # 该类型"总是允许" → 直接自动处理，不弹气泡
            pet.show_bubble(do_clip_save(ctype, content), 2200)
            return
        clip_pending["type"] = ctype
        clip_pending["content"] = content
        sfx.play("notify")
        labels = {"url": "链接", "code": "代码", "command": "命令", "text": "长文本"}
        title = f"检测到你复制了一个{labels.get(ctype, '')}"
        preview = content[:30].replace("\n", " ")
        title += f"：{preview}…" if preview else ""
        btns = []
        if ctype == "url":
            btns = [("🔖 收藏", "save"), ("总是允许", "always"), ("✕ 忽略", "dismiss")]
        elif ctype == "code":
            btns = [("📁 保存", "save"), ("🧠 解释", "explain"), ("✕ 忽略", "dismiss")]
        elif ctype == "command":
            btns = [("🛡 解释安全性", "explain"), ("✕ 忽略", "dismiss")]
        else:
            btns = [("📝 存档", "save"), ("📄 摘要", "summarize"), ("✕ 忽略", "dismiss")]
        clip_bubble.popup(title, btns, _clip_anchor(), timeout_ms=15000)

    clip_watcher.detected.connect(on_clip_detected)

    # ---- 情绪日记（极简版）：纯本地记录，只在用户聊天互动时偶尔问一次 ----
    mood_bubble = ActionBubble()
    pet.register_follow_bubble(mood_bubble)
    chat_msg_count = 0                    # 当天聊天消息计数

    def _schedule_midnight_reset():
        now = datetime.now()
        ms = ((23 - now.hour) * 3600 + (59 - now.minute) * 60
              + (60 - now.second)) * 1000
        QTimer.singleShot(ms + 200, reset_chat_count)

    def reset_chat_count():
        nonlocal chat_msg_count
        chat_msg_count = 0
        _schedule_midnight_reset()        # 每天零点自动重置，循环调度

    _schedule_midnight_reset()

    mood_dlg_ref = {"dlg": None}

    def on_mood_choice(action: str):
        """点了心情表情：本地记录；满一周且本周没展示过总结 → 弹情绪曲线图。"""
        if action not in ("sad", "mid", "happy"):
            return
        mood.set_mood(cfg, {"sad": 1, "mid": 2, "happy": 3}[action])
        save_config(cfg)
        records = mood.week_records(cfg)
        wk = mood._week_key(datetime.now())
        if len(records) >= 7 and cfg.get("mood_summary_week") != wk:
            summary = mood.summary_text(records)
            # 持有引用防止 GC 导致窗口一闪而过
            if mood_dlg_ref["dlg"] is not None:
                mood_dlg_ref["dlg"].close()
            dlg = MoodChartDialog(records, summary)
            mood_dlg_ref["dlg"] = dlg
            dlg.finished.connect(lambda: mood_dlg_ref.update(dlg=None))
            dlg.show()
            cfg["mood_summary_week"] = wk
            save_config(cfg)

    mood_bubble.chosen.connect(on_mood_choice)

    def on_chat_message():
        nonlocal chat_msg_count
        _grant_xp("chat")
        if not cfg.get("mood_enabled", True):
            return
        chat_msg_count += 1
        stats.add(cfg, "chat_count")
        # 当天累计发够 2 条消息，且今天还没问过，才问一次（不打扰）
        if chat_msg_count >= 2 and not mood.has_asked_today(cfg):
            mood_bubble.popup("今天过得怎么样？",
                              [("😔 难过", "sad"), ("😐 一般", "mid"),
                               ("😊 开心", "happy")], _clip_anchor())

    # ---- 本地统计 / 每日总结 / 成就 / 周报（纯本地，低打扰） ----
    def _record_stats():
        """每分钟记录一次活跃/深夜时长，并清理旧数据。"""
        try:
            idle = PetWindow._system_idle_seconds()
        except Exception:
            idle = 999
        if idle < 180:  # 3 分钟内有键盘/鼠标输入 → 视为活跃
            stats.add(cfg, "active_min")
            h = datetime.now().hour
            if h >= 23 or h < 5:
                stats.add(cfg, "night_min")
        stats.prune(cfg)
        save_config(cfg)

    stats_timer = QTimer()
    stats_timer.timeout.connect(_record_stats)
    stats_timer.start(60_000)
    _record_stats()   # 启动先记一次，保证当天有统计

    def maybe_daily_summary():
        """每天一次：弹昨日小结气泡（不弹窗、不打断）。"""
        if not cfg.get("summary_enabled", True):
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if cfg.get("stats_summary_date") == today:
            return
        text = stats.yesterday_text(cfg)
        if text:
            cfg["stats_summary_date"] = today
            save_config(cfg)
            pet.show_bubble(text, 4500)

    def maybe_check_achievements():
        """检查新成就，解锁时庆祝一下。"""
        new = achievements.check_and_unlock(cfg)
        if not new:
            return
        save_config(cfg)
        names = "、".join(f"{a['icon']}{a['name']}" for a in new)
        sfx.play("achievement")
        pet.play_action("proud", 2.5)
        pet.show_prop("sparkle", 2.5)
        pet.show_bubble(f"🏆 解锁新称号：{names}", 4000)

    def maybe_weekly_summary():
        """每周一次：自动弹出本周专注曲线（有数据才弹）。"""
        if not cfg.get("stats_week_summary_enabled", True):
            return
        wk = stats.week_key()
        if cfg.get("stats_week_shown") == wk:
            return
        data = stats.week_focus(cfg)
        if sum(v for _, v in data) <= 0:
            return
        cfg["stats_week_shown"] = wk
        save_config(cfg)
        FocusChartDialog(data).show()

    def _housekeeping():
        maybe_daily_summary()
        maybe_check_achievements()
        maybe_weekly_summary()

    housekeeping = QTimer()
    housekeeping.timeout.connect(_housekeeping)
    housekeeping.start(30 * 60_000)
    QTimer.singleShot(4500, _housekeeping)   # 启动问候播完后跑一次

    # 统计/情绪图表需持有引用，否则函数返回后对象被 Python GC 回收，
    # 窗口会一闪而过（见 open_stats / on_mood_choice）
    stats_dlg_ref = {"dlg": None}

    def open_stats():
        if stats_dlg_ref["dlg"] is not None:
            stats_dlg_ref["dlg"].close()
        dlg = FocusChartDialog(stats.week_focus(cfg))
        stats_dlg_ref["dlg"] = dlg
        dlg.finished.connect(lambda: stats_dlg_ref.update(dlg=None))
        dlg.show()

    # ---- 口袋轻工具面板（便签/天气/待办/随机/计算器） ----
    tools_panel = ToolsPanel()
    _tool_wins = {"note": None, "weather": None, "todo": None,
                  "random": None, "calc": None}

    def _pet_rect():
        return pet.geometry()

    def open_tool(key: str):
        _grant_xp("tool")
        pet_rect = _pet_rect()
        if key == "note":
            if _tool_wins["note"] is None:
                _tool_wins["note"] = NoteWidget(cfg, pet_rect)
            else:
                _tool_wins["note"].show_near(pet_rect)
        elif key == "weather":
            if _tool_wins["weather"] is None:
                _tool_wins["weather"] = WeatherWidget(cfg, pet_rect)
            else:
                _tool_wins["weather"].show_near(pet_rect)
                _tool_wins["weather"]._fetch()
        elif key == "todo":
            if _tool_wins["todo"] is None:
                _tool_wins["todo"] = TodoWidget(cfg, pet_rect)
                _tool_wins["todo"].completed.connect(_on_todo_completed)
            else:
                _tool_wins["todo"].show_near(pet_rect)
        elif key == "random":
            if _tool_wins["random"] is None:
                _tool_wins["random"] = RandomWidget(cfg, pet_rect)
            else:
                _tool_wins["random"].show_near(pet_rect)
        elif key == "calc":
            if _tool_wins["calc"] is None:
                _tool_wins["calc"] = CalcWidget(pet_rect)
            else:
                _tool_wins["calc"].show_near(pet_rect)

    tools_panel.tool_selected.connect(open_tool)

    def _on_todo_completed(_done_count):
        _grant_xp("todo")
        sfx.play("proud")
        pet.play_action("happy", 2.0)
        pet.show_prop("sparkle", 2.0)
        remaining = sum(1 for t in cfg.get("tools_todos", [])
                        if not t.get("done"))
        pet.show_bubble(f"🎉 搞定一件！还剩 {remaining} 件待办，好样的～", 2600)

    def show_tools():
        tools_panel.show_at(_pet_rect())

    # ---- 体力值系统 ----
    energy = EnergyManager(cfg)
    prev_state = {"v": None}
    startup_check = {"done": False}

    # ---- 成长系统（经验/等级/连续天数）：补全 energy → growth → 成就 闭环 ----
    growth = GrowthManager(cfg)

    def _refresh_tooltip():
        pet.set_energy_tooltip(energy.energy, cfg.get("eggs", 0),
                               growth.level(), growth.streak())

    def _grant_xp(source: str, n: int = 1):
        got = growth.add_xp(source, n)
        if got:
            _refresh_tooltip()
            maybe_check_achievements()

    def _on_leveled_up(new_lv: int):
        sfx.play("achievement")
        pet.play_action("proud", 3.0)
        pet.show_prop("sparkle", 3.0)
        pet.show_bubble(f"🎉 升级啦！小团子升到 Lv.{new_lv}，谢谢你陪我～", 3200)
    growth.leveled_up.connect(_on_leveled_up)
    growth.streaked.connect(lambda days: pet.show_bubble(
        f"🔥 连续陪伴 {days} 天啦！", 2600) if days >= 2 else None)
    # ---- 番茄钟专注形象：专注期轮换 4 张，完成显示“完成任务”，休息显示“伸懒腰” ----
    FOCUS_ROTATE = ["focus_work", "focus_note", "focus_read", "focus_think"]
    _pomo_rot = {"i": 0}
    _pomo_rot_timer = QTimer()

    def _rotate_focus():
        _pomo_rot["i"] = (_pomo_rot["i"] + 1) % len(FOCUS_ROTATE)
        pet.set_persistent_action(FOCUS_ROTATE[_pomo_rot["i"]])

    def _start_focus_rotation():
        """专注开始：从“认真工作”起，按专注时长均分轮换 4 张专注形象。"""
        _pomo_rot["i"] = 0
        pet.set_persistent_action(FOCUS_ROTATE[0])
        work_min = max(1, int(cfg.get("pomodoro_work_min", 25) or 25))
        interval = max(30_000, int(work_min * 60_000 / len(FOCUS_ROTATE)))
        _pomo_rot_timer.setInterval(interval)
        _pomo_rot_timer.start()

    def _stop_focus_rotation():
        _pomo_rot_timer.stop()

    def _on_pomo_done():
        # 专注完成 → 经验 + “完成任务”形象
        _grant_xp("pomodoro")
        _stop_focus_rotation()
        sfx.play("pomodoro")
        pet.play_action("pomodoro_done", 2.5)

    def _on_pomo_phase(phase):
        if phase == "work":
            # 休息结束 → 开始新一轮专注轮换
            _start_focus_rotation()
        else:
            # 专注完成已播“完成任务”，稍后切休息“伸懒腰”常驻
            QTimer.singleShot(
                2600,
                lambda: (pet.set_persistent_action("pomodoro_stretch")
                         if cfg.get("pomodoro_running")
                         and cfg.get("pomodoro_phase") == "break" else None))

    reminder.pomodoro_done.connect(_on_pomo_done)
    reminder.pomodoro_phase_changed.connect(_on_pomo_phase)
    growth.check_streak()   # 启动时刷新一次连续天数

    def apply_energy_state():
        _refresh_tooltip()
        state = energy.state()
        pet.set_pet_state(state)
        # 刚进入饥饿状态时提示一次；启动首帧先让打招呼气泡播完再提示
        if state == "hungry" and prev_state["v"] != "hungry":
            if not startup_check["done"]:
                QTimer.singleShot(3600,
                                  lambda: pet.show_bubble("我饿了…🍗", 2000))
            else:
                pet.show_bubble("我饿了…🍗", 2000)
            prev_state["v"] = state
        startup_check["done"] = True

    energy.changed.connect(lambda _v: apply_energy_state())
    apply_energy_state()

    tray = QSystemTrayIcon(tray_icon, app)
    tray.setToolTip("桌面宠物")
    tray_menu = QMenu()
    act_show = QAction("显示/隐藏宠物", tray_menu)
    act_dnm = QAction("防打扰（鼠标穿透）", tray_menu)
    act_dnm.setCheckable(True)
    act_dnm.setChecked(bool(cfg.get("dnm_enabled", False)))
    act_settings = QAction("设置…", tray_menu)
    act_quit = QAction("退出", tray_menu)
    act_show.triggered.connect(lambda: pet.setVisible(not pet.isVisible()))
    act_settings.triggered.connect(lambda: open_settings(pet, cfg))
    act_quit.triggered.connect(app.quit)
    tray_menu.addAction(act_show)
    tray_menu.addAction(act_dnm)
    tray_menu.addSeparator()
    tray_menu.addAction(act_settings)
    tray_menu.addSeparator()
    tray_menu.addAction(act_quit)
    tray.setContextMenu(tray_menu)
    tray.show()

    # 防打扰开关：圆盘菜单 + 托盘菜单共用
    def toggle_dnm():
        on = not pet.dnm
        pet.set_dnm(on)
        save_config(cfg)
        act_dnm.setChecked(on)
        pet.show_bubble("🔇 防打扰开启：鼠标穿透，看视频/打游戏不挡操作～"
                        if on else "🔔 已退出防打扰", 2200)
    act_dnm.triggered.connect(toggle_dnm)

    # 当前打开的圆形菜单（避免重复弹出）
    menu_ref = {"menu": None}

    def show_circle_menu():
        if menu_ref["menu"] is not None:
            return
        apps = cfg.get("apps", [])
        rem_icon = "🔕" if not cfg.get("reminder_enabled", True) else "🔔"
        dnm_icon = "🔇" if pet.dnm else "🔛"
        pomo_icon = "⏹" if cfg.get("pomodoro_running", False) else "🍅"
        actions = [
            {"key": "feed", "name": "喂食", "icon": "🍗"},
            {"key": "chat", "name": "聊天", "icon": "💬"},
            {"key": "aiweb", "name": "AI直达", "icon": "🤖"},
            {"key": "tools", "name": "工具", "icon": "🧰"},
            {"key": "rps", "name": "猜拳", "icon": "🪨"},
            {"key": "stats", "name": "统计", "icon": "📊"},
            {"key": "remind", "name": "提醒", "icon": rem_icon},
            {"key": "pomodoro", "name": "番茄钟", "icon": pomo_icon},
            {"key": "dnm", "name": "防打扰", "icon": dnm_icon},
        ]
        menu = CircleMenu(apps, actions=actions)
        menu_ref["menu"] = menu
        menu.item_clicked.connect(on_item_clicked)
        menu.action_triggered.connect(on_action_triggered)
        menu.destroyed.connect(lambda: menu_ref.update(menu=None))
        pet.pause_wander(True)
        menu.show_at(pet.geometry())
        # 菜单关闭后恢复游走（聊天开着时不要恢复，否则桌宠会飘走挡住聊天窗）
        menu.destroyed.connect(resume_wander)

    def on_item_clicked(app: dict):
        ok, err = launch(app)
        if ok:
            sfx.play("app_launch")
            pet.play_action("work", 3.0)   # 任务运行中 → 敲键盘素材
            # 启动完成 → 成功反馈素材
            QTimer.singleShot(3100,
                              lambda: pet.play_action("success", 2.0))
        else:
            sfx.play("error")
            QMessageBox.information(pet, "桌宠", err)
            pet.play_action("error", 2.0)  # 任务失败/报错 → 报错失败素材
            pet.show_prop("exclaim", 2.0)

    def open_chat():
        if not cfg.get("chat_enabled", True):
            pet.show_bubble("聊天暂时关掉了，在设置里打开就能聊啦～")
            return
        dlg = chat_ref["dlg"]
        if dlg is not None and dlg.isVisible():
            dlg.raise_()
            dlg.activateWindow()
            # 重新停靠：桌宠可能游走到了别处
            dock_chat_beside_pet(dlg, pet)
            return
        dlg = ChatDialog(bot, ai_client=ai, parent=pet, avatar_sheet=avatar_sheet,
                         cfg=cfg)
        chat_ref["dlg"] = dlg
        pet.play_action("wave", 2.0)        # AI 聊天开场 → 挥手
        # 用户在输入框打字 → 倾听姿势素材
        dlg.user_typing.connect(lambda: pet.play_action("listening", 3.0))
        # 用户发消息 → 情绪日记偶尔问一次心情
        dlg.message_sent.connect(on_chat_message)
        # AI 等待回复 → “加载中”素材 + 问号道具；回复结束 → 短暂“AI说话中”
        dlg.ai_started.connect(lambda: pet.play_action("loading", 30))
        dlg.ai_started.connect(lambda: pet.show_prop("question", 30))
        dlg.ai_finished.connect(pet.end_action)
        dlg.ai_finished.connect(pet.clear_prop)
        dlg.ai_finished.connect(lambda: sfx.play("chat_in"))
        dlg.ai_finished.connect(lambda: pet.play_action("ai_talking", 2.5))
        dlg.destroyed.connect(lambda: chat_ref.update(dlg=None))
        dlg.show()
        # 停靠桌宠旁边：聊天窗与桌宠并排，宠物表情不被遮挡；聊天期间暂停游走
        pet.pause_wander(True)
        dock_chat_beside_pet(dlg, pet)
        dlg.destroyed.connect(resume_wander)

    # ---- 猜拳小游戏（直接在桌宠本体 + 旁侧按钮气泡，无独立窗口） ----
    rps_bubble = ActionBubble()
    pet.register_follow_bubble(rps_bubble)   # 按钮气泡随宠物移动

    # 手势映射：用户出拳 key -> 桌宠对应的猜拳手势图 key
    RPS_PET_PIC = {"rock": "rps_rock", "scissor": "rps_scissor",
                   "paper": "rps_paper"}

    def _rps_anchor() -> QPoint:
        """按钮气泡锚点：桌宠头顶偏左（避免盖住手势图）。"""
        g = pet.geometry()
        return QPoint(g.center().x() - g.width() // 3, g.top())

    # 手势图展示时长（先出拳 → 再结果动作），单位毫秒
    RPS_HOLD_MS = 2000

    def _on_rps_choice(user_key: str):
        """用户点完石头/剪刀/布 → 桌宠先出拳（手势图保持 RPS_HOLD_MS）
        → 再切换结果动作图 + 气泡反馈。"""
        if user_key not in RPS_PET_PIC:
            _rps_busy["on"] = False
            pet.end_action()               # 取消 → 恢复形象
            resume_wander()
            return
        _rps_busy["on"] = True             # 出拳动画中：关闭气泡时不要恢复游走
        pet.pause_wander(True)             # 点按钮时气泡先关闭已恢复游走，这里重新暂停
        pet_key = random.choice(["rock", "scissor", "paper"])
        # 判定：石头>剪刀，剪刀>布，布>石头
        if pet_key == user_key:
            result = "draw"
        elif (pet_key, user_key) in (("rock", "scissor"),
                                     ("scissor", "paper"),
                                     ("paper", "rock")):
            result = "win"
        else:
            result = "lose"
        icons = {"rock": "🪨", "scissor": "✂️", "paper": "📄"}

        # 第一步：桌宠亮出对应手势图，保持 RPS_HOLD_MS 毫秒
        sfx.play("rps_ready")
        pet.play_action(RPS_PET_PIC[pet_key], RPS_HOLD_MS / 1000.0)

        def _show_result():
            _rps_busy["on"] = False
            if result == "win":
                _grant_xp("rps_win")
                reminder.add_egg(1)   # 获胜 → 加一颗蛋（攒满自动孵化）
                _refresh_tooltip()
                sfx.play("rps_win")
                pet.show_bubble(f"我出{icons[pet_key]} 你出{icons[user_key]}\n🎉 你赢啦！奖励一颗蛋 🥚", 2600)
                pet.play_action("sad", 2.0)      # 你赢我沮丧
            elif result == "lose":
                _grant_xp("rps_play")
                sfx.play("rps_lose")
                pet.show_bubble(f"我出{icons[pet_key]} 你出{icons[user_key]}\n😄 我赢啦！", 2200)
                pet.play_action("happy", 2.0)    # 我赢我开心
                pet.show_prop("sparkle", 2.0)
            else:
                _grant_xp("rps_play")
                sfx.play("rps_ready")
                pet.show_bubble(f"我出{icons[pet_key]} 你出{icons[user_key]}\n🤝 平局，再来！", 2200)
                pet.play_action("wave", 1.6)
            # 结果动作播放完后再恢复游走
            QTimer.singleShot(2200, resume_wander)
        QTimer.singleShot(RPS_HOLD_MS, _show_result)

    _rps_busy = {"on": False}
    rps_bubble.chosen.connect(_on_rps_choice)
    # 气泡被关闭（ESC/取消/点外部）→ 恢复桌宠形象；出拳动画中不恢复游走
    def _on_rps_bubble_closed():
        pet.end_action()
        if not _rps_busy["on"]:
            resume_wander()
    rps_bubble.closed.connect(_on_rps_bubble_closed)

    def open_rps():
        # 桌宠切换“准备出拳”形象 + 旁边弹三个出拳按钮
        pet.play_action("rps_ready", 4.0)
        pet.pause_wander(True)               # 玩猜拳期间暂停游走
        btns = [("🪨 石头", "rock"),
                ("✂️ 剪刀", "scissor"),
                ("📄 布", "paper"),
                ("✕ 取消", "dismiss")]
        rps_bubble.popup("来，石头剪刀布！", btns, _rps_anchor())

    def on_action_triggered(key: str):
        if key == "feed":
            foods = cfg.get("foods", [])
            food = random.choice(foods) if foods \
                else {"name": "食物", "icon": "🍗", "gain": 20}
            gained = energy.feed(food)
            if gained > 0:
                _grant_xp("feed")
                sfx.play("eat")
                pet.show_bubble(f"{food['icon']} +{gained} 真好吃！", 2600)
                pet.play_feed_effect()
                # 投喂 → 吃东西素材 + 零食道具；吃完 → 得意叉腰（好感度提升）
                pet.play_action("eat", 1.6)
                pet.show_prop("snack", 1.6)
                QTimer.singleShot(1700, lambda: pet.play_action("proud", 1.6))
            else:
                sfx.play("sad")
                pet.show_bubble("吃不下啦～肚肚圆滚滚的", 2000)
                pet.play_action("sad", 1.8)   # 低好感/吃不下 → 沮丧
                pet.show_prop("exclaim", 1.8)
            energy.snapshot()
            save_config(cfg)
        elif key == "chat":
            open_chat()
        elif key == "rps":
            open_rps()
        elif key == "remind":
            on = not cfg.get("reminder_enabled", True)
            cfg["reminder_enabled"] = on
            save_config(cfg)
            pet.show_bubble("🔔 提醒已开启" if on else "🔕 提醒已关闭")
        elif key == "pomodoro":
            toggle_pomodoro()
        elif key == "dnm":
            toggle_dnm()
        elif key == "aiweb":
            _show_ai_web_menu()
        elif key == "stats":
            open_stats()
        elif key == "tools":
            show_tools()

    # ---- AI 网页快捷入口（半自动：开网页 + 内容留剪贴板，你粘贴即可） ----
    aiweb_bubble = ActionBubble()
    pet.register_follow_bubble(aiweb_bubble)

    def _on_aiweb_choice(key: str):
        if key not in web_ai.SITES:
            return
        site = web_ai.SITES[key]
        web_ai.open_site(key)
        pet.play_action("think", 1.5)
        cb = ""
        try:
            cb = QApplication.clipboard().text().strip()
        except Exception:
            pass
        if cb and len(cb) > 3:
            pet.show_bubble(f"已打开 {site['name']}，剪贴板已就绪，去网页 Ctrl+V 粘贴吧～", 3200)
        else:
            pet.show_bubble(f"已打开 {site['name']}，内容可手动输入～", 2200)

    aiweb_bubble.chosen.connect(_on_aiweb_choice)

    def _show_ai_web_menu():
        # 短标签避免气泡过宽；附“取消”保证随时能关掉
        btns = [(s["name"], k) for k, s in web_ai.SITES.items()]
        btns.append(("✕ 取消", "dismiss"))
        aiweb_bubble.popup("把剪贴板内容发给哪个 AI？", btns, _clip_anchor())

    def toggle_pomodoro():
        """启动/停止番茄时钟：专注计时，结束时切番茄钟提醒素材。"""
        if not cfg.get("pomodoro_enabled", False):
            pet.show_bubble("番茄钟未开启，请在设置里打开 ⚙️", 2000)
            return
        if cfg.get("pomodoro_running", False):
            cfg["pomodoro_running"] = False
            cfg["pomodoro_end_ts"] = 0.0
            save_config(cfg)
            _stop_focus_rotation()
            pet.end_action()
            pet.clear_persistent_action()
            pet.show_bubble("⏹ 番茄钟已停止", 1800)
        else:
            work_min = int(cfg.get("pomodoro_work_min", 25))
            cfg["pomodoro_running"] = True
            cfg["pomodoro_phase"] = "work"
            cfg["pomodoro_end_ts"] = time.time() + work_min * 60
            save_config(cfg)
            pet.play_action("tomato", 3.0)
            pet.show_prop("tomato", 3.0)
            # 3 秒开始动画后进入专注形象轮换（认真工作→记笔记→阅读中→思考问题）
            QTimer.singleShot(3000, _start_focus_rotation)
            pet.show_bubble(f"🍅 番茄钟开始！专注 {work_min} 分钟，加油～", 2600)

    def open_settings(pet_widget, cfg):
        # 打开设置期间暂停桌宠提醒/气泡：桌宠弹窗是独立置顶窗口，
        # 不受设置对话框模态限制，会盖在设置页上方，因此这里统一暂停，
        # 关闭设置后自动恢复
        reminder.set_paused(True)
        try:
            dlg = SettingsDialog(cfg, pet_widget)
            ok = dlg.exec()
        finally:
            reminder.set_paused(False)
        if ok:
            save_config(cfg)
            pet_widget.apply_config(cfg)
            # 名字或聊天开关变化后同步机器人
            bot.pet_name = cfg.get("pet_name", "小团子")
            if chat_ref["dlg"] is not None:
                chat_ref["dlg"].bot = bot
                chat_ref["dlg"].setWindowTitle(f"{bot.pet_name} 的聊天室")
                # 同步聊天外观（背景 / 头像）
                chat_ref["dlg"]._apply_bg()
                if chat_ref["dlg"]._messages:
                    chat_ref["dlg"]._refresh_messages()
            # 同步托盘图标到当前形象
            tray.setIcon(build_tray_icon(cfg))
            # 生日/节日开关变化后立即刷新节日形象
            reminder.refresh_festival_idle()

    pet.clicked.connect(show_circle_menu)
    pet.settings_requested.connect(lambda: open_settings(pet, cfg))
    pet.quit_requested.connect(app.quit)

    # ---- 全局快捷键（Ctrl+Alt+字母，无需点击直接调用功能） ----
    hotkeys = GlobalHotkey()

    def _on_hotkey(func_key: str):
        if func_key == "toggle_pet":
            pet.setVisible(not pet.isVisible())
        elif func_key == "chat":
            open_chat()
        elif func_key == "aiweb":
            _show_ai_web_menu()
        elif func_key == "tools":
            show_tools()
        elif func_key == "weather":
            open_tool("weather")
        elif func_key == "note":
            open_tool("note")
        elif func_key == "todo":
            open_tool("todo")
        elif func_key == "calc":
            open_tool("calc")
        elif func_key == "pomodoro":
            toggle_pomodoro()
        elif func_key == "dnm":
            toggle_dnm()

    def _on_hotkey_ready(failed: list):
        if failed:
            keys = "、".join(f"Ctrl+Alt+{DEFAULT_MAP.get(k, '?')}" for k in failed)
            pet.show_bubble(
                f"⌨️ 快捷键 {keys} 被其他程序占用，对应功能暂不可用", 4000)

    hotkeys.hotkey_triggered.connect(_on_hotkey)
    hotkeys.ready.connect(_on_hotkey_ready)
    hotkeys.start()

    # ---- ESC 关闭浮层（气泡 / 工具面板 / 小工具窗 / 猜拳按钮 / 圆盘菜单） ----
    def _esc_targets():
        tools = [w for w in _tool_wins.values() if w is not None]
        menu = menu_ref.get("menu")   # 当前打开的圆盘菜单（None=未打开）
        return [aiweb_bubble, clip_bubble, mood_bubble, rps_bubble, menu,
                tools_panel] + tools

    _esc_filter = _EscCloseFilter(_esc_targets)
    app.installEventFilter(_esc_filter)

    app.aboutToQuit.connect(
        lambda: (energy.snapshot(), save_config(cfg), hotkeys.stop()))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
