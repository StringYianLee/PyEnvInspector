"""「关于」面板: 软件版本、运行环境、版本更新内容。

作为非模态对话框从侧边栏打开, 也可在标题栏右键查看。
"""

from __future__ import annotations

import os
import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.appsettings import log_dir, log_file, user_data_dir
from ..core.changelog import CHANGELOG, full_text
from .theme import Palette
from .widgets import ElidedLabel


def _info_row(label: str, value: str) -> QWidget:
    """一行「标签 : 值」, 值可选中复制。"""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    cap = QLabel(label)
    cap.setFixedWidth(96)
    cap.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
    val = ElidedLabel(value)
    val.setToolTip(value)
    val.setStyleSheet(
        f"color: {Palette.text}; font-size: 12px;"
        " font-family: Consolas, 'Microsoft YaHei UI', monospace;")
    layout.addWidget(cap)
    layout.addWidget(val, 1)
    return widget


class AboutDialog(QDialog):
    """软件属性 / 版本信息对话框。"""

    def __init__(self, parent=None, update_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("关于 PyEnv Inspector")
        self.setMinimumSize(720, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(12)

        # ---- 标题区 ----
        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel("PyEnv")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(56, 56)
        lf = QFont()
        lf.setBold(True)
        lf.setPointSizeF(11)
        logo.setFont(lf)
        logo.setStyleSheet(
            f"color: {Palette.on_primary}; background: {Palette.primary};"
            " border-radius: 14px;")
        head.addWidget(logo)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        name = QLabel("PyEnv Inspector")
        nf = QFont()
        nf.setBold(True)
        nf.setPointSizeF(16)
        name.setFont(nf)
        name.setStyleSheet(f"color: {Palette.text};")
        self._version = QLabel(f"版本 v{__version__}")
        self._version.setStyleSheet(
            f"color: {Palette.primary}; font-size: 13px; font-weight: 700;")
        desc = QLabel("Python 环境与包依赖管理工具 · 解释器扫描 / 依赖分析 / "
                      "Conda / 环境管理")
        desc.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        title_box.addWidget(name)
        title_box.addWidget(self._version)
        title_box.addWidget(desc)
        head.addLayout(title_box, 1)
        root.addLayout(head)

        # ---- 更新提示 ----
        self._update_label = QLabel(update_text or "正在检查更新…")
        self._update_label.setWordWrap(True)
        self._update_label.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;"
            f" background: {Palette.surface_alt}; border-radius: 8px;"
            " padding: 8px 10px;")
        root.addWidget(self._update_label)

        # ---- Tab: 版本更新内容 / 运行环境 ----
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        changelog_page = QWidget()
        cl_layout = QVBoxLayout(changelog_page)
        cl_layout.setContentsMargins(0, 8, 0, 0)
        self._changelog = QPlainTextEdit()
        self._changelog.setReadOnly(True)
        self._changelog.setPlainText(full_text())
        self._changelog.setStyleSheet(
            f"QPlainTextEdit {{ background: {Palette.surface};"
            f" color: {Palette.text}; border: 1px solid {Palette.border};"
            " border-radius: 8px; font-family: Consolas, 'Microsoft YaHei UI',"
            " monospace; font-size: 12px; padding: 10px; }")
        cl_layout.addWidget(self._changelog)
        tabs.addTab(changelog_page, "版本更新内容")

        env_page = QWidget()
        env_layout = QVBoxLayout(env_page)
        env_layout.setContentsMargins(12, 12, 12, 12)
        env_layout.setSpacing(8)
        rows = [
            ("软件版本", f"v{__version__}"),
            ("Python", platform.python_version()),
            ("系统", f"{platform.system()} {platform.release()} "
                    f"({platform.machine()})"),
            ("运行方式", "打包程序 (exe)" if getattr(sys, "frozen", False)
             else "Python 源码"),
            ("可执行文件", sys.executable),
            ("数据目录", user_data_dir()),
            ("日志文件", log_file()),
            ("环境登记表", os.path.join(user_data_dir(), "managed.json")),
            ("版本记录", f"{len(CHANGELOG)} 个版本"),
        ]
        for label, value in rows:
            env_layout.addWidget(_info_row(label, value))
        env_layout.addStretch(1)
        open_log = QPushButton("打开日志目录")
        open_log.clicked.connect(self._open_log_dir)
        env_layout.addWidget(open_log, 0, Qt.AlignLeft)
        tabs.addTab(env_page, "运行环境")

        # ---- 底部按钮 ----
        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.setProperty("variant", "primary")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def set_update_text(self, text: str) -> None:
        self._update_label.setText(text)

    def _open_log_dir(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        path = log_dir()
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
