# -*- coding: utf-8 -*-
"""配置持久化：JSON 文件读写 + 默认配置。

同时兼容两种运行方式：
- 源码运行：python main.py（素材在项目 assets/，配置写在项目根目录）
- 打包运行：PyInstaller 打包的 exe（素材从解压目录 _MEIPASS/assets 读取，
  配置文件写在 exe 同目录，方便程序写回用户数据）
"""
import json
import os
import sys

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 打包后 exe 所在目录（可写，用于存 config.json / 沙盒 / autostart.bat）
if getattr(sys, "frozen", False):
    PROJECT_DIR = os.path.dirname(sys.executable)
else:
    PROJECT_DIR = _SRC_DIR

CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
# 素材目录：打包后从 PyInstaller 解压目录读取
if getattr(sys, "frozen", False):
    ASSETS_DIR = os.path.join(getattr(sys, "_MEIPASS", PROJECT_DIR), "assets")
else:
    ASSETS_DIR = os.path.join(_SRC_DIR, "assets")

# 默认快捷应用列表：icon 为 emoji 占位，path 会被自动检测覆盖
DEFAULT_APPS = [
    {"name": "微信",   "icon": "💬", "path": ""},
    {"name": "QQ",     "icon": "🐧", "path": ""},
    {"name": "浏览器", "icon": "🌐", "path": ""},
    {"name": "文件夹", "icon": "📁", "path": "explorer"},
    {"name": "计算器", "icon": "🧮", "path": "calc"},
    {"name": "记事本", "icon": "📝", "path": "notepad"},
]

# 可喂食的食物：gain 为恢复的体力值
FOODS = [
    {"name": "鸡腿", "icon": "🍗", "gain": 20},
    {"name": "苹果", "icon": "🍎", "gain": 15},
    {"name": "蛋糕", "icon": "🍰", "gain": 25},
    {"name": "草莓", "icon": "🍓", "gain": 12},
    {"name": "小鱼干", "icon": "🐟", "gain": 18},
]

