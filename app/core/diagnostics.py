"""环境体检(诊断): 找出容易出问题但看包列表看不出来的状况。

检查项(全部本地计算, 无网络):
1. PATH 遮蔽 —— 多个解释器目录同时在 PATH 中, 命令行 python 实际只命中第一个
2. 非法版本号 —— 非 PEP 440, 会让 pip 的依赖解析行为不可预期
3. 版本未知 —— 元数据缺版本(手工拷贝/损坏安装)
4. 依赖问题汇总 —— 冲突 / 缺失 / 未知 的边, 指向对应包
5. 许可证缺失 —— 无法确认合规性(配合许可证聚合使用)
6. 循环依赖 —— 打包/升级时的常见死结
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from packaging.version import InvalidVersion, Version

from .models import AnalysisResult, EnvironmentSnapshot, InterpreterInfo


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


@dataclass
class Issue:
    severity: Severity
    title: str
    detail: str
    hint: str = ""

    @property
    def severity_label(self) -> str:
        return {Severity.ERROR: "严重", Severity.WARN: "警告",
                Severity.INFO: "提示"}[self.severity]


@dataclass
class DiagnosticReport:
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity: Severity, title: str, detail: str, hint: str = "") -> None:
        self.issues.append(Issue(severity, title, detail, hint))

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARN)

    def sorted_issues(self) -> list[Issue]:
        order = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}
        return sorted(self.issues, key=lambda i: order[i.severity])


def _env_dir_of(python_path: str) -> str:
    d = os.path.dirname(os.path.normpath(python_path))
    if os.name != "nt" and os.path.basename(d).lower() == "bin":
        return os.path.dirname(d)
    return d


def check_path_shadowing(interpreters: list[InterpreterInfo],
                         path_env: str | None = None) -> list[Issue]:
    """PATH 中多个解释器目录 → 只有第一个生效。"""
    path_env = path_env if path_env is not None else os.environ.get("PATH", "")
    entries = [p.strip().strip('"') for p in path_env.split(os.pathsep)]
    norm_entries = [os.path.normcase(os.path.normpath(p)) for p in entries if p]

    hits: list[tuple[int, InterpreterInfo]] = []
    for info in interpreters:
        env_dir = _env_dir_of(info.path)
        key = os.path.normcase(os.path.normpath(env_dir))
        if key in norm_entries:
            hits.append((norm_entries.index(key), info))

    if len(hits) < 2:
        return []
    hits.sort(key=lambda x: x[0])
    winner = hits[0][1]
    losers = [h[1] for h in hits[1:]]
    detail = (f"PATH 中同时存在 {len(hits)} 个解释器目录, 命令行 `python` 实际生效的是:"
              f"\n  ✔ {winner.path} (Python {winner.version})")
    for info in losers:
        detail += f"\n  ✘ {info.path} (Python {info.version}) — 被遮蔽"
    return [Issue(
        Severity.WARN, "PATH 中存在多个 Python, 命令实际指向第一个", detail,
        "如需切换默认版本, 调整系统环境变量中目录的前后顺序, 或显式使用绝对路径。")]


def run_diagnostics(
    snapshot: EnvironmentSnapshot,
    result: AnalysisResult | None = None,
    interpreters: list[InterpreterInfo] | None = None,
) -> DiagnosticReport:
    """对该环境执行全部体检项。"""
    report = DiagnosticReport()

    # 1) PATH 遮蔽
    if interpreters:
        for issue in check_path_shadowing(interpreters):
            report.issues.append(issue)

    # 2) 非法版本号 / 3) 版本未知
    invalid: list[str] = []
    unknown_ver: list[str] = []
    for p in snapshot.packages:
        if not p.version:
            unknown_ver.append(p.name)
            continue
        try:
            Version(p.version)
        except InvalidVersion:
            invalid.append(f"{p.name} {p.version}")

    if invalid:
        report.add(
            Severity.WARN, f"{len(invalid)} 个包使用了非 PEP 440 版本号",
            "这些版本号会让 pip 的依赖解析结果不可预期:\n  "
            + "\n  ".join(invalid[:12])
            + ("\n  …" if len(invalid) > 12 else ""),
            "建议重新安装为符合规范的正式发行版。")
    if unknown_ver:
        report.add(
            Severity.WARN, f"{len(unknown_ver)} 个包缺少版本信息",
            "元数据中没有版本号(常见于手工拷贝的 site-packages):\n  "
            + "\n  ".join(unknown_ver[:12])
            + ("\n  …" if len(unknown_ver) > 12 else ""),
            "可用 `python -m pip install --force-reinstall <包名>` 修复。")

    # 4) 依赖问题汇总 / 6) 循环
    if result is not None:
        if result.conflict_edges:
            report.add(
                Severity.ERROR, f"{len(result.conflict_edges)} 条版本冲突",
                "\n".join(f"  {e.source_display} → {e.target_display}: {e.message}"
                          for e in result.conflict_edges[:12]),
                "在「依赖分析 → 冲突清单」中可一键生成修复命令。")
        if result.missing_edges:
            report.add(
                Severity.WARN, f"{len(result.missing_edges)} 个依赖未安装",
                "\n".join(f"  {e.source_display} 需要 {e.target_display}"
                          for e in result.missing_edges[:12]),
                "用 `pip install <包名>` 补齐, 或确认该包不是必需依赖。")
        if result.unknown_edges:
            report.add(
                Severity.INFO, f"{len(result.unknown_edges)} 条依赖声明无法判定",
                "\n".join(f"  {e.source_display} → {e.target_display}: {e.message}"
                          for e in result.unknown_edges[:8]),
                "多见于 URL 依赖、本地路径依赖与不规范元数据。")
        if result.cycles:
            report.add(
                Severity.WARN, f"{len(result.cycles)} 组循环依赖",
                "\n".join("  " + " → ".join(c + [c[0]]) for c in result.cycles[:6]),
                "循环依赖通常是打包/元数据错误, 升级相关包有时可消除。")

    # 5) 许可证缺失
    missing_license = [p.name for p in snapshot.packages if not p.license_text]
    if snapshot.packages:
        ratio = len(missing_license) / len(snapshot.packages)
        if ratio >= 0.5:
            report.add(
                Severity.INFO,
                f"{len(missing_license)} 个包未声明许可证({ratio:.0%})",
                "无法自动确认合规性, 许可证汇总中会归入「未声明」:\n  "
                + "\n  ".join(missing_license[:12])
                + ("\n  …" if len(missing_license) > 12 else ""),
                "对外分发前建议人工核对这些包的许可条款。")

    if not report.issues:
        report.add(Severity.INFO, "未发现问题",
                   "PATH 顺序、版本号、依赖关系与许可证声明均正常。")
    return report


def build_diagnostics_text(report: DiagnosticReport,
                           snapshot: EnvironmentSnapshot) -> str:
    """体检结果文本(供导出)。"""
    import datetime
    lines = [
        "=" * 72,
        "PyEnv Inspector · 环境体检报告",
        "=" * 72,
        f"生成时间 : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"解释器   : {snapshot.interpreter.path}",
        f"Python   : {snapshot.python_full_version or snapshot.python_version}",
        f"包数量   : {len(snapshot.packages)}",
        f"结论     : 严重 {report.errors} · 警告 {report.warnings}"
        f" · 提示 {len(report.issues) - report.errors - report.warnings}",
        "",
    ]
    for i, issue in enumerate(report.sorted_issues(), 1):
        lines.append(f"[{issue.severity_label}] {i}. {issue.title}")
        lines.extend("    " + ln for ln in issue.detail.splitlines())
        if issue.hint:
            lines.append(f"    → {issue.hint}")
        lines.append("")
    return "\n".join(lines) + "\n"
