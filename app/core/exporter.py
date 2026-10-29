"""导出器: requirements.txt / environment.yml / 文本报告 / Graphviz DOT。

纯函数 + 文件写入, 无 UI 依赖(CLI 与界面共用同一套实现)。
"""

from __future__ import annotations

import datetime

from packaging.utils import canonicalize_name

from .models import AnalysisResult, EdgeStatus, EnvironmentSnapshot

_STATUS_LABEL = {
    EdgeStatus.VERSION_CONFLICT: "版本冲突",
    EdgeStatus.MISSING: "依赖缺失",
    EdgeStatus.UNKNOWN: "未知项",
}


# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------

def build_requirements(snapshot: EnvironmentSnapshot) -> str:
    """生成 requirements.txt 内容(pkg==version, 按名排序)。"""
    lines = [
        f"# 由 PyEnv Inspector 导出 · {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"# 目标环境: Python {snapshot.python_full_version or snapshot.python_version}"
        f" ({snapshot.platform_machine or 'unknown'})",
        f"# 解释器: {snapshot.interpreter.path}",
        f"# 共 {len(snapshot.packages)} 个包",
        "",
    ]
    for p in sorted(snapshot.packages, key=lambda x: x.name.lower()):
        if p.version:
            lines.append(f"{p.name}=={p.version}")
        else:
            lines.append(f"# {p.name}  (版本未知)")
    return "\n".join(lines) + "\n"


def export_requirements(snapshot: EnvironmentSnapshot, path: str) -> str:
    text = build_requirements(snapshot)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------------------
# environment.yml (conda)
# ---------------------------------------------------------------------------

def build_conda_yaml(snapshot: EnvironmentSnapshot, name: str = "environment") -> str:
    """生成 conda environment.yml(pip 包归入 pip: 段)。"""
    py_ver = snapshot.python_full_version or snapshot.python_version or "3"
    lines = [
        f"# 由 PyEnv Inspector 导出 · {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"name: {name}",
        "dependencies:",
        f"  - python={py_ver}",
        "  - pip",
        "  - pip:",
    ]
    for p in sorted(snapshot.packages, key=lambda x: x.name.lower()):
        if p.version:
            lines.append(f"      - {p.name}=={p.version}")
        else:
            lines.append(f"      - {p.name}")
    return "\n".join(lines) + "\n"


