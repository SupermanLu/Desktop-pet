# -*- coding: utf-8 -*-
"""关怀提醒系统：定时检测用户活跃度与时间，触发各类提醒。

- 饭点：早/中/晚/夜宵，每天每餐只提醒一次
- 深夜：很晚还在用电脑 → 提醒休息
- 久坐：连续活跃超过阈值 → 提醒起身活动
- 喝水：每隔一段时间且处于活跃状态 → 提醒补水
- 专注鼓励：连续工作一段时间 → 给一句鼓励
- 专注攒蛋：连续专注一段时间 → 奖励一颗蛋（累计可攒彩蛋）
- 健康小贴士：每隔一段时间 → 护眼/坐姿等小贴士
- 节日祝福：元旦/情人节/圣诞等当天问候一次
- 整点鼓励：每小时开头给一句打气

活跃度通过 Windows GetLastInputInfo 检测键盘/鼠标空闲时间判断。
所有提醒的文案集中在下方 *_LINES，方便统一修改。
"""
import random
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal, QTimer

from core.lunar import solar_to_lunar
from core import stats
from core.config import save_config

# ---- 提醒文案（可按喜好修改/扩充） ----
MEAL_LINES = {
    "breakfast": [  # 07:00 ~ 09:00
        "早安！记得吃早餐哦～早餐是元气充电站 ☀️",
        "别空着肚子开始一天，先去吃个热乎的早餐吧 🥛",
    ],
    "lunch": [      # 11:30 ~ 13:30
        "到饭点啦！别饿着肚子写代码，先去吃口热乎的 🍚",
        "该吃午饭啦～认真吃饭才有力气调 bug 😋",
    ],
    "dinner": [     # 17:30 ~ 19:30
        "晚上好～该吃晚饭啦，好好吃饭再继续 🍜",
        "饭点到！先吃饭，代码又不会跑掉～ 😄",
    ],
    "supper": [     # 21:00 ~ 23:00 夜宵（仅提示，不强求）
        "要是饿了可以来点夜宵，不过别太晚吃哦 🌙",
    ],
}
MEAL_WINDOWS = [
    ("breakfast", 7, 0, 9, 0),
    ("lunch", 11, 30, 13, 30),
    ("dinner", 17, 30, 19, 30),
    ("supper", 21, 0, 23, 0),
]
LATE_LINES = [
    "已经夜深啦，代码明天还能写，身体要紧，早点休息吧 🌙",
    "这个点还在写代码，你太拼啦～记得给自己留点休息时间 💤",
    "深夜写码伤身体，先去睡吧，剩下的事明天效率更高 😴",
    "夜深了该休息了，明天再战更有精神 🌙",
]
SIT_LINES = [
    "你连续敲代码好久了，起来伸个懒腰、看看远处放松眼睛吧 🌿",
    "劳逸结合效率才高，起来活动 5 分钟再战？🦵",
    "久坐对腰和眼睛都不好哦，站起来走动一下吧 🚶",
    "累了就别硬撑，先放松一会儿吧 🛋️",
]
WATER_LINES = [
    "咕噜咕噜～该喝水啦，记得补水哦 💧",
    "喝口水休息一下眼睛吧～你刚才可一直没停呢 🥤",
    "到喝水时间啦！水是写代码的快乐源泉 💧",
]
ENCOURAGE_LINES = [
    "你已经专注好一会儿了，状态很棒，继续保持！💪",
    "认真的你真的很厉害，给自己点个赞 👍",
    "思路在线，代码稳了～休息两分钟再战更高效 😎",
    "专注的你最有魅力，别忘了偶尔眨眨眼哦 😉",
]
EGG_LINES = [
    "专注满 {egg_min} 分钟啦！送你好运蛋 🥚 现在共有 {eggs} 颗，攒多了能孵出彩蛋哦～",
    "恭喜又完成一个专注段！给你加一颗蛋 🥚 累计 {eggs} 颗，集齐可以召唤小惊喜～",
]
# 彩蛋孵化时的随机小惊喜台词（type="word" 用）
HATCH_LINES = [
    "彩蛋破壳啦！送你一份好心情，今天也要加油鸭 🎉",
    "啵～彩蛋孵出来了！是来自哆啦A梦的神秘小惊喜 🤩",
    "蛋壳裂开啦，里面是一张笑脸和一整个好运，送给你 ✨",
    "恭喜孵出彩蛋！随机掉落一份「幸运加成」，已塞进你的口袋 🎁",
    "彩蛋：其实我是来找你玩的！陪你聊聊天、加加油 🥰",
]
# 彩蛋孵化奖励池：随机三选一（food=加体力 / word=彩蛋台词 / extra_egg=返蛋）
HATCH_REWARDS = ["food", "word", "extra_egg"]
TIPS_LINES = [
    "护眼小贴士：每 20 分钟抬头看看 6 米外的远处 20 秒，眼睛会感谢你 👀",
    "坐姿提醒：脚放平、腰背挺直，屏幕和眼睛大致平齐，写代码更舒服 🪑",
    "屏幕亮度调成和环境差不多的亮度，晚上别太刺眼哦 🌙",
    "记得常眨眼！盯着屏幕久了眼睛容易干涩 😉",
    "手腕用久了转一转、揉一揉，防止鼠标手 🖐️",
    "长时间打字后活动一下手指，做个抓握放松，预防键盘手 🙌",
]
HOURLY_LINES = [
    "整点啦！这小时也辛苦啦，喝口水歇口气 ☕",
    "一小时过去啦～给自己一点掌声，继续加油 👏",
    "滴答～整点了！小团子提醒你：劳逸结合才能走得更远 🌟",
    "新的一小时开始啦，列个小目标，轻轻松松搞定它 ✅",
]
# ---- 时间情景关怀（按时段的情感化提醒；每段每天一次） ----
TIME_CARE_LINES = {
    "morning": [    # 07:00~09:00 早晨问候（首次活跃时）
        "早呀～今天准备干点啥？新的一天，元气满满出发吧 ☀️",
        "早上好呀！要不要先列个小目标，今天一定很棒 🌅",
    ],
    "morning_work": [  # 10:00~11:00 连续工作 30 分钟以上 → 起身活动
        "起来活动一下？我帮你计时 5 分钟，回来再战效率更高 ⏱️",
        "连续工作好一会儿啦，起来伸个懒腰、喝口水再继续吧 🧘",
    ],
    "noon": [       # 12:00~13:00 午休（时间关怀开启时接管午餐提醒）
        "该吃饭啦，要不要我帮你决定吃什么？🍚",
        "到饭点啦～想好吃什么了吗？要不要我给点建议 😋",
    ],
    "afternoon": [  # 15:00~16:00 下午茶摸鱼（连续工作 30 分钟以上）
        "下午茶时间！来摸个鱼、放松一下再继续 ☕",
        "偷得浮生半日闲～下午茶来一口，心情好效率高 🍰",
    ],
    "evening": [    # 20:00~22:00 晚间关怀
        "晚上了，别太累哦，今天的进度已经很棒了 🌆",
        "天黑啦，慢慢来，别把自己绷太紧 💙",
    ],
    "night": [      # 23:00~24:00 深夜陪伴（语气变软，不强制）
        "很晚了，我陪你再干最后一小时就休息好不好？🌙",
        "这个点了还在坚持，我懂～再陪你一会儿，然后就早点睡吧 🛏️",
    ],
    "midnight": [   # 01:00~07:00 凌晨撑不住（打瞌睡动画）
        "你真的该睡了…（打哈欠）我快撑不住了…😴",
        "都这个点了…（揉眼睛）去睡吧，明早我还在 💤",
    ],
}
# 时间段定义：(key, 开始小时, 开始分钟, 结束小时, 结束分钟)
TIME_CARE_WINDOWS = [
    ("morning",      7, 0,  9, 0),
    ("morning_work", 10, 0, 11, 0),
    ("noon",         12, 0, 13, 0),
    ("afternoon",    15, 0, 16, 0),
    ("evening",      20, 0, 22, 0),
    ("night",        23, 0, 24, 0),
    ("midnight",     1, 0,  7, 0),
]
# 情景对应的动作素材与道具；morning_work/afternoon 需要连续工作满该秒数
TIME_CARE_ACTIONS = {
    "morning":      ("stretch", "sparkle", 0),
    "morning_work": ("yawn",    "exclaim", 30 * 60),
    "noon":         ("eat",     "snack",   0),
    "afternoon":    ("fish",    "heart",   30 * 60),
    "evening":      ("wave",    "heart",   0),
    "night":        ("yawn",    "",        0),
    "midnight":     ("doze",    "exclaim", 0),   # 凌晨撑不住 → 瞌睡图
}
# ---- 节日形象（节日当天替换静止待机图；农历节由农历日期决定） ----
FESTIVAL_LUNAR = [
    (1, 1,  "festival_chunjie"),    # 春节 正月初一
    (1, 15, "festival_lantern"),    # 元宵 正月十五
    (5, 5,  "festival_duanwu"),     # 端午 五月初五
    (7, 7,  "festival_qixi"),       # 七夕 七月初七
    (8, 15, "festival_midautumn"),  # 中秋 八月十五
    (9, 9,  "festival_chongyang"),  # 重阳 九月初九
]
FESTIVALS = {
    "01-01": ["元旦快乐！新的一年，小团子陪你一起加油 🎉"],
    "02-14": ["情人节快乐～今天也要甜甜蜜蜜的 💕"],
    "03-08": ["妇女节快乐！辛苦啦，记得照顾好自己 🌸"],
    "05-01": ["劳动节快乐！忙里偷闲，好好放松一下吧 🎈"],
    "06-01": ["儿童节快乐！愿你永远保持好奇心和童心 🍭"],
    "10-01": ["国庆节快乐！祖国生日快乐，你也好好休息 🇨🇳"],
    "12-25": ["圣诞快乐！愿你被这个世界温柔以待 🎄"],
}


