# -*- coding: utf-8 -*-
"""开机自启看护脚本（.pyw = 用 pythonw 运行，全程无窗口）。

解决开机自启静默失败的问题：
- 崩溃原因写入 autostart_err.log（pythonw 无控制台，否则报错完全无声）
- 启动后观察 20 秒，若桌宠退出（开机早期环境未就绪导致的崩溃）则自动重试，
  最多 3 次，每次间隔 10 秒
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(BASE, "main.py")
LOG = os.path.join(BASE, "autostart_err.log")

for attempt in range(1, 4):
    try:
        with open(LOG, "a", encoding="utf-8") as err:
            err.write(f"\n===== autostart attempt {attempt} {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            proc = subprocess.Popen(
                [sys.executable, MAIN],
                cwd=BASE,
                stderr=err,
            )
        # 观察前 20 秒：进程若还活着说明启动成功，看护退出
        time.sleep(20)
        if proc.poll() is None:
            break
        # 进程已退出（崩溃），稍等后重试
        time.sleep(10)
    except Exception:
        # 看护脚本自身异常也不能打扰用户
        break
