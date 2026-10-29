"""版本变更记录(内置于程序, 供「关于」面板展示)。

打包后 docs/ 目录不随 exe 分发, 因此变更日志以 Python 数据结构内嵌,
与 CHANGELOG 保持一致。
"""

from __future__ import annotations

CHANGELOG: list[dict] = [
    {
        "version": "1.3.1",
        "date": "2026-10-29",
        "highlights": [
            "修复打开软件后反复弹出 cmd 黑框: 全部子进程隐藏控制台窗口",
            "修复诊断页切换目标解释器导致闪退/卡死(下拉刷新触发无限递归)",
        ],
    },
    {
        "version": "1.3.0",
        "date": "2026-10-29",
        "highlights": [
            "诊断页可选择目标解释器, 冲突诊断后一键批量修复",
            "明暗主题实时切换(无需重启), 深色模式文字对比度提升",
            "新增「关于」面板: 软件版本、运行环境、完整版本更新内容",
        ],
    },
    {
        "version": "1.2.0",
        "date": "2026-10-29",
        "highlights": [
            "新增环境对比页(仅 A / 仅 B / 升级 / 降级 + CSV 导出)",
            "新增多格式导出: requirements.txt / environment.yml / 报告 / PNG·SVG·DOT",
            "新增 venv 创建与删除、命令行模式(7 个子命令)",
            "新增环境体检、许可证聚合、采集历史变化",
            "依赖分析移入后台线程; 快照磁盘缓存(12h)与采集可取消",
            "设置持久化、日志落盘、深色主题、冲突一键修复、更新检查",
            "新增 CI: 推送 v* 标签自动构建 MSI 并发布 Release",
        ],
    },
    {
        "version": "1.1.3",
        "date": "2026-10-27",
        "highlights": [
            "修复安装 Python 报 TypeError: multiple values for 'on_output'",
        ],
    },
    {
        "version": "1.1.2",
        "date": "2026-10-27",
        "highlights": [
            "修复安装 Python 后解释器列表不刷新",
            "安装支持自定义路径与「添加到用户 Path」",
        ],
    },
    {
        "version": "1.1.1",
        "date": "2026-10-27",
        "highlights": [
            "修复滚轮缩放卡死: 事件合并 + 渲染优化",
            "修复依赖图动画导致界面无响应",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-10-27",
        "highlights": [
            "首个版本: 解释器扫描、包列表、依赖分析、依赖图/冲突矩阵",
            "Conda 环境与包扫描、环境管理(安装/删除/装卸包)",
            "MSI 安装包(PyInstaller + WiX)",
        ],
    },
]


def text_for_version(version: str) -> str:
    """某个版本的更新内容(纯文本)。"""
    for entry in CHANGELOG:
        if entry["version"] == version:
            lines = [f"v{entry['version']}  ({entry['date']})", ""]
            lines += [f"  · {item}" for item in entry["highlights"]]
            return "\n".join(lines)
    return f"v{version}: 无更新记录"


def full_text(limit: int = 6) -> str:
    """最近若干版本的完整变更记录(纯文本)。"""
    blocks: list[str] = []
    for entry in CHANGELOG[:limit]:
        blocks.append(text_for_version(entry["version"]))
    return "\n\n".join(blocks)


def latest_version() -> str:
    return CHANGELOG[0]["version"] if CHANGELOG else ""
