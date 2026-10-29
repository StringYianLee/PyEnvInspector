"""PyEnv Inspector 程序入口。

用法:
    python main.py                      # 启动图形界面
    python main.py --demo               # 启动并加载演示数据
    python main.py --cli <命令> …       # 命令行模式(无 GUI)
        envs | packages | analyze | export | compare | diagnostics | licenses
    更多: python main.py --cli --help
"""

from __future__ import annotations

import sys


def main() -> int:
    from app.core.appsettings import setup_logging

    argv = sys.argv[1:]

    # ---- 命令行模式: 不导入任何 Qt 模块 ----
    if "--cli" in argv:
        setup_logging()
        try:
            from app.cli import main as cli_main
        except ModuleNotFoundError as err:
            print(f"缺少依赖模块 {err.name}, 请先执行: pip install packaging",
                  file=sys.stderr)
            return 1
        return cli_main(argv[1:] if argv and argv[0] == "--cli" else argv)

    # ---- GUI 模式 ----
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as err:
        print(f"缺少依赖模块 {err.name}, 请先执行:  pip install PySide6 packaging")
        return 1

    log_path = setup_logging()

    from app.core.appsettings import theme_is_dark
    from app.ui.theme import apply_theme, use_dark

    use_dark(theme_is_dark())      # 必须在创建窗口之前确定色板

    app = QApplication(sys.argv)
    app.setApplicationName("PyEnv Inspector")
    app.setOrganizationName("PyEnvInspector")
    apply_theme(app)

    from app.main_window import MainWindow
    win = MainWindow()
    win.show()

    if "--demo" in sys.argv:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, win.load_demo)

    # 启动提示(便于用户反馈问题时定位日志)
    win.statusBar().showMessage(f"就绪 · 日志: {log_path}", 8000)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
