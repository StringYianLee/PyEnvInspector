"""后台线程任务封装(QThread), 避免 UI 阻塞。"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from .core.analyzer import analyze
from .core.conda_scanner import scan_conda
from .core.collector import CollectionError, collect_packages
from .core.env_manager import EnvManagerError
from .core.layout import force_layout, hierarchical_layout
from .core.models import (
    AnalysisResult, CondaInfo, EnvironmentSnapshot, InterpreterInfo,
)
from .core.scanner import ScanReport, scan_interpreters
from .core.updater import check_latest


class ScanWorker(QThread):
    """后台扫描解释器。"""

    progress = Signal(str)
    done = Signal(object)  # ScanReport
    failed = Signal(str)

    def run(self) -> None:
        try:
            report = scan_interpreters(progress=self.progress.emit)
        except Exception as exc:  # 兜底: 任何异常都不能挂掉 UI
            self.failed.emit(f"扫描失败: {type(exc).__name__}: {exc}")
            return
        self.done.emit(report)


class CondaScanWorker(QThread):
    """后台扫描 conda 安装/环境/包/配置。"""

    progress = Signal(str)
    done = Signal(object)  # CondaInfo

    def run(self) -> None:
        try:
            info = scan_conda(progress=self.progress.emit)
        except Exception as exc:
            info = CondaInfo(errors=[f"conda 扫描失败: {type(exc).__name__}: {exc}"])
        self.done.emit(info)


class ManageWorker(QThread):
    """通用环境管理操作线程。

    :param fn: 管理函数, 其最后一个关键字参数为 ``on_output``(逐行输出回调)
    :param args: fn 的位置参数
    完成 → done(返回值); 失败 → failed(人读错误信息)。
    """

    output = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self) -> None:
        try:
            result = self._fn(*self._args, on_output=self.output.emit)
        except EnvManagerError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # 兜底: 任何异常都以人读文本回传
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(result)


class CollectWorker(QThread):
    """后台采集目标环境包列表(支持取消)。"""

    progress = Signal(str)
    done = Signal(object)     # EnvironmentSnapshot
    failed = Signal(str)

    def __init__(self, interpreter: InterpreterInfo, parent=None):
        super().__init__(parent)
        self.interpreter = interpreter
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """请求取消: 置位后采集循环会终止子进程并尽快退出。"""
        self._cancel.set()

    def run(self) -> None:
        try:
            snapshot = collect_packages(
                self.interpreter, progress=self.progress.emit,
                cancel_event=self._cancel)
        except CollectionError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(snapshot)


class AnalysisWorker(QThread):
    """后台执行依赖分析(大环境可达数千条边, 不能占用 UI 线程)。"""

    done = Signal(object)   # AnalysisResult
    failed = Signal(str)

    def __init__(self, snapshot: EnvironmentSnapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot

    def run(self) -> None:
        try:
            result = analyze(self.snapshot)
        except Exception as exc:
            self.failed.emit(f"依赖分析失败: {type(exc).__name__}: {exc}")
            return
        self.done.emit(result)


class UpdateCheckWorker(QThread):
    """后台检查 GitHub 最新 Release(失败静默, 不影响主功能)。"""

    done = Signal(object)   # UpdateResult

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self) -> None:
        try:
            result = check_latest(self.current_version)
        except Exception as exc:  # 兜底: 更新检查永不崩
            from .core.updater import UpdateResult
            result = UpdateResult(current=self.current_version,
                                  error=f"{type(exc).__name__}: {exc}")
        self.done.emit(result)


class LayoutWorker(QThread):
    """后台力导向布局(节点多时同步计算会卡顿)。"""

    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, analysis: AnalysisResult, mode: str = "force", parent=None):
        super().__init__(parent)
        self.analysis = analysis
        self.mode = mode

    def run(self) -> None:
        try:
            # 属性读取一并入 try: 任何路径都必须发出一个结果信号
            packages = self.analysis.packages
            edges = self.analysis.edges
            if self.mode == "force":
                positions = force_layout(packages, edges)
            elif self.mode == "hierarchical":
                positions = hierarchical_layout(packages, edges)
            else:
                raise ValueError(f"未知的布局模式: {self.mode!r}")
        except Exception as exc:  # 线程内异常必须回传, 否则 UI 忙碌态无法清理
            self.failed.emit(f"布局计算失败: {type(exc).__name__}: {exc}")
            return
        self.done.emit(positions)
