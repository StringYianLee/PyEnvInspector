"""依赖图可视化(QGraphicsView)。

- ``NodeItem``: 包节点卡片(名称 + 版本), 按状态着色:
  正常=白底细边框 / 冲突=红 / 缺失(幽灵)=橙虚线 / 未知=灰虚线
- ``EdgeItem``: 依赖边(贝塞尔曲线 + 箭头):
  正常=浅灰细线, 冲突=红色粗线, 缺失=橙色虚线, 未知=灰色点线
- ``GraphController``: 场景内容管理, 提供悬停邻域高亮与冲突链条聚焦
- ``DependencyGraphView``: 滚轮缩放(光标锚定)、拖拽平移、适应视图、
  搜索定位脉冲高亮。
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import (
    QAbstractAnimation, QPointF, QRectF, Qt, QTimer, QObject, QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath,
    QPainterPathStroker, QPen, QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView, QWidget,
)

from ..core.models import AnalysisResult, DepEdge, EdgeStatus, PackageInfo
from .theme import Palette

# 动效参数集中定义
ENTRANCE_NODE_DURATION = 380.0   # 单节点入场时长 ms
ENTRANCE_STAGGER_MAX = 12.0      # 相邻节点错峰延迟上限 ms
ENTRANCE_STAGGER_BUDGET = 900.0  # 错峰总预算 ms
ENTRANCE_NODE_LIMIT = 350        # 超过此规模跳过入场动画(性能保护)
HOVER_FADE_MS = 160              # 悬停/聚焦淡入淡出时长
VIEWPORT_MOVE_MS = 240           # 视口平移/适配动画时长
FLOW_INTERVAL_MS = 33            # 冲突边流动帧间隔(~30fps)
FLOW_EDGE_LIMIT = 120            # 参与流动动画的边数上限


def _ease_out_cubic(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1.0 - (1.0 - t) ** 3


# ---------------------------------------------------------------------------
# 节点
# ---------------------------------------------------------------------------
class NodeItem(QGraphicsItem):
    """包节点卡片(名称+版本; 悬停平滑放大, 支持入场缩放动画)。"""

    NODE_H = 46.0
    PAD_X = 14.0
    HOVER_SCALE = 1.06
    NAME_MAX_CHARS = 24

    def __init__(self, pkg: PackageInfo, parent=None):
        super().__init__(parent)
        self.pkg = pkg
        self._edges: list["EdgeItem"] = []
        self._hovered = False
        self._pulsing = False
        self._base_pos = QPointF(0.0, 0.0)   # 布局目标位置(动画使用)
        self._scale = 1.0
        self._scale_anim: QVariantAnimation | None = None
        self._entrance_index = 0             # 入场动画序号(build 时赋值)

        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSizeF(9.2)
        self._name_font = name_font
        ver_font = QFont()
        ver_font.setPointSizeF(8.0)
        self._ver_font = ver_font

        fm = QFontMetrics(name_font)
        raw_name = pkg.name
        self._display_name = (
            fm.elidedText(raw_name, Qt.ElideRight,
                          self.NAME_MAX_CHARS * fm.horizontalAdvance("n"))
            if len(raw_name) > self.NAME_MAX_CHARS else raw_name)
        text_w = max(
            fm.horizontalAdvance(self._display_name),
            QFontMetrics(ver_font).horizontalAdvance(self._version_text()),
        )
        self._w = max(104.0, text_w + 2 * self.PAD_X)

        status_text = {
            "conflict": "存在版本冲突",
            "missing": "依赖缺失",
            "unknown": "存在未知项",
        }.get(self._status_kind(), "正常")
        self.setToolTip(
            f"{raw_name} {self._version_text()}\n状态: {status_text}")

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        # 不用 DeviceCoordinateCache: 视图缩放时它会让**所有节点**的缓存
        # 同时失效并重建(每节点重画位图), 滚轮缩放因此卡顿;
        # 本节点的绘制(圆角矩形+两行文字)本身极廉价, 直绘更优。
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.setZValue(2.0)

    # -- 属性 -------------------------------------------------------------
    def _version_text(self) -> str:
        if not self.pkg.installed:
            return "未安装"
        return self.pkg.version or "?"

    @property
    def width(self) -> float:
        return self._w

    @property
    def height(self) -> float:
        return self.NODE_H

    @property
    def base_pos(self) -> QPointF:
        """布局给出的目标位置(动画起点/终点基准)。"""
        return self._base_pos

    def register_edge(self, edge: "EdgeItem") -> None:
        self._edges.append(edge)

    @property
    def edges(self) -> list["EdgeItem"]:
        return self._edges

    # -- 缩放(围绕卡片中心; 供悬停与入场动画使用) -----------------------------
    def apply_scale(self, s: float) -> None:
        s = min(max(s, 0.05), 1.35)
        self._scale = s
        cx, cy = self._w / 2.0, self.NODE_H / 2.0
        t = QTransform()
        t.translate(cx * (1.0 - s), cy * (1.0 - s))
        t.scale(s, s)
        self.setTransform(t)

    def animate_hover_scale(self, enter: bool) -> None:
        target = self.HOVER_SCALE if enter else 1.0
        if self._scale_anim is not None:
            # 先解除完成回调并显式停止; DeleteWhenStopped 会销毁 C++ 对象,
            # 旧动画对象不可再次 stop/引用
            try:
                self._scale_anim.stop()
            except RuntimeError:
                pass
            self._scale_anim = None
        anim = QVariantAnimation(self)
        anim.setStartValue(self._scale)
        anim.setEndValue(target)
        anim.setDuration(120)
        anim.valueChanged.connect(self.apply_scale)
        anim.finished.connect(lambda: self.apply_scale(target))
        anim.finished.connect(
            lambda: setattr(self, "_scale_anim", None))
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._scale_anim = anim

    # -- 视觉状态 -----------------------------------------------------------
    def set_pulsing(self, on: bool) -> None:
        if self._pulsing != on:
            self._pulsing = on
            self.update()

    def _status_kind(self) -> str:
        p = self.pkg
        if not p.installed:
            return "missing"
        if p.has_conflict:
            return "conflict"
        if p.has_missing:
            return "missing"
        if p.has_unknown:
            return "unknown"
        if any(e.status == EdgeStatus.VERSION_CONFLICT for e in p.incoming):
            return "conflict"
        return "normal"

    # -- 绘制 ---------------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return QRectF(-2.0, -2.0, self._w + 4.0, self.NODE_H + 4.0)

    def paint(self, painter: QPainter, option,
              widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.Antialiasing)
        kind = self._status_kind()
        rect = QRectF(0.0, 0.0, self._w, self.NODE_H)

        colors = {
            "normal": (Palette.surface, Palette.node_normal_border, Palette.text),
            "conflict": (Palette.error_soft, Palette.edge_conflict, "#b32836"),
            "missing": (Palette.warn_soft, Palette.edge_missing, "#a86508"),
            "unknown": (Palette.surface_alt, Palette.text_faint, Palette.text_muted),
        }
        bg, border, text = colors[kind]

        path = QPainterPath()
        path.addRoundedRect(rect, 9.0, 9.0)
        painter.fillPath(path, QBrush(QColor(bg)))

        pen = QPen(QColor(border))
        if kind in ("missing", "unknown"):
            pen.setStyle(Qt.DashLine)
        pen.setWidthF(2.0 if kind in ("conflict", "missing") else 1.3)
        if self._hovered or self._pulsing:
            pen.setColor(QColor(Palette.primary))
            pen.setStyle(Qt.SolidLine)
            pen.setWidthF(2.4)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(QColor(text))
        painter.setFont(self._name_font)
        painter.drawText(QRectF(self.PAD_X, 5.0, self._w - 2 * self.PAD_X, 20.0),
                         Qt.AlignVCenter, self._display_name)

        ver_color = "#c2802a" if kind == "missing" else Palette.text_muted
        painter.setPen(QColor(ver_color))
        painter.setFont(self._ver_font)
        painter.drawText(QRectF(self.PAD_X, 24.0, self._w - 2 * self.PAD_X, 17.0),
                         Qt.AlignVCenter, self._version_text())

    # -- 交互 ---------------------------------------------------------------
    def _controller(self):
        scene = self.scene()
        return getattr(scene, "graph_controller", None)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        ctrl = self._controller()
        if ctrl is not None and not ctrl._animating:
            self.animate_hover_scale(True)
        if ctrl:
            ctrl.on_node_hover(self, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        ctrl = self._controller()
        if ctrl is not None and not ctrl._animating:
            self.animate_hover_scale(False)
        if ctrl:
            ctrl.on_node_hover(self, False)
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        ctrl = self._controller()
        if ctrl:
            ctrl.node_double_clicked.emit(self.pkg.key)
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self._edges:
                edge.update_path()
        return super().itemChange(change, value)


# ---------------------------------------------------------------------------
# 边
# ---------------------------------------------------------------------------
class EdgeItem(QGraphicsPathItem):
    """依赖边: source → target, 状态着色, 悬停/聚焦时显示约束文本。"""

    def __init__(self, edge: DepEdge, source: NodeItem, target: NodeItem, parent=None):
        super().__init__(parent)
        self.edge = edge
        self.source_item = source
        self.target_item = target
        self._show_label = False
        self._highlight = False
        self.is_flowing = (edge.status == EdgeStatus.VERSION_CONFLICT)
        self._flow_phase = 0.0
        self._curve_path = QPainterPath()
        self._arrow_path = QPainterPath()

        self.setAcceptHoverEvents(True)
        self.setZValue(1.0)
        self.setPen(self._make_pen())
        source.register_edge(self)
        target.register_edge(self)

    def _make_pen(self) -> QPen:
        status = self.edge.status
        if status == EdgeStatus.VERSION_CONFLICT:
            pen = QPen(QColor(Palette.edge_conflict), 2.6)
            # 冲突边: 流动虚线(由 FlowClock 推进 dashOffset), 视觉上"有问题在流动"
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern([7.0, 4.5])
        elif status == EdgeStatus.MISSING:
            pen = QPen(QColor(Palette.edge_missing), 2.0)
            pen.setStyle(Qt.DashLine)
        elif status == EdgeStatus.UNKNOWN:
            pen = QPen(QColor(Palette.text_faint), 1.6)
            pen.setStyle(Qt.DotLine)
        else:
            pen = QPen(QColor(Palette.edge_normal), 1.4)
        pen.setCapStyle(Qt.RoundCap)
        return pen

    def advance_flow(self, phase: float) -> None:
        """推进流动虚线相位(由 GraphController 的共享时钟调用)。

        性能关键: 只记录相位并请求重绘, **不调用 setPen** ——
        QGraphicsPathItem.setPen 会触发 prepareGeometryChange + 场景
        BSP 索引更新, 30fps × N 条边持续压垮主线程。
        dashOffset 在 paint() 时应用到画笔副本, 几何与索引零成本。
        """
        if self._flow_phase != phase:
            self._flow_phase = phase
            self.update()

    def set_highlight(self, on: bool) -> None:
        if self._highlight == on:
            return
        self._highlight = on
        self._show_label = on
        # 标签宽度随约束文本变化, 几何变化前必须通知场景
        self.prepareGeometryChange()
        if on:
            pen = self._make_pen()
            pen.setWidthF(max(pen.widthF() + 0.8, 3.0))
            self.setPen(pen)
            self.setZValue(2.5)
        else:
            self.setPen(self._make_pen())
            self.setZValue(1.0)
        self.update_path()

    def set_dimmed(self, on: bool) -> None:
        self.setOpacity(0.10 if on else 1.0)

    # -- 几何 ---------------------------------------------------------------
    @staticmethod
    def _clip_to_rect(center: QPointF, w: float, h: float,
                      toward: QPointF) -> QPointF:
        """从矩形中心向 toward 方向的射线与矩形边界的交点。"""
        dx = toward.x() - center.x()
        dy = toward.y() - center.y()
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return center
        half_w, half_h = w / 2.0 + 4.0, h / 2.0 + 4.0
        scale = min(
            half_w / abs(dx) if abs(dx) > 1e-9 else math.inf,
            half_h / abs(dy) if abs(dy) > 1e-9 else math.inf,
        )
        return QPointF(center.x() + dx * scale, center.y() + dy * scale)

    def update_path(self) -> None:
        self.prepareGeometryChange()
        s_center = self.source_item.pos() + QPointF(
            self.source_item.width / 2.0, self.source_item.height / 2.0)
        t_center = self.target_item.pos() + QPointF(
            self.target_item.width / 2.0, self.target_item.height / 2.0)

        start = self._clip_to_rect(
            s_center, self.source_item.width, self.source_item.height, t_center)
        end = self._clip_to_rect(
            t_center, self.target_item.width, self.target_item.height, s_center)

        direction = QPointF(end.x() - start.x(), end.y() - start.y())
        length = max(math.hypot(direction.x(), direction.y()), 1e-3)
        ux, uy = direction.x() / length, direction.y() / length
        arrow_len = 11.0
        tip = QPointF(end.x(), end.y())
        base = QPointF(end.x() - ux * arrow_len, end.y() - uy * arrow_len)

        # 贝塞尔曲线: 中点法向偏移, 视觉更柔和。
        # 弯曲方向按边标识奇偶交替, 避免同源/汇聚的多条边完全重叠
        mid = QPointF((start.x() + base.x()) / 2.0, (start.y() + base.y()) / 2.0)
        offset = min(length * 0.10, 34.0)
        if (sum(ord(c) for c in f"{self.edge.source_key}->{self.edge.target_key}")
                % 2) == 1:
            offset = -offset
        ctrl = QPointF(mid.x() - uy * offset, mid.y() + ux * offset)

        path = QPainterPath(start)
        path.quadTo(ctrl, base)

        # 箭头三角
        side = 4.8
        left = QPointF(base.x() - uy * side, base.y() + ux * side)
        right = QPointF(base.x() + uy * side, base.y() - ux * side)
        path.moveTo(tip)
        path.lineTo(left)
        path.lineTo(right)
        path.lineTo(tip)
        self.setPath(path)

        # 预拆分缓存: paint 是流动边 30fps 热路径, 不重复解析 path 元素
        curve = QPainterPath(start)
        curve.quadTo(ctrl, base)
        self._curve_path = curve
        arrow = QPainterPath(tip)
        arrow.lineTo(left)
        arrow.lineTo(right)
        arrow.closeSubpath()
        self._arrow_path = arrow

    def _label_text(self) -> str:
        e = self.edge
        if e.status == EdgeStatus.MISSING:
            return f"{e.spec or '任意版本'} → 未安装"
        return e.spec or "无约束"

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        # 使用 update_path 预构建的缓存路径(流动边 30fps 热路径)
        pen = self.pen()
        if self.is_flowing:
            # 流动相位在此处应用(画笔副本), 避免 setPen 引发几何重算
            pen = QPen(pen)
            pen.setDashOffset(-self._flow_phase)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self._curve_path)

        # 箭头填充
        painter.setBrush(self.pen().color())
        painter.drawPath(self._arrow_path)

        # 约束标签
        if self._show_label:
            label = self._label_text()
            font = QFont()
            font.setPointSizeF(8.0)
            painter.setFont(font)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(label)
            mid = self._curve_path.pointAtPercent(0.45)
            rect = QRectF(mid.x() - tw / 2 - 6, mid.y() - 26, tw + 12, 16)
            bg = QColor("#2b3245")
            bg.setAlpha(230)
            painter.setBrush(bg)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 5.0, 5.0)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect, Qt.AlignCenter, label)

    def boundingRect(self) -> QRectF:
        # 约束标签以路径 45% 处为中心, 宽度随文本变化, 双侧各预留 90px
        return super().boundingRect().adjusted(-90, -30, 90, 14)

    # -- 交互 ---------------------------------------------------------------
    def hoverEnterEvent(self, event):
        self._show_label = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self._highlight:
            self._show_label = False
        self.update()
        super().hoverLeaveEvent(event)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF() * 2.6, 9.0))
        return stroker.createStroke(self.path())


# ---------------------------------------------------------------------------
# 动画器
# ---------------------------------------------------------------------------
class _EntranceAnimator(QObject):
    """节点错峰入场: 缩放 0.55→1 + 透明度 0→1, 边随两端节点渐入。

    性能要点:
    - 单个 QVariantAnimation 驱动全部元素(一帧一次批量更新);
    - 每帧**跳过无变化的元素**(未开始/已完成), 实际活跃元素仅为
      错峰窗口内的 ~30 个;
    - 节点数超过 ENTRANCE_NODE_LIMIT 时由调用方跳过动画。
    """

    def __init__(self, controller: "GraphController", nodes: list[NodeItem],
                 edges: list[EdgeItem], on_finished):
        super().__init__(controller)
        self._controller = controller
        self._nodes = nodes
        self._edges = edges
        self._on_finished = on_finished
        n = max(len(nodes), 1)
        self._stagger = min(ENTRANCE_STAGGER_MAX, ENTRANCE_STAGGER_BUDGET / n)
        self._progress: dict[int, float] = {id(nd): 0.0 for nd in nodes}
        self._edge_progress: dict[int, float] = {id(e): 0.0 for e in edges}

        for nd in nodes:
            nd.setOpacity(0.0)
            nd.apply_scale(0.55)
        for e in edges:
            e.setOpacity(0.0)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(int(len(nodes) * self._stagger
                                   + ENTRANCE_NODE_DURATION))
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self._finish)
        self._anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _tick(self, t: float) -> None:
        dur = ENTRANCE_NODE_DURATION
        progress = self._progress
        for nd in self._nodes:
            p = (t - nd._entrance_index * self._stagger) / dur
            cur = progress[id(nd)]
            if p <= 0.0:
                continue            # 未开始: 保持初始态, 零成本
            if p >= 1.0:
                if cur != 1.0:      # 刚完成: 定格一次
                    progress[id(nd)] = 1.0
                    nd.setOpacity(1.0)
                    nd.apply_scale(1.0)
                continue
            e = _ease_out_cubic(p)
            progress[id(nd)] = e
            nd.setOpacity(e)
            nd.apply_scale(0.55 + 0.45 * e)
        for e in self._edges:
            pe = min(progress.get(id(e.source_item), 1.0),
                     progress.get(id(e.target_item), 1.0))
            if pe != self._edge_progress.get(id(e)):
                self._edge_progress[id(e)] = pe
                e.setOpacity(_ease_out_cubic(pe))

    def _finish(self) -> None:
        for nd in self._nodes:
            nd.setOpacity(1.0)
            nd.apply_scale(1.0)
        for e in self._edges:
            e.setOpacity(1.0)
        self._controller._animating = False
        if self._on_finished:
            self._on_finished()

    def stop(self) -> None:
        """显式停止(场景已清空时调用); 定格回调不再执行。"""
        self._on_finished = None
        if self._anim is not None:
            try:
                self._anim.stop()
            except RuntimeError:
                pass


class _OpacityAnimator(QObject):
    """控制器级透明度渐变: **只对动画子集逐帧插值**。

    性能关键: 淡化(邻域外元素变暗)这类"全场景变化"若逐帧插值,
    每帧都会触发整个视口重绘(N 节点 + M 边 × 60fps), 大图上直接
    把主线程压垮。因此本动画只负责 animated 集合(高亮相关元素,
    通常 ~10 个), 其余元素由调用方**一次性** setOpacity 到位 ——
    全场景重绘从 10 帧降到 1 帧。
    """

    def __init__(self, controller: "GraphController",
                 node_targets: dict[int, float],
                 edge_targets: dict[int, float], duration: int = HOVER_FADE_MS):
        super().__init__(controller)
        self._controller = controller
        self._items: list[tuple[object, float, float]] = []
        for node in controller.nodes.values():
            if id(node) in node_targets:
                self._items.append(
                    (node, node.opacity(), node_targets[id(node)]))
        for edge in controller.edges:
            if id(edge) in edge_targets:
                self._items.append(
                    (edge, edge.opacity(), edge_targets[id(edge)]))

        if not self._items:
            self._anim = None
            return
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(duration)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self._stop)
        self._anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _tick(self, t: float) -> None:
        e = _ease_out_cubic(t)
        for item, fr, to in self._items:
            item.setOpacity(fr + (to - fr) * e)

    def stop(self) -> None:
        if self._anim is not None:
            self._anim.stop()

    def _stop(self) -> None:
        if self._controller._opacity_anim is self:
            self._controller._opacity_anim = None


# ---------------------------------------------------------------------------
# 图控制器: 构建/布局/高亮
# ---------------------------------------------------------------------------
class GraphController(QObject):
    """管理场景内容与高亮逻辑(悬停邻域、冲突链条聚焦、入场动画)。"""

    node_double_clicked = Signal(str)

    def __init__(self, scene: QGraphicsScene, parent: QObject = None):
        super().__init__(parent)
        self.scene = scene
        scene.graph_controller = self  # NodeItem 反查
        self.nodes: dict[str, NodeItem] = {}
        self.edges: list[EdgeItem] = []
        self._focus_mode = False
        self._animating = False
        self._opacity_anim: _OpacityAnimator | None = None
        self._zoom_pending = False   # 滚轮缩放合并窗口中(抑制 hover 风暴)

        # 冲突边流动时钟(仅冲突边参与, 单时钟驱动全部)
        self._flow_timer = QTimer(self)
        self._flow_timer.setInterval(FLOW_INTERVAL_MS)
        self._flow_timer.timeout.connect(self._advance_flow)
        self._flow_edges: list[EdgeItem] = []
        self._flow_phase = 0.0
        self.on_build_finished = None   # 入场动画结束后回调(供视图 fit)

    def build(self, analysis: AnalysisResult, positions: dict) -> None:
        self.clear()
        for key, pkg in analysis.packages.items():
            item = NodeItem(pkg)
            x, y = positions.get(key, (0.0, 0.0))
            item._base_pos = QPointF(x, y)
            item._entrance_index = len(self.nodes)
            item.setPos(x, y)
            self.scene.addItem(item)
            self.nodes[key] = item
        for edge in analysis.edges:
            s = self.nodes.get(edge.source_key)
            t = self.nodes.get(edge.target_key)
            if s is None or t is None:
                continue
            e_item = EdgeItem(edge, s, t)
            e_item.update_path()
            self.scene.addItem(e_item)
            self.edges.append(e_item)

        self._start_flow_clock()
        self._start_entrance()

    def _start_entrance(self) -> None:
        nodes = list(self.nodes.values())
        if not nodes:
            return
        if len(nodes) > ENTRANCE_NODE_LIMIT:
            return  # 大图跳过动画, 直接静态呈现
        self._animating = True
        self._entrance = _EntranceAnimator(
            self, nodes, list(self.edges), self._on_entrance_finished)

    def _on_entrance_finished(self) -> None:
        self._entrance = None
        if self.on_build_finished:
            self.on_build_finished()

    def _start_flow_clock(self) -> None:
        self._flow_edges = [e for e in self.edges if e.is_flowing][
            :FLOW_EDGE_LIMIT]
        if self._flow_edges:
            self._flow_timer.start()

    def _advance_flow(self) -> None:
        self._flow_phase = (self._flow_phase + 0.9) % 1000.0
        for e in self._flow_edges:
            e.advance_flow(self._flow_phase)

    def clear(self) -> None:
        self._flow_timer.stop()
        self._flow_edges = []
        # 停掉入场动画: 否则旧动画会继续改写已被 removeItem 的元素
        entrance = getattr(self, "_entrance", None)
        if entrance is not None:
            try:
                entrance.stop()
            except RuntimeError:
                pass
            self._entrance = None
        if self._opacity_anim is not None:
            self._opacity_anim.stop()   # 停掉残留动画, 防止引用已移除的元素
            self._opacity_anim = None
        self._animating = False
        for item in list(self.scene.items()):
            self.scene.removeItem(item)
        self.nodes.clear()
        self.edges.clear()
        self._focus_mode = False

    # -- 透明度过渡 -----------------------------------------------------------
    def _animate_opacities(self, node_targets: dict[int, float],
                           edge_targets: dict[int, float],
                           animated_nodes: set | None = None,
                           animated_edges: set | None = None) -> None:
        """应用透明度目标: 高亮子集渐变, 其余元素瞬时到位。

        性能关键: 全场景逐帧渐变 = 每帧整视口重绘, 是此前卡顿的主因。
        现在只有邻域/聚焦链(约 10 个元素)参与 160ms 渐变, 淡化元素
        一次性 setOpacity(仅 1 次全场景重绘)。
        """
        if self._animating:
            return  # 入场动画期间不启动透明度渐变, 避免两个动画互相覆盖
        if animated_nodes is None:
            animated_nodes = set(node_targets)
        if animated_edges is None:
            animated_edges = set(edge_targets)

        node_anim: dict[int, float] = {}
        edge_anim: dict[int, float] = {}
        for node in self.nodes.values():
            target = node_targets.get(id(node), 1.0)
            if id(node) in animated_nodes:
                node_anim[id(node)] = target
            elif abs(node.opacity() - target) > 1e-3:
                node.setOpacity(target)   # 瞬时(1 次重绘)
        for edge in self.edges:
            target = edge_targets.get(id(edge), 1.0)
            if id(edge) in animated_edges:
                edge_anim[id(edge)] = target
            elif abs(edge.opacity() - target) > 1e-3:
                edge.setOpacity(target)
        if node_anim or edge_anim:
            # 启动新渐变前必须停止旧渐变, 避免两套动画同写一批 opacity
            if self._opacity_anim is not None:
                self._opacity_anim.stop()
                self._opacity_anim = None
            self._opacity_anim = _OpacityAnimator(self, node_anim, edge_anim)
        elif self._opacity_anim is not None:
            self._opacity_anim.stop()
            self._opacity_anim = None

    # -- 悬停邻域高亮 ---------------------------------------------------------
    def on_node_hover(self, node: NodeItem, entered: bool) -> None:
        if self._focus_mode or self._animating or self._zoom_pending:
            # 缩放合并窗口中鼠标下的节点会连续变化, hover 高亮切换
            # (每次=一次全场景重绘)会与缩放重绘叠加成风暴, 直接忽略
            return
        if entered:
            related = set(node.edges)
            neighbor_nodes = {id(node)}
            for edge in related:
                edge.set_highlight(True)
                neighbor_nodes.add(id(edge.source_item))
                neighbor_nodes.add(id(edge.target_item))
            self._animate_opacities(
                {id(n): (1.0 if id(n) in neighbor_nodes else 0.16)
                 for n in self.nodes.values()},
                {id(e): (1.0 if e in related else 0.10) for e in self.edges},
                animated_nodes=neighbor_nodes,
                animated_edges={id(e) for e in related})
        else:
            # 恢复全瞬时: 1 次重绘, 不逐帧
            self._animate_opacities(
                {id(n): 1.0 for n in self.nodes.values()},
                {id(e): 1.0 for e in self.edges},
                animated_nodes=set(), animated_edges=set())
            for e in self.edges:
                e.set_highlight(False)

    # -- 冲突链条聚焦 -----------------------------------------------------------
    def focus_edge(self, edge: DepEdge) -> "str | None":
        """聚焦一条问题边。

        高亮链条 = 该边本身 + 被依赖包(target)的全部入边 —— 让用户看清
        "都有谁在对同一个包提要求、要求是什么", 冲突源头一目了然;
        其余元素淡化。

        :return: 被依赖包的 key(供调用方居中), 定位失败返回 None
        """
        self.clear_focus()
        s = self.nodes.get(edge.source_key)
        t = self.nodes.get(edge.target_key)
        if s is None or t is None:
            return None  # 未进入聚焦态, 保持悬停高亮可用
        self._focus_mode = True
        chain_nodes = {id(s), id(t)}
        chain_edges: list[EdgeItem] = []
        for e in self.edges:
            same = (e.edge.source_key == edge.source_key
                    and e.edge.target_key == edge.target_key)
            into_target = e.edge.target_key == edge.target_key
            if same:
                e.set_highlight(True)
                chain_edges.append(e)
            elif into_target:
                # 同一被依赖包的其它约束来源: 一并高亮以显示约束文本
                e.set_highlight(True)
                chain_edges.append(e)
            if same or into_target:
                chain_nodes.add(id(e.source_item))
                chain_nodes.add(id(e.target_item))
        self._animate_opacities(
            {id(n): (1.0 if id(n) in chain_nodes else 0.14)
             for n in self.nodes.values()},
            {id(e): (1.0 if e in chain_edges else 0.10) for e in self.edges},
            animated_nodes=chain_nodes,
            animated_edges={id(e) for e in chain_edges})
        return edge.target_key  # 供调用方居中

    def clear_focus(self) -> None:
        self._focus_mode = False
        self._animate_opacities(
            {id(n): 1.0 for n in self.nodes.values()},
            {id(e): 1.0 for e in self.edges},
            animated_nodes=set(), animated_edges=set())
        for e in self.edges:
            e.set_highlight(False)

    def highlight_node(self, key: str) -> bool:
        node = self.nodes.get(key)
        if node is None:
            return False
        for n in self.nodes.values():
            n.set_pulsing(n is node)
        return True


# ---------------------------------------------------------------------------
# 视图
# ---------------------------------------------------------------------------
class DependencyGraphView(QGraphicsView):
    """交互视图:滚轮缩放(光标锚定)、拖拽平移、适应视图。"""

    nodeDoubleClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.controller = GraphController(self._scene, self)
        self.controller.node_double_clicked.connect(self.nodeDoubleClicked.emit)
        self._pending_fit = False  # 视图尚不可见时 fit 无效, 首次显示再执行
        self._user_zoomed = False  # 用户手动缩放/拖拽后, 停止自动重适应
        self._resize_fit_timer: QTimer | None = None  # resize 防抖定时器

        # 滚轮缩放事件合并: 高分辨率滚轮/触控板以 60-120Hz 的频率产生
        # wheelEvent, 若每次事件都立即缩放重绘(全视口), 主线程会被
        # 重绘请求淹没直至无响应。改为累积缩放系数, 16ms 定时器一次性
        # 应用 —— 事件合并后重绘频率上限恒为 60fps 且按实际到达率自动
        # 降频, 单帧耗时超预算时 Qt 事件循环自动跳帧不积压。
        self._pending_zoom = 1.0
        self._zoom_anchor_vp = QPointF(0.0, 0.0)  # 鼠标视口像素位置(锚点)
        self._zoom_timer: QTimer | None = None

        # 渲染优化: 跳过抗锯齿的边界扩展计算(大图重绘显著提速,
        # 视觉差异可忽略)。不启用 DontSavePainterState, 保持各
        # item paint 的状态隔离安全。
        self.setOptimizationFlag(
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)

        # 入场动画结束后场景几何已稳定, 此时再 fit 一次
        # (修正 build 发生在窗口布局稳定前导致的错误缩放)
        self.controller.on_build_finished = self.fit_to_view

        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setBackgroundBrush(QBrush(QColor(Palette.graph_bg)))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._pending_fit:
            self._pending_fit = False
            self.fit_to_view()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 窗口/分栏尺寸变化且用户未接管视图时, 重新适应。
        # 性能关键: 用 200ms 防抖 —— 拖动窗口/分栏时 resize 事件以
        # 每秒几十次的频率到达, 若每次都启动 fit 动画(全视口重绘
        # 240ms), 会形成"动画永不完成 + 持续全场景重绘"的冻结风暴。
        if self._user_zoomed or not self.isVisible() \
                or self.viewport().width() < 10:
            return
        if self._resize_fit_timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(200)
            # 守卫: 防抖窗口内用户若已接管视图(滚轮/拖拽), 不再覆盖其视角
            timer.timeout.connect(
                lambda: (not self._user_zoomed) and self.fit_to_view())
            self._resize_fit_timer = timer
        self._resize_fit_timer.start()

    def wheelEvent(self, event) -> None:
        """滚轮缩放(事件合并)。

        性能关键: 不在 wheelEvent 里直接缩放重绘, 而是累积缩放系数,
        由 16ms 定时器统一应用一次 —— 无论如何疯狂滚动/触控板滑动,
        重绘频率封顶 60fps, 且连续事件合并为一次几何变换。
        """
        self._user_zoomed = True
        self._stop_viewport_anim()
        delta = event.angleDelta().y()
        if delta == 0:
            return
        # 连续系数: 标准滚轮每 notch(120) 缩放 1.12 倍, 触控板小 delta
        # 按比例连续缩放(体验平滑)
        self._pending_zoom *= 1.12 ** (delta / 120.0)
        self._zoom_anchor_vp = event.position().toPoint()
        if hasattr(self, "controller"):
            self.controller._zoom_pending = True  # 抑制缩放中的 hover 风暴
        if self._zoom_timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(16)
            timer.timeout.connect(self._apply_pending_zoom)
            self._zoom_timer = timer
        if not self._zoom_timer.isActive():
            # 仅空闲时启动; 活跃期间事件只累积系数 —— 保证连续滚动时
            # 缩放以最高 60fps 的节拍持续应用, 而不是停手后才生效
            self._zoom_timer.start()

    def _apply_pending_zoom(self) -> None:
        factor = self._pending_zoom
        self._pending_zoom = 1.0
        if hasattr(self, "controller"):
            self.controller._zoom_pending = False
        if abs(factor - 1.0) < 1e-4:
            return
        # 用当前 transform 把最新鼠标像素位置映射到场景(锚定正确)
        self.scale_at(self.mapToScene(self._zoom_anchor_vp), factor)

    def mousePressEvent(self, event) -> None:
        self._user_zoomed = True  # 拖拽平移视为用户接管视图
        self._stop_viewport_anim()
        super().mousePressEvent(event)

    def scale_at(self, scene_pos: QPointF, factor: float) -> None:
        new_zoom = self.transform().m11() * factor
        if not (0.10 <= new_zoom <= 8.0):
            return
        self.translate(scene_pos.x(), scene_pos.y())
        self.scale(factor, factor)
        self.translate(-scene_pos.x(), -scene_pos.y())

    def fit_to_view(self) -> None:
        """适应视图: 留白按视口比例, 平滑过渡到目标(小图适度放大)。"""
        rect = self.sceneRect()
        if rect.isEmpty():
            return
        # 视图未显示(视口无尺寸)时推迟到 showEvent
        if not self.isVisible() or self.viewport().width() < 10:
            self._pending_fit = True
            return
        vw, vh = self.viewport().width(), self.viewport().height()
        margin = max(46.0, min(vw, vh) * 0.07)   # 比例留白: 少留白也不贴边
        avail_w = max(vw - 2.0 * margin, 10.0)
        avail_h = max(vh - 2.0 * margin, 10.0)
        scale = min(avail_w / rect.width(), avail_h / rect.height())
        scale = min(max(scale, 0.08), 1.5)
        self._animate_viewport(scale, rect.center(), VIEWPORT_MOVE_MS)

    def render_to_image(self, width: int, height: int):
        """把整张场景渲染为 QImage(导出 PNG 用, 与视口缩放无关)。"""
        from PySide6.QtGui import QImage
        scene_rect = self.sceneRect()
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(Palette.graph_bg))
        painter = QPainter(image)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.TextAntialiasing)
        if not scene_rect.isEmpty():
            self.scene().render(painter, QRectF(0, 0, width, height), scene_rect)
        painter.end()
        return image

    def center_on_node(self, key: str) -> None:
        node = self.controller.nodes.get(key)
        if node is not None:
            center = node.mapToScene(
                QPointF(node.width / 2.0, node.height / 2.0))
            self._animate_viewport(self.transform().m11(), center,
                                   VIEWPORT_MOVE_MS)

    # -- 视口动画 -------------------------------------------------------------
    def _animate_viewport(self, to_scale: float, to_center: QPointF,
                          duration: int) -> None:
        from_scale = self.transform().m11()
        from_center = self.mapToScene(self.viewport().rect().center())
        same_scale = abs(from_scale - to_scale) < 1e-4
        same_center = ((from_center - to_center).manhattanLength() < 1.0)
        if duration <= 0 or (same_scale and same_center):
            self._apply_viewport(to_scale, to_center)
            return
        self._stop_viewport_anim()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(duration)
        anim.valueChanged.connect(
            lambda t: self._apply_viewport(
                from_scale + (to_scale - from_scale) * _ease_out_cubic(t),
                from_center + (to_center - from_center) * _ease_out_cubic(t)))
        anim.finished.connect(lambda: setattr(self, "_vp_anim", None))
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._vp_anim = anim

    def _apply_viewport(self, scale: float, center: QPointF) -> None:
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(center)

    def _stop_viewport_anim(self) -> None:
        anim = getattr(self, "_vp_anim", None)
        if anim is not None:
            anim.stop()
            self._vp_anim = None

    def focus_node(self, key: str) -> None:
        """定位并脉冲高亮一个节点。"""
        node = self.controller.nodes.get(key)
        if node is None:
            return
        self.centerOn(node)
        self.controller.highlight_node(key)

    def clear_visual_state(self) -> None:
        self.controller.clear_focus()
        for n in self.controller.nodes.values():
            n.set_pulsing(False)