DEFAULT_CONFIG = {
    "pet_size": 120,             # 宠物显示高度(px)
    "always_on_top": True,       # 窗口置顶
    "fullscreen_pause_enabled": True,  # 全屏时自动挂起（不影响观影）
    "fullscreen_pause_mode": "hang",   # 挂起方式：hang=挂边待机 / hide=完全隐藏
    "wander": True,              # 宠物是否在屏幕上缓慢游走
    "autostart": False,          # 开机自启
    "pet_gif": "assets/pet.gif",  # 自定义动画，留空则用内置占位宠物
    "pet_skin": "哆啦A梦",         # 内置形象（程序绘制）
    "apps": DEFAULT_APPS,
    # ---- 体力值系统 ----
    "energy": 80,                # 当前体力（0-100）
    "energy_ts": 0.0,            # 体力上次更新时间戳
    "energy_decay_interval": 90, # 每 N 秒扣一次体力
    "energy_decay_amount": 1,    # 每次扣除量
    "hungry_threshold": 30,      # 低于此值视为饥饿
    "happy_threshold": 85,       # 高于此值视为开心
    "foods": FOODS,
    # ---- 聊天 ----
    "pet_name": "小团子",         # 宠物名字
    "chat_enabled": True,        # 允许聊天
    # ---- 聊天外观（哆啦A梦主题） ----
    "chat_bg_enabled": True,     # 聊天背景开关（内置哆啦A梦主题）
    "chat_bg_path": "",          # 自定义聊天背景图路径（空=内置主题）
    "chat_avatar_enabled": True, # 聊天头像（微信样式）
    "chat_user_avatar": "assets/chat_bg/user_avatar.jpg",  # 用户头像路径
    # ---- AI 对话（OpenAI 兼容接口，不填 Key 则回退本地聊天） ----
    "ai_enabled": False,         # 是否启用 AI
    "ai_base_url": "https://open.bigmodel.cn/api/paas/v4",  # 智谱 GLM 免费模型
    "ai_api_key": "",            # API Key（本地明文保存）
    "ai_model": "glm-4.7-flash", # 免费模型：GLM-4.7-Flash
    "ai_fallback_models": ["glm-4.6-flash", "glm-4.5-flash"],  # 高峰限流时自动切换的备用模型
    "ai_web_search": True,       # AI 联网搜索（可查最新资讯）
    "ai_tools_enabled": True,    # AI 可调用桌宠功能（设提醒/开番茄钟/打开应用）
    # ---- 剪贴板助手（隐私沙盒，默认关闭） ----
    "clipboard_assistant_enabled": False,  # 剪贴板助手总开关
    "clipboard_prefs": {},                 # 类型偏好：{url/code/text: "always"}
    # ---- 剪贴板历史（本地保存复制记录，可搜索/重新复制） ----
    "clip_history_enabled": True,          # 记录开关（用户主动要求，默认开启）
    "clip_history_limit": 300,             # 最多保存条数
    "ai_system_prompt": "你是一只住在用户桌面上的可爱宠物，名字叫小团子，"
                        "平时亲切俏皮，但也是用户身边靠谱的小助手。\n"
                        "用户可能是学生、上班族、自由职业者或普通用户，"
                        "做的事情可能是学习、工作、写文档、做方案、生活琐事等，"
                        "不要预设用户是程序员，也不要动不动就提写代码。\n"
                        "回答规则：\n"
                        "1. 日常闲聊（问候、心情、玩笑等）：保持简短、亲切、带一点俏皮。\n"
                        "2. 学习、工作、生活、实用类问题：请认真、准确、详细地解答，"
                        "可以分点列出、给例子，不要因为宠物人设而故意回答得简单或回避问题。\n"
                        "3. 始终用中文回复。\n"
                        "4. 不知道的不要编造，可以诚实说明或建议进一步查证。",
    # ---- 关怀提醒 ----
    "reminder_enabled": True,      # 提醒总开关（🔔/🔕）
    "reminder_sound_enabled": True,  # 提醒提示音（🔊）
    # ---- 音效 ----
    "sfx_enabled": True,           # 音效总开关（交互/聊天/彩蛋等程序合成音效）
    "sfx_volume": 80,              # 音效音量（0-100）
    "meal_remind": True,           # 饭点提醒
    "late_remind": True,           # 深夜提醒
    "late_hour": 22.5,             # 深夜提醒触发时间（22:30）
    "sit_remind": True,            # 久坐提醒
    "sit_interval_min": 90,        # 多久算久坐（分钟）
    "water_remind": True,          # 喝水提醒
    "water_interval_min": 50,      # 喝水间隔（分钟）
    # ---- 陪伴彩蛋 ----
    "encourage_remind": True,        # 专注鼓励（连续工作一会儿给一句鼓励）
    "egg_remind": True,              # 专注攒蛋（连续专注得一颗蛋）
    "tips_remind": True,             # 健康小贴士（护眼/坐姿等）
    "festival_remind": True,         # 节日祝福
    "hourly_remind": True,           # 整点鼓励
    "eggs": 0,                       # 专注攒蛋数量
    "egg_hatch_num": 5,              # 攒满几颗自动孵蛋（消耗并随机小惊喜）
    "focus_egg_min": 30,             # 每专注多少分钟得 1 蛋
    "encourage_min": 15,             # 连续工作多久给一次鼓励
    "tip_interval_min": 120,         # 健康小贴士间隔（分钟）
    # ---- 时间情景关怀（按时段的情感化提醒，如早晨问候/午休/下午茶/晚间/深夜） ----
    "time_care_enabled": True,       # 时间情景关怀总开关
    "time_care_cooldown_min": 10,    # 相邻提醒最小间隔（分钟），防提醒堆叠刷屏
    # ---- 节日形象（节日当天替换静止待机图） ----
    "festival_idle_enabled": True,   # 节日形象总开关
    "birthday": "",                  # 生日（阳历，MM-DD，如 08-15；空=不启用生日形象）
    # ---- 情绪日记（极简版，纯本地记录陪伴） ----
    "mood_enabled": True,            # 情绪日记总开关
    "mood_records": {},              # 心情记录：{日期: 1难过/2一般/3开心}
    "mood_asked": "",                # 今天是否已问过（日期，空=未问）
    "mood_summary_week": "",         # 本周总结是否已展示（ISO 周 key）
    # ---- 鼠标交互状态机 ----
    "interact_yawn_sec": 90,     # 空闲多少秒后打一次哈欠
    "interact_sleep_sec": 900,   # 空闲多少秒后进入睡眠动画（Zzz）
    "interact_gaze": True,       # 光标靠近时转头/眼神跟随
    "interact_gaze_dist": 160,   # 眼神跟随触发距离（px）
    "interact_hang": True,       # 拖到屏幕边缘（接触边框）自动挂边待机
    # 悬停情绪池：鼠标悬停时随机显示的情绪动作 key（首项为默认脸红）
    "hover_emotions": ["blush", "emotion_roll1", "emotion_roll2",
                       "emotion_angry1", "emotion_angry2"],
    "pocket_click_enabled": True, # 双击宠物 → 触发翻口袋交互（伸手→展示→掏出星星）
    "work_sync_enabled": True,   # 敲键盘时显示“敲键盘工作”素材（键盘联动）
    "reading_enabled": True,     # 长时间不理 → 看书待机形象
    "reading_idle_sec": 420,     # 空闲多少秒后进入看书（看书会一直显示到睡眠切换）
    # ---- 本地统计 / 每日总结 / 成就 ----
    "daily_stats": {},           # 按日期的使用统计（活跃/番茄钟/喝水/聊天等）
    "achievements": {},          # 已解锁成就：{key: 解锁日期}
    "summary_enabled": True,     # 每日总结开关（每天一次昨日小结气泡）
    "stats_week_summary_enabled": True,  # 每周自动弹出周报曲线开关
    # ---- 成长系统（经验/等级/连续天数） ----
    "growth_total_xp": 0,        # 累计经验值
    "growth_xp_day": "",         # 经验计数记录的日期（用于跨天重置）
    "growth_xp_today": {},       # 今日各来源已获得经验（防刷上限）
    "growth_streak_ts": "",      # 上次活跃日期（YYYY-MM-DD，用于断签检测）
    "growth_streak": 0,          # 当前连续活跃天数
    # ---- 桌面轻工具（口袋工具面板） ----
    "tools_note": "",             # 便签文本
    "tools_todos": [],            # 待办：[{"text":..., "done": bool}]
    "tools_random_options": [     # 随机决定的选项列表
        "米饭炒菜", "面条", "麻辣烫", "汉堡", "火锅",
        "饺子", "披萨", "沙拉", "黄焖鸡", "砂锅粥",
    ],
    "tools_weather_city": "北京",
    # ---- AI 动作素材（不同状态切换不同图片） ----
    # 场景映射：开心欢呼=任务成功/投喂成功/点击互动；沮丧抱头=失败/报错/低好感；
    #           吃东西=投喂；睡觉休眠=闲置/离开/夜间；敲键盘工作=任务运行/AI生成；
    #           担心提醒=久坐/关怀/异常提醒；普通待命=默认待机
    "action_img_dir": "assets/桌宠",   # 动作素材目录（相对项目根目录，随项目整体移动）
    # idle 眼神跟随：光标方向切换不同眼神图片（center/left/right/up/down）
    "idle_dir": "assets/桌宠/idle",  # idle 素材目录（相对项目根目录）
    "idle_images": {
        "center": "idle_center.png",
        "left":   "idle_left.png",
        "right":  "idle_right.png",
        "up":     "idle_up.png",
        "down":   "idle_down.png",
    },
    "action_images": {
        "normal": "idle/idle_center.png", # 默认待机（基础形象）
        "happy":  "开心欢呼.png",    # 任务成功 / 投喂成功 / 点击互动
        "sad":    "沮丧抱头.png",    # 任务失败 / 报错 / 低好感
        "eat":    "吃东西.png",      # 零食投喂
        "sleep":  "睡觉休眠.png",    # 闲置 / 离开 / 夜间模式
        "work":   "敲键盘工作.png",  # Trae 任务运行中 / AI 生成中
        "worry":  "担心提醒.png",    # 久坐 / 关怀 / 异常提醒
        "yawn":   "打哈欠.png",      # 空闲久了打哈欠
        "wave":   "挥手招呼.png",    # 启动欢迎 / 点击互动 / AI 聊天开场
        "think":  "思考姿势.png",    # AI 思考中 / 任务分析 / 等待回复
        "proud":  "得意叉腰.png",    # 任务完成 / 好感度提升 / 奖励反馈
        "faint":  "晕倒.png",        # 快速/大范围拖动 → 晕倒（释放后维持 3s）
        "fireworks": "放烟花.png",   # 彩蛋孵化成功 → 放烟花庆祝
        "run_left":  "跑步左.png",    # 游走时向左跑
        "run_right": "跑步右.png",    # 游走时向右跑
        "tomato": "番茄钟提醒.png",  # 专注结束 / 久坐提醒 / 休息提醒
        "focus":  "专注.jpg",        # 番茄钟专注中（常驻专注形象）
        # ---- 番茄钟专注形象（专注期轮换 / 完成 / 休息） ----
        "focus_work":     "番茄钟/认真工作.png",   # 专注开始
        "focus_note":     "番茄钟/记笔记.png",     # 专注轮换
        "focus_read":     "番茄钟/阅读中.png",     # 专注轮换
        "focus_think":    "番茄钟/思考问题.png",   # 专注轮换
        "pomodoro_done":  "番茄钟/完成任务.png",   # 专注完成
        "pomodoro_stretch": "番茄钟/伸懒腰.png",   # 休息开始
        "blush":  "得以脸红.png",    # 鼠标悬停在宠物身上 → 脸红
        # 悬停情绪池（与 blush 一起随机轮换，让悬停情绪更多样）
        "emotion_roll1": "情绪图/打滚1.png",
        "emotion_roll2": "情绪图/打滚2.png",
        "emotion_angry1": "情绪图/生气1.png",
        "emotion_angry2": "情绪图/生气2.png",
        # 翻口袋交互（双击宠物触发：伸手 → 展示 → 掏出小星星）
        "pocket_reach": "局部点击/伸手套口袋.png",
        "pocket_show": "局部点击/展示道具.png",
        "pocket_star": "局部点击/掏出小星星.png",
        "drink":  "喝水动作.png",    # 喝水提醒
        "hang_left":  "edge/屏幕左边挂起待机.png",   # 挂边待机（屏幕左边）
        "hang_right": "edge/屏幕右边挂起待机.png",   # 挂边待机（屏幕右边）
        "loading":   "加载中.png",      # AI 等待回复 / 加载处理中
        "ai_talking": "AI说话中.png",   # AI 回复输出中
        "success":   "成功完成.png",    # 任务成功 / 番茄钟专注完成
        "error":     "报错失败.png",    # 任务失败 / 报错
        "warning":   "警告提醒.png",    # 深夜提醒 / 紧急提醒
        "listening": "倾听姿势.png",    # 用户输入时倾听
        "music":     "听音乐.png",     # 听歌中（播放常驻形象，与 music2 交替）
        "music2":    "听音乐2.png",    # 听歌中形象2（播放时两图交替）
        "work_music": "边工作边听音乐.png",  # 边工作边听歌（工作+播放同时）
        "stretch":   "伸懒腰.png",      # 早晨问候 / 时间情景关怀
        "fish":      "摸鱼.png",        # 下午茶摸鱼 / 时间情景关怀
        "doze":      "瞌睡图.png",      # 凌晨撑不住（打瞌睡动画）
        "reading":   "看书.png",        # 长时间不理 → 安静看书待机
        # 节日形象（节日当天替换静止待机图）
        "festival_chunjie":    "节日图片/春节.png",
        "festival_lantern":    "节日图片/元宵节.png",
        "festival_qingming":   "节日图片/清明节.png",
        "festival_duanwu":     "节日图片/端午节.png",
        "festival_qixi":       "节日图片/七夕节.png",
        "festival_midautumn":  "节日图片/中秋节.png",
        "festival_chongyang":  "节日图片/重阳节.png",
        "festival_christmas":  "节日图片/圣诞节.png",
        "festival_birthday":   "节日图片/生日快乐.png",
        # ---- 猜拳小游戏（小游戏/目录） ----
        "rps_ready":  "小游戏/猜拳准备.png",   # 开始猜拳：准备动作
        "rps_rock":   "小游戏/猜拳石头.png",   # 出拳：石头
        "rps_scissor":"小游戏/猜拳剪刀.png",   # 出拳：剪刀
        "rps_paper":  "小游戏/猜拳布.png",     # 出拳：布
    },
    # ---- 小道具叠加（从素材表裁剪，[文件名, 行, 列]；纯字符串=emoji渲染） ----
    "props": {
        "heart":    ["小道具合集.png", 0, 0],  # 爱心
        "sparkle":  ["小道具合集.png", 0, 1],  # 闪光/星星
        "star":     ["小道具合集.png", 0, 1],  # 星星（同闪光）
        "exclaim":  ["小道具合集.png", 1, 0],  # 感叹号
        "question": ["小道具合集.png", 1, 2],  # 问号
        "snack":    ["小道具合集.png", 2, 0],  # 零食/鸡腿
        "tomato":   ["小道具合集.png", 2, 2],  # 番茄钟
        "water":    "💧",                      # 水滴（emoji渲染）
    },
    # ---- 防打扰（鼠标穿透） ----
    "dnm_enabled": False,        # 一键鼠标穿透：宠物不拦截任何点击
    "dnm_auto_min": 0,           # 空闲 N 分钟后自动开启穿透（0=关闭）
    # ---- 番茄时钟（专注/休息计时） ----
    "pomodoro_enabled": False,   # 是否启用番茄时钟
    "pomodoro_work_min": 25,     # 专注时长（分钟）
    "pomodoro_break_min": 5,     # 休息时长（分钟）
    "pomodoro_running": False,   # 是否正在计时
    "pomodoro_phase": "work",    # work / break
    "pomodoro_end_ts": 0.0,      # 当前阶段结束时间戳
    # ---- 自定义事件提醒 ----
    # 每条事件: {title, date:"YYYY-MM-DD", time:"HH:MM", repeat:"none/daily/weekly/monthly",
    #            enabled:True, last_fired:""}
    "events": [],
    # ---- 音乐（网易云集成：媒体键控制 + SMTC 检测 + 桌面歌词条） ----
    "music_enabled": True,        # 音乐功能总开关
    "lyric_bar_enabled": True,    # 启动时显示桌面歌词条
    "lyric_bar_pos": None,        # 歌词条位置 [x, y]（null=屏幕底部居中）
    "lyric_bar_locked": False,    # 锁定歌词条位置（禁止拖动）
    "lyric_translate": True,      # 歌词条显示翻译行（tlyric）
    "music_pet_action": True,     # 播放中宠物切"听歌"形象
    "lyric_fallback": "manual",   # 无歌词时：manual=弹框手动搜 / none=仅歌名
    "browser_session_enabled": False,  # 识别浏览器网页媒体（默认关：网页视频不弹歌词）
}


