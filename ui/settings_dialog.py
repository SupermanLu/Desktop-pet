# -*- coding: utf-8 -*-
"""设置对话框：行为、宠物名、提醒开关、应用列表增删。"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QCheckBox, QSlider, QListWidget, QListWidgetItem,
                               QPushButton, QFileDialog, QLabel, QGroupBox,
                               QLineEdit, QComboBox, QDialogButtonBox,
                               QScrollArea, QFrame, QWidget, QSpinBox)

from core.autostart import is_autostart, set_autostart, current_exe
from core.config import ASSETS_DIR, norm_project_path
from core.event_reminder import REPEAT_LABELS
from core.sandbox import SANDBOX_ROOT
from ui.event_dialog import EventDialog


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self.setWindowTitle("桌宠设置")
        # 置顶显示：桌宠的提醒气泡等浮层是独立置顶窗口，
        # 不加置顶会被它们盖住（配合 main.py 打开设置时暂停提醒）
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(420)
        # 限制窗口不超出屏幕（内容过长可滚动）
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(480, geo.width() - 80), min(620, geo.height() - 120))
        self.setMaximumSize(geo.width() - 40, geo.height() - 40)

        lay = QVBoxLayout(self)
        # 主内容放进滚动区域，超出窗口高度时用滚轮翻看
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        inner = QVBoxLayout(container)
        inner.setContentsMargins(4, 4, 4, 4)
        inner.setSpacing(10)
        scroll.setWidget(container)
        lay.addWidget(scroll, 1)

        # ---- 宠物 ----
        pet_group = QGroupBox("宠物", self)
        pf = QFormLayout(pet_group)
        self.edit_name = QLineEdit(cfg.get("pet_name", "小团子"))
        self.edit_name.setMaxLength(8)
        self.edit_name.setStyleSheet(
            "QLineEdit { background: white; padding:4px 8px; font-size:14px;"
            " color:#333333; border:1px solid #e6c99a; border-radius:8px;"
            " selection-background-color:#ff9f43; selection-color:white; }")
        self.chk_chat = QCheckBox("开启聊天功能")
        self.chk_chat.setChecked(bool(cfg.get("chat_enabled", True)))
        # 形象：程序绘制 + assets 图片 + 自定义，合并为一个下拉
        self.skin_combo = QComboBox()
        self.skin_combo.setStyleSheet(
            "QComboBox { background: white; color:#333333; padding:4px 8px;"
            " border:1px solid #e6c99a; border-radius:8px; }"
            "QComboBox QAbstractItemView { background: white; color:#333333;"
            " selection-background-color:#ff9f43; selection-color:white; }")
        self._pet_gif = cfg.get("pet_gif", "") or ""
        self.skin_combo.currentIndexChanged.connect(self._on_skin_change)
        self._load_skin_combo()
        pf.addRow("宠物名", self.edit_name)
        pf.addRow("形象", self.skin_combo)
        pf.addRow(self.chk_chat)
        inner.addWidget(pet_group)

        # ---- 聊天外观（哆啦A梦主题） ----
        look_group = QGroupBox("聊天外观", self)
        look_v = QVBoxLayout(look_group)
        self.chk_chat_bg = QCheckBox("聊天背景图（哆啦A梦主题）")
        self.chk_chat_bg.setChecked(bool(cfg.get("chat_bg_enabled", True)))
        bg_row = QHBoxLayout()
        btn_pick_bg = QPushButton("选择背景图片…")
        btn_pick_bg.clicked.connect(self._pick_chat_bg)
        btn_reset_bg = QPushButton("恢复内置主题")
        btn_reset_bg.clicked.connect(self._reset_chat_bg)
        bg_hint = QLabel("（也可在聊天窗右上角 🎨 快捷切换）")
        bg_hint.setStyleSheet("color:#8a7a62; font-size:12px;")
        bg_row.addWidget(btn_pick_bg)
        bg_row.addWidget(btn_reset_bg)
        bg_row.addWidget(bg_hint)
        bg_row.addStretch(1)
        self.chk_chat_avatar = QCheckBox("聊天头像（微信样式，宠物=哆啦A梦）")
        self.chk_chat_avatar.setChecked(bool(cfg.get("chat_avatar_enabled", True)))
        av_row = QHBoxLayout()
        btn_pick_av = QPushButton("更换用户头像…")
        btn_pick_av.clicked.connect(self._pick_user_avatar)
        av_hint = QLabel("（用户头像，宠物头像自动用哆啦A梦）")
        av_hint.setStyleSheet("color:#8a7a62; font-size:12px;")
        av_row.addWidget(btn_pick_av)
        av_row.addWidget(av_hint)
        av_row.addStretch(1)
        look_v.addWidget(self.chk_chat_bg)
        look_v.addLayout(bg_row)
        look_v.addWidget(self.chk_chat_avatar)
        look_v.addLayout(av_row)
        inner.addWidget(look_group)

        # ---- 行为设置 ----
        group = QGroupBox("行为", self)
        form = QFormLayout(group)
        self.chk_top = QCheckBox("窗口置顶")
        self.chk_top.setChecked(bool(cfg.get("always_on_top", True)))
        self.chk_wander = QCheckBox("宠物在屏幕上游走")
        self.chk_wander.setChecked(bool(cfg.get("wander", True)))
        self.chk_fs_pause = QCheckBox("全屏时自动挂起（不影响观影）")
        self.chk_fs_pause.setChecked(bool(cfg.get("fullscreen_pause_enabled", True)))
        self.cmb_fs_mode = QComboBox()
        self.cmb_fs_mode.addItem("挂边待机（露出小边）", "hang")
        self.cmb_fs_mode.addItem("完全隐藏", "hide")
        cur = cfg.get("fullscreen_pause_mode", "hang")
        idx = self.cmb_fs_mode.findData(cur)
        self.cmb_fs_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.chk_autostart = QCheckBox("开机自启")
        self.chk_autostart.setChecked(is_autostart())

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(70, 220)
        self.size_slider.setValue(int(cfg.get("pet_size", 120)))
        self.size_label = QLabel(f"{self.size_slider.value()} px")

        form.addRow(self.chk_top)
        form.addRow(self.chk_wander)
        form.addRow(self.chk_fs_pause)
        form.addRow("全屏挂起方式", self.cmb_fs_mode)
        form.addRow(self.chk_autostart)
        form.addRow("宠物大小", self._wrap(self.size_slider, self.size_label))
        inner.addWidget(group)

        # ---- 关怀提醒 ----
        rm_group = QGroupBox("关怀提醒", self)
        rm_v = QVBoxLayout(rm_group)
        self.chk_reminder = QCheckBox("启用所有提醒（🔔）")
        self.chk_reminder.setChecked(bool(cfg.get("reminder_enabled", True)))
        self.chk_sound = QCheckBox("提醒提示音（🔊）")
        self.chk_sound.setChecked(bool(cfg.get("reminder_sound_enabled", True)))
        # 程序合成音效：总开关 + 音量滑块
        self.chk_sfx = QCheckBox("音效（🔉 交互/聊天/彩蛋等）")
        self.chk_sfx.setChecked(bool(cfg.get("sfx_enabled", True)))
        self.sfx_slider = QSlider(Qt.Horizontal)
        self.sfx_slider.setRange(0, 100)
        self.sfx_slider.setValue(int(cfg.get("sfx_volume", 80)))
        self.sfx_label = QLabel(f"{self.sfx_slider.value()}%")
        sfx_row = QHBoxLayout()
        sfx_row.addWidget(self.sfx_slider)
        sfx_row.addWidget(self.sfx_label)
        self.sfx_slider.valueChanged.connect(
            lambda v: self.sfx_label.setText(f"{v}%"))
        self.chk_meal = QCheckBox("饭点提醒（早/中/晚/夜宵）")
        self.chk_meal.setChecked(bool(cfg.get("meal_remind", True)))
        self.chk_late = QCheckBox("深夜提醒（超过 22:30 提示休息）")
        self.chk_late.setChecked(bool(cfg.get("late_remind", True)))
        self.chk_sit = QCheckBox(f"久坐提醒（每 {cfg.get('sit_interval_min', 90)} 分钟）")
        self.chk_sit.setChecked(bool(cfg.get("sit_remind", True)))
        self.chk_water = QCheckBox(f"喝水提醒（每 {cfg.get('water_interval_min', 50)} 分钟）")
        self.chk_water.setChecked(bool(cfg.get("water_remind", True)))
        self.chk_encourage = QCheckBox(f"专注鼓励（连续 {cfg.get('encourage_min', 15)} 分钟）")
        self.chk_encourage.setChecked(bool(cfg.get("encourage_remind", True)))
        self.chk_egg = QCheckBox(f"专注攒蛋（每 {cfg.get('focus_egg_min', 30)} 分钟得 1 蛋 🥚）")
        self.chk_egg.setChecked(bool(cfg.get("egg_remind", True)))
        self.chk_tips = QCheckBox(f"健康小贴士（每 {cfg.get('tip_interval_min', 120)} 分钟）")
        self.chk_tips.setChecked(bool(cfg.get("tips_remind", True)))
        self.chk_festival = QCheckBox("节日祝福（元旦/情人节/圣诞等）")
        self.chk_festival.setChecked(bool(cfg.get("festival_remind", True)))
        self.chk_hourly = QCheckBox("整点鼓励（每小时一次）")
        self.chk_hourly.setChecked(bool(cfg.get("hourly_remind", True)))
        self.chk_time_care = QCheckBox("时间情景关怀（早晨问候/午休/下午茶/晚间/深夜陪伴）")
        self.chk_time_care.setChecked(bool(cfg.get("time_care_enabled", True)))
        care_row = QHBoxLayout()
        care_label = QLabel("相邻提醒最小间隔")
        care_label.setStyleSheet("color:#5a3a15; font-size:12px;")
        self.spin_care_cooldown = QSpinBox()
        self.spin_care_cooldown.setRange(0, 60)
        self.spin_care_cooldown.setSuffix(" 分钟")
        self.spin_care_cooldown.setSpecialValueText("关闭")
        self.spin_care_cooldown.setValue(int(cfg.get("time_care_cooldown_min", 10)))
        self.spin_care_cooldown.setToolTip("防止多条提醒在启动时或同一时段堆叠刷屏")
        care_row.addWidget(care_label)
        care_row.addWidget(self.spin_care_cooldown)
        care_row.addStretch(1)
        rm_v.addWidget(self.chk_reminder)
        rm_v.addWidget(self.chk_sound)
        rm_v.addWidget(self.chk_sfx)
        rm_v.addLayout(sfx_row)
        rm_v.addWidget(self.chk_meal)
        rm_v.addWidget(self.chk_late)
        rm_v.addWidget(self.chk_sit)
        rm_v.addWidget(self.chk_water)
        rm_v.addWidget(self.chk_encourage)
        rm_v.addWidget(self.chk_egg)
        rm_v.addWidget(self.chk_tips)
        rm_v.addWidget(self.chk_festival)
        rm_v.addWidget(self.chk_hourly)
        rm_v.addWidget(self.chk_time_care)
        rm_v.addLayout(care_row)
        # 节日形象 + 生日
        self.chk_festival_idle = QCheckBox("节日形象开关（春节/元宵/清明/端午/七夕/中秋/重阳/圣诞/生日）")
        self.chk_festival_idle.setChecked(bool(cfg.get("festival_idle_enabled", True)))
        rm_v.addWidget(self.chk_festival_idle)
        bday_row = QHBoxLayout()
        bday_label = QLabel("生日（阳历 MM-DD）")
        bday_label.setStyleSheet("color:#5a3a15; font-size:12px;")
        self.bday_input = QLineEdit(cfg.get("birthday") or "")
        self.bday_input.setMaxLength(5)
        self.bday_input.setPlaceholderText("如 08-15")
        self.bday_input.setStyleSheet(
            "QLineEdit { background: white; padding:3px 6px; font-size:13px;"
            " color:#333333; border:1px solid #e6c99a; border-radius:6px;"
            " selection-background-color:#ff9f43; selection-color:white; }")
        bday_hint = QLabel("（生日当天显示🎂待机图）")
        bday_hint.setStyleSheet("color:#8a7a62; font-size:12px;")
        bday_row.addWidget(bday_label)
        bday_row.addWidget(self.bday_input)
        bday_row.addWidget(bday_hint)
        bday_row.addStretch(1)
        rm_v.addLayout(bday_row)
        self.chk_mood = QCheckBox("情绪日记（每天在你聊天互动时偶尔问一次心情，纯本地记录陪伴）")
        self.chk_mood.setChecked(bool(cfg.get("mood_enabled", True)))
        rm_v.addWidget(self.chk_mood)
        inner.addWidget(rm_group)

        # ---- 鼠标交互 & 防打扰 ----
        ia_group = QGroupBox("鼠标交互 & 防打扰", self)
        ia_v = QVBoxLayout(ia_group)
        self.chk_gaze = QCheckBox("光标靠近时眼神跟随（转头看光标）")
        self.chk_gaze.setChecked(bool(cfg.get("interact_gaze", True)))
        self.chk_hang = QCheckBox("拖到屏幕边缘（接触边框）自动挂边待机")
        self.chk_hang.setChecked(bool(cfg.get("interact_hang", True)))
        self.chk_work_sync = QCheckBox("敲键盘时显示“敲键盘工作”素材（键盘联动）")
        self.chk_work_sync.setChecked(bool(cfg.get("work_sync_enabled", True)))
        self.chk_reading = QCheckBox("长时间不理 → 看书待机形象（安静看书）")
        self.chk_reading.setChecked(bool(cfg.get("reading_enabled", True)))
        ia_form = QFormLayout()
        self.spin_yawn = QSpinBox()
        self.spin_yawn.setRange(30, 3600)
        self.spin_yawn.setSuffix(" 秒")
        self.spin_yawn.setValue(int(cfg.get("interact_yawn_sec", 90)))
        self.spin_sleep = QSpinBox()
        self.spin_sleep.setRange(60, 7200)
        self.spin_sleep.setSuffix(" 秒")
        self.spin_sleep.setValue(int(cfg.get("interact_sleep_sec", 900)))
        self.spin_reading = QSpinBox()
        self.spin_reading.setRange(10, 7200)
        self.spin_reading.setSuffix(" 秒")
        self.spin_reading.setValue(int(cfg.get("reading_idle_sec", 420)))
        self.chk_dnm = QCheckBox("防打扰：鼠标穿透（点不到宠物，不挡操作）")
        self.chk_dnm.setChecked(bool(cfg.get("dnm_enabled", False)))
        self.spin_dnm_auto = QSpinBox()
        self.spin_dnm_auto.setRange(0, 180)
        self.spin_dnm_auto.setSuffix(" 分钟")
        self.spin_dnm_auto.setSpecialValueText("关闭")
        self.spin_dnm_auto.setValue(int(cfg.get("dnm_auto_min", 0)))
        ia_form.addRow("空闲多久打哈欠", self.spin_yawn)
        ia_form.addRow("空闲多久睡眠", self.spin_sleep)
        ia_form.addRow("空闲多久看书", self.spin_reading)
        ia_form.addRow("空闲自动防打扰", self.spin_dnm_auto)
        ia_v.addWidget(self.chk_gaze)
        ia_v.addWidget(self.chk_hang)
        ia_v.addWidget(self.chk_work_sync)
        ia_v.addWidget(self.chk_reading)
        ia_v.addLayout(ia_form)
        ia_v.addWidget(self.chk_dnm)
        inner.addWidget(ia_group)

        # ---- 番茄时钟 ----
        pm_group = QGroupBox("番茄时钟（专注/休息）", self)
        pm_v = QVBoxLayout(pm_group)
        self.chk_pomodoro = QCheckBox("启用番茄时钟（圆形菜单 🍅 启动/停止）")
        self.chk_pomodoro.setChecked(bool(cfg.get("pomodoro_enabled", False)))
        pm_form = QFormLayout()
        self.spin_pm_work = QSpinBox()
        self.spin_pm_work.setRange(1, 120)
        self.spin_pm_work.setSuffix(" 分钟")
        self.spin_pm_work.setValue(int(cfg.get("pomodoro_work_min", 25)))
        self.spin_pm_break = QSpinBox()
        self.spin_pm_break.setRange(1, 60)
        self.spin_pm_break.setSuffix(" 分钟")
        self.spin_pm_break.setValue(int(cfg.get("pomodoro_break_min", 5)))
        pm_form.addRow("专注时长", self.spin_pm_work)
        pm_form.addRow("休息时长", self.spin_pm_break)
        hint_pm = QLabel("专注结束会切换“番茄钟提醒”形象并提示休息，"
                         "之后自动进入休息，再自动开始新一轮专注。")
        hint_pm.setWordWrap(True)
        hint_pm.setStyleSheet("color:#8a7a62; font-size:12px;")
        pm_v.addWidget(self.chk_pomodoro)
        pm_v.addLayout(pm_form)
        pm_v.addWidget(hint_pm)
        inner.addWidget(pm_group)

        # ---- 统计与成就 ----
        st_group = QGroupBox("统计与成就", self)
        st_v = QVBoxLayout(st_group)
        self.chk_summary = QCheckBox("每日总结（每天一次，气泡回顾昨天专注/喝水/心情）")
        self.chk_summary.setChecked(bool(cfg.get("summary_enabled", True)))
        self.chk_week = QCheckBox("每周专注曲线（自动弹出本周活跃柱状图）")
        self.chk_week.setChecked(bool(cfg.get("stats_week_summary_enabled", True)))
        ach_label = QLabel("已解锁：")
        ach_label.setStyleSheet("color:#5a3a15; font-size:12px; font-weight:bold;")
        self.ach_text = QLabel()
        self.ach_text.setWordWrap(True)
        self.ach_text.setStyleSheet("color:#8a7a62; font-size:11px;")
        self._refresh_ach(cfg)
        st_v.addWidget(self.chk_summary)
        st_v.addWidget(self.chk_week)
        st_v.addWidget(ach_label)
        st_v.addWidget(self.ach_text)
        inner.addWidget(st_group)

        # ---- 事件提醒 ----
        ev_group = QGroupBox("事件提醒", self)
        ev_v = QVBoxLayout(ev_group)
        self.list_events = QListWidget(ev_group)
        self._reload_events()
        ev_row = QHBoxLayout()
        btn_add_ev = QPushButton("添加事件", ev_group)
        btn_del_ev = QPushButton("移除选中", ev_group)
        btn_add_ev.clicked.connect(self._add_event)
        btn_del_ev.clicked.connect(self._del_event)
        ev_row.addWidget(btn_add_ev)
        ev_row.addWidget(btn_del_ev)
        ev_row.addStretch(1)
        ev_v.addWidget(self.list_events)
        ev_v.addLayout(ev_row)
        inner.addWidget(ev_group)

        # ---- AI 对话 ----
        ai_group = QGroupBox("AI 对话", self)
        ai_form = QFormLayout(ai_group)
        self.chk_ai = QCheckBox("启用 AI 对话（未配置时自动回退本地聊天）")
        self.chk_ai.setChecked(bool(cfg.get("ai_enabled", False)))
        ai_style = ("QLineEdit { background: white; color:#333333;"
                    " border:1px solid #e6c99a; border-radius:8px; padding:4px 8px;"
                    " selection-background-color:#ff9f43; selection-color:white; }")
        self.ai_base = QLineEdit(cfg.get("ai_base_url", "https://open.bigmodel.cn/api/paas/v4"))
        self.ai_base.setStyleSheet(ai_style)
        self.ai_key = QLineEdit(cfg.get("ai_api_key", ""))
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_key.setStyleSheet(ai_style)
        self.ai_model = QLineEdit(cfg.get("ai_model", "glm-4.7-flash"))
        self.ai_model.setStyleSheet(ai_style)
        hint = QLabel("支持 OpenAI 兼容接口：智谱 / DeepSeek / 通义 / Kimi 等。\n"
                      "默认配置为智谱免费模型 GLM-4.7-Flash，需先注册获取 API Key。\n"
                      "Key 保存在本地 config.json。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a7a62; font-size:12px;")
        ai_form.addRow(self.chk_ai)
        ai_form.addRow("接口地址", self.ai_base)
        ai_form.addRow("API Key", self.ai_key)
        ai_form.addRow("模型名", self.ai_model)
        self.chk_ai_web = QCheckBox("AI 联网搜索（可查最新资讯，时效性问题回答更准）")
        self.chk_ai_web.setChecked(bool(cfg.get("ai_web_search", True)))
        ai_form.addRow(self.chk_ai_web)
        self.chk_ai_tools = QCheckBox("AI 可执行桌宠操作（设提醒/开番茄钟/打开应用）")
        self.chk_ai_tools.setChecked(bool(cfg.get("ai_tools_enabled", True)))
        ai_form.addRow(self.chk_ai_tools)
        self.chk_clip = QCheckBox("剪贴板助手（检测复制内容，可选收藏/解释；默认关闭，保护隐私）")
        self.chk_clip.setChecked(bool(cfg.get("clipboard_assistant_enabled", False)))
        ai_form.addRow(self.chk_clip)
        self.chk_clip_hist = QCheckBox(
            "保存剪贴板历史（最近 300 条，本地保存，可搜索/重新复制）")
        self.chk_clip_hist.setChecked(bool(cfg.get("clip_history_enabled", True)))
        ai_form.addRow(self.chk_clip_hist)
        sand_row = QHBoxLayout()
        btn_open_sand = QPushButton("打开沙盒文件夹")
        btn_open_sand.clicked.connect(self._open_sandbox)
        sand_hint = QLabel("（收藏/片段/笔记都存这里，纯本地）")
        sand_hint.setStyleSheet("color:#8a7a62; font-size:12px;")
        sand_row.addWidget(btn_open_sand)
        sand_row.addWidget(sand_hint)
        sand_row.addStretch(1)
        ai_form.addRow(sand_row)
        ai_form.addRow(hint)
        # 长期记忆：展示已记住的信息，可一键清空
        mem_row = QHBoxLayout()
        mem_title = QLabel("AI 记住的信息")
        mem_title.setStyleSheet("color:#5a3a15; font-size:12px; font-weight:bold;")
        btn_clear_mem = QPushButton("清空")
        btn_clear_mem.setFixedWidth(60)
        btn_clear_mem.clicked.connect(self._clear_mem)
        mem_row.addWidget(mem_title)
        mem_row.addStretch(1)
        mem_row.addWidget(btn_clear_mem)
        self.mem_label = QLabel(self._fmt_mem(cfg.get("ai_memory", [])))
        self.mem_label.setWordWrap(True)
        self.mem_label.setStyleSheet(
            "color:#5a3a15; font-size:12px; background:#fff7ea;"
            " border:1px solid #e6c99a; border-radius:8px; padding:6px 8px;")
        ai_form.addRow(mem_row)
        ai_form.addRow(self.mem_label)
        inner.addWidget(ai_group)

        # ---- 快捷应用 ----
        app_group = QGroupBox("快捷应用", self)
        v = QVBoxLayout(app_group)
        self.list_apps = QListWidget(app_group)
        self._reload_apps()
        btn_row = QHBoxLayout()
        btn_add = QPushButton("添加应用", app_group)
        btn_del = QPushButton("移除选中", app_group)
        btn_add.clicked.connect(self._add_app)
        btn_del.clicked.connect(self._del_app)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch(1)
        v.addWidget(self.list_apps)
        v.addLayout(btn_row)
        inner.addWidget(app_group)

        # ---- 音乐歌词（网易云集成） ----
        music_group = QGroupBox("音乐歌词", self)
        mf = QFormLayout(music_group)
        self.chk_music = QCheckBox("启用音乐控制（网易云：播放/切歌）")
        self.chk_music.setChecked(bool(cfg.get("music_enabled", True)))
        self.chk_lyric_bar = QCheckBox("宠物下方显示歌词（点“词”键开关）")
        self.chk_lyric_bar.setChecked(bool(cfg.get("lyric_bar_enabled", True)))
        self.chk_lyric_trans = QCheckBox("歌词显示翻译（有翻译时）")
        self.chk_lyric_trans.setChecked(bool(cfg.get("lyric_translate", True)))
        self.chk_music_pet = QCheckBox("播放中宠物切换听歌形象 + 报歌名")
        self.chk_music_pet.setChecked(bool(cfg.get("music_pet_action", True)))
        self.chk_browser_media = QCheckBox(
            "识别浏览器里的音乐（默认关；开着时 B 站等视频也会弹歌词）")
        self.chk_browser_media.setChecked(
            bool(cfg.get("browser_session_enabled", False)))
        self.cmb_lyric_fallback = QComboBox()
        self.cmb_lyric_fallback.addItem("弹框手动搜索", "manual")
        self.cmb_lyric_fallback.addItem("仅显示歌名", "none")
        cur_fb = cfg.get("lyric_fallback", "manual")
        self.cmb_lyric_fallback.setCurrentIndex(
            1 if cur_fb == "none" else 0)
        mf.addRow(self.chk_music)
        mf.addRow(self.chk_lyric_bar)
        mf.addRow(self.chk_lyric_trans)
        mf.addRow(self.chk_music_pet)
        mf.addRow(self.chk_browser_media)
        mf.addRow("无歌词时", self.cmb_lyric_fallback)
        inner.addWidget(music_group)

        # ---- 按钮 ----
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    @staticmethod
    def _wrap(slider, label):
        row = QHBoxLayout()
        row.addWidget(slider)
        row.addWidget(label)
        slider.valueChanged.connect(lambda v: label.setText(f"{v} px"))
        return row

    @staticmethod
    def _fmt_mem(mem):
        items = [str(m).strip() for m in (mem or []) if str(m).strip()]
        return "\n".join(f"• {m}" for m in items) or "（还没有记住任何信息）"

    def _gallery_images(self):
        """扫描 assets 目录 + AI 动作素材目录下的图片，返回 (文件名, 绝对路径) 列表。"""
        imgs = []
        dirs = [ASSETS_DIR, norm_project_path(self._cfg.get("action_img_dir", ""))]
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            try:
                for f in sorted(os.listdir(d)):
                    if f.lower().endswith((".png", ".gif", ".jpg", ".jpeg", ".webp", ".bmp")):
                        if f.startswith("小道具"):   # 道具素材表不是形象，跳过
                            continue
                        imgs.append((f, os.path.join(d, f)))
            except OSError:
                pass
        return imgs

    @staticmethod
    def _norm_path(p):
        """归一化路径用于比较：绝对化 + 统一分隔符 + 忽略大小写。"""
        if not p:
            return ""
        return os.path.normpath(os.path.abspath(os.path.expanduser(p))).lower()

    def _find_skin_index(self):
        """定位当前配置对应的下拉索引：有图找图，无图用程序绘制。"""
        if self._pet_gif:
            np = self._norm_path(self._pet_gif)
            for i in range(self.skin_combo.count()):
                d = self.skin_combo.itemData(i)
                if d and d[0] == "gif" and self._norm_path(d[1]) == np:
                    return i
            return 0
        return 0  # 程序绘制

    def _load_skin_combo(self):
        """填充形象下拉：程序绘制 + assets 图片 + 浏览自定义。"""
        self.skin_combo.blockSignals(True)
        self.skin_combo.clear()
        self.skin_combo.addItem("哆啦A梦（程序绘制）", ("skin", "哆啦A梦"))
        gif_paths = []
        for name, path in self._gallery_images():
            self.skin_combo.addItem(name, ("gif", path))
            gif_paths.append(self._norm_path(path))
        cur = self._pet_gif
        if cur and self._norm_path(cur) not in gif_paths:
            self.skin_combo.addItem(os.path.basename(cur), ("gif", cur))
        self.skin_combo.addItem("浏览自定义图片…", ("browse", ""))
        self.skin_combo.setCurrentIndex(self._find_skin_index())
        self.skin_combo.blockSignals(False)

    def _on_skin_change(self, idx):
        data = self.skin_combo.itemData(idx)
        if not data:
            return
        kind = data[0]
        if kind == "browse":
            self._choose_custom_skin()
        elif kind == "gif":
            self._pet_gif = data[1]
        elif kind == "skin":
            self._pet_gif = ""

    def _choose_custom_skin(self):
        # 窗口级模态：不抢占其它应用窗口的顶层显示
        fd = QFileDialog(self, "选择宠物图片（GIF 动图 / PNG / JPG）", "C:\\",
                         "图片 (*.gif *.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        fd.setWindowModality(Qt.WindowModal)
        if fd.exec():
            files = fd.selectedFiles()
            if files:
                self._pet_gif = files[0]
                self._load_skin_combo()  # 重建下拉并选中新图

    def _clear_mem(self):
        self._cfg["ai_memory"] = []
        self.mem_label.setText("（还没有记住任何信息）")

    def _open_sandbox(self):
        os.makedirs(SANDBOX_ROOT, exist_ok=True)
        try:
            os.startfile(SANDBOX_ROOT)
        except OSError:
            pass

    # ---------- 聊天外观 ----------
    def _pick_chat_bg(self):
        fd = QFileDialog(self, "选择聊天背景图片", "",
                         "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        fd.setWindowModality(Qt.WindowModal)
        if fd.exec() and fd.selectedFiles():
            self._cfg["chat_bg_path"] = fd.selectedFiles()[0]
            self._cfg["chat_bg_enabled"] = True
            self.chk_chat_bg.setChecked(True)

    def _reset_chat_bg(self):
        self._cfg["chat_bg_path"] = ""
        self._cfg["chat_bg_enabled"] = True
        self.chk_chat_bg.setChecked(True)

    def _pick_user_avatar(self):
        fd = QFileDialog(self, "选择用户头像", "",
                         "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        fd.setWindowModality(Qt.WindowModal)
        if fd.exec() and fd.selectedFiles():
            self._cfg["chat_user_avatar"] = fd.selectedFiles()[0]

    def _reload_apps(self):
        self.list_apps.clear()
        for app in self._cfg.get("apps", []):
            name = app.get("name", "?")
            path = app.get("path", "")
            item = QListWidgetItem(f"{name}   →   {path or '(未检测到路径)'}")
            item.setData(Qt.UserRole, app)
            self.list_apps.addItem(item)

    def _add_app(self):
        # 手动创建并设为窗口级模态：只约束本应用，不抢占其它应用的顶层显示
        fd = QFileDialog(self, "选择应用", "C:\\", "程序 (*.exe *.lnk);;所有文件 (*)")
        fd.setWindowModality(Qt.WindowModal)
        if fd.exec() != QDialog.Accepted or not fd.selectedFiles():
            return
        path = fd.selectedFiles()[0]
        name = os.path.splitext(os.path.basename(path))[0]
        app = {"name": name, "icon": "📦", "path": path}
        self._cfg.setdefault("apps", []).append(app)
        self._reload_apps()

    def _del_app(self):
        row = self.list_apps.currentRow()
        if row >= 0 and 0 <= row < len(self._cfg.get("apps", [])):
            del self._cfg["apps"][row]
            self._reload_apps()

    # ---------- 事件提醒 ----------
    def _reload_events(self):
        self.list_events.clear()
        for ev in self._cfg.get("events", []):
            rep = REPEAT_LABELS.get(ev.get("repeat", "none"), "不重复")
            text = f"{ev.get('title','?')}  {ev.get('date','')} {ev.get('time','')} [{rep}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, ev)
            self.list_events.addItem(item)

    def _refresh_ach(self, cfg):
        """刷新成就展示：未解锁的成就也列出（🔒），让用户知道还有哪些可解锁。"""
        from core import achievements as ach_mod
        done = ach_mod.unlocked(cfg)
        lines = []
        for a in ach_mod.ACHIEVEMENTS:
            if a["key"] in done:
                lines.append(f"✅ {a['icon']} {a['name']}——{a['desc']}（{done[a['key']]}）")
            else:
                lines.append(f"🔒 {a['icon']} {a['name']}——{a['desc']}")
        self.ach_text.setText("\n".join(lines))

    def _add_event(self):
        dlg = EventDialog(self)
        if dlg.exec():
            self._cfg.setdefault("events", []).append(dlg.event_data())
            self._reload_events()

    def _del_event(self):
        row = self.list_events.currentRow()
        if row >= 0 and 0 <= row < len(self._cfg.get("events", [])):
            del self._cfg["events"][row]
            self._reload_events()

    def accept(self):
        cfg = self._cfg
        cfg["pet_name"] = self.edit_name.text().strip() or "小团子"
        cfg["pet_skin"] = "哆啦A梦"          # 内置形象固定为哆啦A梦
        cfg["pet_gif"] = self._pet_gif        # 选中的图片（空=用程序绘制）
        cfg["chat_enabled"] = self.chk_chat.isChecked()
        cfg["chat_bg_enabled"] = self.chk_chat_bg.isChecked()
        cfg["chat_avatar_enabled"] = self.chk_chat_avatar.isChecked()
        cfg["always_on_top"] = self.chk_top.isChecked()
        cfg["wander"] = self.chk_wander.isChecked()
        cfg["fullscreen_pause_enabled"] = self.chk_fs_pause.isChecked()
        cfg["fullscreen_pause_mode"] = self.cmb_fs_mode.currentData() or "hang"
        cfg["pet_size"] = self.size_slider.value()
        cfg["meal_remind"] = self.chk_meal.isChecked()
        cfg["late_remind"] = self.chk_late.isChecked()
        cfg["sit_remind"] = self.chk_sit.isChecked()
        cfg["water_remind"] = self.chk_water.isChecked()
        cfg["encourage_remind"] = self.chk_encourage.isChecked()
        cfg["egg_remind"] = self.chk_egg.isChecked()
        cfg["tips_remind"] = self.chk_tips.isChecked()
        cfg["festival_remind"] = self.chk_festival.isChecked()
        cfg["hourly_remind"] = self.chk_hourly.isChecked()
        cfg["reminder_enabled"] = self.chk_reminder.isChecked()
        cfg["reminder_sound_enabled"] = self.chk_sound.isChecked()
        cfg["sfx_enabled"] = self.chk_sfx.isChecked()
        cfg["sfx_volume"] = self.sfx_slider.value()
        cfg["time_care_enabled"] = self.chk_time_care.isChecked()
        cfg["time_care_cooldown_min"] = self.spin_care_cooldown.value()
        cfg["festival_idle_enabled"] = self.chk_festival_idle.isChecked()
        cfg["birthday"] = self.bday_input.text().strip()
        cfg["mood_enabled"] = self.chk_mood.isChecked()
        # 鼠标交互 & 防打扰
        cfg["interact_gaze"] = self.chk_gaze.isChecked()
        cfg["interact_hang"] = self.chk_hang.isChecked()
        cfg["work_sync_enabled"] = self.chk_work_sync.isChecked()
        cfg["reading_enabled"] = self.chk_reading.isChecked()
        cfg["reading_idle_sec"] = self.spin_reading.value()
        cfg["interact_yawn_sec"] = self.spin_yawn.value()
        cfg["interact_sleep_sec"] = self.spin_sleep.value()
        cfg["dnm_enabled"] = self.chk_dnm.isChecked()
        cfg["dnm_auto_min"] = self.spin_dnm_auto.value()
        # 番茄时钟
        cfg["pomodoro_enabled"] = self.chk_pomodoro.isChecked()
        cfg["pomodoro_work_min"] = self.spin_pm_work.value()
        cfg["pomodoro_break_min"] = self.spin_pm_break.value()
        # 事件提醒列表
        cfg["events"] = [self.list_events.item(i).data(Qt.UserRole)
                         for i in range(self.list_events.count())]
        # AI 对话
        cfg["ai_enabled"] = self.chk_ai.isChecked()
        cfg["ai_base_url"] = self.ai_base.text().strip() or "https://api.deepseek.com"
        cfg["ai_api_key"] = self.ai_key.text().strip()
        cfg["ai_model"] = self.ai_model.text().strip() or "deepseek-chat"
        cfg["ai_web_search"] = self.chk_ai_web.isChecked()
        cfg["ai_tools_enabled"] = self.chk_ai_tools.isChecked()
        cfg["clipboard_assistant_enabled"] = self.chk_clip.isChecked()
        cfg["clip_history_enabled"] = self.chk_clip_hist.isChecked()
        # 统计与成就
        cfg["summary_enabled"] = self.chk_summary.isChecked()
        cfg["stats_week_summary_enabled"] = self.chk_week.isChecked()
        # 音乐歌词（网易云集成）
        cfg["music_enabled"] = self.chk_music.isChecked()
        cfg["lyric_bar_enabled"] = self.chk_lyric_bar.isChecked()
        cfg["lyric_translate"] = self.chk_lyric_trans.isChecked()
        cfg["music_pet_action"] = self.chk_music_pet.isChecked()
        cfg["browser_session_enabled"] = self.chk_browser_media.isChecked()
        cfg["lyric_fallback"] = self.cmb_lyric_fallback.currentData() or "manual"
        # 应用列表
        cfg["apps"] = [self.list_apps.item(i).data(Qt.UserRole)
                       for i in range(self.list_apps.count())]
        # 开机自启
        if self.chk_autostart.isChecked() != is_autostart():
            set_autostart(self.chk_autostart.isChecked(), current_exe())
        cfg["autostart"] = self.chk_autostart.isChecked()
        super().accept()