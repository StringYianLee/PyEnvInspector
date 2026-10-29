"""回归测试: 子进程不弹控制台 + 诊断页切换目标解释器不递归。

对应线上两个缺陷:
1. 打开软件后不停弹出 cmd 黑框 —— 探测/conda 子进程未隐藏控制台;
2. 诊断页选择目标解释器后闪退/卡死 —— set_interpreters 恢复选中项时
   触发 currentIndexChanged, 形成 "填充→诊断→刷新→再填充" 无限递归。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from app.core import scanner  # noqa: E402
from app.core.subproc import hidden_kwargs  # noqa: E402


# ---------------------------------------------------------------------------
# 子进程隐藏控制台
# ---------------------------------------------------------------------------

def test_hidden_kwargs_windows_flags():
    kw = hidden_kwargs()
    if os.name == "nt":
        assert kw["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert kw["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert kw["startupinfo"].wShowWindow == subprocess.SW_HIDE
    else:
        assert kw["start_new_session"] is True


def test_probe_interpreter_hides_console(monkeypatch):
    """解释器探测是启动时最高频的子进程调用, 必须隐藏控制台。"""
    captured: list[dict] = []

    class FakeProc:
        returncode = 0
        stdout = ('{"version": "3.12.4", "implementation": "cpython", '
                  '"arch": "64bit", "prefix": "C:/py", '
                  '"base_prefix": "C:/py", "executable": "C:/py/python.exe"}')
        stderr = ""

    def fake_run(argv, **kwargs):
        captured.append(kwargs)
        return FakeProc()

    monkeypatch.setattr(scanner.subprocess, "run", fake_run)
    info = scanner.probe_interpreter(sys.executable, "path")
    assert not info.probe_error
    assert captured, "应至少启动一次探测子进程"
    if os.name == "nt":
        assert all("creationflags" in kw for kw in captured), captured
        assert all(kw["creationflags"] == subprocess.CREATE_NO_WINDOW
                   for kw in captured)
        assert all("startupinfo" in kw for kw in captured)


def test_conda_version_hides_console(monkeypatch):
    from app.core import conda_scanner

    captured: list[dict] = []

    class FakeProc:
        returncode = 0
        stdout = "conda 24.5.0\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured.append(kwargs)
        return FakeProc()

    monkeypatch.setattr(conda_scanner.subprocess, "run", fake_run)
    assert conda_scanner._conda_version("conda.exe") == "24.5.0"
    if os.name == "nt":
        assert captured[0]["creationflags"] == subprocess.CREATE_NO_WINDOW


# ---------------------------------------------------------------------------
# 诊断页: 下拉填充不得触发选择回调(否则递归)
# ---------------------------------------------------------------------------

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.models import InterpreterInfo  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.theme import apply_theme, use_dark
    use_dark(False)
    apply_theme(app)
    return app


def test_set_interpreters_does_not_emit_selection(qapp):
    """程序化填充/保留选中项时不能发出 interpreter_selected。"""
    from app.ui.reports_page import ReportsPage

    page = ReportsPage()
    emitted: list[str] = []
    page.interpreter_selected.connect(emitted.append)

    infos = [InterpreterInfo(path=f"C:/py{i}/python.exe", version="3.12")
             for i in range(3)]
    page.set_interpreters(infos)                      # 首次填充
    page.set_interpreters(infos, current_path=infos[2].path)  # 恢复选中项
    assert emitted == [], f"填充过程不应触发选择回调, 实际: {emitted}"
    assert os.path.normcase(page.selected_path()) == os.path.normcase(
        infos[2].path)
    page.deleteLater()


def test_main_window_switch_target_no_recursion(qapp):
    """模拟用户连续切换目标解释器: 不能递归/闪退, 结果要落在所选环境。"""
    from app.main_window import MainWindow

    win = MainWindow()
    win.load_demo()

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        qapp.processEvents()
        if win.analysis_page._analysis is not None:
            break
        time.sleep(0.02)
    assert win.analysis_page._analysis is not None

    emitted: list[str] = []
    win.reports_page.interpreter_selected.connect(emitted.append)
    count = win.reports_page.interp_combo.count()
    assert count >= 2

    for idx in (1, 0, min(2, count - 1)):
        win.reports_page.interp_combo.setCurrentIndex(idx)
        end = time.monotonic() + 15
        while time.monotonic() < end:
            qapp.processEvents()
            if (win._reports_loading is None
                    and win.analysis_page._analysis is not None):
                break
            time.sleep(0.02)
        assert win._reports_loading is None, "重入标记未释放(可能卡死)"

    # 每次用户切换恰好一次信号(程序化刷新不再叠加)
    assert len(emitted) == 3, emitted
    # 报告与下拉选中项一致
    assert os.path.normcase(win.reports_page.selected_path()) == os.path.normcase(
        win.reports_page.interp_combo.currentData())
    assert "诊断" in win.reports_page.diag_summary.text() or \
        "严重" in win.reports_page.diag_summary.text()
    win.close()
