"""离屏渲染截图验证:不打开真实窗口, 验证 UI 可构建并导出各页面截图。

运行:  QT_QPA_PLATFORM=offscreen python scripts/ui_screenshot.py [输出目录]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def main() -> int:
    # offscreen 平台默认只加载 Qt 内置字体; 字体目录与平台独立设置
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    fontdir = r"C:\Windows\Fonts"
    if os.path.isdir(fontdir):
        os.environ.setdefault("QT_QPA_FONTDIR", fontdir)
    from PySide6.QtWidgets import QApplication

    from app.ui.theme import apply_theme

    app = QApplication(sys.argv)
    apply_theme(app)

    from app.main_window import MainWindow

    win = MainWindow()
    win.resize(1240, 800)
    win.show()
    app.processEvents()

    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) 解释器页(等待扫描线程片刻, 真实数据)
    from PySide6.QtCore import QDeadlineTimer, QThread

    def settle(ms: int = 300) -> None:
        """处理事件队列若干轮, 确保布局事件(异步 LayoutRequest)完成。"""
        for _ in range(8):
            app.processEvents()
            QThread.msleep(max(ms // 8, 10))
        app.processEvents()

    if win._scan_worker is not None:
        if not win._scan_worker.wait(QDeadlineTimer(20000)):
            print("SCAN_TIMEOUT: 扫描线程 20s 内未结束, 截图不可信",
                  file=sys.stderr)
            return 1
    settle(500)

    def grab_to(name: str) -> int:
        path = os.path.join(OUT_DIR, name)
        if not win.grab().save(path):
            print(f"SCREENSHOT_FAILED: {path}", file=sys.stderr)
            return 1
        return 0

    # 1) 解释器页(真实扫描数据)
    if grab_to("shot_1_interpreters.png"):
        return 1

    # 1b) Conda 页(真实扫描数据; 解释器扫描完成后 conda 扫描自动启动)
    conda_worker = win._conda_worker
    if conda_worker is not None and not conda_worker.wait(QDeadlineTimer(30000)):
        print("CONDA_TIMEOUT: conda 扫描线程 30s 内未结束, 截图不可信",
              file=sys.stderr)
        return 1
    win._goto_page(3)
    settle(400)
    if grab_to("shot_8_conda.png"):
        return 1

    # 2) 演示数据 → 包列表页(load_demo 会排空 conda worker 并加载演示 conda)
    win._load_demo()
    settle(400)
    if grab_to("shot_2_packages.png"):
        return 1

    # 3) 依赖分析页 - 依赖图(等待入场动画播完, 拍最终状态)
    win._goto_page(2)
    settle(1700)
    if grab_to("shot_3_graph.png"):
        return 1

    # 4) 冲突清单
    win.analysis_page.tabs.setCurrentIndex(1)
    settle(150)
    if grab_to("shot_4_conflicts.png"):
        return 1

    # 5) 冲突链条聚焦(点击第一行冲突)
    model = win.analysis_page.conflict_table.model()
    if model.rowCount() == 0:
        print("SCREENSHOT_SKIPPED: 冲突表为空, 跳过 shot_5_focus.png",
              file=sys.stderr)
    else:
        win.analysis_page._on_conflict_clicked(model.index(0, 0))
        settle(400)
        if grab_to("shot_5_focus.png"):
            return 1

    # 6) 循环依赖 & 冲突矩阵
    win.analysis_page.tabs.setCurrentIndex(2)
    settle(150)
    if grab_to("shot_6_cycles.png"):
        return 1
    win.analysis_page.tabs.setCurrentIndex(3)
    settle(150)
    if grab_to("shot_7_matrix.png"):
        return 1

    # 7) Conda 页(演示数据)
    win._goto_page(3)
    settle(400)
    if grab_to("shot_9_conda_demo.png"):
        return 1

    # 8) 环境管理页(演示数据: 解释器/venv/conda 环境/包管理)
    win._goto_page(4)
    settle(400)
    if grab_to("shot_10_manage.png"):
        return 1
    win.manage_page.tabs.setCurrentIndex(1)   # venv Tab
    settle(150)
    if grab_to("shot_11_venv.png"):
        return 1
    win.manage_page.tabs.setCurrentIndex(3)   # 包管理 Tab
    settle(150)
    if grab_to("shot_12_packages_mgmt.png"):
        return 1

    # 9) 环境对比(用演示数据里的两个环境)
    win._goto_page(5)
    if win.compare_page.combo_a.count() >= 2:
        a = win.compare_page.combo_a.itemData(0)
        b = win.compare_page.combo_b.itemData(1)
        win._on_compare_requested(a, b)
        settle(700)
    if grab_to("shot_13_compare.png"):
        return 1

    # 10) 诊断与报告
    win._goto_page(6)
    settle(300)
    if grab_to("shot_14_reports.png"):
        return 1
    win.reports_page.tabs.setCurrentIndex(1)   # 许可证
    settle(150)
    if grab_to("shot_15_licenses.png"):
        return 1
    win.reports_page.tabs.setCurrentIndex(2)   # 历史变化
    settle(150)
    if grab_to("shot_16_history.png"):
        return 1

    # 11) 深色主题 + 关于面板(实时切换, 无需重启)
    win._toggle_theme()
    settle(900)
    win._goto_page(6)
    settle(400)
    if grab_to("shot_18_reports_dark.png"):
        return 1
    win.open_about()
    settle(600)
    if win._about_dialog is not None:
        path = os.path.join(OUT_DIR, "shot_19_about.png")
        if not win._about_dialog.grab().save(path):
            print(f"SCREENSHOT_FAILED: {path}", file=sys.stderr)
            return 1
        win._about_dialog.close()
    win._toggle_theme()   # 切回浅色, 保持后续截图风格一致
    settle(600)

    print("SCREENSHOTS_OK:", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
