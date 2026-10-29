"""页面三:依赖关系分析(依赖图 / 冲突清单 / 循环依赖 / 冲突矩阵)。"""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from ..core import exporter, licenses
from ..core.analyzer import suggest_constraint
from ..core.layout import force_layout, hierarchical_layout
from ..core.models import AnalysisResult, DepEdge, EdgeStatus
from .graph_view import DependencyGraphView
from .theme import Palette
from .widgets import BusyOverlay, FlowLayout, make_badge


class AnalysisPage(QWidget):
    """依赖分析页。"""

    fix_requested = Signal(str, str)   # (目标解释器路径, pip 安装表达式)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._analysis: AnalysisResult | None = None
        self._selected_problem: DepEdge | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        # ---- 统计卡片行 ----
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_packages = self._make_stat("已安装包", "info", "目标环境中已安装的发行包数量")
        self._stat_edges = self._make_stat("依赖关系", "info", "有效的依赖边数量(不含环境标记不适用的依赖)")
        self._stat_conflicts = self._make_stat("版本冲突", "error", "已安装版本不满足依赖方声明的约束")
        self._stat_missing = self._make_stat("依赖缺失", "warn", "声明的依赖在环境中未安装")
        self._stat_unknown = self._make_stat("未知项", "muted", "无法解析的依赖声明 / 非法版本号 / URL 依赖")
        self._stat_cycles = self._make_stat("循环依赖", "muted", "互相依赖形成的环(强连通分量)")
        for card in (self._stat_packages, self._stat_edges, self._stat_conflicts,
                     self._stat_missing, self._stat_unknown, self._stat_cycles):
            stats_row.addWidget(card)
        root.addLayout(stats_row)

        # ---- Tab 区 ----
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Tab 1: 依赖图
        self._build_graph_tab()
        # Tab 2: 冲突清单
        self._build_conflicts_tab()
        # Tab 3: 循环依赖
        self._build_cycles_tab()
        # Tab 4: 冲突矩阵
        self._build_matrix_tab()

        # 导出(多格式菜单)
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        self.export_button = QToolButton()
        self.export_button.setText("导出")
        self.export_button.setPopupMode(
            self.export_button.ToolButtonPopupMode.InstantPopup)
        self.export_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly)
        menu = QMenu(self.export_button)
        for label, key in (
            ("分析报告 (.txt)", "report"),
            ("requirements.txt", "requirements"),
            ("environment.yml", "yaml"),
            ("依赖图 PNG", "png"),
            ("依赖图 SVG", "svg"),
            ("Graphviz DOT(仅问题边)", "dot"),
            ("许可证汇总 (.txt)", "licenses"),
        ):
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, k=key: self._export_format(k))
        self.export_button.setMenu(menu)
        export_row.addWidget(self.export_button)
        root.addLayout(export_row)

        self.busy = BusyOverlay(self)

    # ------------------------------------------------------------------
    # 构建 Tab
    # ------------------------------------------------------------------
    def _make_stat(self, label: str, variant: str, tooltip: str):
        from .widgets import StatCard
        return StatCard(label, "0", variant, tooltip)

    def _build_graph_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.layout_combo = QComboBox()
        self.layout_combo.addItem("分层布局", "hierarchical")
        self.layout_combo.addItem("力导向布局", "force")
        self.layout_combo.setFixedWidth(150)
        self.layout_combo.setToolTip(
            "分层布局: 依赖方在上被依赖方在下, 速度快\n力导向布局: 聚簇观感好, 节点多时后台计算")
        toolbar.addWidget(QLabel("布局:"))
        toolbar.addWidget(self.layout_combo)

        fit_btn = QPushButton("适应视图")
        fit_btn.clicked.connect(lambda: self.graph.fit_to_view())
        toolbar.addWidget(fit_btn)

        clear_btn = QPushButton("清除聚焦")
        clear_btn.clicked.connect(self._clear_focus)
        toolbar.addWidget(clear_btn)

        toolbar.addSpacing(12)
        search_label = QLabel("定位包:")
        toolbar.addWidget(search_label)
        self.graph_search = QLineEdit()
        self.graph_search.setPlaceholderText("输入包名, 回车定位")
        self.graph_search.setClearButtonEnabled(True)
        self.graph_search.setFixedWidth(200)
        self.graph_search.returnPressed.connect(self._locate_package)
        toolbar.addWidget(self.graph_search)
        toolbar.addStretch(1)

        # 图例
        legend = QHBoxLayout()
        legend.setSpacing(14)
        for text, color in (
            ("正常包", Palette.node_normal_border), ("版本冲突", Palette.edge_conflict),
            ("缺失(未安装)", Palette.edge_missing), ("未知项", Palette.text_faint),
        ):
            dot = QFrame()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"background: {color}; border-radius: 5px; border: 1px solid {Palette.border};"
            )
            item = QHBoxLayout()
            item.setSpacing(5)
            item.addWidget(dot)
            lab = QLabel(text)
            lab.setStyleSheet(f"color: {Palette.text_muted}; font-size: 11px;")
            item.addWidget(lab)
            holder = QWidget()
            holder.setLayout(item)
            legend.addWidget(holder)
        legend.addStretch(1)
        toolbar.addLayout(legend)

        layout.addLayout(toolbar)

        self.graph = DependencyGraphView()
        layout.addWidget(self.graph, 1)
        self.tabs.addTab(page, "依赖图")

        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)

    def _build_conflicts_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)

        hint = QLabel(
            "点击任意一行, 将在「依赖图」中高亮该冲突链条"
            "(含同一被依赖包的全部约束来源)"
        )
        hint.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        layout.addWidget(hint)

        self.conflict_table = QTableWidget(0, 6)
        headers = ["类型", "依赖方", "要求的约束", "被依赖方", "已安装版本", "结论"]
        self.conflict_table.setHorizontalHeaderLabels(headers)
        self.conflict_table.verticalHeader().setVisible(False)
        self.conflict_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.conflict_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.conflict_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.conflict_table.setAlternatingRowColors(True)
        header = self.conflict_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.conflict_table.setShowGrid(False)
        self.conflict_table.clicked.connect(self._on_conflict_clicked)
        layout.addWidget(self.conflict_table, 1)

        # 冲突修复: 合并所有约束 → 生成 pip 表达式 → 可复制/可执行
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.fix_hint = QLabel("")
        self.fix_hint.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;")
        actions.addWidget(self.fix_hint, 1)
        self.copy_fix_btn = QPushButton("复制修复命令")
        self.copy_fix_btn.setEnabled(False)
        self.copy_fix_btn.clicked.connect(self._copy_fix_command)
        actions.addWidget(self.copy_fix_btn)
        self.apply_fix_btn = QPushButton("在目标环境执行修复")
        self.apply_fix_btn.setProperty("variant", "primary")
        self.apply_fix_btn.setEnabled(False)
        self.apply_fix_btn.clicked.connect(self._apply_fix_command)
        actions.addWidget(self.apply_fix_btn)
        layout.addLayout(actions)
        self.tabs.addTab(page, "冲突清单")

    def _build_cycles_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self._cycles_host = QWidget()
        self._cycles_layout = QVBoxLayout(self._cycles_host)
        self._cycles_layout.setSpacing(8)
        self._cycles_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.setWidget(self._cycles_host)
        layout.addWidget(scroll)
        self.tabs.addTab(page, "循环依赖")

    def _build_matrix_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        hint = QLabel(
            "行 = 依赖方, 列 = 被依赖方; 仅列出与问题相关的包。"
            "红 = 版本冲突, 橙 = 依赖缺失, 灰 = 未知项, 绿 = 满足。悬浮查看约束详情。"
        )
        hint.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.matrix_table = QTableWidget(0, 0)
        self.matrix_table.verticalHeader().setVisible(True)
        self.matrix_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.matrix_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.matrix_table.setShowGrid(True)
        self.matrix_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        layout.addWidget(self.matrix_table, 1)
        self.tabs.addTab(page, "冲突矩阵")

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def load_analysis(self, analysis: AnalysisResult) -> None:
        self._analysis = analysis
        stats = analysis.stats
        self._stat_packages.set_value(str(stats["packages"]))
        self._stat_edges.set_value(str(stats["edges"]))
        self._stat_conflicts.set_value(str(stats["conflicts"]))
        self._stat_missing.set_value(str(stats["missing"]))
        self._stat_unknown.set_value(str(stats["unknown"]))
        self._stat_cycles.set_value(str(stats["cycles"]))

        self._render_graph()
        self._render_conflicts()
        self._render_cycles()
        self._render_matrix()

    def _render_graph(self) -> None:
        if self._analysis is None:
            return
        self._cancel_pending_layout()  # 切布局/换数据时丢弃旧的后台计算
        mode = self.layout_combo.currentData() or "hierarchical"
        if mode == "force" and len(self._analysis.packages) > 60:
            # 后台计算, 避免卡顿
            self.busy.start("正在计算力导向布局…")
            self._start_layout_worker()
            return
        positions = self._compute_layout(mode)
        self.graph.controller.build(self._analysis, positions)
        self.graph.fit_to_view()

    def _cancel_pending_layout(self) -> None:
        """取消未完成的后台布局任务(断开信号, 线程结束后延迟回收)。"""
        old = getattr(self, "_layout_worker", None)
        if old is None:
            return
        try:
            old.done.disconnect()
            old.failed.disconnect()
        except (RuntimeError, TypeError):
            pass
        if old.isRunning():
            old.finished.connect(old.deleteLater)  # 延迟回收, 不销毁运行中线程
        else:
            old.deleteLater()
        self._layout_worker = None
        self.busy.stop()  # 旧任务被取消, 忙碌遮罩必须清理(否则卡住)

    def _compute_layout(self, mode: str) -> dict:
        assert self._analysis is not None
        if mode == "force":
            return force_layout(self._analysis.packages, self._analysis.edges)
        return hierarchical_layout(self._analysis.packages, self._analysis.edges)

    def _start_layout_worker(self) -> None:
        from ..workers import LayoutWorker

        self._cancel_pending_layout()
        worker = LayoutWorker(self._analysis, mode="force", parent=self)
        worker.done.connect(self._on_layout_done)
        worker.failed.connect(self._on_layout_failed)
        self._layout_worker = worker
        worker.start()

    def _on_layout_failed(self, message: str) -> None:
        worker = self.sender()
        if worker is not self._layout_worker:
            return
        self._layout_worker = None
        worker.deleteLater()
        self.busy.stop()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "布局计算失败", message)

    def _on_layout_done(self, positions: dict) -> None:
        worker = self.sender()
        if worker is not self._layout_worker:
            return
        self._layout_worker = None
        worker.deleteLater()
        self.busy.stop()
        # 结果基于旧的分析数据(期间已载入新环境)则直接丢弃
        if getattr(worker, "analysis", None) is not self._analysis:
            return
        self.graph.controller.build(self._analysis, positions)
        self.graph.fit_to_view()

    def _render_conflicts(self) -> None:
        assert self._analysis is not None
        problems = (
            self._analysis.conflict_edges
            + self._analysis.missing_edges
            + self._analysis.unknown_edges
        )
        type_names = {
            EdgeStatus.VERSION_CONFLICT: "版本冲突",
            EdgeStatus.MISSING: "依赖缺失",
            EdgeStatus.UNKNOWN: "未知项",
        }
        self.conflict_table.setRowCount(len(problems))
        for row, edge in enumerate(problems):
            kind = type_names[edge.status]
            cells = [
                kind, edge.source_display, edge.spec or "任意版本",
                edge.target_display,
                self._target_version(edge), edge.message,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    color = {
                        "版本冲突": Palette.error,
                        "依赖缺失": Palette.warn,
                        "未知项": Palette.text_muted,
                    }[kind]
                    item.setForeground(QColor(color))
                    f = QFont()
                    f.setBold(True)
                    item.setFont(f)
                elif col == 2:
                    item.setForeground(QColor(Palette.text_muted))
                elif col == 5:
                    color = (Palette.error if edge.status == EdgeStatus.VERSION_CONFLICT
                             else Palette.warn if edge.status == EdgeStatus.MISSING
                             else Palette.text_muted)
                    item.setForeground(QColor(color))
                item.setData(Qt.UserRole, (edge.source_key, edge.target_key))
                self.conflict_table.setItem(row, col, item)
        self.conflict_table.setRowCount(len(problems))
        if problems:
            self.tabs.setTabText(1, f"冲突清单 ({len(problems)})")
        else:
            self.tabs.setTabText(1, "冲突清单")

    def _target_version(self, edge: DepEdge) -> str:
        if self._analysis is None:
            return ""
        pkg = self._analysis.packages.get(edge.target_key)
        if pkg is None or not pkg.installed:
            return "—"
        return pkg.version or "?"

    def _render_cycles(self) -> None:
        # 清空
        while self._cycles_layout.count() > 1:
            item = self._cycles_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        assert self._analysis is not None
        cycles = self._analysis.cycles
        if not cycles:
            empty = QLabel("✔ 未检测到循环依赖")
            empty.setStyleSheet(f"color: {Palette.ok}; font-size: 13px; font-weight: 600;")
            self._cycles_layout.insertWidget(0, empty)
            self.tabs.setTabText(2, "循环依赖")
            return

        self.tabs.setTabText(2, f"循环依赖 ({len(cycles)})")
        for idx, cycle in enumerate(cycles, start=1):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(6)
            title = QLabel(f"环 #{idx} · {len(cycle)} 个包")
            tf = QFont()
            tf.setBold(True)
            title.setFont(tf)
            title.setStyleSheet(f"color: {Palette.text}; font-size: 12px;")
            card_layout.addWidget(title)
            chain = QLabel(" → ".join(cycle) + " → " + cycle[0])
            chain.setStyleSheet(
                f"color: {Palette.text_muted}; font-size: 12px;"
                " font-family: Consolas, monospace;"
            )
            chain.setWordWrap(True)
            card_layout.addWidget(chain)
            self._cycles_layout.insertWidget(idx - 1, card)

    def _render_matrix(self) -> None:
        assert self._analysis is not None
        problems = (
            self._analysis.conflict_edges
            + self._analysis.missing_edges
            + self._analysis.unknown_edges
        )
        if not problems:
            self.matrix_table.setRowCount(0)
            self.matrix_table.setColumnCount(0)
            self.tabs.setTabText(3, "冲突矩阵")
            return

        # 行: 依赖方; 列: 被依赖方(只取问题相关包)
        sources = sorted({e.source_key for e in problems})
        targets = sorted({e.target_key for e in problems})
        name_of = {k: p.name for k, p in self._analysis.packages.items()}
        ver_of = {
            k: (p.version or "?") if p.installed else "未安装"
            for k, p in self._analysis.packages.items()
        }

        # 重渲染前清空旧单元格: 行列数相同时 setRowCount 不会移除已有 item
        self.matrix_table.clearContents()
        self.matrix_table.setRowCount(len(sources))
        self.matrix_table.setColumnCount(len(targets))
        self.matrix_table.setHorizontalHeaderLabels(
            [f"{name_of.get(t, t)}\n{ver_of.get(t, '')}" for t in targets])
        self.matrix_table.setVerticalHeaderLabels(
            [f"{name_of.get(s, s)} {ver_of.get(s, '')}" for s in sources])

        cell_map = {}
        for e in problems:
            cell_map.setdefault((e.source_key, e.target_key), []).append(e)
        # 补充满足的边(同一批行列间)
        for e in self._analysis.edges:
            if e.status == EdgeStatus.OK:
                cell_map.setdefault((e.source_key, e.target_key), []).append(e)

        marks = {
            EdgeStatus.VERSION_CONFLICT: ("✗", Palette.error, Palette.error_soft),
            EdgeStatus.MISSING: ("✗", Palette.warn, Palette.warn_soft),
            EdgeStatus.UNKNOWN: ("?", Palette.text_muted, Palette.neutral_soft),
            EdgeStatus.OK: ("✓", Palette.ok, Palette.ok_soft),
        }
        for i, s in enumerate(sources):
            for j, t in enumerate(targets):
                edges = cell_map.get((s, t))
                if not edges:
                    continue
                # 多条边时问题优先
                edge = sorted(
                    edges, key=lambda e: e.is_problem, reverse=True)[0]
                mark, fg, bg = marks[edge.status]
                item = QTableWidgetItem(mark)
                item.setTextAlignment(Qt.AlignCenter)
                f = QFont()
                f.setBold(True)
                item.setFont(f)
                item.setForeground(QColor(fg))
                item.setBackground(QColor(bg))
                tooltip = (
                    f"{edge.source_display} → {edge.target_display}\n"
                    f"约束: {edge.spec or '任意版本'}\n"
                    f"已安装: {self._target_version(edge)}\n"
                    f"结论: {edge.message}"
                )
                item.setToolTip(tooltip)
                self.matrix_table.setItem(i, j, item)
        self.matrix_table.resizeColumnsToContents()
        self.matrix_table.resizeRowsToContents()
        self.tabs.setTabText(3, f"冲突矩阵 ({len(problems)})")

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_layout_changed(self) -> None:
        self._render_graph()

    def _problems(self) -> list[DepEdge]:
        assert self._analysis is not None
        return (self._analysis.conflict_edges
                + self._analysis.missing_edges
                + self._analysis.unknown_edges)

    def _on_conflict_clicked(self, index) -> None:
        if self._analysis is None or not index.isValid():
            return
        row = index.row()
        # 行号与 problems 渲染顺序一一对应, 直接按行取边
        # (同一对包可能有多条不同约束的边, 按 key 匹配会取错)
        problems = self._problems()
        if row >= len(problems):
            return
        edge = problems[row]
        self._selected_problem = edge
        self._update_fix_hint(edge)
        self.tabs.setCurrentIndex(0)
        target = self.graph.controller.focus_edge(edge)
        if target:
            self.graph.center_on_node(target)

    # -- 冲突修复 ---------------------------------------------------------
    def _update_fix_hint(self, edge: DepEdge) -> None:
        assert self._analysis is not None
        expression, sources = suggest_constraint(self._analysis, edge.target_key)
        if not expression:
            self.fix_hint.setText("该问题没有可合并的版本约束(缺失/未知项), 无法自动修复")
            self.copy_fix_btn.setEnabled(False)
            self.apply_fix_btn.setEnabled(False)
            return
        self.fix_hint.setText(
            f"合并 {len(sources)} 条约束 → {expression}")
        self.copy_fix_btn.setEnabled(True)
        self.apply_fix_btn.setEnabled(True)

    def _fix_command(self) -> tuple[str, str]:
        """返回 (python 路径, pip 安装表达式)。"""
        if self._analysis is None or self._selected_problem is None:
            return "", ""
        expression, _ = suggest_constraint(
            self._analysis, self._selected_problem.target_key)
        python = self._analysis.snapshot.interpreter.path
        return python, expression

    def _copy_fix_command(self) -> None:
        _python, expression = self._fix_command()
        if not expression:
            return
        from PySide6.QtGui import QGuiApplication
        command = f'python -m pip install "{expression}"'
        QGuiApplication.clipboard().setText(command)
        self.fix_hint.setText(f"已复制: {command}")

    def _apply_fix_command(self) -> None:
        python, expression = self._fix_command()
        if not python or not expression:
            return
        command = f'python -m pip install "{expression}"'
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("确认执行修复")
        box.setText("将在目标环境中执行以下命令:")
        box.setInformativeText(command)
        box.setDetailedText(
            "执行前建议:\n"
            "  · 确认目标环境中没有正在运行的程序\n"
            "  · 该操作会改变已安装的包版本\n"
            "  · 若所有约束无法同时满足, pip 会报错且不改变现有安装")
        box.setStandardButtons(QMessageBox.StandardButton.Ok |
                               QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Ok:
            return
        self.fix_requested.emit(python, expression)

    def _clear_focus(self) -> None:
        self.graph.clear_visual_state()

    def _locate_package(self) -> None:
        text = self.graph_search.text().strip().lower()
        if not text:
            return
        if self._analysis is None:
            return
        # 模糊匹配: 精确 → 前缀 → 包含
        keys = list(self._analysis.packages.keys())
        key = None
        for k in keys:
            if k == text:
                key = k
                break
        if key is None:
            for k in keys:
                if k.startswith(text):
                    key = k
                    break
        if key is None:
            for k in keys:
                if text in k:
                    key = k
                    break
        if key:
            self.graph.focus_node(key)

    def focus_package(self, key: str) -> None:
        """从其他页跳转: 切到图并定位包。"""
        self.tabs.setCurrentIndex(0)
        self.graph.focus_node(key)

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def _export_format(self, key: str) -> None:
        """统一导出入口: 报告 / requirements / yaml / PNG / SVG / DOT / 许可证。"""
        if self._analysis is None:
            return
        snapshot = self._analysis.snapshot
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        version = snapshot.interpreter.version or "env"

        if key in ("png", "svg"):
            self._export_graph_image(key, f"依赖图_{version}_{stamp}")
            return

        if key == "report":
            default, filt, writer = (
                f"依赖分析报告_{version}_{stamp}.txt", "文本文件 (*.txt)", None)
        elif key == "requirements":
            default, filt, writer = (
                f"requirements_{version}_{stamp}.txt", "文本文件 (*.txt)", None)
        elif key == "yaml":
            default, filt, writer = (
                f"environment_{version}_{stamp}.yml", "YAML 文件 (*.yml *.yaml)", None)
        elif key == "dot":
            default, filt, writer = (
                f"deps_{version}_{stamp}.dot", "Graphviz DOT (*.dot)", None)
        elif key == "licenses":
            default, filt, writer = (
                f"许可证汇总_{version}_{stamp}.txt", "文本文件 (*.txt)", None)
        else:
            return

        path, _ = QFileDialog.getSaveFileName(self, "导出", default, filt)
        if not path:
            return
        try:
            if key == "report":
                exporter.export_report(self._analysis, path)
            elif key == "requirements":
                exporter.export_requirements(snapshot, path)
            elif key == "yaml":
                exporter.export_conda_yaml(
                    snapshot, path, name=f"py{version.replace('.', '')}")
            elif key == "dot":
                exporter.export_dot(self._analysis, path, only_problems=True)
            elif key == "licenses":
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(licenses.build_license_text(snapshot))
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"无法写入文件: {exc}")
            return
        QMessageBox.information(self, "导出成功", f"文件已保存到:\n{path}")

    def _export_graph_image(self, fmt: str, base_name: str) -> None:
        """把依赖图渲染为 PNG / SVG。"""
        assert self._analysis is not None
        scene_rect = self.graph.sceneRect()
        if scene_rect.isEmpty():
            QMessageBox.information(self, "无内容", "依赖图为空, 无法导出。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出依赖图", f"{base_name}.{fmt}",
            "PNG 图片 (*.png)" if fmt == "png" else "SVG 矢量图 (*.svg)")
        if not path:
            return
        scene = self.graph.scene()
        try:
            if fmt == "png":
                size = scene_rect.size().toSize()
                # 留白 + 上限, 避免超大图内存暴涨
                width = min(max(size.width() + 80, 640), 8000)
                height = min(max(size.height() + 80, 480), 8000)
                image = self.graph.render_to_image(width, height)
                if not image.save(path, "PNG"):
                    raise OSError("图片编码失败")
            else:
                from PySide6.QtSvg import QSvgGenerator
                generator = QSvgGenerator()
                generator.setFileName(path)
                generator.setSize(scene_rect.size().toSize())
                generator.setViewBox(scene_rect)
                generator.setTitle("PyEnv Inspector 依赖图")
                painter = QPainter(generator)
                painter.setRenderHint(QPainter.Antialiasing)
                scene.render(painter, scene_rect, scene_rect)
                painter.end()
        except ImportError:
            QMessageBox.warning(
                self, "缺少模块",
                "当前构建不包含 QtSvg, 无法导出 SVG。请改用 PNG 或 DOT。")
            return
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出成功", f"依赖图已保存到:\n{path}")

