"""PyEnv Inspector —— Python 环境与包依赖管理工具。

模块结构:
    app.core   数据层:解释器扫描 / 包采集 / 依赖分析 / 环境管理 / 缓存 / 导出 / 诊断
    app.ui     界面层:主题 / 主窗口 / 各功能页 / 依赖图可视化
    app.cli    命令行接口(无 Qt 依赖, 可进 CI)
"""

__version__ = "1.3.0"
