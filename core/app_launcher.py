# -*- coding: utf-8 -*-
"""应用扫描与启动：自动探测常用软件路径，并拉起外部进程。"""
import os
import subprocess

# 常用软件的候选安装路径（顺序优先）
KNOWN_APPS = {
    "微信": [
        r"C:\Program Files\Tencent\WeChat\WeChat.exe",
        r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
        os.path.expandvars(r"%USERPROFILE%\AppData\Roaming\Tencent\WeChat\WeChat.exe"),
        os.path.expandvars(r"%USERPROFILE%\Desktop\WeChat.lnk"),
    ],
    "QQ": [
        r"C:\Program Files\Tencent\QQ\Bin\QQ.exe",
        r"C:\Program Files (x86)\Tencent\QQ\Bin\QQ.exe",
        r"C:\Program Files\Tencent\QQNT\QQ.exe",
        r"C:\Program Files (x86)\Tencent\QQNT\QQ.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Tencent\QQ\QQ.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tencent\QQ\QQ.exe"),
    ],
    "浏览器": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
    ],
}


def detect_path(app: dict) -> str:
    """优先使用用户配置的 path；否则在候选路径中探测。"""
    path = (app.get("path") or "").strip()
    if path and (os.path.isfile(path) or os.path.exists(path)):
        return path
    for cand in KNOWN_APPS.get(app.get("name", ""), []):
        if os.path.exists(cand):
            return cand
    return ""


def launch(app: dict) -> tuple[bool, str]:
    """启动应用，返回 (是否成功, 错误信息)。"""
    path = detect_path(app)
    if not path:
        return False, f"未找到 {app.get('name', '')} 的安装路径，请在设置中手动指定"

    try:
        if path.lower().endswith(".exe") and os.path.isfile(path):
            subprocess.Popen([path])          # exe：直接拉起进程，不闪黑窗
        else:
            os.startfile(path)                # .lnk / explorer / calc 等 shell 命令
        return True, ""
    except OSError as e:
        return False, f"启动失败: {e}"