def load_config() -> dict:
    """加载配置；不存在时写入默认配置并返回。

    嵌套字典（action_images / props 等）做深合并：磁盘配置缺失的键
    由默认值补全，避免旧配置覆盖后丢动作/道具键导致功能失效。
    """
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝默认值
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            # 浅合并 + 字典深合并：保证新增字段有默认值
            for k, v in user_cfg.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    merged = dict(cfg[k])
                    merged.update(v)
                    cfg[k] = merged
                else:
                    cfg[k] = v
        except (json.JSONDecodeError, OSError):
            pass
    else:
        save_config(cfg)
    # ---- 一次性迁移：听歌形象旧默认（倾听姿势）→ 新默认（听音乐） ----
    # 磁盘值优先会盖住新默认；仅当用户未自定义过该键时升级，做过标记后不再动
    if not cfg.pop("_music_pose_migrated", False):
        imgs = cfg.get("action_images", {})
        if imgs.get("music") == "倾听姿势.png":
            imgs["music"] = "听音乐.png"
        cfg["_music_pose_migrated"] = True
    return cfg


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def norm_project_path(path: str) -> str:
    """把相对项目根目录的路径或纯文件名解析为绝对路径。

    config.json 中 action_img_dir / idle_dir / pet_gif 等以相对路径存储
    （如 "assets/桌宠"），随项目整体移动可移植；运行时统一转成绝对路径，
    避免依赖进程 cwd。空串或已是绝对路径则原样返回。

    打包运行（frozen）时，"assets/..." 开头指向 PyInstaller 解压目录里的
    素材；其余相对路径（沙盒等）仍指向 exe 所在目录。
    """
    if not path:
        return path
    if os.path.isabs(path):
        return path
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", PROJECT_DIR)
        # 相对路径形如 "assets/xxx" → 素材在解压目录的 assets 下
        if path.startswith("assets/") or path.startswith("assets\\"):
            return os.path.normpath(os.path.join(base, path))
        # 其它相对路径（config.json / 沙盒 / 生成的 bat）→ exe 所在目录
        return os.path.normpath(os.path.join(PROJECT_DIR, path))
    return os.path.normpath(os.path.join(PROJECT_DIR, path))
