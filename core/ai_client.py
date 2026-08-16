# -*- coding: utf-8 -*-
"""AI 对话客户端：OpenAI 兼容 /chat/completions 接口。

支持 DeepSeek / 通义千问 / Kimi / 智谱 等 OpenAI 兼容服务。
API 调用在后台线程执行，通过 Qt 信号把结果安全送回主线程，避免卡住聊天界面。
自动重试 429/5xx 错误，失败时返回友好提示，不中断聊天。
"""
import json
import random
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from PySide6.QtCore import QObject, Signal


class AIClient(QObject):
    finished = Signal(str)          # 回复文本（成功或失败提示）
    memory_new = Signal(list)       # 本轮新记住的信息（交给主线程持久化）
    tool_request = Signal(dict)     # 请求主线程执行工具 {"id","name","args"}

    # 429/5xx 限流保护：指数退避 + 随机抖动，重试耗尽后自动切换备用模型
    _MAX_RETRIES = 3          # 每个模型最多额外重试次数
    _RETRY_BASE_DELAY = 3.0   # 退避基数（秒），每次翻倍
    _RETRY_MAX_DELAY = 15.0   # 单次退避上限（秒）
    _MAX_TOOL_ROUNDS = 3  # 单次对话最多连续调用几轮工具，防止失控

    # 轻量安全版 Function Calling：只允许 AI 控制桌宠已有功能
    # （设提醒 / 开番茄钟 / 打开应用），不做文件修改、鼠标键盘等高危操作。
    _FUNCTION_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "set_reminder",
                "description": "设置一个定时提醒：几分钟后在宠物头顶弹气泡并播放提示音，"
                               "适合用户要求'X 分钟后提醒我'。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "提醒内容，如 该喝水啦"},
                        "minutes": {"type": "integer",
                                    "description": "多少分钟后提醒（1~120）"},
                    },
                    "required": ["text", "minutes"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_app",
                "description": "打开用户电脑上的常见应用（微信/QQ/浏览器等）或桌宠已配置的快捷应用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "应用名称，如 微信、QQ、浏览器"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "start_pomodoro",
                "description": "启动番茄钟专注计时（默认 25 分钟专注 + 5 分钟休息）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "work_min": {"type": "integer", "description": "专注分钟数（默认25）"},
                        "break_min": {"type": "integer", "description": "休息分钟数（默认5）"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sandbox_write",
                "description": "在桌宠的隐私沙盒目录内写入/新建文件（相对路径，越界会被拒绝）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rel_path": {"type": "string", "description": "沙盒内相对路径，如 笔记/a.txt"},
                        "content": {"type": "string", "description": "文件内容"},
                    },
                    "required": ["rel_path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sandbox_read",
                "description": "读取桌宠隐私沙盒目录内的文件内容（相对路径）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rel_path": {"type": "string", "description": "沙盒内相对路径"},
                    },
                    "required": ["rel_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sandbox_list",
                "description": "列出桌宠隐私沙盒目录里的所有文件。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "运行桌宠沙盒白名单内的只读系统信息命令（ipconfig/systeminfo/tasklist/whoami/hostname 等），其他命令会被拒绝。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "白名单命令名，如 ipconfig"},
                    },
                    "required": ["command"],
                },
            },
        },
    ]

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        # 已记住的长期信息（跨会话），只在本线程内读写
        self._memory = [str(m).strip() for m in cfg.get("ai_memory", [])
                        if str(m).strip()]
        # 工具调用：worker 线程等待主线程执行结果（id -> [Event, holder]）
        self._tool_events = {}
        self._tool_seq = 0
        import threading as _th
        self._tool_lock = _th.Lock()

    def is_ready(self) -> bool:
        c = self._cfg
        return bool(c.get("ai_enabled") and c.get("ai_api_key"))

    def _endpoint(self) -> str:
        """拼出 chat/completions 地址，兼容 /v1（OpenAI/DeepSeek）与 /v4（智谱）。"""
        base = (self._cfg.get("ai_base_url")
                or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        if base.endswith("/v1") or base.endswith("/v4"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"

    def ask_async(self, history: list):
        """在后台线程请求 AI，完成后通过 finished 信号发射回复。"""
        def worker():
            try:
                reply = self._ask_sync(history)
            except Exception as e:
                reply = self._friendly_error(e)
            self.finished.emit(reply)
        threading.Thread(target=worker, daemon=True).start()

    def _friendly_error(self, e: Exception) -> str:
        msg = str(e)
        if "429" in msg:
            return ("（免费 AI 高峰时段限流，自动换了好几个模型还是挤不进去，"
                    "稍等 1-2 分钟再问就好 😅）")
        if "401" in msg or "Unauthorized" in msg or "认证" in msg:
            return "（AI 连不上啦，API Key 可能不对，去设置里检查一下吧 🔑）"
        if "Timeout" in msg or "timed out" in msg:
            return "（AI 响应超时，网络不太稳定，稍后再试试～）"
        return f"（AI 暂时没连上，稍后再试试吧～）"

    def _ask_sync(self, history: list) -> str:
        system = self._cfg.get("ai_system_prompt") \
            or "你是一只可爱的桌面宠物，回答简短亲切，用中文。"
        # 注入当前时间，让 AI 能准确回答"现在几点/几号/星期几"这类问题
        now = datetime.now()
        time_text = now.strftime("%Y-%m-%d %H:%M（%A）")
        system += (f"\n\n<time>当前真实时间（北京时间）：{time_text}。</time>"
                   "用户问时间、日期、星期几时，直接按这个时间回答，不要推算。")
        # 注入已记住的长期信息，让 AI 跨会话记得用户（最多取最近 20 条）
        if self._memory:
            facts = "\n".join(f"- {m}" for m in self._memory[-20:])
            system += (f"\n\n<memory_facts>你已经记住的用户信息：\n{facts}\n"
                       "</memory_facts>")
        # 提示 AI 提炼值得记住的新信息
        system += ("\n\n如果用户刚说出了值得长期记住的信息（姓名、职业、喜好、"
                   "重要日子、习惯等），在回复末尾单独一行输出"
                   " <memory>信息1|信息2</memory>；没有就不输出，正文不要提到这个标记。")
        messages = [{"role": "system", "content": system}]
        messages += list(history)[-10:]

        # 最多 _MAX_TOOL_ROUNDS 轮：AI 可连续调用工具后再给出最终答复
        for _ in range(self._MAX_TOOL_ROUNDS):
            payload = {
                "model": self._cfg.get("ai_model") or "glm-4.7-flash",
                "messages": messages,
                "stream": False,
            }
            tools = []
            # 智谱等模型内置联网搜索：遇到时效性问题自动联网检索
            if self._cfg.get("ai_web_search", False):
                tools.append({"type": "web_search", "web_search": {"enable": True}})
            # 轻量安全版函数调用：控制桌宠已有功能
            if self._cfg.get("ai_tools_enabled", True):
                tools.extend(self._FUNCTION_TOOLS)
            if tools:
                payload["tools"] = tools

            data = self._request(payload)
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return self._save_memories(msg.get("content") or "")
            # 有工具调用：把 assistant 消息 + 工具结果追加进对话，继续下一轮
            messages.append({"role": "assistant",
                             "content": msg.get("content") or "",
                             "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}
                result = self._execute_tool(name, args if isinstance(args, dict) else {})
                messages.append({"role": "tool",
                                 "tool_call_id": tc.get("id", ""),
                                 "content": result})
        return self._save_memories("（工具调用太多，我先停一下，你换个说法再试试～）")

    def _request(self, payload: dict) -> dict:
        """发一次请求：429/5xx 指数退避重试；主模型持续 429 时自动切换备用模型。"""
        primary = payload.get("model") or "glm-4.7-flash"
        models = [primary] + [m for m in (self._cfg.get("ai_fallback_models") or [])
                              if m and m != primary]
        last = None
        for idx, model in enumerate(models):
            payload["model"] = model
            for attempt in range(self._MAX_RETRIES + 1):
                try:
                    return self._do_post(payload)
                except urllib.error.HTTPError as e:
                    last = e
                    retriable = e.code in (429, 500, 502, 503)
                    if retriable and attempt < self._MAX_RETRIES:
                        time.sleep(self._backoff(attempt))
                        continue
                    # 重试耗尽或不可重试：主模型非限流错误（如 401）直接上报，
                    # 其余情况换下一个备用模型试试
                    if idx == 0 and not retriable:
                        raise
                    break
        raise last

    def _backoff(self, attempt: int) -> float:
        """指数退避 + 随机抖动，避免同时重试加剧限流。"""
        delay = min(self._RETRY_MAX_DELAY, self._RETRY_BASE_DELAY * (2 ** attempt))
        return delay * random.uniform(0.8, 1.2)

    def _do_post(self, payload: dict) -> dict:
        """实际发一次 POST 并解析 JSON。"""
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._cfg.get('ai_api_key', '')}",
        }
        req = urllib.request.Request(self._endpoint(), data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _execute_tool(self, name: str, args: dict) -> str:
        """把工具调用交给主线程执行并阻塞等待结果（默认 20s 超时）。"""
        self._tool_seq += 1
        tid = f"t{self._tool_seq}"
        event = threading.Event()
        holder = {}
        with self._tool_lock:
            self._tool_events[tid] = (event, holder)
        self.tool_request.emit({"id": tid, "name": name, "args": args})
        event.wait(timeout=20)
        with self._tool_lock:
            self._tool_events.pop(tid, None)
        return holder.get("result", "（执行超时，请稍后再试）")

    def tool_result(self, tid: str, result: str):
        """主线程执行完工具后调用，唤醒等待中的 worker。"""
        with self._tool_lock:
            item = self._tool_events.get(tid)
        if item:
            item[1]["result"] = result
            item[0].set()

    def _save_memories(self, content: str) -> str:
        """解析 <memory>…</memory> 标记，去重存入长期记忆，返回去掉标记的正文。"""
        m = re.search(r"<memory>(.*?)</memory>", content, flags=re.S)
        if not m:
            return content
        new = [f.strip() for f in m.group(1).split("|") if f.strip()]
        if new:
            kept = [f for f in new if f not in self._memory]
            if kept:
                self._memory.extend(kept)
                self.memory_new.emit(kept)  # 主线程收到后写回 config.json
        return content.replace(m.group(0), "").strip()
