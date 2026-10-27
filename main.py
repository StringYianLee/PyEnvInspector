"""PyEnv Inspector 程序入口。

用法:
    python main.py            # 正常启动 GUI
    python main.py --demo     # 直接加载演示数据启动
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.theme import apply_theme
    except ModuleNotFoundError as err:
        print(f"缺少依赖模块 {err.name}, 请先执行:  pip install PySide6 packaging")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("PyEnv Inspector")
    app.setOrganizationName("PyEnvInspector")
    apply_theme(app)

    try:
        from app.main_window import MainWindow
    except ModuleNotFoundError as err:
        print(f"缺少依赖模块 {err.name}, 请先执行:  pip install PySide6 packaging")
        return 1

    win = MainWindow()
    win.show()

    if "--demo" in sys.argv:
        # 投递到事件循环: UI 就绪后立即加载演示数据
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, win.load_demo)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
