"""子进程启动参数: 确保不弹出控制台窗口。

GUI 程序(PyInstaller windowed)自身没有控制台, 但它启动的任何控制台
子进程(解释器探测 / py 启动器 / conda)在 Windows 上都会被分配一个新
控制台窗口 —— 表现为"打开软件后不停闪出 cmd 黑框"。

所有子进程调用都必须带上本模块的 ``hidden_kwargs()``。
"""

from __future__ import annotations

import os
import subprocess


def hidden_kwargs() -> dict:
    """返回隐藏控制台的 Popen/run 参数。

    Windows: CREATE_NO_WINDOW + STARTF_USESHOWWINDOW/SW_HIDE(双保险,
              后者对以 shell 方式启动的 .bat/launcher 也生效)
    POSIX  : 独立会话, 不与终端争抢输入(避免 Ctrl+C 波及/终端回显)
    """
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "startupinfo": startupinfo,
        }
    return {"start_new_session": True}
