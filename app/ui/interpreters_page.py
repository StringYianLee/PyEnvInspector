"""页面一:Python 解释器发现与选择(卡片式列表)。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ..core.models import InterpreterInfo
from .theme import Palette
from .widgets import ElidedLabel, FlowLayout, IconLabel, make_badge

# 不同来源的图标底色
_SOURCE_COLORS = {
    "launcher": Palette.primary,
    "registry": "#4c8d4c",
    "conda": "#3aa0a8",
    "store": "#5a6acf",
    "common": "#5f6b83",
    "path": "#7c66c9",
}


class _PyIcon(QWidget):
    """解释器图标(圆角方块 + Py)。"""

    def __init__(self, color: str, size: int = 40, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._color))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 9, 9)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setBold(True)
        font.setPointSizeF(self.width() * 0.34)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "Py")
        painter.end()


class InterpreterCard(QFrame):
    """单张解释器卡片。"""

    clicked = Signal(object)          # InterpreterInfo
    double_clicked = Signal(object)

    def __init__(self, info: InterpreterInfo, parent=None):
        super().__init__(parent)
        self.info = info
        self._selected = False
        self.setObjectName("interpCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(272)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._apply_style()
        self.setToolTip(
            f"{info.display_name}\n路径: {info.path}\n"
            f"来源: {info.source_label}\n实现: {info.implementation or '?'}"
            + (f"\n基础环境: {info.base_prefix}" if info.is_venv else "")
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(12)

        color = _SOURCE_COLORS.get(info.source, Palette.primary)
        if info.is_venv:
            color = "#9254de"
        layout.addWidget(_PyIcon(color, 40))

        right = QVBoxLayout()
        right.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        ver_label = QLabel(f"Python {info.version or '?'}")
        f = QFont()
        f.setBold(True)
        f.setPointSizeF(12.5)
        ver_label.setFont(f)
        ver_label.setStyleSheet(f"color: {Palette.text};")
        title_row.addWidget(ver_label)
        title_row.addStretch(1)
        right.addLayout(title_row)

        meta = QLabel(
            f"{(info.implementation or 'python').capitalize()}"
            f"{' · ' + info.arch if info.arch else ''}"
        )
        meta.setStyleSheet(f"color: {Palette.text_muted}; font-size: 11px;")
        right.addWidget(meta)

        path_label = ElidedLabel(info.path)
        path_label.setStyleSheet(
            f"color: {Palette.text_faint}; font-size: 11px; font-family: Consolas, monospace;"
        )
        right.addWidget(path_label)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        badge = make_badge(info.source_label,
                           "info" if not info.is_venv else "muted")
        badge_row.addWidget(badge)
        if info.is_venv:
            badge_row.addWidget(make_badge("venv", "muted"))
        if info.env_name:
            badge_row.addWidget(make_badge(f"conda env: {info.env_name}", "info"))
        if info.tag:
            badge_row.addWidget(make_badge(f"py -{info.tag}", "muted"))
        badge_row.addStretch(1)
        right.addLayout(badge_row)

        layout.addLayout(right)

    def _apply_style(self) -> None:
        border = Palette.primary if self._selected else Palette.border
        border_w = 2 if self._selected else 1
        shadow = f"background: {Palette.primary_soft};" if self._selected else ""
        self.setStyleSheet(
            f"QFrame#interpCard {{ background: {Palette.surface};"
            f" border: {border_w}px solid {border}; border-radius: 12px; {shadow} }}"
            f"QFrame#interpCard:hover {{ border-color: {Palette.primary}; }}"
        )

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self._apply_style()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.info)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit(self.info)
        super().mouseDoubleClickEvent(event)


class InterpretersPage(QWidget):
    """解释器列表页。"""

    interpreter_selected = Signal(object)    # 选中(单击)
    interpreter_activated = Signal(object)   # 确认(双击或按钮)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._cards: list[InterpreterCard] = []
        self._current: InterpreterInfo | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        # 顶部标题行
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Python 解释器")
        tf = QFont()
        tf.setBold(True)
        tf.setPointSizeF(15)
        title.setFont(tf)
        title.setStyleSheet(f"color: {Palette.text};")
        subtitle = QLabel("自动检索本机已安装的全部 Python 版本, 单击选择, 双击直接加载包列表")
        subtitle.setStyleSheet(f"color: {Palette.text_muted}; font-size: 12px;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch(1)
        self.rescan_button = QPushButton("重新扫描")
        self.rescan_button.setProperty("variant", "primary")
        header.addWidget(self.rescan_button)
        root.addLayout(header)

        # 状态行
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 12px;"
        )
        root.addWidget(self.status_label)

        # 卡片滚动区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._flow = FlowLayout(container, margin=2, spacing=16)
        container.setLayout(self._flow)
        self._scroll.setWidget(container)
        root.addWidget(self._scroll, 1)

        # 底部操作
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet(f"color: {Palette.text_faint}; font-size: 12px;")
        bottom.addWidget(self.hint_label)
        bottom.addSpacing(10)
        self.load_button = QPushButton("查看已安装包  →")
        self.load_button.setProperty("variant", "primary")
        self.load_button.setEnabled(False)
        bottom.addWidget(self.load_button)
        root.addLayout(bottom)

        self.load_button.clicked.connect(self._emit_activate)

    # -- API -----------------------------------------------------------------
    def set_scanning(self, on: bool, text: str = "") -> None:
        self.rescan_button.setEnabled(not on)
        self.status_label.setText(text)

    def show_interpreters(self, interpreters: list[InterpreterInfo]) -> None:
        for card in self._cards:
            self._flow.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._current = None
        self.load_button.setEnabled(False)
        self.hint_label.setText("")

        for info in interpreters:
            card = InterpreterCard(info)
            card.clicked.connect(self._on_card_clicked)
            card.double_clicked.connect(self._on_card_activated)
            self._flow.addWidget(card)
            self._cards.append(card)

        count = len(interpreters)
        self.status_label.setText(
            f"共发现 {count} 个可用解释器"
            if count else "未发现任何可用的 Python 解释器, 可点击「重新扫描」重试"
        )

    # -- 内部 -----------------------------------------------------------------
    def _on_card_clicked(self, info: InterpreterInfo) -> None:
        self._current = info
        for card in self._cards:
            card.set_selected(card.info is info)
        self.load_button.setEnabled(True)
        self.hint_label.setText("")
        self.interpreter_selected.emit(info)

    def _on_card_activated(self, info: InterpreterInfo) -> None:
        self._on_card_clicked(info)
        self.interpreter_activated.emit(info)

    def _emit_activate(self) -> None:
        if self._current is not None:
            self.interpreter_activated.emit(self._current)
