# -*- coding: utf-8 -*-
"""开机自启：通过 HKCU 注册表 Run 键实现。"""
import os
import sys
import winreg

APP_NAME = "TraeDeskPet"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(enabled: bool, cmd: str) -> bool:
    """enabled=True 写入注册表；False 删除。返回是否成功。

    cmd 为完整的启动命令（含引号，由 current_exe() 生成）。
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def is_autostart() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def _ensure_launcher() -> str:
    """生成/返回项目根目录下的 autostart_run.pyw 看护脚本路径。

    .pyw 由 pythonw 运行（无控制台窗口），脚本内部带崩溃重试与错误日志
    （见 autostart_run.pyw），解决开机早期环境未就绪导致的静默启动失败。
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pyw = os.path.join(project_dir, "autostart_run.pyw")
    if os.path.isfile(pyw):
        return pyw
    # 看护脚本缺失时兜底退回直接启动 main.py
    return os.path.join(project_dir, "main.py")


def current_exe() -> str:
    """返回注册表 Run 键应写入的完整启动命令（含引号）。

    - 打包（frozen）：直接指向 exe
    - 脚本运行：用 pythonw 运行 autostart_run.pyw 看护脚本
      （无窗口、自动重试、崩溃写 autostart_err.log）
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(pythonw):
        exe = pythonw
    return f'"{exe}" "{_ensure_launcher()}"'
