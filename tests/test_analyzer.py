"""analyzer 依赖分析与冲突判定单元测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.analyzer import analyze, _normalize_requirement_string  # noqa: E402
from app.core.models import (  # noqa: E402
    EdgeStatus, EnvironmentSnapshot, InstalledPackage, InterpreterInfo,
)


def make_snapshot(packages, py="3.12", full="3.12.4"):
    interp = InterpreterInfo(path="C:/Demo/python.exe", version=full,
                             implementation="cpython", arch="64bit")
    return EnvironmentSnapshot(
        interpreter=interp, python_version=py, python_full_version=full,
        platform_machine="AMD64", packages=packages,
    )


def find_edge(result, src, dst):
    for e in result.edges:
        if e.source_key == src and e.target_key == dst:
            return e
    return None


def test_version_conflict_detected():
    snap = make_snapshot([
        InstalledPackage("numpy", "1.26.4", []),
        InstalledPackage("old-lib", "0.9", ["numpy<1.20"]),
    ])
    result = analyze(snap)
    edge = find_edge(result, "old-lib", "numpy")
    assert edge is not None
    assert edge.status == EdgeStatus.VERSION_CONFLICT
    assert "1.26.4" in edge.message
    assert result.stats["conflicts"] == 1


def test_satisfied_dependency_ok():
    snap = make_snapshot([
        InstalledPackage("numpy", "1.26.4", []),
        InstalledPackage("pandas", "2.2", ["numpy>=1.22"]),
    ])
    result = analyze(snap)
    edge = find_edge(result, "pandas", "numpy")
    assert edge is not None
    assert edge.status == EdgeStatus.OK
    assert result.stats["conflicts"] == 0


def test_missing_dependency():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["six>=1.5"]),
    ])
    result = analyze(snap)
    edge = find_edge(result, "a", "six")
    assert edge is not None
    assert edge.status == EdgeStatus.MISSING
    assert result.stats["missing"] == 1
    # 幽灵占位包
    assert "six" in result.packages
    assert result.packages["six"].installed is False


def test_marker_not_applicable_is_skipped():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["ujson; platform_system != 'Windows'"]),
    ])
    result = analyze(snap)
    assert find_edge(result, "a", "ujson") is None
    assert all(e.status != EdgeStatus.INACTIVE for e in result.edges)
    assert result.stats["edges"] == 0


def test_marker_uses_target_python_version():
    # 目标环境 3.12, 依赖要求 python_version < "3.8" → 不适用
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ['old-thing; python_version < "3.8"']),
    ], py="3.12", full="3.12.4")
    result = analyze(snap)
    assert result.stats["edges"] == 0
    # 目标环境 3.6, 同一依赖适用 → 缺失
    snap2 = make_snapshot([
        InstalledPackage("a", "1.0", ['old-thing; python_version < "3.8"']),
    ], py="3.6", full="3.6.8")
    result2 = analyze(snap2)
    assert result2.stats["missing"] == 1


def test_extras_not_enabled_skipped():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["requests[socks]>=2.28"]),
        InstalledPackage("requests", "2.31.0",
                         ["socks; extra == 'socks'", "certifi>=2017"]),
        InstalledPackage("certifi", "2024.2", []),
    ])
    result = analyze(snap)
    # extra == 'socks' 的边不应出现
    assert find_edge(result, "requests", "socks") is None
    # 非 extras 边正常
    assert find_edge(result, "requests", "certifi") is not None


def test_url_dependency_unknown():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["local-wheel @ file:///wheels/x.whl"]),
    ])
    result = analyze(snap)
    assert result.stats["unknown"] >= 1


def test_invalid_version_unknown():
    snap = make_snapshot([
        InstalledPackage("weird", "final", []),
        InstalledPackage("needs-weird", "1.0", ["weird>1"]),
    ])
    result = analyze(snap)
    edge = find_edge(result, "needs-weird", "weird")
    assert edge is not None
    assert edge.status == EdgeStatus.UNKNOWN


def test_cycle_detection():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["b>=1"]),
        InstalledPackage("b", "1.0", ["a>=1"]),
        InstalledPackage("c", "1.0", []),
    ])
    result = analyze(snap)
    assert len(result.cycles) == 1
    assert set(result.cycles[0]) == {"a", "b"}


def test_self_dependency_not_cycle_error():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["a>=1"]),
    ])
    result = analyze(snap)
    assert len(result.cycles) == 1  # 自环记录
    edge = find_edge(result, "a", "a")
    assert edge is not None
    assert edge.status == EdgeStatus.OK


def test_legacy_parenthesis_spec():
    # 保留空格: "numpy >=1.0" 仍是合法 PEP 508
    assert _normalize_requirement_string("numpy (>=1.0)") == "numpy >=1.0"
    assert _normalize_requirement_string("numpy (>=1.0,<2)") == "numpy >=1.0,<2"
    assert _normalize_requirement_string("numpy>=1.0") == "numpy>=1.0"

    snap = make_snapshot([
        InstalledPackage("legacy-lib", "2.3", []),
        InstalledPackage("pretty-bad", "1.0", ["legacy-lib (>=2.0)"]),
    ])
    result = analyze(snap)
    edge = find_edge(result, "pretty-bad", "legacy-lib")
    assert edge is not None
    assert edge.status == EdgeStatus.OK


def test_legacy_parenthesis_not_spec():
    # 括号内容不是版本约束 → 拼接后 Requirement 解析失败 → UNKNOWN
    snap = make_snapshot([
        InstalledPackage("foo", "1.0", ["foo (bar)"]),
        InstalledPackage("bar", "1.0", []),
    ])
    result = analyze(snap)
    edge = find_edge(result, "foo", "foo")
    assert edge is not None
    assert edge.status == EdgeStatus.UNKNOWN
    # 不应误判出对 bar 的依赖
    assert find_edge(result, "foo", "bar") is None


def test_no_constraint_ok():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["b"]),
        InstalledPackage("b", "2.0", []),
    ])
    result = analyze(snap)
    edge = find_edge(result, "a", "b")
    assert edge is not None
    assert edge.status == EdgeStatus.OK


def test_complex_specifiers():
    snap = make_snapshot([
        InstalledPackage("x", "1.9", []),
        InstalledPackage("y", "1.0", ["x!=2.0,>=1.5,==1.9"]),
        InstalledPackage("z", "1.0", ["x~=1.8"]),
        InstalledPackage("w", "1.0", ["x<1.9"]),
    ])
    result = analyze(snap)
    e1 = find_edge(result, "y", "x")
    assert e1 is not None and e1.status == EdgeStatus.OK  # 1.9 满足全部
    e2 = find_edge(result, "z", "x")
    assert e2 is not None and e2.status == EdgeStatus.OK  # 1.9 满足 ~=1.8
    e3 = find_edge(result, "w", "x")
    assert e3 is not None and e3.status == EdgeStatus.VERSION_CONFLICT  # 1.9 不满足 <1.9


def test_contradictory_specifiers_conflict():
    # PEP 440 中 1.9 == 1.9.0, 故 !=1.9.0 与 ==1.9 互相矛盾 → 必然冲突
    snap = make_snapshot([
        InstalledPackage("x", "1.9", []),
        InstalledPackage("y", "1.0", ["x!=1.9.0,==1.9"]),
    ])
    result = analyze(snap)
    edge = find_edge(result, "y", "x")
    assert edge is not None
    assert edge.status == EdgeStatus.VERSION_CONFLICT


def test_stats_and_ghost_not_counted():
    snap = make_snapshot([
        InstalledPackage("a", "1.0", ["ghost-pkg>=1"]),
    ])
    result = analyze(snap)
    assert result.stats["packages"] == 1  # ghost 不计入已安装
    assert result.installed_count == 1
