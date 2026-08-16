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


def _ensure_bat_stub() -> str:
    """生成/返回项目根目录下的 autostart.bat 路径。

    .bat 内容显式调用 pythonw.exe 执行 main.py，绕过 .py 文件关联
    （避免系统把 .py 关联到 PyCharm 等编辑器导致 LightEdit 弹窗）。
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bat_path = os.path.join(project_dir, "autostart.bat")
    if not os.path.isfile(bat_path):
        exe = sys.executable
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(pythonw):
            exe = pythonw
        main_py = os.path.join(project_dir, "main.py")
        # 先切到项目目录再执行，确保相对路径（assets 等）正确
        content = (
            f'@echo off\r\n'
            f'cd /d "{project_dir}"\r\n'
            f'"{exe}" "{main_py}"\r\n'
        )
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(content)
    return bat_path


def current_exe() -> str:
    """返回注册表 Run 键应写入的完整启动命令（含引号）。

    - 打包（frozen）：直接指向 exe
    - 脚本运行：通过 autostart.bat 启动（绕过 .py 文件关联问题）
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{_ensure_bat_stub()}"'