class ReminderManager(QObject):
    remind = Signal(str)  # 发射提醒文本
    action = Signal(str)  # 提醒对应的动作素材 key（worry/happy 等）
    prop = Signal(str)    # 提醒对应的道具 key（如 snack/water，空则不带）
    festival_idle = Signal(str)  # 节日形象 key（空串=恢复默认待机图）
    egg_hatched = Signal(dict)   # 彩蛋攒满自动孵化：发射奖励字典 {"type":...}
    pomodoro_done = Signal()     # 一个专注段完成
    # 番茄钟阶段切换：'work' 进入专注 / 'break' 进入休息（main 据此切换专注形象）
    pomodoro_phase_changed = Signal(str)

    def _remind(self, kind: str, text: str, prop_key: str = "",
                force: bool = False, care: bool = False) -> bool:
        """先发动作素材（切宠物图片）与道具，再发提醒文本。

        冷却分两条独立通道，互不干扰：
        - care=True（时间情景关怀：问候/午休/下午茶/晚间/深夜）走关怀冷却；
        - care=False（功能提醒：喝水/久坐/小贴士/鼓励/饭点等）走功能冷却。
        这样喝水等提醒不会被时间关怀的冷却窗口反复挡住。
        force=True 的关键提醒（如番茄钟结束）不受任何限制。
        返回 True 表示本次真正弹出了，调用方据此再更新"已提醒"状态，被跳过的
        提醒会在下个检查周期自动重试。
        """
        if not force:
            now = time.time()
            if care:
                if now - self._last_care_ts < self._care_cooldown:
                    return False
                self._last_care_ts = now
            else:
                if now - self._last_func_ts < self._func_cooldown:
                    return False
                self._last_func_ts = now
        self.action.emit(kind)
        if prop_key:
            self.prop.emit(prop_key)
        self.remind.emit(text)
        return True

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._meal_done = {}      # 餐名 -> 日期字符串
        self._last_late_date = "" # 深夜提醒：每天一次
        # 喝水/小贴士：从"当前启动时刻"开始计时，避免开机刚打开就立刻弹提示
        self._last_water = time.time()
        self._active_accum = 0    # 连续活跃累计秒数（久坐）
        self._focus_accum = 0     # 连续活跃累计秒数（专注/鼓励）
        self._focus_encouraged = False   # 本次专注段是否已鼓励过
        self._last_festival_date = ""    # 节日祝福：每天一次
        self._last_tip_time = time.time()
        self._last_hour_key = ""         # 整点报时：记录上次报时的时刻
        # 时间情景关怀
        self._care_done = {}      # 情景 key -> 日期字符串（每天一次）
        self._care_work_accum = 0 # 情景关怀用：连续活跃累计秒数（早晨/下午茶）
        # 节日形象
        self._last_festival_idle = None  # 上次发出的节日形象 key（None=未评估过）
        # 提醒冷却：分关怀/功能两条通道，互不干扰（见 _remind）
        self._care_cooldown = int(cfg.get("time_care_cooldown_min", 10) or 10) * 60
        self._func_cooldown = 300   # 功能提醒冷却 5 分钟，防同类型刷屏
        self._last_care_ts = 0.0    # 上次时间关怀弹出时间（0 → 启动后第一条立即生效）
        self._last_func_ts = 0.0    # 上次功能提醒弹出时间
        self._paused = False        # 全屏挂起期间暂停所有提醒
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30_000)  # 每 30 秒检查一次

    def set_paused(self, paused: bool):
        """全屏挂起时暂停所有提醒（节日形象与番茄钟除外），退出全屏自动恢复。"""
        self._paused = bool(paused)

    # ---------- 活跃度检测（Windows 键盘/鼠标最后输入时间） ----------
    @staticmethod
    def _idle_seconds() -> float:
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

    def _active(self) -> bool:
        """3 分钟内没有键盘/鼠标输入视为离开。"""
        return self._idle_seconds() < 180

    # ---------- 节日形象（节日当天替换静止待机图） ----------
    def _festival_idle_key(self, now) -> str:
        """返回今天的节日形象 key；无则返回空串。"""
        if not self._cfg.get("festival_idle_enabled", True):
            return ""
        y, m, d = now.year, now.month, now.day
        # 农历节（春节/元宵/端午/七夕/中秋/重阳）
        lunar = solar_to_lunar(y, m, d)
        if lunar:
            _ly, lm, ld, _leap = lunar
            for fm, fd, key in FESTIVAL_LUNAR:
                if lm == fm and ld == fd:
                    return key
        # 阳历节
        if m == 12 and d == 25:
            return "festival_christmas"
        # 清明（节气，约 4 月 4-6 日，用近似公式）
        if m == 4:
            qd = int((y % 100) * 0.2422 + 4.81) - int((y % 100) / 4)
            if d == qd:
                return "festival_qingming"
        # 生日（阳历 MM-DD，可在设置里填）
        bday = (self._cfg.get("birthday") or "").strip()
        if bday:
            try:
                bm, bd = (int(x) for x in bday.split("-"))
                if bm == m and bd == d:
                    return "festival_birthday"
            except (ValueError, TypeError):
                pass
        return ""

    def refresh_festival_idle(self):
        """评估今天的节日形象，变化时发出信号（key 或空串表示恢复默认）。"""
        key = self._festival_idle_key(datetime.now())
        if key != self._last_festival_idle:
            self._last_festival_idle = key
            self.festival_idle.emit(key)

    # ---------- 主检查 ----------
    def _tick(self):
        self.refresh_festival_idle()   # 节日形象：与活跃度无关，始终评估
        self._check_pomodoro()   # 番茄钟独立墙钟计时，不依赖提醒开关/活跃度
        if self._paused:
            return   # 全屏挂起中：跳过一切提醒，退出全屏后自动恢复
        if not self._cfg.get("reminder_enabled", True):
            self._active_accum = 0
            self._focus_accum = 0
            self._focus_encouraged = False
            self._care_work_accum = 0
            return
        active = self._active()
        if not active:
            # 人不在电脑前 → 专注/久坐/情景计时清零，重新开始
            self._active_accum = 0
            self._focus_accum = 0
            self._focus_encouraged = False
            self._care_work_accum = 0
            return
        self._focus_accum += 30
        self._care_work_accum += 30
        self._check_time_care()   # 时间情景关怀（先于功能提醒，保证问候第一时间弹出）
        self._check_meal()
        self._check_late_night()
        self._check_sitting()
        self._check_water()
        self._check_encourage()
        self._check_focus_egg()
        self._check_tips()
        self._check_festival()
        self._check_hourly()

    # ---------- 番茄时钟（专注/休息轮换） ----------
    def _check_pomodoro(self):
        if not self._cfg.get("pomodoro_enabled", False) \
                or not self._cfg.get("pomodoro_running", False):
            return
        end = float(self._cfg.get("pomodoro_end_ts", 0) or 0)
        if end <= 0 or time.time() < end:
            return
        phase = self._cfg.get("pomodoro_phase", "work")
        work_min = int(self._cfg.get("pomodoro_work_min", 25))
        break_min = int(self._cfg.get("pomodoro_break_min", 5))
        if phase == "work":
            # 专注结束 → 成功完成素材 + 闪光，进入休息
            self._cfg["pomodoro_phase"] = "break"
            self._cfg["pomodoro_end_ts"] = time.time() + break_min * 60
            stats.add(self._cfg, "pomodoro_done")
            self.pomodoro_done.emit()
            self.pomodoro_phase_changed.emit("break")
            self._remind("success",
                         f"🍅 专注 {work_min} 分钟结束！休息 {break_min} 分钟，"
                         f"起身活动一下吧～",
                         "sparkle", force=True)
        else:
            # 休息结束 → 挥手 + 爱心，开始新一轮专注
            self._cfg["pomodoro_phase"] = "work"
            self._cfg["pomodoro_end_ts"] = time.time() + work_min * 60
            self.pomodoro_phase_changed.emit("work")
            self._remind("wave",
                         f"休息结束～开始新一轮 {work_min} 分钟专注吧，加油 💪",
                         "heart", force=True)
        try:
            save_config(self._cfg)
        except Exception:
            pass

    # ---------- 饭点 ----------
    def _check_meal(self):
        if not self._cfg.get("meal_remind", True):
            return
        care = self._cfg.get("time_care_enabled", True)
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        for name, sh, sm, eh, em in MEAL_WINDOWS:
            # 时间关怀开启时，午餐由"午休"情景接管，避免重复提示吃饭
            if care and name == "lunch":
                continue
            if self._meal_done.get(name) == today:
                continue
            start, end = sh * 60 + sm, eh * 60 + em
            cur = now.hour * 60 + now.minute
            if start <= cur < end:
                if self._remind("eat", random.choice(MEAL_LINES[name]), "snack"):
                    self._meal_done[name] = today

    # ---------- 深夜提醒 ----------
    def _check_late_night(self):
        if not self._cfg.get("late_remind", True):
            return
        now = datetime.now()
        if now.hour < self._cfg.get("late_hour", 22.5):
            return
        today = now.strftime("%Y-%m-%d")
        if self._last_late_date != today:
            if self._remind("yawn", random.choice(LATE_LINES)):
                self._last_late_date = today

    # ---------- 时间情景关怀（按时段的情感化提醒，每天一次） ----------
    def _check_time_care(self):
        if not self._cfg.get("time_care_enabled", True):
            return
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        cur = now.hour * 60 + now.minute
        for key, sh, sm, eh, em in TIME_CARE_WINDOWS:
            if self._care_done.get(key) == today:
                continue
            start, end = sh * 60 + sm, eh * 60 + em
            if not (start <= cur < end):
                continue
            action, prop, need_work = TIME_CARE_ACTIONS[key]
            # 需要"连续工作"的情景：没累计够就等下次，不标记已提醒
            if need_work and self._care_work_accum < need_work:
                continue
            # 距上一条关怀提醒太近就跳过，下个周期自动重试（走关怀冷却通道）
            if self._remind(action, random.choice(TIME_CARE_LINES[key]), prop,
                            care=True):
                self._care_done[key] = today

    # ---------- 久坐提醒 ----------
    def _check_sitting(self):
        if not self._cfg.get("sit_remind", True):
            return
        interval = int(self._cfg.get("sit_interval_min", 90)) * 60
        self._active_accum += 30
        if self._active_accum >= interval:
            if self._remind("yawn", random.choice(SIT_LINES), "exclaim"):
                self._active_accum = 0   # 被冷却跳过则不清零，下个周期重试

    # ---------- 喝水提醒 ----------
    def _check_water(self):
        if not self._cfg.get("water_remind", True):
            return
        interval = int(self._cfg.get("water_interval_min", 50)) * 60
        now = time.time()
        if now - self._last_water >= interval:
            if self._remind("drink", random.choice(WATER_LINES), "water"):
                self._last_water = now   # 被冷却跳过则不更新，下个周期重试
                stats.add(self._cfg, "water_count")

    # ---------- 专注鼓励（每段只鼓励一次） ----------
    def _check_encourage(self):
        if not self._cfg.get("encourage_remind", True):
            return
        minutes = int(self._cfg.get("encourage_min", 15))
        if self._focus_accum >= minutes * 60 and not self._focus_encouraged:
            if self._remind("wave", random.choice(ENCOURAGE_LINES), "heart"):
                self._focus_encouraged = True

    # ---------- 专注攒蛋 / 彩蛋孵化 ----------
    def _check_focus_egg(self):
        if not self._cfg.get("egg_remind", True):
            return
        minutes = int(self._cfg.get("focus_egg_min", 30))
        if self._focus_accum >= minutes * 60:
            if self._remind("proud",
                            random.choice(EGG_LINES).format(
                                egg_min=minutes,
                                eggs=int(self._cfg.get("eggs", 0)) + 1),
                            "sparkle"):
                # 真正弹出后才加蛋并重开专注段，避免被冷却跳过时白攒/白扣
                self._cfg["eggs"] = int(self._cfg.get("eggs", 0)) + 1
                self._focus_accum = 0
                self._focus_encouraged = False
                self._maybe_hatch_egg()
                try:
                    save_config(self._cfg)
                except Exception:
                    pass

    def _maybe_hatch_egg(self):
        """攒满 egg_hatch_num 颗 → 消耗并随机孵化一个彩蛋小惊喜。"""
        hatch_num = max(1, int(self._cfg.get("egg_hatch_num", 5)))
        if int(self._cfg.get("eggs", 0)) < hatch_num:
            return
        self._cfg["eggs"] = int(self._cfg.get("eggs", 0)) - hatch_num
        kind = random.choice(HATCH_REWARDS)
        reward = {"type": kind, "hatch_num": hatch_num}
        if kind == "food":
            food = random.choice(self._cfg.get("foods")
                                 or [{"name": "美食", "icon": "🍗", "gain": 20}])
            reward["icon"] = food.get("icon", "🍗")
            reward["name"] = food.get("name", "美食")
            reward["gain"] = int(food.get("gain", 20))
        elif kind == "extra_egg":
            reward["gain"] = 1
        else:
            reward["text"] = random.choice(HATCH_LINES)
        self.egg_hatched.emit(reward)

    def add_egg(self, n: int = 1):
        """额外加蛋（如猜拳获胜）：加蛋后自动判断是否触发孵化。"""
        self._cfg["eggs"] = int(self._cfg.get("eggs", 0)) + n
        self._maybe_hatch_egg()
        try:
            save_config(self._cfg)
        except Exception:
            pass

    # ---------- 健康小贴士 ----------
    def _check_tips(self):
        if not self._cfg.get("tips_remind", True):
            return
        interval = int(self._cfg.get("tip_interval_min", 120)) * 60
        now = time.time()
        if now - self._last_tip_time >= interval:
            if self._remind("think", random.choice(TIPS_LINES), "question"):
                self._last_tip_time = now
                stats.add(self._cfg, "tip_count")

    # ---------- 节日祝福（每天一次） ----------
    def _check_festival(self):
        if not self._cfg.get("festival_remind", True):
            return
        today = datetime.now().strftime("%m-%d")
        if today in FESTIVALS and self._last_festival_date != today:
            if self._remind("happy", random.choice(FESTIVALS[today]), "heart"):
                self._last_festival_date = today

    # ---------- 整点鼓励（每小时一次） ----------
    def _check_hourly(self):
        if not self._cfg.get("hourly_remind", True):
            return
        now = datetime.now()
        key = now.strftime("%Y-%m-%d %H")
        if now.minute < 5 and self._last_hour_key != key:
            if self._remind("wave", random.choice(HOURLY_LINES), "star"):
                self._last_hour_key = key