def export_conda_yaml(snapshot: EnvironmentSnapshot, path: str,
                      name: str = "environment") -> str:
    text = build_conda_yaml(snapshot, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------------------
# 文本报告
# ---------------------------------------------------------------------------

def build_report_text(result: AnalysisResult) -> str:
    """依赖分析纯文本报告(冲突/缺失/未知/循环 + 统计)。"""
    snap = result.snapshot
    interp = snap.interpreter
    stats = result.stats
    lines = [
        "=" * 72,
        "PyEnv Inspector · 依赖分析报告",
        "=" * 72,
        f"生成时间 : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"解释器   : {interp.path}",
        f"版本     : Python {interp.version or snap.python_full_version}"
        f" ({interp.arch or 'unknown'})",
        f"实现     : {interp.implementation or 'unknown'}",
        "",
        "-" * 72,
        "统计",
        "-" * 72,
        f"已安装包     : {stats['packages']}",
        f"依赖关系     : {stats['edges']}",
        f"版本冲突     : {stats['conflicts']}",
        f"依赖缺失     : {stats['missing']}",
        f"未知项       : {stats['unknown']}",
        f"循环依赖     : {stats['cycles']}",
        "",
    ]

    def _section(title: str, edges) -> None:
        if not edges:
            return
        lines.extend(["-" * 72, title, "-" * 72])
        for e in edges:
            lines.append(f"  {e.source_display} → {e.target_display}  [{e.spec or '无约束'}]")
            lines.append(f"      {e.message}")
        lines.append("")

    _section("版本冲突", result.conflict_edges)
    _section("依赖缺失", result.missing_edges)
    _section("未知项", result.unknown_edges)

    if result.cycles:
        lines.extend(["-" * 72, "循环依赖", "-" * 72])
        for i, cycle in enumerate(result.cycles, 1):
            lines.append(f"  环 {i}: {' → '.join(cycle)} → {cycle[0]}")
        lines.append("")

    if result.warnings:
        lines.extend(["-" * 72, "解析告警", "-" * 72])
        for w in result.warnings:
            lines.append(f"  {w}")
        lines.append("")

    if not (result.conflict_edges or result.missing_edges
            or result.unknown_edges or result.cycles):
        lines.append("✔ 未发现依赖冲突、缺失、未知项与循环。")
    return "\n".join(lines) + "\n"


def export_report(result: AnalysisResult, path: str) -> str:
    text = build_report_text(result)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------------------
# Graphviz DOT
# ---------------------------------------------------------------------------

def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_dot(result: AnalysisResult, only_problems: bool = False) -> str:
    """生成依赖图 DOT(可直接 `dot -Tsvg` 渲染)。

    :param only_problems: 只导出问题边及其端点(冲突排查视角)
    """
    lines = [
        "// 由 PyEnv Inspector 导出",
        "digraph deps {",
        '  rankdir=TB;',
        '  splines=true;',
        '  node [shape=box, style="rounded,filled", fontname="Microsoft YaHei",'
        ' fontsize=10, fillcolor="#ffffff", color="#d4dae7"];',
        '  edge [fontname="Consolas", fontsize=8, color="#c4cbdb"];',
        "",
    ]

    edges = result.edges
    if only_problems:
        edges = [e for e in edges if e.is_problem]
    used = {e.source_key for e in edges} | {e.target_key for e in edges}

    for key, pkg in sorted(result.packages.items()):
        if only_problems and key not in used:
            continue
        if not pkg.installed:
            fill, color = "#fbeee0", "#e8b478"
            label = f"{pkg.name}\\n未安装"
        elif pkg.has_conflict:
            fill, color = "#fdebec", "#dc3545"
            label = f"{pkg.name}\\n{pkg.version}"
        elif pkg.has_missing:
            fill, color = "#fdf2e2", "#e8850c"
            label = f"{pkg.name}\\n{pkg.version}"
        else:
            fill, color = "#ffffff", "#d4dae7"
            label = f"{pkg.name}\\n{pkg.version}"
        lines.append(
            f'  "{_dot_escape(pkg.name)}" [label="{label}", '
            f'fillcolor="{fill}", color="{color}"];')

    for e in edges:
        src = result.packages.get(e.source_key)
        dst = result.packages.get(e.target_key)
        if src is None or dst is None:
            continue
        attrs = []
        if e.status == EdgeStatus.VERSION_CONFLICT:
            attrs = ['color="#e4404f"', 'penwidth=2.2', 'style=dashed']
        elif e.status == EdgeStatus.MISSING:
            attrs = ['color="#ef9f3c"', 'penwidth=1.8', 'style=dashed']
        elif e.status == EdgeStatus.UNKNOWN:
            attrs = ['color="#aab2c3"', 'style=dotted']
        label = e.spec.replace('"', "'")
        attr_text = (", ".join(attrs) + f', label="{label}"') if attrs else \
            (f'label="{label}"' if label else "")
        suffix = f" [{attr_text}]" if attr_text else ""
        lines.append(
            f'  "{_dot_escape(src.name)}" -> "{_dot_escape(dst.name)}"{suffix};')

    lines.append("}")
    return "\n".join(lines) + "\n"


def export_dot(result: AnalysisResult, path: str,
               only_problems: bool = False) -> str:
    text = build_dot(result, only_problems)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------------------
# JSON(CLI / 自动化)
# ---------------------------------------------------------------------------

def build_json(result: AnalysisResult) -> dict:
    """结构化分析结果(供 CLI --json / CI 消费)。"""
    return {
        "interpreter": {
            "path": result.snapshot.interpreter.path,
            "version": result.snapshot.interpreter.version,
            "implementation": result.snapshot.interpreter.implementation,
            "python_full_version": result.snapshot.python_full_version,
        },
        "stats": result.stats,
        "conflicts": [
            {"source": e.source_display, "target": e.target_display,
             "spec": e.spec, "message": e.message}
            for e in result.conflict_edges
        ],
        "missing": [
            {"source": e.source_display, "target": e.target_display,
             "spec": e.spec}
            for e in result.missing_edges
        ],
        "unknown": [
            {"source": e.source_display, "target": e.target_display,
             "message": e.message}
            for e in result.unknown_edges
        ],
        "cycles": result.cycles,
        "warnings": result.warnings,
        "packages": {
            p.name: p.version for p in result.snapshot.packages
        },
    }


def package_map(snapshot: EnvironmentSnapshot) -> dict[str, str]:
    """{canonical name: 版本} 映射(供跨环境搜索)。"""
    return {canonicalize_name(p.name): p.version for p in snapshot.packages}
