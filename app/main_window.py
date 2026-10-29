"""主窗口:侧边栏导航 + 七个功能页 + 流程编排。

页面:
  0 解释器   1 包列表   2 依赖分析   3 Conda   4 管理   5 环境对比   6 诊断与报告

关键流程:
- 启动 → 后台扫描解释器 → (顺带)conda 扫描 → 启动时可选检查更新
- 选择环境 → 磁盘/内存缓存命中则直接用, 否则后台采集 → 后台分析 → 四个页面共享结果
- 分析完成后落盘快照(支持历史变化与跨重启复用)
- 冲突清单可一键生成合并约束并在目标环境执行 pip 修复
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import __version__
from .core import cache, diagnostics as diag_mod, licenses
from .core.appsettings import Settings
from .core.compare import compare_snapshots
from .core.models import EnvironmentSnapshot, InterpreterInfo
from .demo import (
    build_demo_conda_info,
    build_demo_env_snapshot,
    build_demo_interpreter,
    build_demo_snapshot,
)
from .ui.analysis_page import AnalysisPage
from .ui.compare_page import ComparePage
from .ui.conda_page import CondaPage
from .ui.interpreters_page import InterpretersPage
from .ui.manage_page import ManagePage
from .ui.packages_page import PackagesPage
from .ui.reports_page import ReportsPage
from .ui.theme import Palette
from .workers import (
    AnalysisWorker, CollectWorker, CondaScanWorker, ScanWorker,
    UpdateCheckWorker,
)

log = logging.getLogger(__name__)

PAGE_INTERPRETERS = 0
PAGE_PACKAGES = 1
PAGE_ANALYSIS = 2
PAGE_CONDA = 3
PAGE_MANAGE = 4
PAGE_COMPARE = 5
PAGE_REPORTS = 6


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
    elif kind == "manage":       # 管理: 齿轮(外圆 + 内圆 + 齿)
        c = size / 2
        painter.drawEllipse(x + 1, y + 1, size - 2, size - 2)
        painter.drawEllipse(x + size // 2 - 3, y + size // 2 - 3, 6, 6)
        for dx, dy in ((c, 0), (c, size), (0, c), (size, c)):
            painter.drawLine(x + int(dx), y + 1 if dy == 0 else
                             (y + size - 1 if dy == size else y + int(dy)),
                             x + int(dx), y + int(dy))
    elif kind == "compare":      # 对比: 左右两个方块
        painter.drawRect(x + 1, y + 2, int(size * 0.42), size - 4)
        painter.drawRect(x + int(size * 0.57), y + 2,
                         int(size * 0.42), size - 4)
    elif kind == "reports":      # 报告: 文档 + 行
        painter.drawRect(x + 3, y + 1, size - 6, size - 2)
        for i in range(3):
            painter.drawLine(x + 6, y + 6 + i * 4, x + size - 6, y + 6 + i * 4)
    elif kind == "theme":        # 主题: 半圆
        painter.drawEllipse(x + 2, y + 2, size - 4, size - 4)
        painter.drawLine(x + size // 2, y + 3, x + size // 2, y + size - 3)
    elif kind == "about":        # 关于: 信息圆圈
        painter.drawEllipse(x + 2, y + 2, size - 4, size - 4)
        painter.drawLine(x + size // 2, y + 9, x + size // 2, y + size - 5)
        painter.setBrush(color)
        painter.drawEllipse(x + size // 2 - 1, y + 4, 2, 2)
        painter.setBrush(Qt.NoBrush)
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
        self.setFixedSize(66, 58)
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

        color = QColor(Palette.on_primary) if active else QColor(Palette.text_muted)
        if self.underMouse() and not active:
            color = QColor(Palette.text)

        icon_size = 20
        _draw_nav_icon(painter, self._kind,
                       rect.center().x() - icon_size // 2, 8,
                       icon_size, color)

        font = QFont()
        font.setPointSizeF(8.2)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(
            rect.adjusted(0, rect.height() - 28, 0, -6),
            int(Qt.AlignHCenter | Qt.AlignVCenter), self._text)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PyEnv Inspector · Python 环境与包依赖管理工具 (v{__version__})")
        self.resize(1240, 800)

        self._settings = Settings()
        self._scan_worker: ScanWorker | None = None
        self._collect_worker: CollectWorker | None = None
        self._conda_worker: CondaScanWorker | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._update_worker: UpdateCheckWorker | None = None
        self._snapshots: dict[str, EnvironmentSnapshot] = {}   # 内存缓存
        self._snapshot: EnvironmentSnapshot | None = None
        self._interpreters: list[InterpreterInfo] = []
        self._conda_info = None
        self._compare_pending: tuple[str, str] | None = None
        self._compare_need: set[str] = set()
        self._stray_workers: list = []
        self._about_dialog = None
        self._update_text = ""
        self._analysis_purpose = "normal"   # normal | reports
        self._reports_pending: str | None = None

        self._build_ui()
        self._restore_settings()
        self._goto_page(self._settings.get_int(Settings.KEY_PAGE, PAGE_INTERPRETERS))
        self.statusBar().showMessage("就绪")
        self.start_scan()
        self._maybe_check_updates()

    # ------------------------------------------------------------------
    # 界面构建(拆出以便主题切换时原地重建)
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
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
        side.setContentsMargins(9, 14, 9, 10)
        side.setSpacing(4)

        logo = QLabel("PyEnv")
        lf = QFont()
        lf.setBold(True)
        lf.setPointSizeF(10)
        logo.setFont(lf)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"color: {Palette.primary}; background: {Palette.primary_soft};"
            " border-radius: 10px; padding: 8px 4px;"
        )
        side.addWidget(logo)
        side.addSpacing(10)

        self._nav_buttons: list[_NavItem] = []
        nav_specs = (
            ("env", "解释器", PAGE_INTERPRETERS),
            ("packages", "包列表", PAGE_PACKAGES),
            ("graph", "依赖分析", PAGE_ANALYSIS),
            ("conda", "Conda", PAGE_CONDA),
            ("manage", "管理", PAGE_MANAGE),
            ("compare", "对比", PAGE_COMPARE),
            ("reports", "诊断", PAGE_REPORTS),
        )
        for kind, text, page_idx in nav_specs:
            btn = _NavItem(kind, text)
            btn.clicked.connect(lambda _checked, idx=page_idx: self._goto_page(idx))
            side.addWidget(btn)
            self._nav_buttons.append(btn)

        side.addStretch(1)

        self._theme_btn = _NavItem("theme", "主题")
        self._theme_btn.setToolTip(
            f"切换到{'浅色' if Palette.is_dark else '深色'}主题(立即生效)")
        self._theme_btn.clicked.connect(
            lambda: (self._theme_btn.setChecked(False), self._toggle_theme()))
        side.addWidget(self._theme_btn)

        about_btn = _NavItem("about", "关于")
        about_btn.setToolTip("软件版本与版本更新内容")
        about_btn.clicked.connect(
            lambda: (about_btn.setChecked(False), self.open_about()))
        side.addWidget(about_btn)

        demo_btn = _NavItem("demo", "演示")
        demo_btn.setToolTip("加载内置演示数据(含冲突/缺失/循环示例)")
        demo_btn.clicked.connect(lambda: (demo_btn.setChecked(False),
                                          self._load_demo()))
        side.addWidget(demo_btn)

        self._version_label = QLabel(f"v{__version__}")
        self._version_label.setStyleSheet(
            f"color: {Palette.text_faint}; font-size: 10px;")
        self._version_label.setAlignment(Qt.AlignHCenter)
        self._version_label.setCursor(Qt.PointingHandCursor)
        side.addWidget(self._version_label)
        layout.addWidget(sidebar)

        # ---- 页面栈 ----
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.interp_page = InterpretersPage()
        self.packages_page = PackagesPage()
        self.analysis_page = AnalysisPage()
        self.conda_page = CondaPage()
        self.manage_page = ManagePage()
        self.compare_page = ComparePage()
        self.reports_page = ReportsPage()
        for page in (self.interp_page, self.packages_page, self.analysis_page,
                     self.conda_page, self.manage_page, self.compare_page,
                     self.reports_page):
            self.stack.addWidget(page)

        self._wire_signals()

    def _wire_signals(self) -> None:
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
        self.compare_page.compare_requested.connect(self._on_compare_requested)
        self.reports_page.diagnostics_requested.connect(self._refresh_reports)
        self.reports_page.interpreter_selected.connect(
            self._on_reports_interpreter)
        self.reports_page.fix_all_requested.connect(self._on_fix_all)
        self.analysis_page.fix_requested.connect(self._on_fix_requested)

    # ------------------------------------------------------------------
    # 设置
    # ------------------------------------------------------------------
    def _restore_settings(self) -> None:
        geometry = self._settings.get(Settings.KEY_GEOMETRY)
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
            except (TypeError, RuntimeError):
                pass
        mode = self._settings.get(Settings.KEY_LAYOUT_MODE, "hierarchical")
        idx = self.analysis_page.layout_combo.findData(mode)
        if idx >= 0:
            self.analysis_page.layout_combo.setCurrentIndex(idx)
        index_label = self._settings.get(Settings.KEY_PIP_INDEX, "官方")
        idx = self.manage_page.pkg_index_combo.findText(index_label) \
            if hasattr(self.manage_page, "pkg_index_combo") else -1
        if idx >= 0:
            self.manage_page.pkg_index_combo.setCurrentIndex(idx)

    def _save_settings(self) -> None:
        try:
            self._settings.set(Settings.KEY_GEOMETRY, self.saveGeometry())
            self._settings.set(Settings.KEY_PAGE, self.stack.currentIndex())
            self._settings.set(
                Settings.KEY_LAYOUT_MODE,
                self.analysis_page.layout_combo.currentData())
            if hasattr(self.manage_page, "pkg_index_combo"):
                self._settings.set(
                    Settings.KEY_PIP_INDEX,
                    self.manage_page.pkg_index_combo.currentText())
            if self._snapshot is not None:
                self._settings.set(Settings.KEY_LAST_PYTHON,
                                   self._snapshot.interpreter.path)
            self._settings.set(Settings.KEY_COMPARE_A,
                               self.compare_page.combo_a.currentData() or "")
            self._settings.set(Settings.KEY_COMPARE_B,
                               self.compare_page.combo_b.currentData() or "")
            self._settings.sync()
        except Exception as exc:   # 设置保存失败不能影响退出
            log.warning("保存设置失败: %s", exc)

    def _toggle_theme(self) -> None:
        """浅色/深色实时切换: 重设调色板 + 全局 QSS, 再原地重建界面。

        各页面在构造期就把 Palette 颜色写进了内联样式, 因此必须重建
        控件树才能彻底换色; 状态(快照/解释器/conda/设置)都保存在 self,
        重建后自动恢复, 用户无需重启。
        """
        running = [w for w in (
            self._scan_worker, self._collect_worker, self._conda_worker)
            if w is not None and w.isRunning()]
        manage_busy = (self.manage_page._worker is not None
                       and self.manage_page._worker.isRunning())
        if running or manage_busy:
            # 非阻塞提示(模态框会打断用户, 也不利于自动化测试)
            self.statusBar().showMessage(
                "有后台任务正在执行, 完成后再切换主题", 6000)
            return
        if self._analysis_worker is not None and self._analysis_worker.isRunning():
            self._analysis_worker.wait(5000)   # 分析很快, 等它收尾即可

        dark = not Palette.is_dark
        self._settings.set(Settings.KEY_DARK_THEME, dark)
        from .ui.theme import apply_theme, use_dark
        use_dark(dark)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)

        current_page = self.stack.currentIndex()
        self.qss_rebuild(current_page)
        self.statusBar().showMessage(
            f"已切换到{'深色' if dark else '浅色'}主题", 4000)

    def qss_rebuild(self, current_page: int) -> None:
        """替换中央控件并按当前状态重建界面。"""
        snapshot = self._snapshot
        compare_a = self.compare_page.combo_a.currentData() or ""
        compare_b = self.compare_page.combo_b.currentData() or ""
        reports_path = self.reports_page.selected_path() or ""

        old = self.centralWidget()
        self.setCentralWidget(QWidget())   # 先摘下旧控件树
        if old is not None:
            old.setParent(None)
            old.deleteLater()

        self._build_ui()
        if self._interpreters:
            self.interp_page.show_interpreters(self._interpreters)
            self.manage_page.set_data(self._interpreters, self._conda_info)
            self.compare_page.set_interpreters(
                self._interpreters, current_path=compare_a)
            self.compare_page.set_selection(compare_a, compare_b)
            self.reports_page.set_interpreters(
                self._interpreters, current_path=reports_path)
        if self._conda_info is not None:
            self.conda_page.load_conda(self._conda_info)
        self._goto_page(current_page)
        if snapshot is not None:
            self._refresh_view_from_snapshot(snapshot)

    def _refresh_view_from_snapshot(self, snapshot) -> None:
        """主题重建后: 重新分析并恢复三个页面的数据(不触发采集)。"""
        self._snapshot = snapshot
        if self._analysis_worker is not None:
            self._analysis_worker.wait(1500)
        self._analysis_worker = AnalysisWorker(snapshot, self)
        self._analysis_worker.done.connect(self._on_analysis_done)
        self._analysis_worker.failed.connect(self._on_analysis_failed)
        self._analysis_worker.start()

    def open_about(self) -> None:
        """打开「关于」面板: 版本 + 运行环境 + 版本更新内容。"""
        from .ui.about_dialog import AboutDialog
        if self._about_dialog is None:
            self._about_dialog = AboutDialog(self, update_text=self._update_text)
        else:
            self._about_dialog.set_update_text(
                self._update_text or "尚未完成更新检查")
        self._about_dialog.show()
        self._about_dialog.raise_()

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._save_settings()
        workers = [self._scan_worker, self._collect_worker, self._conda_worker,
                   self._analysis_worker, self._update_worker,
                   getattr(self.analysis_page, "_layout_worker", None),
                   *self._stray_workers]
        for worker in workers:
            if worker is None:
                continue
            try:
                if hasattr(worker, "cancel"):
                    worker.cancel()
                if worker.isRunning():
                    worker.quit()
                    if not worker.wait(3000):
                        worker.terminate()
                        worker.wait(1000)
                    if worker.isRunning():
                        worker.finished.connect(worker.deleteLater)
                        continue
                worker.deleteLater()
            except RuntimeError:
                pass
        super().closeEvent(event)

    def _retire_worker(self, worker, timeout_ms: int) -> bool:
        if worker.isRunning() and not worker.wait(timeout_ms):
            try:
                worker.finished.connect(worker.deleteLater)
            except (RuntimeError, TypeError):
                pass
            self._stray_workers.append(worker)
            return False
        return True

    # ------------------------------------------------------------------
    # 导航
    # ------------------------------------------------------------------
    def _goto_page(self, index: int) -> None:
        if not (0 <= index < self.stack.count()):
            index = PAGE_INTERPRETERS
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

    # ------------------------------------------------------------------
    # 扫描
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
        QMessageBox.warning(self, "解释器扫描失败", message)

    def _on_scan_done(self, report) -> None:
        worker = self._scan_worker
        if worker is None or self.sender() is not worker:
            return
        self._scan_worker = None
        worker.deleteLater()
        self.interp_page.set_scanning(False)
        self.interp_page.show_interpreters(report.interpreters)
        self._interpreters = list(report.interpreters)
        self.manage_page.set_data(self._interpreters, self._conda_info)
        self.compare_page.set_interpreters(
            self._interpreters,
            current_path=self._settings.get(Settings.KEY_LAST_PYTHON, "") or "")
        self.compare_page.set_selection(
            self._settings.get(Settings.KEY_COMPARE_A, "") or "",
            self._settings.get(Settings.KEY_COMPARE_B, "") or "")
        self.reports_page.set_interpreters(
            self._interpreters,
            current_path=self._snapshot.interpreter.path if self._snapshot
            else (self._settings.get(Settings.KEY_LAST_PYTHON, "") or ""))
        n = len(report.interpreters)
        self.statusBar().showMessage(f"扫描完成: 发现 {n} 个 Python 解释器")
        self.start_conda_scan()

    # ------------------------------------------------------------------
    # Conda
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
            return
        self._conda_worker = None
        worker.deleteLater()
        self._conda_info = info
        self.conda_page.load_conda(info)
        self.manage_page.set_data(self._interpreters, info)
        if not info.roots:
            self.statusBar().showMessage(
                f"未检测到 conda 安装: {info.errors[0]}" if info.errors
                else "未检测到 conda 安装")
            return
        self.statusBar().showMessage(
            f"Conda 扫描完成: {len(info.envs)} 个环境 · "
            f"{info.total_conda_packages} 个原生包")

    def _on_conda_environment_activated(self, env_path: str) -> None:
        target = os.path.normcase(os.path.normpath(env_path))
        for info in self._interpreters:
            if info.source == "conda":
                exe_dir = os.path.dirname(os.path.normpath(info.path))
                env_dir = os.path.dirname(exe_dir) if os.name != "nt" else exe_dir
                if os.path.normcase(os.path.normpath(env_dir)) == target:
                    self._on_interpreter_activated(info)
                    return
        exe = "python.exe" if os.name == "nt" else os.path.join("bin", "python")
        self._on_interpreter_activated(InterpreterInfo(
            path=os.path.join(env_path, exe), source="conda",
            env_name=os.path.basename(os.path.normpath(env_path))))

    # ------------------------------------------------------------------
    # 采集
    # ------------------------------------------------------------------
    def _on_interpreter_activated(self, interp: InterpreterInfo) -> None:
        cached = self._snapshots.get(interp.path)
        if cached is None:
            cached = cache.load_snapshot(interp.path)   # 跨重启缓存
            if cached is not None:
                self._snapshots[interp.path] = cached
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
            self.statusBar().showMessage("正在读取环境包信息, 请稍候…(可点状态栏取消)")
            return
        if force:
            self._snapshots.pop(interp.path, None)
            cache.invalidate(interp.path)
        self.interp_page.set_scanning(True, "正在读取包元数据…")
        self.statusBar().showMessage(f"正在采集 {interp.path} 的包信息…")
        self._collect_worker = CollectWorker(interp, self)
        self._collect_worker.progress.connect(self.statusBar().showMessage)
        self._collect_worker.done.connect(self._on_collect_done)
        self._collect_worker.failed.connect(self._on_collect_failed)
        self._collect_worker.start()

    def cancel_collect(self) -> None:
        """取消进行中的采集(供外部/快捷键调用)。"""
        if self._collect_worker is not None:
            self._collect_worker.cancel()
            self.statusBar().showMessage("正在取消采集…")

    def _on_collect_done(self, snapshot: EnvironmentSnapshot) -> None:
        worker = self._collect_worker
        if worker is None or self.sender() is not worker:
            return
        self._collect_worker = None
        worker.deleteLater()
        self.interp_page.set_scanning(False)
        self._snapshots[snapshot.interpreter.path] = snapshot
        try:
            cache.save_snapshot(snapshot)   # 落盘: 跨重启复用 + 历史对比
        except OSError as exc:
            log.warning("快照写入缓存失败: %s", exc)
        if self._compare_pending:
            self._try_compare()
            return
        # 诊断页选定环境触发的采集: 只刷新报告, 不切页
        if self._reports_pending and os.path.normcase(
                snapshot.interpreter.path) == os.path.normcase(
                self._reports_pending):
            self._reports_pending = None
            self._snapshot = snapshot
            self.statusBar().showMessage(
                f"正在诊断 {snapshot.interpreter.path} …")
            self._apply_snapshot(snapshot, purpose="reports")
            return
        self._apply_snapshot(snapshot)

    def _on_collect_failed(self, message: str) -> None:
        worker = self._collect_worker
        if worker is None or self.sender() is not worker:
            return
        self._collect_worker = None
        worker.deleteLater()
        self.interp_page.set_scanning(False)
        self.statusBar().showMessage(f"采集失败: {message}")
        if self._compare_pending:
            self._compare_pending = None
            self._compare_need.clear()
            self.compare_page.set_busy(False, f"采集失败: {message}")
            return
        QMessageBox.warning(self, "包信息采集失败", message)

    # ------------------------------------------------------------------
    # 分析(后台)
    # ------------------------------------------------------------------
    def _apply_snapshot(self, snapshot: EnvironmentSnapshot,
                        purpose: str = "normal") -> None:
        self._snapshot = snapshot
        self._analysis_purpose = purpose
        interp = snapshot.interpreter
        self.manage_page.set_current_env_dir(self._env_dir_of(interp.path))
        self.statusBar().showMessage(
            f"正在分析 {interp.path} 的 {len(snapshot.packages)} 个包…")
        if self._analysis_worker is not None and self._analysis_worker.isRunning():
            self._analysis_worker.wait(1500)
        self._analysis_worker = AnalysisWorker(snapshot, self)
        self._analysis_worker.done.connect(self._on_analysis_done)
        self._analysis_worker.failed.connect(self._on_analysis_failed)
        self._analysis_worker.start()

    def _on_analysis_failed(self, message: str) -> None:
        worker = self._analysis_worker
        if worker is None or self.sender() is not worker:
            return
        self._analysis_worker = None
        worker.deleteLater()
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "依赖分析失败", message)

    def _on_analysis_done(self, result) -> None:
        worker = self._analysis_worker
        if worker is None or self.sender() is not worker:
            return
        self._analysis_worker = None
        worker.deleteLater()
        self.packages_page.load_analysis(result)
        self.analysis_page.load_analysis(result)
        self._refresh_reports(result)
        interp = result.snapshot.interpreter
        stats = result.stats
        self.statusBar().showMessage(
            f"环境: Python {interp.version} · {interp.path} · "
            f"{stats['packages']} 个包 · 冲突 {stats['conflicts']} · "
            f"缺失 {stats['missing']}")
        if self._analysis_purpose == "reports":
            # 从诊断页发起: 停留原页面, 仅刷新报告
            self._analysis_purpose = "normal"
            self._goto_page(PAGE_REPORTS)
            return
        self._analysis_purpose = "normal"
        if self.stack.currentIndex() == PAGE_INTERPRETERS:
            self._goto_page(PAGE_PACKAGES)

    # ------------------------------------------------------------------
    # 诊断与报告
    # ------------------------------------------------------------------
    def _refresh_reports(self, result=None) -> None:
        if self._snapshot is None:
            return
        if result is None:
            # 从已有分析结果重新体检(用户点"重新体检")
            result = self._current_result()
        snapshot = self._snapshot
        reports = self.reports_page
        reports.set_interpreters(self._interpreters,
                                 current_path=snapshot.interpreter.path)
        reports.set_snapshot(snapshot)
        diag = diag_mod.run_diagnostics(snapshot, result, self._interpreters)
        reports.show_diagnostics(diag, result)
        reports.show_licenses(licenses.aggregate(snapshot))
        try:
            history = cache.load_history(snapshot.interpreter.path)
        except OSError:
            history = []
        reports.set_history(history)

    # -- 诊断页: 选定解释器 / 一键修复 ------------------------------------
    def _on_reports_interpreter(self, path: str) -> None:
        """诊断页切换目标解释器 → 加载(必要时采集)并诊断该环境。"""
        if not path:
            return
        snapshot = self._snapshots.get(path) or cache.load_snapshot(path)
        if snapshot is not None:
            self._snapshots[path] = snapshot
            if self._snapshot is not None and os.path.normcase(
                    self._snapshot.interpreter.path) == os.path.normcase(path):
                # 已是当前环境: 直接刷报告, 不重复分析
                self._refresh_reports()
                return
            self._apply_snapshot(snapshot, purpose="reports")
            return
        if self._collect_worker is not None and self._collect_worker.isRunning():
            self.statusBar().showMessage("正在采集其它环境, 请稍候…")
            return
        info = next((i for i in self._interpreters
                     if os.path.normcase(i.path) == os.path.normcase(path)),
                    None)
        if info is None:
            info = InterpreterInfo(path=path, source="path")
        self._reports_pending = path
        self.reports_page._subtitle.setText(f"正在采集 {path} …")
        self._collect(info, force=False)

    def _on_fix_all(self, python_path: str, expressions: list) -> None:
        """一键修复: 交给管理页批量执行(复用其日志与进度反馈)。"""
        if not expressions:
            return
        self._goto_page(PAGE_MANAGE)
        self.manage_page.run_pip_install_batch(python_path, expressions)
        # 修复完成后需要刷新诊断页: 包变更会经 packages_changed 回流
        self._reports_pending = python_path

    def _current_result(self):
        """当前分析结果(从分析页取, 避免重复分析)。"""
        return getattr(self.analysis_page, "_analysis", None)

    # ------------------------------------------------------------------
    # 环境对比
    # ------------------------------------------------------------------
    def _on_compare_requested(self, a_path: str, b_path: str) -> None:
        self._compare_pending = (a_path, b_path)
        self._compare_need = set()
        for path in (a_path, b_path):
            snapshot = self._snapshots.get(path) or cache.load_snapshot(path)
            if snapshot is not None:
                self._snapshots[path] = snapshot
            else:
                self._compare_need.add(path)
        if not self._compare_need:
            self._try_compare()
            return
        self._goto_page(PAGE_COMPARE)
        if self._collect_worker is not None and self._collect_worker.isRunning():
            return
        self._collect_next_for_compare()

    def _collect_next_for_compare(self) -> None:
        if not self._compare_need:
            return
        path = next(iter(self._compare_need))
        info = next((i for i in self._interpreters if i.path == path), None)
        if info is None:
            info = InterpreterInfo(path=path, source="path")
        self.compare_page.set_busy(True, f"正在采集 {path} …")
        self._collect(info, force=False)

    def _try_compare(self) -> None:
        if not self._compare_pending:
            return
        a_path, b_path = self._compare_pending
        snap_a = self._snapshots.get(a_path) or cache.load_snapshot(a_path)
        snap_b = self._snapshots.get(b_path) or cache.load_snapshot(b_path)
        if snap_a is None or snap_b is None:
            if self._compare_need:
                self._compare_need.discard(a_path)
                self._compare_need.discard(b_path)
                self._collect_next_for_compare()
            return
        self._snapshots[a_path] = snap_a
        self._snapshots[b_path] = snap_b
        self._compare_pending = None
        self._compare_need.clear()
        self.compare_page.set_busy(False)
        try:
            self.compare_page.show_result(compare_snapshots(snap_a, snap_b))
        except Exception as exc:
            log.exception("环境对比失败")
            self.compare_page.show_error(f"对比失败: {exc}")

    # ------------------------------------------------------------------
    # 冲突修复(转交管理页执行, 复用其日志与反馈)
    # ------------------------------------------------------------------
    def _on_fix_requested(self, python_exe: str, expression: str) -> None:
        self._goto_page(PAGE_MANAGE)
        self.manage_page.run_pip_install(python_exe, expression)

    # ------------------------------------------------------------------
    @staticmethod
    def _env_dir_of(python_path: str) -> str:
        d = os.path.dirname(os.path.normpath(python_path))
        if os.name != "nt" and os.path.basename(d).lower() == "bin":
            return os.path.dirname(d)
        return d

    def _on_packages_changed(self, python_path: str) -> None:
        target = os.path.normcase(python_path)
        for key in list(self._snapshots):
            snap = self._snapshots[key]
            if snap.interpreter.path and os.path.normcase(
                    snap.interpreter.path) == target:
                del self._snapshots[key]
        cache.invalidate(python_path)

        current = self._snapshot.interpreter.path if self._snapshot else ""
        reports_target = self.reports_page.selected_path()

        if current and os.path.normcase(current) == target:
            self._collect(self._snapshot.interpreter, force=True)
            return
        # 修复的不是"当前浏览环境", 但可能是诊断页选中的环境:
        # 采集后只刷新报告(_reports_pending 机制)
        if reports_target and os.path.normcase(reports_target) == target:
            info = next((i for i in self._interpreters
                         if os.path.normcase(i.path) == target), None)
            if info is None:
                info = InterpreterInfo(path=python_path, source="path")
            self._reports_pending = python_path
            self._collect(info, force=True)

    def _on_package_activated(self, key: str) -> None:
        self._goto_page(PAGE_ANALYSIS)
        self.analysis_page.focus_package(key)

    # ------------------------------------------------------------------
    # 更新检查(静默)
    # ------------------------------------------------------------------
    def _maybe_check_updates(self) -> None:
        if not self._settings.get_bool(Settings.KEY_CHECK_UPDATES, True):
            return
        self._update_worker = UpdateCheckWorker(__version__, self)
        self._update_worker.done.connect(self._on_update_checked)
        self._update_worker.start()

    def _on_update_checked(self, result) -> None:
        worker = self._update_worker
        if worker is None or self.sender() is not worker:
            return
        self._update_worker = None
        worker.deleteLater()
        if result.error:
            log.info("更新检查未完成: %s", result.error)
            self._update_text = "更新检查未完成(网络不可用, 不影响使用)"
        elif result.has_update:
            self._update_text = (
                f"发现新版本 {result.latest}(当前 v{__version__})。\n"
                f"下载: {result.url}")
            self.statusBar().showMessage(
                f"发现新版本 {result.latest}(当前 v{__version__}) · {result.url}",
                20000)
            log.info("发现新版本: %s", result.latest)
        else:
            self._update_text = f"已是最新版本 v{__version__}"
        if self._about_dialog is not None:
            self._about_dialog.set_update_text(self._update_text)

    # ------------------------------------------------------------------
    # 演示数据
    # ------------------------------------------------------------------
    def load_demo(self) -> None:
        for worker in (self._conda_worker, self._collect_worker,
                       self._scan_worker, self._analysis_worker):
            if worker is None:
                continue
            try:
                if hasattr(worker, "cancel"):
                    worker.cancel()
                if worker.isRunning() and not self._retire_worker(worker, 15000):
                    continue
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
        self._analysis_worker = None
        self.interp_page.set_scanning(False)

        snapshot = build_demo_snapshot()
        snapshot.is_demo = True
        self._snapshots[snapshot.interpreter.path] = snapshot
        demo_conda = build_demo_conda_info()
        for env in demo_conda.envs:
            if env.interpreter and env.interpreter not in self._snapshots:
                env_snapshot = build_demo_env_snapshot(env)
                env_snapshot.is_demo = True
                self._snapshots[env.interpreter] = env_snapshot
        demo_interpreters = [build_demo_interpreter()] + [
            build_demo_env_snapshot(e).interpreter for e in demo_conda.envs]
        self._interpreters = demo_interpreters
        self.conda_page.load_conda(demo_conda)
        self.manage_page.set_data(demo_interpreters, demo_conda)
        self.compare_page.set_interpreters(demo_interpreters)
        self._apply_snapshot(snapshot)
        self.statusBar().showMessage("已加载演示数据(假想环境, 含冲突/缺失/循环示例)")

    _load_demo = load_demo
