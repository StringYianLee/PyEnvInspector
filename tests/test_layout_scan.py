"""布局引擎与扫描/采集集成测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.analyzer import analyze  # noqa: E402
from app.core.collector import collect_packages  # noqa: E402
from app.core.layout import force_layout, hierarchical_layout  # noqa: E402
from app.core.models import InstalledPackage, InterpreterInfo  # noqa: E402
from app.core.scanner import probe_interpreter  # noqa: E402
from app.demo import build_demo_snapshot  # noqa: E402


def _demo_analysis():
    return analyze(build_demo_snapshot())


def test_hierarchical_layout_covers_all_nodes():
    result = _demo_analysis()
    pos = hierarchical_layout(result.packages, result.edges)
    assert set(pos.keys()) == set(result.packages.keys())
    # 每个节点都有有限坐标
    for (x, y) in pos.values():
        assert x == x and y == y  # 非 NaN
        assert abs(x) < 1e7 and abs(y) < 1e7


def test_hierarchical_layout_no_overlap_same_row():
    result = _demo_analysis()
    pos = hierarchical_layout(result.packages, result.edges)
    # 同一 y 层的节点 x 至少差 100
    by_y = {}
    for key, (x, y) in pos.items():
        by_y.setdefault(round(y), []).append(x)
    for y, xs in by_y.items():
        xs = sorted(xs)
        for a, b in zip(xs, xs[1:]):
            assert b - a >= 100, f"层 y={y} 出现重叠: {xs}"


def test_force_layout_covers_all_nodes():
    result = _demo_analysis()
    pos = force_layout(result.packages, result.edges, iterations=30)
    assert set(pos.keys()) == set(result.packages.keys())


def test_layout_empty():
    assert hierarchical_layout({}, []) == {}
    assert force_layout({}, []) == {}


def test_hierarchical_spacing_adapts_to_name_width():
    """长名节点层间距应比短名节点层间距更大(自适应排布)。"""
    from app.core.models import InstalledPackage, EnvironmentSnapshot, InterpreterInfo
    short = InstalledPackage("ab", "1.0", ["cd"])
    cd = InstalledPackage("cd", "1.0", [])
    long_name = InstalledPackage("a-very-long-package-name-here", "1.0", ["cd"])
    interp = InterpreterInfo(path="C:/x/python.exe", version="3.12",
                             implementation="cpython", arch="64bit")
    snap_short = EnvironmentSnapshot(interpreter=interp, packages=[short, cd])
    snap_long = EnvironmentSnapshot(interpreter=interp, packages=[long_name, cd])
    from app.core.analyzer import analyze
    r_short = analyze(snap_short)
    r_long = analyze(snap_long)
    pos_s = hierarchical_layout(r_short.packages, r_short.edges)
    pos_l = hierarchical_layout(r_long.packages, r_long.edges)
    def _span(pos):
        xs = [x for x, _ in pos.values()]
        return max(xs) - min(xs)
    # 长名布局的水平跨度应更大(占用更多空间)
    assert _span(pos_l) > _span(pos_s)


def test_hierarchical_layer_spacing_adapts():
    """最宽层更宽时, 层间垂直距离应随之增大。"""
    from app.core.models import InstalledPackage, EnvironmentSnapshot, InterpreterInfo
    interp = InterpreterInfo(path="C:/x/python.exe", version="3.12",
                             implementation="cpython", arch="64bit")
    def build(names_src, names_dst):
        pkgs = [InstalledPackage(n, "1.0", list(src))
                for n, src in names_src] + \
               [InstalledPackage(n, "1.0", []) for n in names_dst]
        return EnvironmentSnapshot(interpreter=interp, packages=pkgs)
    from app.core.analyzer import analyze
    small = analyze(build([("a", ["b"])], ["b"]))
    big = analyze(build([(f"pkg-{i:02d}-with-long-name", ["dep"])
                         for i in range(12)], ["dep"]))
    pos_s = hierarchical_layout(small.packages, small.edges)
    pos_b = hierarchical_layout(big.packages, big.edges)
    ys_s = sorted({y for _, y in pos_s.values()})
    ys_b = sorted({y for _, y in pos_b.values()})
    gap_s = ys_s[1] - ys_s[0]
    gap_b = ys_b[1] - ys_b[0]
    assert gap_b >= gap_s


def test_demo_snapshot_has_expected_problems():
    result = _demo_analysis()
    assert result.stats["conflicts"] >= 1   # old-ml-lib → numpy<1.20
    assert result.stats["missing"] >= 2     # scikit-learn, six
    assert result.stats["unknown"] >= 2     # URL 依赖, 非法版本
    assert result.stats["cycles"] == 1      # cycle-a ↔ cycle-b
    assert result.stats["packages"] == 18


def test_probe_real_interpreter():
    """对本机 managed Python 做真实探测。"""
    candidates = [
        r"C:\Users\Liyian\.workbuddy\binaries\python\versions\3.13.12\python.exe",
        r"C:\Python314\python.exe",
    ]
    probed = 0
    for path in candidates:
        if not os.path.isfile(path):
            continue
        info = probe_interpreter(path, "common")
        assert not info.probe_error, f"探测失败: {info.probe_error}"
        assert info.version.startswith("3.")
        assert info.implementation == "cpython"
        probed += 1
    assert probed >= 1, "本机应至少有一个可探测的 Python"


def test_collect_real_environment():
    """对真实解释器采集包元数据(venv 内含 PySide6/packaging/pytest)。"""
    path = r"C:\Users\Liyian\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
    if not os.path.isfile(path):
        path = r"C:\Users\Liyian\.workbuddy\binaries\python\versions\3.13.12\python.exe"
    assert os.path.isfile(path), "找不到可用的测试解释器"
    snap = collect_packages(InterpreterInfo(path=path, version="3.13"))
    names = {p.name.lower() for p in snap.packages}
    assert "pyside6" in names, f"应采集到 PySide6, 实际: {sorted(names)[:20]}"
    assert "packaging" in names
    # 依赖声明应被带出
    pyside = next(p for p in snap.packages if p.name.lower() == "pyside6")
    assert len(pyside.requires) > 0
