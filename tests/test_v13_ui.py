"""UI 级测试(离屏): 诊断页修复计划、主题实时重建、关于面板。

需要 offscreen 平台; 无 Qt 时自动跳过。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.analyzer import analyze  # noqa: E402
from app.demo import build_demo_snapshot  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui.theme import apply_theme, use_dark
    use_dark(False)
    apply_theme(app)
    return app


def test_reports_page_builds_fix_plan(qapp):
    """诊断页应根据冲突生成可执行的修复表达式。"""
    from app.ui.reports_page import ReportsPage

    page = ReportsPage()
    result = analyze(build_demo_snapshot())
    from app.core.diagnostics import run_diagnostics
    report = run_diagnostics(result.snapshot, result, [])
    page.show_diagnostics(report, result)

    assert page._fix_expressions, "演示环境存在冲突, 应生成修复计划"
    assert any("numpy" in expr for expr in page._fix_expressions)
    assert page.fix_all_btn.isEnabled()
    assert "一键修复全部冲突" in page.fix_all_btn.text()
    page.deleteLater()


def test_reports_page_no_conflict_disables_fix(qapp):
    from app.core.diagnostics import run_diagnostics
    from app.core.models import EnvironmentSnapshot, InstalledPackage, InterpreterInfo
    from app.ui.reports_page import ReportsPage

    snapshot = EnvironmentSnapshot(
        interpreter=InterpreterInfo(path="C:/py/python.exe", version="3.12"),
        python_full_version="3.12.4",
        packages=[InstalledPackage("numpy", "1.26.4")])
    result = analyze(snapshot)
    page = ReportsPage()
    page.show_diagnostics(run_diagnostics(snapshot, result, []), result)
    assert page._fix_expressions == []
    assert not page.fix_all_btn.isEnabled()
    page.deleteLater()


def test_main_window_theme_toggle_rebuilds_ui(qapp):
    """实时切换主题: 不重启、界面重建、调色板与数据保留。"""
    import time

    from app.ui.theme import Palette
    from app.main_window import MainWindow

    win = MainWindow()
    win.load_demo()

    # 等分析完成(load_demo 走后台 AnalysisWorker)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        qapp.processEvents()
        if win.analysis_page._analysis is not None:
            break
        time.sleep(0.05)
    assert win.analysis_page._analysis is not None

    original_pages = win.stack.count()
    original_bg = Palette.bg

    win._toggle_theme()          # 浅色 → 深色

    assert Palette.is_dark is True
    assert Palette.bg != original_bg
    assert win.stack.count() == original_pages
    assert "一键修复" in win.reports_page.fix_all_btn.text()

    # 重建后数据应自动恢复
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        qapp.processEvents()
        if win.analysis_page._analysis is not None:
            break
        time.sleep(0.05)
    assert win.analysis_page._analysis is not None
    win.close()


def test_about_dialog_shows_version_and_changelog(qapp):
    from app import __version__
    from app.ui.about_dialog import AboutDialog

    dialog = AboutDialog(None, update_text="已是最新版本")
    assert __version__ in dialog._version.text()
    text = dialog._changelog.toPlainText()
    assert "v1.3.0" in text and "v1.2.0" in text
    dialog.close()
