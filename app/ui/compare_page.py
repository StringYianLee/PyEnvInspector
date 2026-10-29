"""页面:环境对比(两个解释器的包版本差异)。

只负责展示与交互; 数据由主窗口提供(必要时先在后台采集)。
"""

from __future__ import annotations

import csv
import datetime
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ..core.compare import CompareResult, PackageDiff
from ..core.models import InterpreterInfo
from .theme import Palette
from .widgets import ElidedLabel

_FILTERS = [
    ("全部差异", "all"),
    ("仅 A 有", "removed"),
    ("仅 B 有", "added"),
    ("升级", "upgraded"),
    ("降级", "downgraded"),
    ("无法比较", "changed"),
]

_KIND_STYLE = {
    "removed": ("仅 A 有", "#c8303e"),
    "added": ("仅 B 有", "#2f8f5b"),
    "upgraded": ("升级", "#3d6df2"),
    "downgraded": ("降级", "#e8850c"),
    "changed": ("版本变化", "#7a8499"),
}


class _StatChip(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(1)
        cap = QLabel(label)
        cap.setStyleSheet(f"color: {Palette.text_muted}; font-size: 11px;")
        self._value = QLabel("0")
        f = QFont()
        f.setBold(True)
        f.setPointSizeF(15)
        self._value.setFont(f)
        self._value.setStyleSheet(f"color: {Palette.text};")
        layout.addWidget(cap)
        layout.addWidget(self._value)

    def set_value(self, value: int, color: str | None = None) -> None:
        self._value.setText(str(value))
        self._value.setStyleSheet(f"color: {color or Palette.text};")


class ComparePage(QWidget):
    """环境对比页。"""

    compare_requested = Signal(str, str)   # a_path, b_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._result: CompareResult | None = None
        self._interpreters: list[InterpreterInfo] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(10)

        title = QLabel("环境对比")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSizeF(15)
        title.setFont(tf)
        title.setStyleSheet(f"color: {Palette.text};")
        root.addWidget(title)

        self._subtitle = ElidedLabel("选择两个环境, 对比包版本差异(A 为基准, B 为对照)")
        self._subtitle.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        root.addWidget(self._subtitle)

        # 选择区
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("A 基准:"))
        self.combo_a = QComboBox()
        self.combo_a.setMinimumWidth(240)
        row.addWidget(self.combo_a, 1)
        swap_btn = QPushButton("⇄")
        swap_btn.setFixedWidth(38)
        swap_btn.setToolTip("交换 A / B")
        swap_btn.clicked.connect(self._swap)
        row.addWidget(swap_btn)
        row.addWidget(QLabel("B 对照:"))
        self.combo_b = QComboBox()
        self.combo_b.setMinimumWidth(240)
        row.addWidget(self.combo_b, 1)

        self.compare_btn = QPushButton("开始对比")
        self.compare_btn.setProperty("variant", "primary")
        self.compare_btn.clicked.connect(self._request_compare)
        row.addWidget(self.compare_btn)
        root.addLayout(row)

        # 统计卡
        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.chip_added = _StatChip("仅 B 有")
        self.chip_removed = _StatChip("仅 A 有")
        self.chip_up = _StatChip("升级")
        self.chip_down = _StatChip("降级")
        self.chip_other = _StatChip("无法比较")
        self.chip_same = _StatChip("相同")
        for chip in (self.chip_added, self.chip_removed, self.chip_up,
                     self.chip_down, self.chip_other, self.chip_same):
            stats.addWidget(chip)
        root.addLayout(stats)

        # 工具条
        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(QLabel("筛选:"))
        self.filter_combo = QComboBox()
        for label, key in _FILTERS:
            self.filter_combo.addItem(label, key)
        self.filter_combo.setFixedWidth(130)
        self.filter_combo.currentIndexChanged.connect(self._reload_table)
        tools.addWidget(self.filter_combo)
        self.count_label = QLabel("尚未对比")
        self.count_label.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        tools.addWidget(self.count_label)
        tools.addStretch(1)
        self.export_btn = QPushButton("导出 CSV")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_csv)
        tools.addWidget(self.export_btn)
        root.addLayout(tools)

        # 结果表
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["包名", "A 版本", "B 版本", "变化"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)

    # ------------------------------------------------------------------
    def set_interpreters(self, interpreters: list[InterpreterInfo],
                         current_path: str = "") -> None:
        self._interpreters = list(interpreters)
        for combo in (self.combo_a, self.combo_b):
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for info in interpreters:
                label = f"Python {info.version} · {info.source_label}"
                if info.env_name:
                    label += f" · {info.env_name}"
                label += f" · {info.path}"
                combo.addItem(label, info.path)
            combo.blockSignals(False)
            if previous:
                idx = combo.findData(previous)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        if current_path:
            idx = self.combo_a.findData(current_path)
            if idx >= 0:
                self.combo_a.setCurrentIndex(idx)
        if self.combo_b.count() > 1 and self.combo_b.currentIndex() == 0:
            self.combo_b.setCurrentIndex(1)

    def set_selection(self, a_path: str, b_path: str) -> None:
        for combo, path in ((self.combo_a, a_path), (self.combo_b, b_path)):
            idx = combo.findData(path)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.compare_btn.setEnabled(not busy)
        self.compare_btn.setText("对比中…" if busy else "开始对比")
        if text:
            self._subtitle.setText(text)

    def show_result(self, result: CompareResult) -> None:
        self._result = result
        st = result.stats
        self.chip_added.set_value(st["added"], "#2f8f5b")
        self.chip_removed.set_value(st["removed"], "#c8303e")
        self.chip_up.set_value(st["upgraded"], "#3d6df2")
        self.chip_down.set_value(st["downgraded"], "#e8850c")
        self.chip_other.set_value(st["changed"], Palette.text_muted)
        self.chip_same.set_value(st["same"], Palette.text_muted)
        a = result.snapshot_a
        b = result.snapshot_b
        self._subtitle.setText(
            f"A: Python {a.python_full_version or a.interpreter.version} "
            f"({len(a.packages)} 包)   →   B: Python "
            f"{b.python_full_version or b.interpreter.version} "
            f"({len(b.packages)} 包)")
        self.export_btn.setEnabled(True)
        self._reload_table()

    def show_error(self, message: str) -> None:
        self._subtitle.setText(message)
        self._result = None
        self.export_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.count_label.setText("对比失败")

    # ------------------------------------------------------------------
    def _request_compare(self) -> None:
        a = self.combo_a.currentData()
        b = self.combo_b.currentData()
        if not a or not b:
            QMessageBox.information(self, "缺少环境",
                                    "请先在「解释器」页扫描到至少两个环境。")
            return
        if os.path.normcase(a) == os.path.normcase(b):
            QMessageBox.information(self, "无法对比", "A 与 B 是同一个环境。")
            return
        self.set_busy(True, "正在准备两个环境的快照…")
        self.compare_requested.emit(a, b)

    def _swap(self) -> None:
        ia, ib = self.combo_a.currentIndex(), self.combo_b.currentIndex()
        self.combo_a.setCurrentIndex(ib)
        self.combo_b.setCurrentIndex(ia)

    def _reload_table(self) -> None:
        if self._result is None:
            return
        key = self.filter_combo.currentData()
        rows: list[PackageDiff] = self._result.differences
        if key and key != "all":
            rows = [d for d in rows if d.kind == key]
        rows.sort(key=lambda d: (d.kind, d.name.lower()))

        self.table.setRowCount(len(rows))
        for r, diff in enumerate(rows):
            name_item = QTableWidgetItem(diff.name)
            self.table.setItem(r, 0, name_item)
            va = QTableWidgetItem(diff.version_a or "—")
            vb = QTableWidgetItem(diff.version_b or "—")
            for item in (va, vb):
                item.setForeground(QColor(Palette.text_muted))
            self.table.setItem(r, 1, va)
            self.table.setItem(r, 2, vb)
            label, color = _KIND_STYLE.get(diff.kind, (diff.kind, Palette.text))
            kind_item = QTableWidgetItem(label)
            kind_item.setForeground(QColor(color))
            kind_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 3, kind_item)
        self.count_label.setText(
            f"显示 {len(rows)} 条差异 / 共 {len(self._result.differences)} 条")

    def _export_csv(self) -> None:
        if self._result is None:
            return
        default = (f"环境对比_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出对比结果", default, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            # utf-8-sig 让 Excel 正确识别中文
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["包名", "A 版本", "B 版本", "变化"])
                for d in self._result.differences:
                    writer.writerow([d.name, d.version_a or "",
                                     d.version_b or "",
                                     _KIND_STYLE.get(d.kind, (d.kind,))[0]])
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self._subtitle.setText(f"已导出: {path}")
