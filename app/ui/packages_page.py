"""页面二:包列表与详情(目标环境已安装的包)。"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, Qt, Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSplitter, QStyledItemDelegate, QStyle,
    QTableView, QVBoxLayout, QWidget,
)

from ..core.models import AnalysisResult, DepEdge, EdgeStatus, PackageInfo
from .theme import Palette
from .widgets import ElidedLabel, make_badge

_COLUMNS = ["包名", "当前版本", "依赖数", "被依赖数", "状态"]

_STATUS_TEXT = {
    "conflict": "版本冲突",
    "missing": "依赖缺失",
    "unknown": "存在未知项",
    "ok": "正常",
}


def _package_status(pkg: PackageInfo) -> str:
    if not pkg.installed:
        return "missing"   # 依赖缺失产生的占位幽灵包
    if pkg.has_conflict:
        return "conflict"
    if pkg.has_missing:
        return "missing"
    if pkg.has_unknown:
        return "unknown"
    if any(e.status == EdgeStatus.VERSION_CONFLICT for e in pkg.incoming):
        return "conflict"
    return "ok"


class PackageTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[PackageInfo] = []
        self._full: list[PackageInfo] = []

    def load(self, rows: list[PackageInfo]) -> None:
        self.beginResetModel()
        self._full = rows
        self._rows = rows
        self.endResetModel()

    def filter(self, text: str, status: str) -> None:
        text = text.strip().lower()
        self.beginResetModel()
        result = []
        for p in self._full:
            if text and text not in p.name.lower() and text not in p.version.lower():
                continue
            if status != "all" and _package_status(p) != status:
                continue
            result.append(p)
        self._rows = result
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def total_count(self) -> int:
        """未筛选的全量包数(供显示"X / Y")。"""
        return len(self._full)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return _COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        pkg = self._rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return pkg.name
            if col == 1:
                return pkg.version or ("未安装" if not pkg.installed else "?")
            if col == 2:
                return str(len(pkg.outgoing))
            if col == 3:
                return str(len(pkg.incoming))
            if col == 4:
                return _STATUS_TEXT[_package_status(pkg)]
        elif role == Qt.UserRole:
            return pkg.key
        elif role == Qt.ForegroundRole and col == 4:
            status = _package_status(pkg)
            color = {
                "conflict": Palette.error,
                "missing": Palette.warn,
                "unknown": Palette.text_muted,
                "ok": Palette.ok,
            }[status]
            return QColor(color)
        elif role == Qt.TextAlignmentRole and col in (2, 3):
            return int(Qt.AlignCenter)
        return None

    def package_at(self, row: int) -> PackageInfo | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class StatusDotDelegate(QStyledItemDelegate):
    """状态列:彩色圆点 + 文字。"""

    _COLORS = {
        "conflict": Palette.error,
        "missing": Palette.warn,
        "unknown": Palette.text_muted,
        "ok": Palette.ok,
    }

    def paint(self, painter, option, index):
        if index.column() != 4:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        # 先绘制选中/交替行背景, 保持与其他列一致
        option.widget.style().drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter,
            option.widget)
        rect = option.rect
        text = index.data(Qt.DisplayRole) or ""
        model = index.model()
        pkg = model.package_at(index.row())
        status = _package_status(pkg) if pkg else "ok"
        color = QColor(self._COLORS.get(status, Palette.ok))

        y = rect.center().y()
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect.left() + 12, int(y - 4), 8, 8)
        painter.setPen(QColor(Palette.text))
        painter.setFont(option.font)
        painter.drawText(
            rect.adjusted(28, 0, 0, 0), int(Qt.AlignVCenter | Qt.AlignLeft), text)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if index.column() == 4:
            # 补偿圆点 + 文字右移占用的宽度
            size.setWidth(size.width() + 30)
        return size


class _EdgeRow(QFrame):
    """详情面板中的一条依赖行。"""

    _META = {
        EdgeStatus.OK: ("ok", "✓"),
        EdgeStatus.VERSION_CONFLICT: ("error", "✗"),
        EdgeStatus.MISSING: ("warn", "✗"),
        EdgeStatus.UNKNOWN: ("muted", "?"),
        EdgeStatus.INACTIVE: ("muted", "–"),
    }

    def __init__(self, edge: DepEdge, outgoing: bool, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        variant, mark = self._META.get(edge.status, ("muted", "?"))
        mark_label = QLabel(mark)
        mark_label.setFixedWidth(14)
        mark_label.setStyleSheet(
            f"color: {Palette.error if variant == 'error' else (Palette.warn if variant == 'warn' else (Palette.ok if variant == 'ok' else Palette.text_faint))};"
            f" font-weight: 700;"
        )
        layout.addWidget(mark_label)

        arrow = "→" if outgoing else "←"
        name = QLabel(f"{arrow} {edge.target_display if outgoing else edge.source_display}")
        name.setStyleSheet(f"color: {Palette.text}; font-size: 12px;")
        layout.addWidget(name)
        layout.addStretch(1)

        spec = edge.spec or "任意版本"
        spec_label = QLabel(spec if len(spec) < 30 else spec[:28] + "…")
        spec_label.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 11px;"
            f" font-family: Consolas, monospace;"
        )
        spec_label.setToolTip(f"{edge.message}\n约束: {spec or '无'}"
                              + (f"\n标记: {edge.marker}" if edge.marker else ""))
        layout.addWidget(spec_label)


class PackageDetailPanel(QWidget):
    """右侧详情面板:选中包的依赖与被依赖(内容超出时可滚动)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self._title = QLabel("包详情")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSizeF(13)
        self._title.setFont(tf)
        self._title.setStyleSheet(f"color: {Palette.text};")
        layout.addWidget(self._title)

        self._name = QLabel("—")
        nf = QFont()
        nf.setBold(True)
        nf.setPointSizeF(12)
        self._name.setFont(nf)
        self._name.setStyleSheet(f"color: {Palette.text};")
        layout.addWidget(self._name)

        meta_row = QHBoxLayout()
        self._version_badge = make_badge("—", "muted")
        self._status_badge = make_badge("—", "muted")
        meta_row.addWidget(self._version_badge)
        meta_row.addWidget(self._status_badge)
        meta_row.addStretch(1)
        layout.addLayout(meta_row)

        self._path_note = QLabel("")
        self._path_note.setStyleSheet(f"color: {Palette.text_faint}; font-size: 11px;")
        layout.addWidget(self._path_note)

        self._out_title = QLabel("依赖 (0)")
        self._out_title.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px; font-weight: 700;"
            " border-top: 1px solid #e3e7ef; padding-top: 8px;"
        )
        layout.addWidget(self._out_title)
        self._out_list = QVBoxLayout()
        self._out_list.setSpacing(0)
        layout.addLayout(self._out_list)
        layout.addSpacing(6)

        self._in_title = QLabel("被依赖 (0)")
        self._in_title.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px; font-weight: 700;"
        )
        layout.addWidget(self._in_title)
        self._in_list = QVBoxLayout()
        self._in_list.setSpacing(0)
        layout.addLayout(self._in_list)
        layout.addStretch(1)

    def show_package(self, pkg: PackageInfo | None, interpreter_path: str = "") -> None:
        # 清空旧内容
        for lst in (self._out_list, self._in_list):
            while lst.count():
                item = lst.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        self._path_note.setText("")

        if pkg is None:
            self._name.setText("—")
            self._version_badge.setText("—")
            self._status_badge.setText("—")
            self._out_title.setText("依赖 (0)")
            self._in_title.setText("被依赖 (0)")
            return

        self._name.setText(pkg.name)
        if pkg.installed:
            self._version_badge.setText(f"v{pkg.version or '?'}")
        else:
            self._version_badge.setText("未安装")
        status = _package_status(pkg)
        variant_map = {"conflict": "error", "missing": "warn",
                       "unknown": "muted", "ok": "ok"}
        self._status_badge.setText(_STATUS_TEXT[status])
        # 重建 badge 以刷新样式
        self._status_badge.setProperty("variant", variant_map[status])
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        if interpreter_path:
            site_hint = interpreter_path
            self._path_note.setText(f"环境: {site_hint}")

        self._out_title.setText(f"依赖 ({len(pkg.outgoing)})")
        for edge in pkg.outgoing:
            self._out_list.addWidget(_EdgeRow(edge, outgoing=True))
        self._in_title.setText(f"被依赖 ({len(pkg.incoming)})")
        for edge in pkg.incoming:
            self._in_list.addWidget(_EdgeRow(edge, outgoing=False))


