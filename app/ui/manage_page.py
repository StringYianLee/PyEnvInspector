"""页面五:环境管理(Python 解释器安装/删除、conda 环境创建/删除、包装卸)。

安全策略:
- 删除操作全部二次确认(列出完整路径与不可恢复警告)
- 删除前检测进程占用(列出 PID), 被占用/为 base/正被本应用浏览 → 阻止
- 外部(非托管)解释器不提供删除入口
所有操作在后台线程执行, 输出实时写入底部日志面板, 结果以弹窗+日志反馈。
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..core import env_manager as em
from ..core.models import CondaInfo, InterpreterInfo
from .theme import Palette
from .widgets import ElidedLabel, make_badge


class ManagePage(QWidget):
    """环境管理页。"""

    python_changed = Signal()       # 解释器变化 → 主窗口重扫解释器
    conda_changed = Signal()        # conda 环境变化 → 主窗口重扫 conda
    packages_changed = Signal(str)  # 参数=目标 python 路径 → 主窗口按需刷新

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._interpreters: list[InterpreterInfo] = []
        self._conda_info: CondaInfo | None = None
        self._worker = None
        self._current_env_dir = ""   # 本应用正在浏览的环境(删除保护)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(10)

        # 标题
        title = QLabel("环境管理")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSizeF(15)
        title.setFont(tf)
        title.setStyleSheet(f"color: {Palette.text};")
        self._subtitle = QLabel("安装/删除 Python 解释器 · 创建/删除 Conda 环境 · pip 与 Conda 包装卸")
        self._subtitle.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        root.addWidget(title)
        root.addWidget(self._subtitle)

        # Tab 区
        self.tabs = QTabWidget()
        self._build_interpreter_tab()
        self._build_conda_tab()
        self._build_packages_tab()
        root.addWidget(self.tabs, 1)

        # 底部操作日志
        log_frame = QFrame()
        log_frame.setObjectName("card")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 8, 10, 8)
        log_layout.setSpacing(4)
        log_head = QHBoxLayout()
        log_title = QLabel("操作日志")
        log_title.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px; font-weight: 700;")
        log_head.addWidget(log_title)
        log_head.addStretch(1)
        clear_btn = QPushButton("清空日志")
        clear_btn.setFixedHeight(24)
        clear_btn.clicked.connect(lambda: self._log.clear())
        log_head.addWidget(clear_btn)
        log_layout.addLayout(log_head)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(170)
        self._log.setStyleSheet(
            "QPlainTextEdit { background: #f8f9fc; border: none;"
            " font-family: Consolas, monospace; font-size: 11px; }")
        log_layout.addWidget(self._log)
        root.addWidget(log_frame)

        self.busy = _BusyLabel()
        root.addWidget(self.busy)

    # ------------------------------------------------------------------
    # Tab 构建
    # ------------------------------------------------------------------
    def _build_interpreter_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        hint = QLabel("仅显示由本工具安装的解释器(位于 ~/PyEnvInspector/runtimes); "
                      "外部解释器不受本页管理。安装过程自动下载并校验 sha256。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("选择版本:"))
        self.py_version_combo = QComboBox()
        for v in sorted(em.PYTHON_DISTRIBUTIONS,
                        key=lambda s: [int(x) for x in s.split(".")],
                        reverse=True):
            self.py_version_combo.addItem(f"Python {v}", v)
        self.py_version_combo.setFixedWidth(140)
        row.addWidget(self.py_version_combo)
        self.py_install_btn = QPushButton("安装 Python")
        self.py_install_btn.setProperty("variant", "primary")
        self.py_install_btn.clicked.connect(self._install_python)
        row.addWidget(self.py_install_btn)
        row.addSpacing(20)
        self.py_remove_btn = QPushButton("删除所选")
        self.py_remove_btn.clicked.connect(self._remove_python)
        self.py_remove_btn.setEnabled(False)
        row.addWidget(self.py_remove_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.py_table = QTableWidget(0, 3)
        self.py_table.setHorizontalHeaderLabels(["版本", "安装目录", "安装时间"])
        self.py_table.verticalHeader().setVisible(False)
        self.py_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.py_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.py_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.py_table.setAlternatingRowColors(True)
        self.py_table.setShowGrid(False)
        self.py_table.verticalHeader().setDefaultSectionSize(32)
        h = self.py_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.py_table.itemSelectionChanged.connect(
            lambda: self.py_remove_btn.setEnabled(
                bool(self.py_table.selectedItems())))
        layout.addWidget(self.py_table, 1)
        self.tabs.addTab(page, "Python 解释器")

    def _build_conda_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        self.conda_hint = QLabel("")
        self.conda_hint.setWordWrap(True)
        self.conda_hint.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        layout.addWidget(self.conda_hint)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("环境名:"))
        self.env_name_edit = QLineEdit()
        self.env_name_edit.setPlaceholderText("如 ml-research")
        self.env_name_edit.setFixedWidth(180)
        row.addWidget(self.env_name_edit)
        row.addWidget(QLabel("Python 版本:"))
        self.conda_py_combo = QComboBox()
        for v in ("3.13", "3.12", "3.11", "3.10", "3.9", "不指定"):
            self.conda_py_combo.addItem(v if v != "不指定" else "(仅空环境)", v)
        self.conda_py_combo.setFixedWidth(140)
        row.addWidget(self.conda_py_combo)
        self.env_create_btn = QPushButton("创建环境")
        self.env_create_btn.setProperty("variant", "primary")
        self.env_create_btn.clicked.connect(self._create_conda_env)
        row.addWidget(self.env_create_btn)
        row.addSpacing(20)
        self.env_remove_btn = QPushButton("删除所选")
        self.env_remove_btn.clicked.connect(self._remove_conda_env)
        self.env_remove_btn.setEnabled(False)
        row.addWidget(self.env_remove_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.env_table = QTableWidget(0, 4)
        self.env_table.setHorizontalHeaderLabels(
            ["环境名", "路径", "Python 版本", "Conda 包数"])
        self.env_table.verticalHeader().setVisible(False)
        self.env_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.env_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.env_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.env_table.setAlternatingRowColors(True)
        self.env_table.setShowGrid(False)
        self.env_table.verticalHeader().setDefaultSectionSize(32)
        h = self.env_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.env_table.itemSelectionChanged.connect(
            lambda: self._update_env_remove_enabled())
        layout.addWidget(self.env_table, 1)
        self.tabs.addTab(page, "Conda 环境")

    def _build_packages_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(QLabel("目标类型:"))
        self.pkg_target_type = QComboBox()
        self.pkg_target_type.addItem("Python 解释器", "interpreter")
        self.pkg_target_type.addItem("Conda 环境", "conda")
        row1.addWidget(self.pkg_target_type)
        row1.addWidget(QLabel("目标:"))
        self.pkg_target_combo = QComboBox()
        self.pkg_target_combo.setMinimumWidth(340)
        row1.addWidget(self.pkg_target_combo, 1)
        row1.addWidget(QLabel("PyPI 镜像:"))
        self.pkg_index_combo = QComboBox()
        for label in em.PIPY_INDEXES:
            self.pkg_index_combo.addItem(label)
        row1.addWidget(self.pkg_index_combo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(QLabel("包名/约束:"))
        self.pkg_spec_edit = QLineEdit()
        self.pkg_spec_edit.setPlaceholderText(
            "如 requests  /  requests==2.31.0  /  numpy pandas (空格分隔多个)")
        row2.addWidget(self.pkg_spec_edit, 1)
        self.pip_install_btn = QPushButton("安装 (pip)")
        self.pip_install_btn.setProperty("variant", "primary")
        self.pip_install_btn.clicked.connect(
            lambda: self._do_package_op("pip_install"))
        row2.addWidget(self.pip_install_btn)
        self.pip_uninstall_btn = QPushButton("卸载 (pip)")
        self.pip_uninstall_btn.clicked.connect(
            lambda: self._do_package_op("pip_uninstall"))
        row2.addWidget(self.pip_uninstall_btn)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(10)
        note = QLabel("目标为 Conda 环境时, 可用下方 conda 命令管理频道包; "
                      "纯 Python 包同样可用上方 pip 按钮(作用于该环境的 Python)。")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Palette.text_faint}; font-size: 11px;")
        row3.addWidget(note, 1)
        self.conda_install_btn = QPushButton("安装 (conda)")
        self.conda_install_btn.clicked.connect(
            lambda: self._do_package_op("conda_install"))
        row3.addWidget(self.conda_install_btn)
        self.conda_remove_btn = QPushButton("卸载 (conda)")
        self.conda_remove_btn.clicked.connect(
            lambda: self._do_package_op("conda_remove"))
        row3.addWidget(self.conda_remove_btn)
        layout.addLayout(row3)

        result_card = QFrame()
        result_card.setObjectName("card")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(14, 10, 14, 10)
        result_layout.setSpacing(4)
        self._last_result_title = QLabel("最近一次操作")
        self._last_result_title.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px; font-weight: 700;")
        self._last_result = ElidedLabel("尚无操作")
        self._last_result.setStyleSheet(f"color: {Palette.text}; font-size: 12px;")
        result_layout.addWidget(self._last_result_title)
        result_layout.addWidget(self._last_result)
        layout.addWidget(result_card)
        layout.addStretch(1)
        self.tabs.addTab(page, "包管理")

        self.pkg_target_type.currentIndexChanged.connect(
            lambda _i: self._fill_targets())

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def set_data(self, interpreters: list[InterpreterInfo],
                 conda_info: CondaInfo | None) -> None:
        self._interpreters = interpreters
        self._conda_info = conda_info
        self._reload_py_table()
        self._reload_env_table()
        self._fill_targets()

    def set_current_env_dir(self, env_dir: str) -> None:
        """主窗口告知当前浏览的环境目录(删除保护)。"""
        self._current_env_dir = env_dir or ""

    def _reload_py_table(self) -> None:
        managed = em.list_managed_interpreters()
        self.py_table.setRowCount(len(managed))
        for row, item in enumerate(managed):
            self.py_table.setItem(
                row, 0, QTableWidgetItem(f"Python {item['version']}"))
            path_item = QTableWidgetItem(item["dir"])
            path_item.setForeground(QColor(Palette.text_muted))
            self.py_table.setItem(row, 1, path_item)
            self.py_table.setItem(
                row, 2, QTableWidgetItem(item["installed_at"] or "—"))

    def _reload_env_table(self) -> None:
        envs = self._conda_info.envs if self._conda_info else []
        self.env_table.setRowCount(len(envs))
        for row, env in enumerate(envs):
            name_item = QTableWidgetItem(("★ " if env.is_base else "") + env.name)
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
            count = QTableWidgetItem(str(env.package_count))
            count.setTextAlignment(Qt.AlignCenter)
            self.env_table.setItem(row, 3, count)
        has_conda = bool(self._conda_info and self._conda_info.roots)
        self.conda_hint.setText(
            f"Conda: {self._conda_info.executable or '(未找到 conda.exe, 使用根目录推断)'}"
            if has_conda else
            "未检测到 Conda 安装, 无法创建/删除环境。请先安装 Anaconda/Miniconda。")
        for w in (self.env_create_btn, self.env_remove_btn,
                  self.conda_install_btn, self.conda_remove_btn):
            w.setEnabled(has_conda and w is not self.env_remove_btn or False)
        self.env_create_btn.setEnabled(has_conda)
        self.conda_install_btn.setEnabled(has_conda)
        self.conda_remove_btn.setEnabled(has_conda)
        self._update_env_remove_enabled()

    def _update_env_remove_enabled(self) -> None:
        env = self._selected_conda_env()
        # base 环境不可删
        self.env_remove_btn.setEnabled(
            bool(env) and not env.is_base
            and bool(self._conda_info and self._conda_info.roots))

    def _selected_conda_env(self):
        row = self.env_table.currentRow()
        if row < 0 or not self._conda_info or row >= len(self._conda_info.envs):
            return None
        return self._conda_info.envs[row]

    def _fill_targets(self) -> None:
        self.pkg_target_combo.clear()
        if self.pkg_target_type.currentData() == "conda":
            for env in (self._conda_info.envs if self._conda_info else []):
                if not env.interpreter:
                    continue
                self.pkg_target_combo.addItem(
                    f"{env.name} ({env.path})", env.interpreter)
        else:
            for info in self._interpreters:
                self.pkg_target_combo.addItem(
                    f"{info.display_name} ({info.path})", info.path)
            for item in em.list_managed_interpreters():
                key = os.path.normcase(item["python_exe"])
                existing = {os.path.normcase(
                    self.pkg_target_combo.itemData(i))
                    for i in range(self.pkg_target_combo.count())}
                if key not in existing:
                    self.pkg_target_combo.addItem(
                        f"Python {item['version']} (托管)", item["python_exe"])
        self.pkg_target_combo.setEnabled(self.pkg_target_combo.count() > 0)

    def _selected_target_python(self) -> str | None:
        return self.pkg_target_combo.currentData()

    # ------------------------------------------------------------------
    # 操作执行(后台线程 + 日志)
    # ------------------------------------------------------------------
    def _log_line(self, text: str) -> None:
        self._log.appendPlainText(text)
        bar = self._log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _start_op(self, title: str, fn, *args, after: str = "",
                  message: str = "", result_text: str = "") -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "操作进行中",
                                    "已有环境管理操作在执行, 请等待其完成。")
            return
        self._log_line(f"── {title} ──")
        self._set_busy(True, title)
        self._worker = _ManageWorkerWrapper(
            self, title, fn, args, after=after, message=message,
            result_text=result_text)
        self._worker.start()

    def _set_busy(self, on: bool, title: str = "") -> None:
        self.busy.set_state(on, title)
        for w in (self.py_install_btn, self.py_remove_btn,
                  self.env_create_btn, self.env_remove_btn,
                  self.pip_install_btn, self.pip_uninstall_btn,
                  self.conda_install_btn, self.conda_remove_btn):
            w.setEnabled(not on)
        if not on:
            # 恢复条件化禁用状态(如 conda 未检测到)
            self._reload_env_table()
            self._reload_py_table()

    def _on_op_success(self, payload: dict) -> None:
        self._worker = None
        self._set_busy(False)
        title = payload.get("title", "操作")
        self._last_result_title.setText(f"最近一次操作:{title} —— 成功")
        self._last_result.setText(payload.get("result_text", "") or "完成")
        self._log_line(f"✔ {title} 成功")
        self._refresh_related(payload.get("after", ""))
        QMessageBox.information(self, title + " 成功",
                                payload.get("message", f"{title} 已成功完成。"))

    def _on_op_failed(self, message: str) -> None:
        self._worker = None
        self._set_busy(False)
        self._last_result_title.setText("最近一次操作:失败")
        self._last_result.setText(message.splitlines()[0] if message else "失败")
        self._log_line(f"✗ 操作失败:\n{message}")
        QMessageBox.critical(self, "操作失败", message)

    def _refresh_related(self, after: str) -> None:
        if after == "interpreters":
            self._reload_py_table()
            self.python_changed.emit()
        elif after == "conda":
            self.conda_changed.emit()
        elif after.startswith("packages:"):
            self.packages_changed.emit(after.split(":", 1)[1])

    # ------------------------------------------------------------------
    # 具体操作
    # ------------------------------------------------------------------
    def _install_python(self) -> None:
        version = self.py_version_combo.currentData()
        self._start_op(
            f"安装 Python {version}",
            em.install_python, version,
            after="interpreters",
            message=f"Python {version} 已安装并出现在解释器列表中。",
            result_text=f"安装目录: {os.path.join(em.get_runtimes_dir(), 'py-' + version)}")

    def _remove_python(self) -> None:
        row = self.py_table.currentRow()
        if row < 0:
            return
        item = em.list_managed_interpreters()[row]
        version = item["version"]
        # 保护: 当前应用正在浏览的环境
        if self._current_env_dir and os.path.normcase(
                item["dir"]) == os.path.normcase(self._current_env_dir):
            QMessageBox.warning(
                self, "无法删除",
                "该环境是当前正在浏览的环境, 请先切换到其他环境再删除。")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("确认删除 Python 解释器")
        box.setText(
            f"确定要删除 Python {version} 吗?\n\n路径: {item['dir']}\n\n"
            "该操作不可恢复!")
        box.setStandardButtons(QMessageBox.StandardButton.Yes |
                               QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self._start_op(f"删除 Python {version}",
                       em.remove_interpreter, item["dir"],
                       after="interpreters",
                       message=f"Python {version} 已删除。",
                       result_text=f"已删除: {item['dir']}")

    def _create_conda_env(self) -> None:
        if not self._conda_info or not self._conda_info.roots:
            QMessageBox.warning(self, "未检测到 Conda", "请先安装 Anaconda/Miniconda。")
            return
        conda_exe = self._conda_info.executable or ""
        if not conda_exe:
            QMessageBox.warning(
                self, "未找到 conda 可执行文件",
                "检测到 conda 安装目录但未找到 conda.exe/conda 命令, "
                "无法创建环境。请确认 Conda 安装完整。")
            return
        name = self.env_name_edit.text().strip()
        py_ver = self.conda_py_combo.currentData()
        if py_ver == "不指定":
            py_ver = ""
        try:
            em.validate_env_name(name)
        except em.EnvManagerError as exc:
            QMessageBox.warning(self, "环境名不合法", str(exc))
            return
        root = self._conda_info.roots[0]
        self._start_op(
            f"创建 Conda 环境 {name}",
            em.create_conda_env, conda_exe, root, name, py_ver,
            after="conda",
            message=f"环境 {name} 已创建, 现在可以在 Conda 页查看并安装包。",
            result_text=f"环境路径: {os.path.join(root, 'envs', name)}")

    def _remove_conda_env(self) -> None:
        env = self._selected_conda_env()
        if env is None:
            return
        if env.is_base:
            QMessageBox.critical(self, "无法删除",
                                 "base 是 Conda 的基础环境, 不允许删除。")
            return
        if self._current_env_dir and os.path.normcase(
                env.path) == os.path.normcase(self._current_env_dir):
            QMessageBox.warning(
                self, "无法删除",
                "该环境是当前正在浏览的环境, 请先切换到其他环境再删除。")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("确认删除 Conda 环境")
        box.setText(
            f"确定要删除 Conda 环境 {env.name} 吗?\n\n路径: {env.path}\n"
            f"包含 {env.package_count} 个包。\n\n该操作不可恢复!")
        box.setStandardButtons(QMessageBox.StandardButton.Yes |
                               QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        conda_exe = self._conda_info.executable if self._conda_info else ""
        if not conda_exe:
            QMessageBox.warning(self, "未找到 conda 可执行文件",
                                "无法执行删除操作, 请确认 Conda 安装完整。")
            return
        self._start_op(f"删除 Conda 环境 {env.name}",
                       em.remove_conda_env, conda_exe,
                       self._conda_info.roots[0] if self._conda_info else "",
                       env.name, env.path,
                       after="conda",
                       message=f"环境 {env.name} 已删除。",
                       result_text=f"已删除: {env.path}")

    def _do_package_op(self, op: str) -> None:
        target = self._selected_target_python()
        if not target:
            QMessageBox.warning(self, "未选择目标", "请先选择目标解释器或环境。")
            return
        spec = self.pkg_spec_edit.text().strip()
        index = self.pkg_index_combo.currentText()
        op_names = {"pip_install": "pip 安装", "pip_uninstall": "pip 卸载",
                    "conda_install": "conda 安装", "conda_remove": "conda 卸载"}
        title = f"{op_names[op]}: {spec or '(未指定)'}"

        if op.startswith("pip"):
            # pip_uninstall(python_exe, package, on_output) 无镜像参数,
            # 不能把 index 传进第 3 位(会与 on_output 冲突)
            if op == "pip_install":
                self._start_op(title, em.pip_install, target, spec, index,
                               after=f"packages:{target}",
                               message=f"{op_names[op]} 操作已完成: {spec}",
                               result_text=f"目标: {target}")
            else:
                self._start_op(title, em.pip_uninstall, target, spec,
                               after=f"packages:{target}",
                               message=f"{op_names[op]} 操作已完成: {spec}",
                               result_text=f"目标: {target}")
        else:
            if not self._conda_info or not self._conda_info.executable:
                QMessageBox.warning(self, "未检测到 Conda", "conda 包操作需要 conda.exe。")
                return
            env_path = self._conda_env_path_of(target)
            if not env_path:
                QMessageBox.warning(self, "目标不是 Conda 环境",
                                    "conda 包操作需要目标为 Conda 环境, 请切换目标类型。")
                return
            fn = em.conda_install if op == "conda_install" else em.conda_remove
            self._start_op(title, fn, self._conda_info.executable, env_path, spec,
                           after=f"packages:{target}",
                           message=f"{op_names[op]} 操作已完成: {spec}",
                           result_text=f"环境: {env_path}")

    def _conda_env_path_of(self, python_exe: str) -> str:
        """由解释器路径反查所属 conda 环境路径。"""
        for env in (self._conda_info.envs if self._conda_info else []):
            if env.interpreter and os.path.normcase(env.interpreter) == os.path.normcase(python_exe):
                return env.path
        return ""


# ---------------------------------------------------------------------------
# worker 包装(把 on_output 回调转成 Qt 信号, 并携带操作元数据)
# ---------------------------------------------------------------------------
class _ManageWorkerWrapper:
    """轻量包装: 用 workers.ManageWorker 启动任务并转发完成/失败信号。"""

    def __init__(self, page: "ManagePage", title: str, fn, args,
                 after: str = "", message: str = "", result_text: str = ""):
        from ..workers import ManageWorker
        self._page = page
        self._title = title
        self._after = after
        self._message = message
        self._result_text = result_text
        self._qthread = ManageWorker(fn, *args, parent=page)
        self.output = self._qthread.output
        self._qthread.done.connect(self._on_done)
        self._qthread.failed.connect(page._on_op_failed)

    def _on_done(self, result) -> None:
        self._page._on_op_success({
            "title": self._title,
            "after": self._after,
            "message": self._message,
            "result_text": self._result_text or str(result or ""),
        })

    def isRunning(self) -> bool:
        return self._qthread.isRunning()

    def start(self) -> None:
        self._qthread.start()


class _BusyLabel(QLabel):
    """忙碌状态条。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"color: {Palette.primary}; font-size: 12px; font-weight: 700;")
        self.hide()

    def set_state(self, on: bool, title: str = "") -> None:
        if on:
            self.setText(f"⏳ 正在执行: {title} … (详情见下方操作日志)")
            self.show()
        else:
            self.hide()
