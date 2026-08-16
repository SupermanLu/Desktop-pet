# -*- coding: utf-8 -*-
"""隐私沙盒：桌宠的自动化只允许在专属目录内读写文件，
执行白名单内只读的系统信息命令；任何路径越界都会被拒绝。

沙盒目录结构（项目目录/沙盒）：
- 收藏夹.txt       URL 收藏，一行一条
- 命令历史.txt     复制的命令记录
- 代码片段/        复制的代码（带时间戳）
- 笔记/            复制的长文本（带时间戳）
"""
import os
import subprocess
from datetime import datetime

from core.config import PROJECT_DIR

SANDBOX_ROOT = os.path.join(PROJECT_DIR, "沙盒")
BOOKMARKS = os.path.join(SANDBOX_ROOT, "收藏夹.txt")
CODE_DIR = os.path.join(SANDBOX_ROOT, "代码片段")
NOTES_DIR = os.path.join(SANDBOX_ROOT, "笔记")
CMDS_LOG = os.path.join(SANDBOX_ROOT, "命令历史.txt")

# 命令白名单：只允许这些只读、无副作用的系统信息命令（沙盒策略）
SAFE_COMMANDS = {
    "ipconfig": ["ipconfig"],
    "systeminfo": ["systeminfo"],
    "netstat": ["netstat", "-an"],
    "tasklist": ["tasklist"],
    "ver": ["ver"],
    "date": ["date", "/t"],
    "time": ["time", "/t"],
    "whoami": ["whoami"],
    "hostname": ["hostname"],
    "path": ["path"],
}


def _mkdir(*parts) -> str:
    p = os.path.join(*parts)
    os.makedirs(p, exist_ok=True)
    return p


def safe_path(rel: str) -> str:
    """把相对路径解析到沙盒内；越界直接抛 ValueError。"""
    root = os.path.abspath(SANDBOX_ROOT)
    p = os.path.abspath(os.path.join(root, (rel or "").lstrip("/\\")))
    if p != root and not p.startswith(root + os.sep):
        raise ValueError("路径越界，已按沙盒策略拒绝")
    return p


def sandbox_write(rel: str, content: str) -> str:
    p = safe_path(rel)
    _mkdir(os.path.dirname(p))
    with open(p, "w", encoding="utf-8") as f:
        f.write(content or "")
    return f"已写入沙盒：{os.path.relpath(p, SANDBOX_ROOT)}"


def sandbox_read(rel: str) -> str:
    p = safe_path(rel)
    if not os.path.isfile(p):
        return f"沙盒里没有这个文件：{rel}"
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()[:1500]


def sandbox_list() -> str:
    if not os.path.isdir(SANDBOX_ROOT):
        return "沙盒目录还是空的"
    lines = []
    for root, _dirs, files in os.walk(SANDBOX_ROOT):
        rel = os.path.relpath(root, SANDBOX_ROOT)
        for fn in sorted(files):
            relf = os.path.join(rel, fn) if rel != "." else fn
            lines.append(relf)
    return "沙盒文件：\n" + "\n".join(lines) if lines else "沙盒目录还是空的"


def append_bookmark(url: str) -> str:
    _mkdir(SANDBOX_ROOT)
    with open(BOOKMARKS, "a", encoding="utf-8") as f:
        f.write(url.strip() + "\n")
    return "已收藏到 沙盒/收藏夹.txt"


def _safe_filename(name: str, ext: str, default: str) -> str:
    """由用户输入的名字生成安全文件名：去掉路径分隔符与非法字符，
    缺后缀自动补；留空用 default（时间戳名）。ext 为后缀（不含点）。"""
    name = (name or "").strip()
    if not name:
        return f"{default}.{ext}"
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, "_")
    name = name.rstrip(". ") or "_"
    if not name.lower().endswith("." + ext.lower()):
        name += "." + ext
    return name


def save_code(content: str, ext: str = "txt", name: str = "") -> str:
    d = _mkdir(CODE_DIR)
    fn = _safe_filename(name, ext, datetime.now().strftime("片段_%Y%m%d_%H%M%S"))
    with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
        f.write(content or "")
    return f"已保存到 沙盒/代码片段/{fn}"


def save_note(content: str, name: str = "") -> str:
    d = _mkdir(NOTES_DIR)
    fn = _safe_filename(name, "txt", datetime.now().strftime("笔记_%Y%m%d_%H%M%S"))
    with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
        f.write(content or "")
    return f"已存档到 沙盒/笔记/{fn}"


def append_command(cmd: str) -> str:
    _mkdir(SANDBOX_ROOT)
    with open(CMDS_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {cmd}\n")
    return "已记入 沙盒/命令历史.txt"


def run_whitelisted(name: str) -> str:
    """执行白名单内的只读命令；非白名单一律拒绝。"""
    name = (name or "").strip().lower()
    if name not in SAFE_COMMANDS:
        return "该命令不在白名单内，已按沙盒策略拒绝执行"
    try:
        out = subprocess.run(SAFE_COMMANDS[name], capture_output=True,
                             encoding="mbcs", errors="replace",
                             timeout=15, shell=False)
        return (out.stdout or out.stderr or "(无输出)").strip()[:1500]
    except Exception as e:
        return f"执行出错：{e}"
