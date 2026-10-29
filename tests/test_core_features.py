"""缓存 / 对比 / 导出 / 诊断 / 许可证 单元测试。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import cache  # noqa: E402
from app.core.analyzer import analyze, suggest_constraint  # noqa: E402
from app.core.compare import compare_snapshots  # noqa: E402
from app.core.diagnostics import run_diagnostics  # noqa: E402
from app.core.exporter import (  # noqa: E402
    build_conda_yaml, build_dot, build_json, build_report_text,
    build_requirements, export_requirements,
)
from app.core.licenses import aggregate, category_summary, normalize_license  # noqa: E402
from app.core.models import (  # noqa: E402
    EnvironmentSnapshot, InstalledPackage, InterpreterInfo,
)
from app.demo import build_demo_snapshot  # noqa: E402


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

def _snap(packages, path="C:/x/python.exe"):
    return EnvironmentSnapshot(
        interpreter=InterpreterInfo(path=path, version="3.12",
                                    implementation="cpython", arch="64bit"),
        python_version="3.12", python_full_version="3.12.4",
        platform_machine="AMD64",
        packages=[InstalledPackage(n, v) for n, v in packages],
    )


def test_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "cache_root", lambda: str(tmp_path))
    snap = _snap([("numpy", "1.26.4"), ("requests", "2.31.0")])
    cache.save_snapshot(snap)
    loaded = cache.load_snapshot(snap.interpreter.path)
    assert loaded is not None
    assert {p.name: p.version for p in loaded.packages} == {
        "numpy": "1.26.4", "requests": "2.31.0"}
    assert loaded.python_full_version == "3.12.4"


def test_cache_ttl_expiry(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "cache_root", lambda: str(tmp_path))
    snap = _snap([("numpy", "1.26.4")])
    cache.save_snapshot(snap)
    # ttl=-1 视为永不过期; ttl=0 也视为不过期(见实现)
    assert cache.load_snapshot(snap.interpreter.path, ttl=-1) is not None
    # 把文件时间戳改到很久以前 → 过期
    path = cache._snapshot_file(snap.interpreter.path)
    os.utime(path, (0, 0))
    assert cache.load_snapshot(snap.interpreter.path, ttl=3600) is None
    assert cache.load_snapshot(snap.interpreter.path, ttl=-1) is not None


def test_cache_history_and_invalidate(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "cache_root", lambda: str(tmp_path))
    snap1 = _snap([("numpy", "1.26.4")])
    cache.save_snapshot(snap1)
    snap2 = _snap([("numpy", "2.0.0"), ("pandas", "2.2.1")])
    cache.save_snapshot(snap2)
    history = cache.load_history(snap1.interpreter.path)
    assert len(history) == 2
    assert history[-1]["packages"]["pandas"] == "2.2.1"

    cache.invalidate(snap1.interpreter.path)
    assert cache.load_snapshot(snap1.interpreter.path) is None
    assert len(cache.load_history(snap1.interpreter.path)) == 2   # 历史保留


def test_cached_environments(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "cache_root", lambda: str(tmp_path))
    cache.save_snapshot(_snap([("a", "1")], path="C:/py1/python.exe"))
    cache.save_snapshot(_snap([("b", "2")], path="C:/py2/python.exe"))
    envs = cache.cached_environments()
    assert len(envs) == 2
    assert {e["path"] for e in envs} == {"C:/py1/python.exe", "C:/py2/python.exe"}


def test_cache_schema_mismatch_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "cache_root", lambda: str(tmp_path))
    path = cache._snapshot_file("C:/x/python.exe")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema": 999, "packages": []}, fh)
    assert cache.load_snapshot("C:/x/python.exe") is None


# ---------------------------------------------------------------------------
# 环境对比
# ---------------------------------------------------------------------------

def test_compare_snapshots_kinds():
    a = _snap([("numpy", "1.20.0"), ("pandas", "2.0.0"), ("old", "1.0"),
               ("same", "3.0"), ("weird", "abc")])
    b = _snap([("numpy", "1.26.4"), ("pandas", "1.5.0"), ("new", "1.0"),
               ("same", "3.0"), ("weird", "xyz")])
    result = compare_snapshots(a, b)
    kinds = {d.name: d.kind for d in result.diffs}
    assert kinds["numpy"] == "upgraded"
    assert kinds["pandas"] == "downgraded"
    assert kinds["old"] == "removed"
    assert kinds["new"] == "added"
    assert kinds["same"] == "same"
    assert kinds["weird"] == "changed"
    st = result.stats
    assert st["added"] == 1 and st["removed"] == 1
    assert st["upgraded"] == 1 and st["downgraded"] == 1


def test_compare_name_normalization():
    a = _snap([("Foo_Bar", "1.0")])
    b = _snap([("foo-bar", "2.0")])
    result = compare_snapshots(a, b)
    assert len(result.diffs) == 1
    assert result.diffs[0].kind == "upgraded"


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

def test_requirements_export(monkeypatch, tmp_path):
    snap = _snap([("numpy", "1.26.4"), ("requests", "2.31.0"), ("broken", "")])
    text = build_requirements(snap)
    assert "numpy==1.26.4" in text
    assert "requests==2.31.0" in text
    assert "# broken  (版本未知)" in text
    out = tmp_path / "req.txt"
    export_requirements(snap, str(out))
    assert out.read_text(encoding="utf-8").startswith("# 由 PyEnv Inspector")


def test_conda_yaml_export():
    snap = _snap([("numpy", "1.26.4")])
    text = build_conda_yaml(snap, name="proj")
    assert "name: proj" in text
    assert "  - python=3.12.4" in text
    assert "      - numpy==1.26.4" in text


def test_report_and_dot_from_demo():
    result = analyze(build_demo_snapshot())
    report = build_report_text(result)
    assert "PyEnv Inspector · 依赖分析报告" in report
    assert "版本冲突" in report

    dot = build_dot(result, only_problems=True)
    assert dot.startswith("// 由 PyEnv Inspector 导出")
    assert "digraph deps {" in dot
    assert 'color="#e4404f"' in dot          # 冲突边红色
    # 只导出问题边 → 不应包含完全正常的孤立包
    assert dot.count("->") <= len(result.edges)


def test_build_json_structure():
    result = analyze(build_demo_snapshot())
    data = build_json(result)
    assert data["stats"]["conflicts"] >= 1
    assert data["conflicts"]
    assert "packages" in data
    json.dumps(data)   # 必须可序列化


def test_suggest_constraint_merges_specs():
    result = analyze(build_demo_snapshot())
    expression, sources = suggest_constraint(result, "numpy")
    assert expression.startswith("numpy")
    assert "<1.20" in expression
    assert sources


# ---------------------------------------------------------------------------
# 诊断
# ---------------------------------------------------------------------------

def test_diagnostics_detects_invalid_and_unknown_versions():
    snap = _snap([("good", "1.0"), ("bad", "not-a-version"), ("noversion", "")])
    report = run_diagnostics(snap, None, None)
    titles = " ".join(i.title for i in report.issues)
    assert "非 PEP 440" in titles
    assert "缺少版本信息" in titles


def test_diagnostics_path_shadowing():
    from app.core.diagnostics import check_path_shadowing
    a = InterpreterInfo(path="C:/PythonA/python.exe", version="3.12")
    b = InterpreterInfo(path="C:/PythonB/python.exe", version="3.11")
    issues = check_path_shadowing(
        [a, b], path_env="C:/PythonA;C:/PythonB")
    assert len(issues) == 1
    assert "3.12" in issues[0].detail and "3.11" in issues[0].detail
    # 只有一个在 PATH 中 → 无告警
    assert check_path_shadowing([a, b], path_env="C:/PythonA") == []


def test_diagnostics_dependency_issues_from_analysis():
    result = analyze(build_demo_snapshot())
    report = run_diagnostics(result.snapshot, result, None)
    titles = " ".join(i.title for i in report.issues)
    assert "版本冲突" in titles
    assert "未安装" in titles


# ---------------------------------------------------------------------------
# 许可证
# ---------------------------------------------------------------------------

def test_normalize_license():
    assert normalize_license("MIT License") == "MIT"
    assert normalize_license("Apache Software License") == "Apache-2.0"
    assert normalize_license("GNU Lesser General Public License v3") == "LGPL-3.0"
    assert normalize_license("BSD") == "BSD-3-Clause"
    assert normalize_license("") == "未声明"
    assert normalize_license("Weird Custom Terms") == "Weird Custom Terms"


def test_license_aggregate_and_summary():
    snap = EnvironmentSnapshot(
        interpreter=InterpreterInfo(path="C:/x/python.exe", version="3.12"),
        packages=[
            InstalledPackage("a", "1", license_text="MIT License"),
            InstalledPackage("b", "1", license_text="MIT"),
            InstalledPackage("c", "1", license_text="Apache-2.0"),
            InstalledPackage("d", "1", license_text=""),
        ])
    groups = aggregate(snap)
    by_name = {g["license"]: g for g in groups}
    assert by_name["MIT"]["count"] == 2
    assert by_name["MIT"]["category"] == "宽松许可"
    assert by_name["未声明"]["count"] == 1
    summary = category_summary(snap)
    assert summary["宽松许可"] == 3
