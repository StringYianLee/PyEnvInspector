"""主窗口:侧边栏导航 + 四个功能页 + 流程编排。

整体交互流程:
1. 启动 → 自动后台扫描解释器 → 卡片列表(图列表形式)供选择
2. 单击选中 / 双击或按钮确认 → 后台采集该环境包元数据 → 包列表页
3. 依赖分析页自动完成冲突判定 → 依赖图 / 冲突清单 / 循环依赖 / 冲突矩阵
4. 冲突清单点击行 → 依赖图聚焦冲突链条; 包列表双击行 → 图中定位该包
5. Conda 页:环境列表 / 原生包 / 环境路径 / .condarc 配置,
   双击环境直接接入既有流水线
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from .core.analyzer import analyze
from .core.models import (
    CondaEnvironment, CondaInfo, EnvironmentSnapshot, InterpreterInfo,
)
from .demo import (
    build_demo_conda_info,
    build_demo_env_snapshot,
    build_demo_interpreter,
    build_demo_snapshot,
)
from .ui.analysis_page import AnalysisPage
from .ui.conda_page import CondaPage
from .ui.interpreters_page import InterpretersPage
from .ui.manage_page import ManagePage
from .ui.packages_page import PackagesPage
from .ui.theme import Palette
from .workers import CollectWorker, CondaScanWorker, ScanWorker


def _draw_nav_icon(painter: QPainter, kind: str, x: int, y: int,
                   size: int, color: QColor) -> None:
    """绘制导航小图标(纯几何, 无字体依赖)。"""
    pen = QPen(color)
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if kind == "env":            # 环境: 同心圆
        painter.drawEllipse(x + 1, y + 1, size - 2, size - 2)
        painter.drawEllipse(x + size // 3, y + size // 3,
                            size // 3, size // 3)
    elif kind == "packages":     # 包: 层叠矩形
        painter.drawRect(x + 2, y + int(size * 0.55),
                         size - 4, int(size * 0.35))
        painter.drawRect(x + int(size * 0.22), y + int(size * 0.22),
                         int(size * 0.56), int(size * 0.26))
    elif kind == "graph":        # 分析: 三节点网络
        painter.drawEllipse(x, y, 5, 5)
        painter.drawEllipse(x + size - 5, y, 5, 5)
        painter.drawEllipse(x + size // 2 - 3, y + size - 7, 6, 6)
        painter.drawLine(x + 5, y + 3, x + size - 6, y + 3)
        painter.drawLine(x + 4, y + 5, x + size // 2 - 1, y + size - 6)
        painter.drawLine(x + size - 4, y + 5, x + size // 2 + 1, y + size - 6)
    elif kind == "conda":        # Conda: 圆环 + 中心点
        painter.drawEllipse(x + 1, y + 1, size - 2, size - 2)
        painter.setBrush(color)
        painter.drawEllipse(x + size // 2 - 2, y + size // 2 - 2, 4, 4)
    elif kind == "manage":       # 管理: 齿轮(外圆 + 内圆 + 四齿)
        c = size / 2
        painter.drawEllipse(x + 1, y + 1, size - 2, size - 2)
        painter.drawEllipse(x + size // 2 - 3, y + size // 2 - 3, 6, 6)
        for dx, dy in ((c, 0), (c, size), (0, c), (size, c)):
            painter.drawLine(x + int(dx), y + 1 if dy == 0 else
                             (y + size - 1 if dy == size else y + int(dy)),
                             x + int(dx), y + int(dy))
    elif kind == "demo":         # 演示: 播放三角
        from PySide6.QtCore import QPoint
        painter.drawPolygon([
            QPoint(x + 4, y + 2),
            QPoint(x + size - 5, y + size // 2),
            QPoint(x + 4, y + size - 2),
        ])


class _NavItem(QToolButton):
    """侧边栏导航按钮(自绘图标 + 文字)。"""

    def __init__(self, kind: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("navButton")
        self._kind = kind
        self._text = text
        self.setCheckable(True)
        self.setFixedSize(66, 62)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(text)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        active = self.isChecked()
        if active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(Palette.primary))
            painter.drawRoundedRect(rect.adjusted(2, 3, -2, -3), 10, 10)

        color = QColor("#ffffff") if active else QColor(Palette.text_muted)
        if self.underMouse() and not active:
            color = QColor(Palette.text)

        icon_size = 20
        _draw_nav_icon(painter, self._kind,
                       rect.center().x() - icon_size // 2, 9,
                       icon_size, color)

        font = QFont()
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(
            rect.adjusted(0, rect.height() - 30, 0, -8),
            int(Qt.AlignHCenter | Qt.AlignVCenter), self._text)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyEnv Inspector · Python 环境与包依赖管理工具")
        self.resize(1240, 800)

        self._scan_worker: ScanWorker | None = None
        self._collect_worker: CollectWorker | None = None
        self._conda_worker: CondaScanWorker | None = None
        self._snapshots: dict[str, EnvironmentSnapshot] = {}  # 路径 -> 缓存
        self._snapshot: EnvironmentSnapshot | None = None
        self._interpreters: list[InterpreterInfo] = []        # 最近一次扫描结果
        self._conda_info = None                                # 最近一次 conda 扫描

        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 侧边栏 ----
        sidebar = QWidget()
        sidebar.setFixedWidth(84)
        sidebar.setStyleSheet(
            f"background: {Palette.surface}; border-right: 1px solid {Palette.border};"
        )
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(9, 18, 9, 14)
        side.setSpacing(6)

        logo = QLabel("PyEnv")
        lf = QFont()
        lf.setBold(True)
        lf.setPointSizeF(10)
        logo.setFont(lf)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"color: {Palette.primary}; background: {Palette.primary_soft};"
            " border-radius: 10px; padding: 9px 4px;"
        )
        side.addWidget(logo)
        side.addSpacing(18)

        self._nav_buttons: list[_NavItem] = []
        for kind, text, page_idx in (
            ("env", "解释器", 0),
            ("packages", "包列表", 1),
            ("graph", "依赖分析", 2),
            ("conda", "Conda", 3),
            ("manage", "管理", 4),
        ):
            btn = _NavItem(kind, text)
            btn.clicked.connect(lambda _checked, idx=page_idx: self._goto_page(idx))
            side.addWidget(btn)
            self._nav_buttons.append(btn)

        side.addStretch(1)

        demo_btn = _NavItem("demo", "演示")
        demo_btn.setToolTip("加载内置演示数据(含冲突/缺失/循环示例)")
        demo_btn.clicked.connect(lambda: (demo_btn.setChecked(False),
                                          self._load_demo()))
        side.addWidget(demo_btn)

        version = QLabel("v1.0.0")
        version.setStyleSheet(f"color: {Palette.text_faint}; font-size: 10px;")
        version.setAlignment(Qt.AlignHCenter)
        side.addWidget(version)
        layout.addWidget(sidebar)

        # ---- 页面栈 ----
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.interp_page = InterpretersPage()
        self.packages_page = PackagesPage()
        self.analysis_page = AnalysisPage()
        self.conda_page = CondaPage()
        self.manage_page = ManagePage()
        self.stack.addWidget(self.interp_page)    # 0
        self.stack.addWidget(self.packages_page)  # 1
        self.stack.addWidget(self.analysis_page)  # 2
        self.stack.addWidget(self.conda_page)     # 3
        self.stack.addWidget(self.manage_page)    # 4

        # ---- 信号 ----
        self.interp_page.rescan_button.clicked.connect(self.start_scan)
        self.interp_page.interpreter_activated.connect(
            self._on_interpreter_activated)
        self.packages_page.reload_requested.connect(self._on_reload_requested)
        self.packages_page.package_activated.connect(self._on_package_activated)
        self.conda_page.rescan_requested.connect(self.start_conda_scan)
        self.conda_page.environment_activated.connect(
            self._on_conda_environment_activated)
        self.manage_page.python_changed.connect(self.start_scan)
        self.manage_page.conda_changed.connect(self.start_conda_scan)
        self.manage_page.packages_changed.connect(self._on_packages_changed)

        self.statusBar().showMessage("就绪")
        self._goto_page(0)
        self.start_scan()

    # ------------------------------------------------------------------
    # 关闭时清理后台线程(避免 QThread 运行中析构崩溃)
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        workers = [self._scan_worker, self._collect_worker, self._conda_worker,
                   getattr(self.analysis_page, "_layout_worker", None),
                   *getattr(self, "_stray_workers", [])]
        for worker in workers:
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    worker.quit()
                    if not worker.wait(3000):
                        worker.terminate()
                        worker.wait(1000)
                    if worker.isRunning():
                        # 仍无法终止: 挂 finished 清理, 避免析构运行中线程
                        worker.finished.connect(worker.deleteLater)
                        continue
                worker.deleteLater()
            except RuntimeError:
                pass  # 线程已结束, C++ 对象被回收
        super().closeEvent(event)

    def _retire_worker(self, worker, timeout_ms: int) -> bool:
        """等待线程结束。

        返回 True=已结束(调用方可安全 deleteLater); 超时未结束时挂
        finished 清理并隔离到 _stray_workers(保持引用 + closeEvent 兜底),
        返回 False。
        """
        if worker.isRunning() and not worker.wait(timeout_ms):
            try:
                worker.finished.connect(worker.deleteLater)
            except (RuntimeError, TypeError):
                pass
            if not hasattr(self, "_stray_workers"):
                self._stray_workers = []
            self._stray_workers.append(worker)
            return False
        return True

    # ------------------------------------------------------------------
    # 导航
    # ------------------------------------------------------------------
    def _goto_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

    # ------------------------------------------------------------------
    # 扫描流程
    # ------------------------------------------------------------------
    def start_scan(self) -> None:
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self.statusBar().showMessage("已有扫描任务进行中, 请稍候…")
            return
        self.interp_page.set_scanning(True, "正在扫描, 请稍候…")
        self.statusBar().showMessage("正在扫描本机 Python 解释器…")
        self._scan_worker = ScanWorker(self)
        self._scan_worker.progress.connect(
            lambda text: (self.interp_page.set_scanning(True, text),
                          self.statusBar().showMessage(text)))
        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_failed(self, message: str) -> None:
        worker = self._scan_worker
        if worker is None or self.sender() is not worker:
            return
        self._scan_worker = None
        worker.deleteLater()
        self.interp_page.set_scanning(False)
        self.interp_page.show_interpreters([])
        self.statusBar().showMessage(message)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "解释器扫描失败", message)

    def _on_scan_done(self, report) -> None:
        worker = self._scan_worker
        if worker is None or self.sender() is not worker:
            return  # 丢弃过期扫描结果
        self._scan_worker = None
        worker.deleteLater()
        self.interp_page.set_scanning(False)
        self.interp_page.show_interpreters(report.interpreters)
        self._interpreters = list(report.interpreters)
        self.manage_page.set_data(self._interpreters, self._conda_info)
        n = len(report.interpreters)
        self.statusBar().showMessage(f"扫描完成: 发现 {n} 个 Python 解释器")
        # 解释器扫描完成后, 顺带执行 conda 专属扫描
        self.start_conda_scan()

    # ------------------------------------------------------------------
    # Conda 专属扫描流程
    # ------------------------------------------------------------------
    def start_conda_scan(self) -> None:
        if self._conda_worker is not None and self._conda_worker.isRunning():
            return
        self.statusBar().showMessage("正在扫描 conda 环境与配置…")
        self._conda_worker = CondaScanWorker(self)
        self._conda_worker.progress.connect(self.statusBar().showMessage)
        self._conda_worker.done.connect(self._on_conda_done)
        self._conda_worker.start()

    def _on_conda_done(self, info) -> None:
        worker = self._conda_worker
        if worker is None or self.sender() is not worker:
            return  # 丢弃过期结果(worker 可能已被演示模式排空)
        self._conda_worker = None
        worker.deleteLater()
        self._conda_info = info
        self.conda_page.load_conda(info)
        self.manage_page.set_data(self._interpreters, info)
        n_envs = len(info.envs)
        n_pkgs = info.total_conda_packages
        if not info.roots:
            # 区分"确实没有 conda"与"扫描出错": 错误信息优先展示
            self.statusBar().showMessage(
                f"未检测到 conda 安装: {info.errors[0]}" if info.errors
                else "未检测到 conda 安装")
        else:
            self.statusBar().showMessage(
                f"Conda 扫描完成: {n_envs} 个环境 · {n_pkgs} 个原生包")

    def _on_conda_environment_activated(self, env_path: str) -> None:
        """从 Conda 页双击环境 → 接入既有解释器流水线。"""
        target = os.path.normcase(os.path.normpath(env_path))
        # 优先在已扫描解释器中找(有真实探测信息)
        for info in self._interpreters:
            if info.source == "conda":
                exe_dir = os.path.dirname(os.path.normpath(info.path))
                env_dir = os.path.dirname(exe_dir) if os.name != "nt" else exe_dir
                if os.path.normcase(os.path.normpath(env_dir)) == target:
                    self._on_interpreter_activated(info)
                    return
        # 兜底: 用环境内 python 路径直接激活(采集阶段会再次验证)
        exe = "python.exe" if os.name == "nt" else os.path.join("bin", "python")
        python_path = os.path.join(env_path, exe)
        self._on_interpreter_activated(InterpreterInfo(
            path=python_path, source="conda",
            env_name=os.path.basename(os.path.normpath(env_path))))

    # ------------------------------------------------------------------
    # 采集流程
    # ------------------------------------------------------------------
    def _on_interpreter_activated(self, interp: InterpreterInfo) -> None:
        cached = self._snapshots.get(interp.path)
        if cached is not None:
            self._apply_snapshot(cached)
            return
        self._collect(interp, force=False)

    def _on_reload_requested(self) -> None:
        if self._snapshot is None:
            return
        if getattr(self._snapshot, "is_demo", False):
            self._load_demo()
            return
        self._collect(self._snapshot.interpreter, force=True)

    def _collect(self, interp: InterpreterInfo, force: bool) -> None:
        if self._collect_worker is not None and self._collect_worker.isRunning():
            self.statusBar().showMessage("正在读取当前环境的包信息, 请稍候…")
            return
        if force:
            self._snapshots.pop(interp.path, None)
        self.interp_page.set_scanning(True, "正在读取包元数据…")
        self.statusBar().showMessage(f"正在采集 {interp.path} 的包信息…")
        self._collect_worker = CollectWorker(interp, self)
        self._collect_worker.progress.connect(self.statusBar().showMessage)
        self._collect_worker.done.connect(self._on_collect_done)
        self._collect_worker.failed.connect(self._on_collect_failed)
        self._collect_worker.start()

    def _on_collect_done(self, snapshot: EnvironmentSnapshot) -> None:
        worker = self._collect_worker
        if worker is None or self.sender() is not worker:
            return  # 丢弃过期采集结果
        self._collect_worker = None
        worker.deleteLater()
        self.interp_page.set_scanning(False)
        self._snapshots[snapshot.interpreter.path] = snapshot
        self._apply_snapshot(snapshot)

    def _on_collect_failed(self, message: str) -> None:
        worker = self._collect_worker
        if worker is None or self.sender() is not worker:
            return
        self._collect_worker = None
        worker.deleteLater()
        self.interp_page.set_scanning(False)
        self.statusBar().showMessage(f"采集失败: {message}")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "包信息采集失败", message)

    def _apply_snapshot(self, snapshot: EnvironmentSnapshot) -> None:
        self._snapshot = snapshot
        result = analyze(snapshot)
        self.packages_page.load_analysis(result)
        self.analysis_page.load_analysis(result)
        interp = snapshot.interpreter
        self.manage_page.set_current_env_dir(self._env_dir_of(interp.path))
        self.statusBar().showMessage(
            f"当前环境: Python {interp.version} · {interp.path} · "
            f"{result.stats['packages']} 个包"
        )
        self._goto_page(1)

    @staticmethod
    def _env_dir_of(python_path: str) -> str:
        """由解释器路径推算环境根目录(删除保护用)。"""
        d = os.path.dirname(os.path.normpath(python_path))
        if os.name != "nt" and os.path.basename(d) == "bin":
            return os.path.dirname(d)
        return d

    def _on_packages_changed(self, python_path: str) -> None:
        """包管理页装卸包后: 使缓存失效; 若为当前环境则立即重采刷新。"""
        target = os.path.normcase(python_path)
        for key in list(self._snapshots):
            snap = self._snapshots[key]
            if snap.interpreter.path and os.path.normcase(
                    snap.interpreter.path) == target:
                del self._snapshots[key]
        if self._snapshot and self._snapshot.interpreter.path and \
                os.path.normcase(self._snapshot.interpreter.path) == target:
            self._collect(self._snapshot.interpreter, force=True)

    # ------------------------------------------------------------------
    # 跨页联动
    # ------------------------------------------------------------------
    def _on_package_activated(self, key: str) -> None:
        self._goto_page(2)
        self.analysis_page.focus_package(key)

    # ------------------------------------------------------------------
    # 演示数据
    # ------------------------------------------------------------------
    def load_demo(self) -> None:
        """加载内置演示数据(公开入口, 供侧边栏按钮与 --demo 参数使用)。"""
        # 排空运行中的后台任务, 避免其迟到结果覆盖演示数据
        for worker in (self._conda_worker, self._collect_worker,
                       self._scan_worker):
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    if not self._retire_worker(worker, 15000):
                        continue  # 未结束: 结果经 disconnect 丢弃, 不销毁
                for sig_name in ("done", "failed", "progress"):
                    sig = getattr(worker, sig_name, None)
                    if sig is not None:
                        try:
                            sig.disconnect()
                        except (RuntimeError, TypeError):
                            pass
                worker.deleteLater()
            except (RuntimeError, TypeError):
                pass
        self._conda_worker = None
        self._collect_worker = None
        self._scan_worker = None
        # 后台任务被排空, 复位解释器页忙碌态(否则按钮永久置灰)
        self.interp_page.set_scanning(False)

        snapshot = build_demo_snapshot()
        snapshot.is_demo = True  # 标记演示快照: 刷新时重建而非真实采集
        self._snapshots[snapshot.interpreter.path] = snapshot
        demo_conda = build_demo_conda_info()
        # 为每个演示 conda 环境注册配套 pip 快照, 双击环境即可无缝联动
        for env in demo_conda.envs:
            if env.interpreter and env.interpreter not in self._snapshots:
                env_snapshot = build_demo_env_snapshot(env)
                env_snapshot.is_demo = True
                self._snapshots[env.interpreter] = env_snapshot
        self.conda_page.load_conda(demo_conda)
        self.manage_page.set_data(
            [build_demo_interpreter()], demo_conda)
        self._apply_snapshot(snapshot)
        self.statusBar().showMessage("已加载演示数据(假想环境, 含冲突/缺失/循环示例)")

    # 兼容旧调用名
    _load_demo = load_demo
