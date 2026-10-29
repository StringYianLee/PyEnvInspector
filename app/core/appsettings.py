"""日志与用户设置。

日志: 写入用户级目录, 便于用户反馈问题时提供 (RotatingFileHandler, 1MB×3)。
设置: QSettings(Windows 注册表 HKCU\\Software\\PyEnvInspector),
      保存窗口几何、主题、上次环境、布局模式、镜像、对比选择等。
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

_SETTINGS_ORG = "PyEnvInspector"
_SETTINGS_APP = "PyEnvInspector"


# ---------------------------------------------------------------------------
# 目录
# ---------------------------------------------------------------------------

def user_data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    name = "PyEnvInspector" if os.name == "nt" else "pyenv-inspector"
    return os.path.join(base, name)


def log_dir() -> str:
    return os.path.join(user_data_dir(), "logs")


def log_file() -> str:
    return os.path.join(log_dir(), "app.log")


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def setup_logging(level: int = logging.INFO) -> str:
    """初始化根日志(文件 + 非打包时的控制台)。返回日志文件路径。"""
    os.makedirs(log_dir(), exist_ok=True)
    root = logging.getLogger()
    if getattr(root, "_pyenv_configured", False):
        return log_file()

    root.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.handlers.RotatingFileHandler(
        log_file(), maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if not getattr(sys, "frozen", False):   # PyInstaller 窗口版无控制台
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

    root._pyenv_configured = True  # type: ignore[attr-defined]
    logging.getLogger(__name__).info("日志已初始化: %s", log_file())
    return log_file()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# 设置(惰性导入 Qt, 便于 CLI 环境不依赖 GUI)
# ---------------------------------------------------------------------------

class Settings:
    """QSettings 薄封装: 提供带默认值的读写。"""

    def __init__(self):
        from PySide6.QtCore import QSettings
        self._s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

    def get(self, key: str, default=None):
        value = self._s.value(key, default)
        return value if value is not None else default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._s.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes")

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self._s.value(key, default))
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value) -> None:
        self._s.setValue(key, value)

    def sync(self) -> None:
        self._s.sync()

    # -- 常用键 ---------------------------------------------------------
    KEY_DARK_THEME = "ui/dark_theme"
    KEY_GEOMETRY = "ui/geometry"
    KEY_PAGE = "ui/last_page"
    KEY_LAYOUT_MODE = "analysis/layout_mode"
    KEY_PIP_INDEX = "manage/pip_index"
    KEY_LAST_PYTHON = "env/last_python"
    KEY_COMPARE_A = "compare/a"
    KEY_COMPARE_B = "compare/b"
    KEY_CHECK_UPDATES = "app/check_updates"


def theme_is_dark() -> bool:
    """读取主题偏好(启动前调用, 供 main.py 决定调色板)。"""
    try:
        return Settings().get_bool(Settings.KEY_DARK_THEME, False)
    except Exception:
        return False
