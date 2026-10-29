"""命令行接口(无 Qt 依赖, 可进 CI)。

用法示例:
    python main.py --cli envs
    python main.py --cli analyze --python "C:/Python312/python.exe"
    python main.py --cli analyze --python ... --json --fail-on-conflict
    python main.py --cli export --python ... --format requirements --out req.txt
    python main.py --cli compare --a <pythonA> --b <pythonB>
    python main.py --cli diagnostics --python ...
    python main.py --cli licenses --python ...

退出码: 0 成功 / 1 执行错误 / 2 检出冲突(--fail-on-conflict 时)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .core import cache, compare as compare_mod, diagnostics as diag_mod
from .core import exporter, licenses
from .core.analyzer import analyze
from .core.collector import CollectionError, collect_packages
from .core.models import EnvironmentSnapshot
from .core.scanner import find_conda_roots, probe_interpreter, scan_interpreters


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _snapshot(python_path: str, use_cache: bool = True,
              quiet: bool = False) -> EnvironmentSnapshot:
    """取目标解释器的快照(优先缓存)。"""
    if not python_path or not os.path.isfile(python_path):
        raise SystemExit(f"[错误] 解释器不存在: {python_path}")
    if use_cache:
        cached = cache.load_snapshot(python_path)
        if cached is not None:
            if not quiet:
                _err(f"[信息] 使用缓存快照({len(cached.packages)} 个包)")
            return cached
    info = probe_interpreter(python_path, "path")
    if getattr(info, "probe_error", ""):
        raise SystemExit(f"[错误] 无法运行解释器: {info.probe_error}")
    if not quiet:
        _err(f"[信息] 正在采集 {python_path} …")
    try:
        snap = collect_packages(info)
    except CollectionError as exc:
        raise SystemExit(f"[错误] {exc}") from exc
    try:
        cache.save_snapshot(snap)
    except OSError as exc:
        _err(f"[警告] 缓存写入失败: {exc}")
    return snap


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_envs(args) -> int:
    report = scan_interpreters()
    rows = report.interpreters
    if args.json:
        print(json.dumps([
            {"path": i.path, "version": i.version, "source": i.source,
             "env_name": i.env_name, "is_venv": i.is_venv,
             "implementation": i.implementation, "arch": i.arch}
            for i in rows], ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("未发现 Python 解释器")
        return 0
    print(f"{'版本':<12}{'来源':<12}{'环境':<16}路径")
    print("-" * 96)
    for i in rows:
        print(f"{i.version:<12}{i.source_label:<12}"
              f"{(i.env_name or '-'):<16}{i.path}")
    print(f"\n共 {len(rows)} 个解释器")
    return 0


def _analysis_of(snap: EnvironmentSnapshot):
    return analyze(snap)


def cmd_analyze(args) -> int:
    snap = _snapshot(args.python, use_cache=not args.no_cache, quiet=args.json)
    result = _analysis_of(snap)
    stats = result.stats
    if args.json:
        print(json.dumps(exporter.build_json(result), ensure_ascii=False, indent=2))
    else:
        print(f"解释器 : {snap.interpreter.path}")
        print(f"Python : {snap.python_full_version or snap.python_version}")
        print(f"包数量 : {stats['packages']}    依赖边: {stats['edges']}")
        print(f"冲突 {stats['conflicts']} · 缺失 {stats['missing']} · "
              f"未知 {stats['unknown']} · 循环 {stats['cycles']}")
        for label, edges in (("版本冲突", result.conflict_edges),
                             ("依赖缺失", result.missing_edges),
                             ("未知项", result.unknown_edges)):
            if edges:
                print(f"\n[{label}]")
                for e in edges:
                    print(f"  {e.source_display} → {e.target_display} "
                          f"[{e.spec or '无约束'}] {e.message}")
        for i, cycle in enumerate(result.cycles, 1):
            print(f"\n[循环依赖 {i}] " + " → ".join(cycle + [cycle[0]]))
    if args.out:
        exporter.export_report(result, args.out)
        _err(f"[信息] 报告已写入: {args.out}")
    if args.fail_on_conflict and (result.conflict_edges or result.missing_edges):
        _err("[结果] 检出依赖问题, 退出码 2")
        return 2
    return 0


def cmd_export(args) -> int:
    snap = _snapshot(args.python, use_cache=not args.no_cache)
    fmt = args.format
    default_names = {
        "requirements": "requirements.txt",
        "yaml": "environment.yml",
        "report": "report.txt",
        "dot": "deps.dot",
        "licenses": "licenses.txt",
    }
    out = args.out or default_names[fmt]
    if fmt == "requirements":
        exporter.export_requirements(snap, out)
    elif fmt == "yaml":
        exporter.export_conda_yaml(snap, out, name=args.name)
    elif fmt == "report":
        exporter.export_report(_analysis_of(snap), out)
    elif fmt == "dot":
        exporter.export_dot(_analysis_of(snap), out,
                            only_problems=args.only_problems)
    elif fmt == "licenses":
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(licenses.build_license_text(snap))
    else:  # pragma: no cover - argparse 已限定
        raise SystemExit(f"未知格式: {fmt}")
    print(f"已导出: {os.path.abspath(out)}")
    return 0


def cmd_compare(args) -> int:
    snap_a = _snapshot(args.a, use_cache=not args.no_cache)
    snap_b = _snapshot(args.b, use_cache=not args.no_cache)
    result = compare_mod.compare_snapshots(snap_a, snap_b)
    if args.json:
        print(json.dumps({
            "a": snap_a.interpreter.path, "b": snap_b.interpreter.path,
            "stats": result.stats,
            "differences": [
                {"name": d.name, "a": d.version_a, "b": d.version_b,
                 "kind": d.kind} for d in result.differences],
        }, ensure_ascii=False, indent=2))
        return 0
    print(f"A(基准): {snap_a.interpreter.path}  Python {snap_a.python_full_version}")
    print(f"B(对照): {snap_b.interpreter.path}  Python {snap_b.python_full_version}")
    st = result.stats
    print(f"\n仅 A {st['removed']} · 仅 B {st['added']} · 升级 {st['upgraded']}"
          f" · 降级 {st['downgraded']} · 无法比较 {st['changed']}")
    labels = {"removed": "仅 A", "added": "仅 B", "upgraded": "升级",
              "downgraded": "降级", "changed": "版本变化"}
    for kind, label in labels.items():
        items = [d for d in result.differences if d.kind == kind]
        if not items:
            continue
        print(f"\n[{label}]")
        for d in items:
            print(f"  {d.name:<32}{d.version_a or '-':<16}→ {d.version_b or '-'}")
    return 0


def cmd_diagnostics(args) -> int:
    snap = _snapshot(args.python, use_cache=not args.no_cache)
    result = _analysis_of(snap)
    report = diag_mod.run_diagnostics(
        snap, result, scan_interpreters().interpreters)
    if args.json:
        print(json.dumps({
            "interpreter": snap.interpreter.path,
            "errors": report.errors, "warnings": report.warnings,
            "issues": [{"severity": i.severity.value, "title": i.title,
                        "detail": i.detail, "hint": i.hint}
                       for i in report.sorted_issues()],
        }, ensure_ascii=False, indent=2))
    else:
        print(diag_mod.build_diagnostics_text(report, snap))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(diag_mod.build_diagnostics_text(report, snap))
        _err(f"[信息] 体检报告已写入: {args.out}")
    return 1 if report.errors else 0


def cmd_licenses(args) -> int:
    snap = _snapshot(args.python, use_cache=not args.no_cache)
    if args.json:
        print(json.dumps({
            "summary": licenses.category_summary(snap),
            "groups": licenses.aggregate(snap),
        }, ensure_ascii=False, indent=2))
        return 0
    text = licenses.build_license_text(snap)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        _err(f"[信息] 许可证明细已写入: {args.out}")
    return 0


def cmd_conda(args) -> int:
    roots = find_conda_roots()
    print(json.dumps({"roots": roots}, ensure_ascii=False, indent=2)
          if args.json else ("\n".join(roots) or "未发现 conda 安装"))
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyenv-inspector", description="PyEnv Inspector 命令行接口")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("envs", help="列出本机 Python 解释器")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_envs)

    for name, func, help_text in (
        ("packages", None, "列出目标环境已安装的包"),
        ("analyze", cmd_analyze, "依赖分析(冲突/缺失/循环)"),
        ("diagnostics", cmd_diagnostics, "环境体检"),
        ("licenses", cmd_licenses, "许可证汇总"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--python", required=True, help="目标解释器路径")
        p.add_argument("--json", action="store_true")
        p.add_argument("--no-cache", action="store_true", help="忽略缓存重新采集")
        if name == "analyze":
            p.add_argument("--out", help="额外导出文本报告到该路径")
            p.add_argument("--fail-on-conflict", action="store_true",
                           help="检出冲突/缺失时退出码 2(CI 用)")
        if name == "diagnostics":
            p.add_argument("--out", help="导出体检报告")
        if name == "licenses":
            p.add_argument("--out", help="导出许可证明细")
        p.set_defaults(func=func)

    p = sub.add_parser("export", help="导出 requirements/yaml/报告/DOT/许可证")
    p.add_argument("--python", required=True)
    p.add_argument("--format", required=True,
                   choices=["requirements", "yaml", "report", "dot", "licenses"])
    p.add_argument("--out", help="输出文件路径")
    p.add_argument("--name", default="environment", help="environment.yml 的环境名")
    p.add_argument("--only-problems", action="store_true",
                   help="DOT 只导出问题边")
    p.add_argument("--no-cache", action="store_true")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("compare", help="对比两个环境")
    p.add_argument("--a", required=True, help="基准环境解释器路径")
    p.add_argument("--b", required=True, help="对照环境解释器路径")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("conda", help="列出 conda 根目录")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_conda)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--cli" in argv:
        argv.remove("--cli")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "packages":
        return _cmd_packages(args)
    return int(args.func(args) or 0)


def _cmd_packages(args) -> int:
    snap = _snapshot(args.python, use_cache=not args.no_cache, quiet=args.json)
    if args.json:
        print(json.dumps(
            {p.name: p.version for p in snap.packages},
            ensure_ascii=False, indent=2))
        return 0
    print(f"{'包名':<40}版本")
    print("-" * 64)
    for p in snap.packages:
        print(f"{p.name:<40}{p.version or '?'}")
    print(f"\n共 {len(snap.packages)} 个包")
    return 0
