"""通用 UI 组件:FlowLayout、徽章、统计卡片、忙碌遮罩、省略标签、图标绘制。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QSizePolicy, QVBoxLayout,
    QWidget, QWidgetItem,
)

from .theme import Palette, status_color


# ---------------------------------------------------------------------------
# FlowLayout: 自适应换行的流式布局(官方示例移植)
# ---------------------------------------------------------------------------
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=4, spacing=14):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list[QWidgetItem] = []

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(),
                                  -margins.right(), -margins.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self.spacing()
            if next_x - self.spacing() > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self.spacing()
                next_x = x + hint.width() + self.spacing()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        # 高度从原 rect 顶算起(含上边距), 再补下边距
        return y + line_height - rect.y() + margins.bottom()


# ---------------------------------------------------------------------------
# 徽章 / 统计卡片 / 省略标签
# ---------------------------------------------------------------------------
def make_badge(text: str, variant: str = "muted", parent=None) -> QLabel:
    label = QLabel(text, parent)
    label.setProperty("variant", variant)
    label.setAlignment(Qt.AlignCenter)
    label.setAttribute(Qt.WA_StyledBackground, True)
    return label


class StatCard(QFrame):
    """统计卡片:左侧色条 + 大数字 + 标签。"""

    def __init__(self, label: str, value: str = "0", variant: str = "info",
                 tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setToolTip(tooltip or label)
        self._variant = variant

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 16, 12)
        layout.setSpacing(12)

        bar = QFrame(self)
        bar.setFixedWidth(4)
        bar.setStyleSheet(
            f"background: {status_color(variant)}; border-radius: 2px;"
        )
        layout.addWidget(bar)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._value_label = QLabel(value)
        f = QFont()
        f.setPointSizeF(16)
        f.setBold(True)
        self._value_label.setFont(f)
        self._value_label.setStyleSheet(f"color: {Palette.text}; border: none;")
        caption = QLabel(label)
        caption.setStyleSheet(f"color: {Palette.text_muted}; border: none; font-size: 12px;")
        text_col.addWidget(self._value_label)
        text_col.addWidget(caption)
        layout.addLayout(text_col)

    def set_value(self, value: str) -> None:
        self._value_label.setText(str(value))


class ElidedLabel(QLabel):
    """超宽自动省略并悬浮显示全文的标签。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.setToolTip(text)
        self.setMinimumHeight(18)

    def setText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        super().setText(text)
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, Qt.ElideMiddle, max(self.width() - 2, 20))
        super().setText(elided)


# ---------------------------------------------------------------------------
# 忙碌遮罩(旋转指示)
# ---------------------------------------------------------------------------
class BusyOverlay(QWidget):
    """半透明忙碌遮罩, 悬浮于父控件之上显示进度文本。

    通过 eventFilter 监听父控件 Resize, 保证遮罩始终覆盖父控件。
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background: rgba(238, 241, 246, 200); border-radius: 12px;"
        )
        self._angle = 0
        self._text = "处理中…"

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self._spinner = _Spinner(self)
        self._spinner.setFixedSize(44, 44)
        self._label = QLabel(self._text)
        self._label.setStyleSheet(
            f"color: {Palette.text_muted}; font-size: 13px; background: transparent;"
        )
        self._label.setAlignment(Qt.AlignCenter)
        layout.addSpacing(120)
        layout.addWidget(self._spinner, 0, Qt.AlignHCenter)
        layout.addWidget(self._label, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        self.hide()

        if parent is not None:
            parent.installEventFilter(self)

    def _sync_geometry(self) -> None:
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._sync_geometry()
        return super().eventFilter(obj, event)

    def showEvent(self, event) -> None:
        self._sync_geometry()
        super().showEvent(event)

    def start(self, text: str = "处理中…") -> None:
        self._text = text
        self._label.setText(text)
        self._sync_geometry()
        self.raise_()
        self.show()
        self._angle = 0
        self._timer.start(40)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def set_text(self, text: str) -> None:
        self._text = text
        self._label.setText(text)

    def _tick(self) -> None:
        self._angle = (self._angle + 24) % 360
        self._spinner.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())


class _Spinner(QWidget):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(Palette.primary), 3.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        rect = QRect(4, 4, self.width() - 8, self.height() - 8)
        span = 100 * 16  # 100°
        start = -self.parent()._angle * 16 if self.parent() else 0
        painter.drawArc(rect, start, -span)
        painter.end()


# ---------------------------------------------------------------------------
# 自绘小图标
# ---------------------------------------------------------------------------
def draw_py_icon(painter: QPainter, rect: QRect, color: str) -> None:
    """绘制圆角方块 + "Py" 字样的解释器图标。"""
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(float(rect.x()), float(rect.y()),
                        float(rect.width()), float(rect.height()), 7.0, 7.0)
    painter.fillPath(path, QColor(color))
    painter.setPen(QColor("#ffffff"))
    f = QFont()
    f.setBold(True)
    f.setPointSizeF(max(rect.width() * 0.36, 7))
    painter.setFont(f)
    painter.drawText(rect, Qt.AlignCenter, "Py")


class IconLabel(QWidget):
    """小尺寸自绘图标(导航用)。"""

    def __init__(self, kind: str, size: int = 18, color: str = "#ffffff",
                 parent=None):
        super().__init__(parent)
        self._kind = kind
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(self._color))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        kind = self._kind
        if kind == "env":            # 环境: 同心圆
            painter.drawEllipse(2, 2, w - 4, h - 4)
            painter.drawEllipse(int(w * 0.3), int(h * 0.3), int(w * 0.4), int(h * 0.4))
        elif kind == "packages":     # 包: 层叠矩形
            painter.drawRect(3, int(h * 0.55), w - 6, int(h * 0.3))
            painter.drawRect(int(w * 0.2), int(h * 0.25), int(w * 0.6), int(h * 0.22))
        elif kind == "graph":        # 分析: 三节点网络
            painter.drawEllipse(1, 1, 5, 5)
            painter.drawEllipse(w - 6, 1, 5, 5)
            painter.drawEllipse(int(w / 2) - 3, h - 7, 6, 6)
            painter.drawLine(6, 5, w - 7, 5)
            painter.drawLine(5, 6, int(w / 2) - 1, h - 6)
            painter.drawLine(w - 5, 6, int(w / 2) + 1, h - 6)
        elif kind == "demo":         # 演示: 播放三角
            painter.drawPolygon([
                QPoint(4, 2), QPoint(w - 4, int(h / 2)), QPoint(4, h - 2),
            ])
        painter.end()


class SearchBox(QLineEdit):
    """带占位提示的搜索框。"""

    textSubmitted = Signal(str)

    def __init__(self, placeholder: str = "搜索…", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setFixedWidth(240)
        self.returnPressed.connect(
            lambda: self.textSubmitted.emit(self.text()))
