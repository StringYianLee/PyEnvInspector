"""页面四:Conda 专属视图(环境列表 / conda 包 / 环境路径 / .condarc 配置)。

与现有输出格式保持一致:
- 环境列表使用与包列表页相同的表格样式(行选中 → 下方详情)
- 双击环境行(或「查看 pip 包」按钮)直接接入既有
  解释器 → 包采集 → 依赖分析流水线
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..core.conda_scanner import summarize_config
from ..core.models import CondaEnvironment, CondaInfo
from .theme import Palette
from .widgets import ElidedLabel, make_badge


class _InfoChip(QFrame):
    """conda 安装信息小卡片:标签 + 值。"""

    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)
        cap = QLabel(label)
        cap.setStyleSheet(f"color: {Palette.text_muted}; font-size: 11px;")
        self._value = ElidedLabel(value)
        self._value.setStyleSheet(
            f"color: {Palette.text}; font-size: 12px;"
            " font-family: Consolas, monospace; font-weight: 600;"
        )
        layout.addWidget(cap)
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        self._value.setText(value or "—")


class _ConfigCard(QFrame):
    """单个 .condarc 配置文件卡片。"""

    def __init__(self, path: str, exists: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = ElidedLabel(path)
        title.setStyleSheet(
            f"color: {Palette.text}; font-size: 12px;"
            " font-family: Consolas, monospace; font-weight: 700;"
        )
        head.addWidget(title, 1)
        head.addWidget(make_badge("已找到" if exists else "不存在",
                                  "ok" if exists else "muted"))
        self._layout.addLayout(head)

        if not exists:
            note = QLabel("该候选位置未发现配置文件")
            note.setStyleSheet(f"color: {Palette.text_faint}; font-size: 11px;")
            self._layout.addWidget(note)

    def load_content(self, cf) -> None:
        """填充配置摘要(cf: CondaConfigFile)。"""
        if not cf.exists:
            return
        if cf.error:
            err = QLabel(cf.error)
            err.setWordWrap(True)
            err.setStyleSheet(f"color: {Palette.error}; font-size: 11px;")
            self._layout.addWidget(err)
            return
        summary = summarize_config(cf)
        if not summary:
            note = QLabel("存在, 但未包含常用配置键")
            note.setStyleSheet(f"color: {Palette.text_faint}; font-size: 11px;")
            self._layout.addWidget(note)
            return
        for key, value in summary.items():
            row = QHBoxLayout()
            row.setSpacing(8)
            key_label = QLabel(key)
            key_label.setStyleSheet(
                f"color: {Palette.primary}; font-size: 11px; font-weight: 700;"
            )
            key_label.setFixedWidth(140)
            if isinstance(value, list):
                val_text = "  ".join(str(x) for x in value) if value else "(空)"
            elif value is None:
                val_text = "(未设置)"
            else:
                val_text = str(value)
            val_label = QLabel(val_text)
            val_label.setWordWrap(True)
            val_label.setStyleSheet(
                f"color: {Palette.text_muted}; font-size: 11px;"
                " font-family: Consolas, monospace;"
            )
            row.addWidget(key_label)
            row.addWidget(val_label, 1)
            holder = QWidget()
            holder.setLayout(row)
            self._layout.addWidget(holder)


class CondaPage(QWidget):
    """Conda 页面。"""

    environment_activated = Signal(str)   # 双击环境 → 激活(参数=环境根路径)
    rescan_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._conda_info: CondaInfo | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        # 标题行
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Conda 管理")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSizeF(15)
        title.setFont(tf)
        title.setStyleSheet(f"color: {Palette.text};")
        self._subtitle = QLabel("扫描 conda 环境、原生包、环境路径与配置文件")
        self._subtitle.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        title_col.addWidget(title)
        title_col.addWidget(self._subtitle)
        header.addLayout(title_col)
        header.addStretch(1)
        self.rescan_button = QPushButton("重新扫描 Conda")
        self.rescan_button.setProperty("variant", "primary")
        header.addWidget(self.rescan_button)
        root.addLayout(header)

        # conda 安装信息卡
        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        self._chip_version = _InfoChip("Conda 版本")
        self._chip_exec = _InfoChip("可执行文件")
        self._chip_base = _InfoChip("Base 环境路径")
        self._chip_stats = _InfoChip("环境 / 原生包总数")
        for chip in (self._chip_version, self._chip_exec,
                     self._chip_base, self._chip_stats):
            info_row.addWidget(chip, 1)
        root.addLayout(info_row)

        # 主体: 上环境表, 下 Tab(conda 包 / 配置文件)
        splitter = QSplitter(Qt.Vertical)

        env_panel = QWidget()
        env_layout = QVBoxLayout(env_panel)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_layout.setSpacing(6)
        env_hint = QLabel("环境列表(双击任意环境, 直接进入该环境的 pip 包分析流水线)")
        env_hint.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        env_layout.addWidget(env_hint)

        self.env_table = QTableWidget(0, 4)
        self.env_table.setHorizontalHeaderLabels(
            ["环境名", "环境路径", "Python 版本", "Conda 包数"])
        self.env_table.verticalHeader().setVisible(False)
        self.env_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.env_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.env_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.env_table.setAlternatingRowColors(True)
        self.env_table.setShowGrid(False)
        self.env_table.verticalHeader().setDefaultSectionSize(32)
        header = self.env_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        env_layout.addWidget(self.env_table, 1)
        splitter.addWidget(env_panel)

        self.tabs = QTabWidget()
        # Tab: conda 原生包
        pkg_page = QWidget()
        pkg_layout = QVBoxLayout(pkg_page)
        pkg_layout.setContentsMargins(0, 8, 0, 0)
        self._pkg_title = QLabel("选中环境的 conda 原生包(不含 pip 包)")
        self._pkg_title.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        pkg_layout.addWidget(self._pkg_title)
        self.pkg_table = QTableWidget(0, 4)
        self.pkg_table.setHorizontalHeaderLabels(
            ["包名", "版本", "频道", "构建串"])
        self.pkg_table.verticalHeader().setVisible(False)
        self.pkg_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pkg_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.pkg_table.setAlternatingRowColors(True)
        self.pkg_table.setShowGrid(False)
        pkg_header = self.pkg_table.horizontalHeader()
        pkg_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        pkg_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        pkg_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        pkg_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        pkg_layout.addWidget(self.pkg_table, 1)
        self.tabs.addTab(pkg_page, "Conda 包")

        # Tab: 配置文件
        config_page = QWidget()
        config_layout = QVBoxLayout(config_page)
        config_layout.setContentsMargins(0, 8, 0, 0)
        config_hint = QLabel(
            ".condarc 候选位置(按优先级排列; channels / envs_dirs 等常用键会被解析)")
        config_hint.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        config_layout.addWidget(config_hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self._config_host = QWidget()
        self._config_layout = QVBoxLayout(self._config_host)
        self._config_layout.setSpacing(10)
        self._config_layout.addStretch(1)
        scroll.setWidget(self._config_host)
        config_layout.addWidget(scroll, 1)
        self.tabs.addTab(config_page, "配置文件")

        splitter.addWidget(self.tabs)
        splitter.setSizes([420, 380])
        root.addWidget(splitter, 1)

        # 信号
        self.env_table.doubleClicked.connect(self._on_env_double_clicked)
        # currentCellChanged 覆盖键盘上下键切换场景(clicked 只响应鼠标)
        self.env_table.currentCellChanged.connect(
            lambda *_args: self._render_env_detail(self._current_env()))
        self.rescan_button.clicked.connect(
            lambda _checked=False: self.rescan_requested.emit())

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def load_conda(self, info: CondaInfo) -> None:
        self._conda_info = info
        self._chip_version.set_value(info.version or "未检测到")
        self._chip_exec.set_value(info.executable or "—")
        base = next((e for e in info.envs if e.is_base), None)
        self._chip_base.set_value(base.path if base else
                                  (info.roots[0] if info.roots else "—"))
        self._chip_stats.set_value(
            f"{len(info.envs)} 个环境 · {info.total_conda_packages} 个包")

        if not info.roots and not info.envs:
            self._subtitle.setText(
                "未检测到 conda 安装(已检查用户目录 / ProgramData / PATH)")
        else:
            found_configs = sum(1 for c in info.config_files if c.exists)
            self._subtitle.setText(
                f"发现 {len(info.envs)} 个 conda 环境 · "
                f"{info.total_conda_packages} 个原生包 · "
                f"{found_configs} 个配置文件")
        if info.errors:
            self._subtitle.setToolTip(" · ".join(info.errors))
        else:
            self._subtitle.setToolTip("")

        # 环境表
        self.env_table.clearContents()
        self.env_table.setRowCount(len(info.envs))
        for row, env in enumerate(info.envs):
            name_item = QTableWidgetItem(
                ("★ " if env.is_base else "") + env.name)
            if env.is_base:
                name_item.setForeground(QColor(Palette.primary))
                f = QFont()
                f.setBold(True)
                name_item.setFont(f)
            name_item.setData(Qt.UserRole, env.path)
            self.env_table.setItem(row, 0, name_item)
            self.env_table.setItem(row, 1, QTableWidgetItem(env.path))
            self.env_table.setItem(
                row, 2, QTableWidgetItem(env.python_version or "—"))
            count_item = QTableWidgetItem(str(env.package_count))
            count_item.setTextAlignment(Qt.AlignCenter)
            if not env.readable:
                count_item.setForeground(QColor(Palette.warn))
                count_item.setToolTip("conda-meta 读取异常")
            self.env_table.setItem(row, 3, count_item)

        # 配置卡
        while self._config_layout.count() > 1:
            item = self._config_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for cf in info.config_files:
            card = _ConfigCard(cf.path, cf.exists)
            card.load_content(cf)
            self._config_layout.insertWidget(
                self._config_layout.count() - 1, card)

        if info.envs:
            self.env_table.selectRow(0)
            self._render_env_detail(info.envs[0])
        else:
            self._render_env_detail(None)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _current_env(self) -> CondaEnvironment | None:
        row = self.env_table.currentRow()
        if (self._conda_info is None or row < 0
                or row >= len(self._conda_info.envs)):
            return None
        return self._conda_info.envs[row]

    def _on_env_double_clicked(self, index) -> None:
        env = self._current_env()
        if env is not None:
            self.environment_activated.emit(env.path)

    def _render_env_detail(self, env: CondaEnvironment | None) -> None:
        self.pkg_table.setRowCount(0)
        if env is None:
            self._pkg_title.setText("选中环境的 conda 原生包(不含 pip 包)")
            return
        self._pkg_title.setText(
            f"{env.name} · {env.path} · {env.package_count} 个 conda 原生包"
            + (f" · Python {env.python_version}" if env.python_version else ""))
        self.pkg_table.setRowCount(len(env.packages))
        for row, pkg in enumerate(env.packages):
            self.pkg_table.setItem(row, 0, QTableWidgetItem(pkg.name))
            self.pkg_table.setItem(row, 1, QTableWidgetItem(pkg.version))
            ch = QTableWidgetItem(pkg.channel or "—")
            ch.setForeground(QColor(Palette.text_muted))
            self.pkg_table.setItem(row, 2, ch)
            build = QTableWidgetItem(pkg.build_string or "—")
            build.setForeground(QColor(Palette.text_faint))
            self.pkg_table.setItem(row, 3, build)
