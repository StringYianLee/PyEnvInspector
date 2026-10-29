"""页面:诊断与报告(环境体检 / 许可证汇总 / 历史变化)。

数据由主窗口在采集完成后计算并传入; 本页只做展示与导出。
"""

from __future__ import annotations

import datetime
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ..core.compare import compare_package_maps
from ..core.diagnostics import DiagnosticReport, build_diagnostics_text
from ..core.licenses import category_summary
from ..core.models import EnvironmentSnapshot
from .theme import Palette
from .widgets import ElidedLabel

_SEVERITY_STYLE = {
    "error": ("严重", "#c8303e", "#fdebec"),
    "warn": ("警告", "#e8850c", "#fdf2e2"),
    "info": ("提示", "#3d6df2", "#e8eefe"),
}


class _IssueCard(QFrame):
    def __init__(self, severity: str, title: str, detail: str, hint: str,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        label, color, soft = _SEVERITY_STYLE.get(
            severity, _SEVERITY_STYLE["info"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        badge = QLabel(label)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(38)
        badge.setStyleSheet(
            f"color: {color}; background: {soft}; border-radius: 6px;"
            " padding: 2px 4px; font-size: 11px; font-weight: 700;")
        head.addWidget(badge)
        title_label = QLabel(title)
        f = QFont()
        f.setBold(True)
        title_label.setFont(f)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"color: {Palette.text}; font-size: 13px;")
        head.addWidget(title_label, 1)
        layout.addLayout(head)

        body = QLabel(detail)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;"
            " font-family: Consolas, 'Microsoft YaHei UI', monospace;")
        layout.addWidget(body)

        if hint:
            tip = QLabel("→ " + hint)
            tip.setWordWrap(True)
            tip.setStyleSheet(f"color: {Palette.success_text}; font-size: 12px;")
            layout.addWidget(tip)


class ReportsPage(QWidget):
    """诊断与报告页(支持指定解释器诊断 + 一键修复全部冲突)。"""

    diagnostics_requested = Signal()
    interpreter_selected = Signal(str)        # 目标解释器路径
    fix_all_requested = Signal(str, list)     # (解释器路径, pip 表达式列表)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._snapshot: EnvironmentSnapshot | None = None
        self._report: DiagnosticReport | None = None
        self._history: list[dict] = []
        self._analysis = None
        self._fix_expressions: list[str] = []
        self._populating = False          # 程序化填充下拉时抑制信号回调

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("诊断与报告")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSizeF(15)
        title.setFont(tf)
        title.setStyleSheet(f"color: {Palette.text};")
        head.addWidget(title)
        head.addStretch(1)
        self.refresh_btn = QPushButton("重新体检")
        self.refresh_btn.clicked.connect(self.diagnostics_requested.emit)
        head.addWidget(self.refresh_btn)
        root.addLayout(head)

        # 目标环境选择 + 一键修复
        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        target_row.addWidget(QLabel("目标解释器:"))
        self.interp_combo = QComboBox()
        self.interp_combo.setMinimumWidth(360)
        self.interp_combo.currentIndexChanged.connect(self._on_interp_changed)
        target_row.addWidget(self.interp_combo, 1)
        self.diagnose_btn = QPushButton("诊断")
        self.diagnose_btn.clicked.connect(self._emit_selected)
        target_row.addWidget(self.diagnose_btn)
        self.fix_all_btn = QPushButton("一键修复全部冲突")
        self.fix_all_btn.setProperty("variant", "primary")
        self.fix_all_btn.setEnabled(False)
        self.fix_all_btn.clicked.connect(self._request_fix_all)
        target_row.addWidget(self.fix_all_btn)
        root.addLayout(target_row)

        self._subtitle = ElidedLabel("在「解释器」页选择一个环境后, 这里会显示体检结果")
        self._subtitle.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        root.addWidget(self._subtitle)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_diag_tab()
        self._build_license_tab()
        self._build_history_tab()

    # ------------------------------------------------------------------
    # 目标环境选择 / 一键修复
    # ------------------------------------------------------------------
    def set_interpreters(self, interpreters, current_path: str = "") -> None:
        """填充目标解释器下拉(保留当前选择)。

        注意: 恢复选中项也必须在 blockSignals 生效期间完成 ——
        否则 setCurrentIndex 会触发 currentIndexChanged → 通知主窗口加载
        → 刷新报告 → 再次调用本方法, 形成无限递归(表现为闪退/卡死)。
        """
        previous = current_path or self.interp_combo.currentData()
        self._populating = True
        self.interp_combo.blockSignals(True)
        try:
            self.interp_combo.clear()
            for info in interpreters:
                label = f"Python {info.version} · {info.source_label}"
                if info.env_name:
                    label += f" · {info.env_name}"
                label += f" · {info.path}"
                self.interp_combo.addItem(label, info.path)
            if previous:
                idx = self.interp_combo.findData(previous)
                if idx >= 0:
                    self.interp_combo.setCurrentIndex(idx)
        finally:
            self.interp_combo.blockSignals(False)
            self._populating = False

    def selected_path(self) -> str:
        return self.interp_combo.currentData() or ""

    def _on_interp_changed(self, _index: int) -> None:
        if self._populating:
            return          # 程序化填充/恢复, 不是用户切换
        self.fix_all_btn.setEnabled(False)
        self._fix_expressions = []
        self._emit_selected()

    def _emit_selected(self) -> None:
        path = self.selected_path()
        if path:
            self.interpreter_selected.emit(path)

    def _request_fix_all(self) -> None:
        path = self.selected_path()
        if not path or not self._fix_expressions:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("确认一键修复")
        box.setText(
            f"将在目标环境执行 {len(self._fix_expressions)} 条 pip 安装命令:")
        box.setInformativeText("\n".join(self._fix_expressions))
        box.setDetailedText(
            f"目标解释器: {path}\n\n"
            "修复逻辑: 对每个被多个包约束的依赖, 合并全部版本约束后重装, "
            "由 pip 求解出一个同时满足所有约束的版本。\n\n"
            "注意:\n  · 会改变该环境中的包版本\n"
            "  · 若约束之间没有交集, pip 会报错且不改变现有安装\n"
            "  · 单个包失败不会中断其余包的修复")
        box.setStandardButtons(QMessageBox.StandardButton.Ok |
                               QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Ok:
            return
        self.fix_all_requested.emit(path, list(self._fix_expressions))

    # ------------------------------------------------------------------
    def _build_diag_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        tools = QHBoxLayout()
        self.diag_summary = QLabel("尚未体检")
        self.diag_summary.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        tools.addWidget(self.diag_summary)
        tools.addStretch(1)
        export_btn = QPushButton("导出体检报告")
        export_btn.clicked.connect(self._export_diag)
        tools.addWidget(export_btn)
        layout.addLayout(tools)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._issues_layout = QVBoxLayout(container)
        self._issues_layout.setContentsMargins(0, 0, 0, 0)
        self._issues_layout.setSpacing(8)
        self._issues_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        self.tabs.addTab(page, "环境体检")

    def _build_license_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        tools = QHBoxLayout()
        self.license_summary = QLabel("尚未采集")
        self.license_summary.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        tools.addWidget(self.license_summary)
        tools.addStretch(1)
        export_btn = QPushButton("导出许可证汇总")
        export_btn.clicked.connect(self._export_licenses)
        tools.addWidget(export_btn)
        layout.addLayout(tools)

        self.license_table = QTableWidget(0, 4)
        self.license_table.setHorizontalHeaderLabels(
            ["许可证", "类别", "包数", "包含的包"])
        self.license_table.verticalHeader().setVisible(False)
        self.license_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.license_table.setAlternatingRowColors(True)
        self.license_table.setShowGrid(False)
        self.license_table.verticalHeader().setDefaultSectionSize(28)
        header = self.license_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.license_table, 1)
        self.tabs.addTab(page, "许可证汇总")

    def _build_history_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("与之前某次采集对比:"))
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(240)
        self.history_combo.currentIndexChanged.connect(self._reload_history)
        row.addWidget(self.history_combo, 1)
        self.history_summary = QLabel("尚无历史记录")
        self.history_summary.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        row.addWidget(self.history_summary)
        layout.addLayout(row)

        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setStyleSheet(
            f"background: {Palette.surface}; border: 1px solid {Palette.border};"
            f" border-radius: 8px; color: {Palette.text};"
            " font-family: Consolas, monospace; font-size: 12px; padding: 8px;")
        layout.addWidget(self.history_text, 1)
        self.tabs.addTab(page, "历史变化")

    # ------------------------------------------------------------------
    def set_snapshot(self, snapshot: EnvironmentSnapshot) -> None:
        self._snapshot = snapshot
        interp = snapshot.interpreter
        self._subtitle.setText(
            f"{interp.path} · Python "
            f"{snapshot.python_full_version or interp.version} · "
            f"{len(snapshot.packages)} 个包")

    def show_diagnostics(self, report: DiagnosticReport,
                         analysis=None) -> None:
        self._report = report
        self._analysis = analysis
        while self._issues_layout.count() > 1:
            item = self._issues_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for issue in report.sorted_issues():
            self._issues_layout.insertWidget(
                self._issues_layout.count() - 1,
                _IssueCard(issue.severity.value, issue.title,
                           issue.detail, issue.hint, self))
        others = len(report.issues) - report.errors - report.warnings
        self.diag_summary.setText(
            f"严重 {report.errors} · 警告 {report.warnings} · 提示 {others}")

        # 计算一键修复计划: 每个冲突目标包的合并约束 → pip 表达式
        self._fix_expressions = []
        if analysis is not None:
            from ..core.analyzer import suggest_constraint
            targets: list[str] = []
            for edge in analysis.conflict_edges:
                if edge.target_key not in targets:
                    targets.append(edge.target_key)
            for key in targets:
                expression, _sources = suggest_constraint(analysis, key)
                if expression and expression not in self._fix_expressions:
                    self._fix_expressions.append(expression)
        self.fix_all_btn.setEnabled(bool(self._fix_expressions))
        self.fix_all_btn.setText(
            f"一键修复全部冲突 ({len(self._fix_expressions)})"
            if self._fix_expressions else "一键修复全部冲突")

    def show_licenses(self, groups: list[dict]) -> None:
        self.license_table.setRowCount(len(groups))
        for r, group in enumerate(groups):
            self.license_table.setItem(r, 0, QTableWidgetItem(group["license"]))
            cat_item = QTableWidgetItem(group["category"])
            color = {"强著佐权": "#c8303e", "弱著佐权": "#e8850c",
                     "未声明": Palette.text_faint}.get(
                group["category"], Palette.success_text)
            cat_item.setForeground(QColor(color))
            self.license_table.setItem(r, 1, cat_item)
            count_item = QTableWidgetItem(str(group["count"]))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.license_table.setItem(r, 2, count_item)
            packages = ", ".join(group["packages"])
            pkg_item = QTableWidgetItem(packages)
            pkg_item.setToolTip(packages)
            pkg_item.setForeground(QColor(Palette.text_muted))
            self.license_table.setItem(r, 3, pkg_item)
        summary = category_summary(self._snapshot) if self._snapshot else {}
        self.license_summary.setText(
            " · ".join(f"{k} {v}" for k, v in summary.items()) or "尚无数据")

    def set_history(self, entries: list[dict]) -> None:
        """entries: cache.load_history() 的结果(时间升序)。"""
        self._history = entries
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        # 最后一条是最近一次采集(即当前), 之前的作为对比基准
        earlier = entries[:-1]
        for entry in reversed(earlier):
            self.history_combo.addItem(
                f"{entry.get('collected_at', '?')} · "
                f"{len(entry.get('packages') or {})} 个包")
        self.history_combo.blockSignals(False)
        if earlier:
            self.history_combo.setCurrentIndex(0)
            self._reload_history()
        else:
            self.history_summary.setText("尚无历史记录(需要至少两次采集)")
            self.history_text.setPlainText(
                "每次采集都会记录一份包清单; 再次采集后即可在此查看变化。")

    def _reload_history(self) -> None:
        if not self._history or not self._snapshot:
            return
        earlier = self._history[:-1]
        idx = self.history_combo.currentIndex()
        if idx < 0 or idx >= len(earlier):
            return
        base = list(reversed(earlier))[idx]
        old_map = base.get("packages") or {}
        new_map = {p.name: p.version for p in self._snapshot.packages}
        added, removed, changed = compare_package_maps(old_map, new_map)

        lines = [
            f"基准: {base.get('collected_at', '?')}"
            f" (Python {base.get('python_full_version', '?')})",
            f"现在: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"
            f" (Python {self._snapshot.python_full_version})",
            "",
            f"新增 {len(added)} · 移除 {len(removed)} · 版本变化 {len(changed)}",
            "",
        ]
        if added:
            lines.append("[新增]")
            lines += [f"  + {name}" for name in added]
            lines.append("")
        if removed:
            lines.append("[移除]")
            lines += [f"  - {name}" for name in removed]
            lines.append("")
        if changed:
            lines.append("[版本变化]")
            lines += [f"  ~ {name}: {old} → {new}"
                      for name, old, new in changed]
        if not (added or removed or changed):
            lines.append("✔ 与基准采集相比没有任何变化。")
        self.history_text.setPlainText("\n".join(lines))
        self.history_summary.setText(
            f"+{len(added)} / -{len(removed)} / ~{len(changed)}")

    # ------------------------------------------------------------------
    def _export_diag(self) -> None:
        if self._report is None or self._snapshot is None:
            QMessageBox.information(self, "无数据", "请先选择一个环境。")
            return
        default = f"体检报告_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出体检报告", default, "文本文件 (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(build_diagnostics_text(self._report, self._snapshot))
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self._subtitle.setText(f"已导出: {path}")

    def _export_licenses(self) -> None:
        if self._snapshot is None:
            QMessageBox.information(self, "无数据", "请先选择一个环境。")
            return
        from ..core.licenses import build_license_text
        default = f"许可证汇总_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出许可证汇总", default, "文本文件 (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(build_license_text(self._snapshot))
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self._subtitle.setText(f"已导出: {path}")