class PackagesPage(QWidget):
    """包列表页。"""

    package_activated = Signal(str)   # 双击包名 → 跳到分析图定位
    reload_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._analysis: AnalysisResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        # 环境信息条
        env_card = QFrame()
        env_card.setObjectName("card")
        env_layout = QHBoxLayout(env_card)
        env_layout.setContentsMargins(16, 12, 16, 12)
        env_layout.setSpacing(12)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self._env_title = QLabel("尚未加载环境")
        ef = QFont()
        ef.setBold(True)
        ef.setPointSizeF(13)
        self._env_title.setFont(ef)
        self._env_title.setStyleSheet(f"color: {Palette.text};")
        self._env_path = ElidedLabel("请先在「解释器」页选择并加载一个 Python 环境")
        self._env_path.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 11px;"
            " font-family: Consolas, monospace;"
        )
        info_col.addWidget(self._env_title)
        info_col.addWidget(self._env_path)
        env_layout.addLayout(info_col)
        env_layout.addStretch(1)
        self._env_badge = make_badge("—", "muted")
        env_layout.addWidget(self._env_badge)
        self.reload_button = QPushButton("重新加载")
        env_layout.addWidget(self.reload_button)
        root.addWidget(env_card)

        # 过滤行
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索包名或版本…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(260)
        filter_row.addWidget(self.search_edit)

        self.status_filter = QComboBox()
        for key, text in (
            ("all", "全部状态"), ("conflict", "版本冲突"),
            ("missing", "依赖缺失"), ("unknown", "存在未知项"),
            ("ok", "正常"),
        ):
            self.status_filter.addItem(text, key)
        self.status_filter.setFixedWidth(140)
        filter_row.addWidget(self.status_filter)
        filter_row.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        filter_row.addWidget(self.count_label)
        root.addLayout(filter_row)

        # 表格 + 详情
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        self.table = QTableView()
        self.model = PackageTableModel(self)
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(4, StatusDotDelegate(self.table))
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1,):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        for col in (2, 3, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setShowGrid(False)
        splitter.addWidget(self.table)

        self.detail = PackageDetailPanel()
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([800, 340])
        root.addWidget(splitter, 1)

        # 信号
        self.table.clicked.connect(self._on_row_clicked)
        self.table.selectionModel().currentRowChanged.connect(
            self._on_current_row_changed)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.status_filter.currentIndexChanged.connect(self._apply_filter)
        self.reload_button.clicked.connect(self.reload_requested.emit)

    # -- API -----------------------------------------------------------------
    def load_analysis(self, analysis: AnalysisResult) -> None:
        self._analysis = analysis
        interp = analysis.snapshot.interpreter
        self._env_title.setText(
            f"{interp.display_name} · {len(analysis.packages)} 个包(含缺失占位)")
        self._env_path.setText(interp.path)
        self._env_badge.setText(interp.source_label)
        self._env_badge.setProperty("variant", "info" if not interp.is_venv else "muted")
        self._env_badge.style().unpolish(self._env_badge)
        self._env_badge.style().polish(self._env_badge)
        rows = [p for p in analysis.packages.values()]
        rows.sort(key=lambda p: (not p.is_problematic, p.name.lower()))
        self.model.load(rows)
        # 统一走筛选入口, 保持搜索框/状态筛选与表格内容一致
        self._apply_filter()
        if self.model.rowCount():
            self.table.selectRow(0)   # 触发 currentRowChanged → 刷新详情
        else:
            self.detail.show_package(None)

    # -- 内部 -----------------------------------------------------------------
    def _apply_filter(self, *_) -> None:
        self.model.filter(
            self.search_edit.text(), self.status_filter.currentData()
        )
        self._update_count()

    def _update_count(self) -> None:
        self.count_label.setText(
            f"显示 {self.model.rowCount()} / {self.model.total_count()} 个包")

    def _on_row_clicked(self, index) -> None:
        pkg = self.model.package_at(index.row()) if index.isValid() else None
        if pkg is not None and self._analysis is not None:
            self.detail.show_package(pkg, self._analysis.snapshot.interpreter.path)
        else:
            self.detail.show_package(None)

    def _on_current_row_changed(self, current, _previous) -> None:
        """键盘上下键切换选中行时同样刷新详情。"""
        self._on_row_clicked(current)

    def _on_row_double_clicked(self, index) -> None:
        pkg = self.model.package_at(index.row())
        if pkg is not None:
            self.package_activated.emit(pkg.key)
