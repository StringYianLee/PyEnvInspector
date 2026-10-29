"""依赖关系分析与版本冲突判定。

冲突判定逻辑
============

对目标环境快照中每个已安装包 P 的每条 ``Requires-Dist`` 声明 D:

1. **解析 PEP 508**: 依赖名 N、版本约束 S、环境标记 M(legacy 括号写法
   ``numpy (>=1.0)`` 会被先规范化)。解析失败 → 状态 ``UNKNOWN``。
2. **评估环境标记 M**: 以目标解释器环境(python_version 等来自采集快照,
   其余来自本机)评估;``extra == "..."`` 之类的 extras 依赖视为未启用。
   不适用的依赖直接忽略(不计入图, 不算冲突)。
3. **定位被依赖方**:
   - N 未安装            → ``MISSING``(依赖缺失, 链条断开)
   - N 无版本约束         → ``OK``
   - N 已安装版本 V, 检查 ``V in S``:
       * 满足            → ``OK``
       * 不满足          → ``VERSION_CONFLICT``(版本冲突)
       * V 不是合法 PEP 440 版本 → ``UNKNOWN``
   - D 是 URL/本地路径依赖 → ``UNKNOWN``(无版本可比)
4. **循环检测**: 对活动边做 Tarjan 强连通分量, 成员数 > 1(或自环)即
   循环依赖。

所有问题边(status != OK)即构成"冲突清单", 端点包在依赖图中以
红(冲突)/橙(缺失)/灰(未知)着色, 冲突链条一目了然。
"""

from __future__ import annotations

import re

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from .models import (
    AnalysisResult,
    DepEdge,
    EdgeStatus,
    EnvironmentSnapshot,
    InstalledPackage,
    PackageInfo,
)
from .scc import find_cycles

# legacy setuptools 写法: "numpy (>=1.0)" / "numpy (>=1.0,<2)"
_LEGACY_SPEC_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*\(\s*(.+?)\s*\)$")


def _normalize_requirement_string(raw: str) -> str:
    """把 legacy 括号约束规范成 PEP 508 形式。

    保留空格: 仅当括号内确实是版本约束时才等价于 PEP 508 写法;
    其它内容(如 "foo (bar)")交给 Requirement() 判定为非法 → UNKNOWN,
    避免无分隔拼接把 "foo (bar)" 误拼成对 "foobar" 的依赖。
    """
    text = raw.strip()
    m = _LEGACY_SPEC_RE.match(text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return text


def analyze(snapshot: EnvironmentSnapshot) -> AnalysisResult:
    """对环境快照执行完整依赖分析。"""
    packages: dict[str, PackageInfo] = {}
    for p in snapshot.packages:
        key = canonicalize_name(p.name)
        entry = PackageInfo(
            key=key, name=p.name, version=p.version, requires_raw=p.requires
        )
        old = packages.get(key)
        if old is None or len(entry.requires_raw) > len(old.requires_raw):
            packages[key] = entry

    # marker 评估环境: 目标解释器版本信息优先, 其余取本机
    env = dict(default_environment())
    env["extra"] = ""
    if snapshot.python_version:
        env["python_version"] = snapshot.python_version
    if snapshot.python_full_version:
        env["python_full_version"] = snapshot.python_full_version
    elif snapshot.python_version:
        # 快照只给主版本时不得回退到本机完整版本, 否则 marker 会误判
        env["python_full_version"] = snapshot.python_version
    if snapshot.platform_machine:
        env["platform_machine"] = snapshot.platform_machine

    warnings: list[str] = []
    edges: list[DepEdge] = []

    for pkg in list(packages.values()):
        for raw in pkg.requires_raw:
            edge_or_none, warning = _build_edge(pkg, raw, packages, env)
            if warning:
                warnings.append(warning)
            if edge_or_none is None or edge_or_none.status == EdgeStatus.INACTIVE:
                continue  # 标记不适用: 不进入图
            edges.append(edge_or_none)

    # 挂接出入边; 缺失依赖生成占位幽灵节点
    for e in edges:
        packages[e.source_key].outgoing.append(e)
        target = packages.get(e.target_key)
        if target is None:
            target = PackageInfo(
                key=e.target_key, name=e.target_display, version="",
                requires_raw=[], installed=False,
            )
            packages[e.target_key] = target
        target.incoming.append(e)

    # 循环检测仅基于确定性的边: UNKNOWN(声明无法解析/URL 依赖)不应计入
    # 强连通分量, 否则会报告出并不确定的循环依赖
    cycles = find_cycles(
        packages, [e for e in edges if e.status != EdgeStatus.UNKNOWN])
    return AnalysisResult(
        snapshot=snapshot,
        packages=packages,
        edges=edges,
        cycles=cycles,
        warnings=warnings,
    )


def _build_edge(
    pkg: PackageInfo,
    raw: str,
    packages: dict[str, PackageInfo],
    env: dict,
):
    """解析一条 Requires-Dist 声明并判定状态。

    :return: (DepEdge 或 None, warning 或 None); None 表示标记不适用
    """
    text = _normalize_requirement_string(raw)
    if not text or not text.strip():
        # 空声明: 无法定位目标, 直接跳过并告警, 避免产生空 key 幽灵节点
        return None, f"{pkg.name}: 依赖声明为空, 已跳过 ({raw!r})"

    base = dict(
        source_key=pkg.key,
        target_key="",
        source_display=pkg.name,
        target_display="",
        marker="",
        marker_applies=True,
    )

    try:
        req = Requirement(text)
    except InvalidRequirement:
        first_token = text.split()[0] if text.split() else "?"
        base.update(
            target_key=canonicalize_name(first_token) or "?invalid?",
            target_display=first_token,
            status=EdgeStatus.UNKNOWN,
            message="依赖声明无法解析",
        )
        return DepEdge(**base), f"{pkg.name}: 无法解析依赖声明 {raw!r}"

    marker_str = str(req.marker) if req.marker else ""
    base["marker"] = marker_str
    base["target_display"] = req.name
    target_key = canonicalize_name(req.name)
    base["target_key"] = target_key
    spec_str = str(req.specifier) if req.specifier else ""

    warning = None
    marker_applies = True
    if req.marker is not None:
        try:
            marker_applies = bool(req.marker.evaluate(env))
        except Exception as exc:  # 罕见: marker 语法怪异/变量未定义
            # 不按适用处理(避免产生虚假 MISSING/CONFLICT), 置为未知项交人工确认
            base["marker_applies"] = False
            base.update(
                status=EdgeStatus.UNKNOWN,
                message=f"环境标记 {marker_str!r} 评估失败({exc}), 需人工确认",
            )
            return DepEdge(**base), f"{pkg.name}: 环境标记评估失败 {marker_str!r}"
    base["marker_applies"] = marker_applies
    if not marker_applies:
        base["status"] = EdgeStatus.INACTIVE
        base["message"] = "环境标记不适用"
        return DepEdge(**base), warning

    # URL / 本地路径依赖
    if req.url:
        base.update(
            spec=req.url,
            status=EdgeStatus.UNKNOWN,
            message="URL/本地路径依赖, 未校验版本",
        )
        return DepEdge(**base), warning

    # 自引用: 不再短路返回, 与普通依赖一样走约束校验
    # (元数据声明 itself>=2.0 而实际 1.0 同样是版本冲突, 应当暴露)

    target = packages.get(target_key)
    if target is None:
        base.update(
            spec=spec_str,
            status=EdgeStatus.MISSING,
            message=f"未安装(要求 {spec_str or '任意版本'})",
        )
        return DepEdge(**base), warning

    if not spec_str:
        base.update(spec="", status=EdgeStatus.OK, message="无版本约束")
        return DepEdge(**base), warning

    installed_version = target.version
    # 先验证已安装版本号是否符合 PEP 440:
    # 新版 packaging(>=25) 对非法版本返回 False 而非抛异常, 需前置校验
    try:
        Version(installed_version)
    except InvalidVersion:
        base.update(
            spec=spec_str,
            status=EdgeStatus.UNKNOWN,
            message=f"{target.name} 的版本号 {installed_version!r} 不符合 PEP 440, 无法比较",
        )
        return DepEdge(**base), warning

    try:
        satisfied = req.specifier.contains(installed_version, prereleases=True)
    except InvalidVersion:
        base.update(
            spec=spec_str,
            status=EdgeStatus.UNKNOWN,
            message=f"约束 {spec_str} 与版本 {installed_version!r} 无法比较",
        )
        return DepEdge(**base), warning

    if satisfied:
        base.update(spec=spec_str, status=EdgeStatus.OK, message=f"满足 {spec_str}")
    else:
        base.update(
            spec=spec_str,
            status=EdgeStatus.VERSION_CONFLICT,
            message=f"要求 {spec_str}, 实际安装 {installed_version}",
        )
    return DepEdge(**base), warning


# ---------------------------------------------------------------------------
# 冲突修复建议
# ---------------------------------------------------------------------------

def suggest_constraint(result: AnalysisResult, target_key: str
                       ) -> tuple[str, list[str]]:
    """为"被多个包同时约束"的包生成合并约束建议。

    例如 numpy 被 A 要求 ``<1.20``、B 要求 ``>=1.19``,
    返回 ("numpy<1.20,>=1.19", ["A: <1.20", "B: >=1.19"])。

    :return: (pip 安装表达式, 每条约束的来源说明)
    """
    pkg = result.packages.get(target_key)
    display = pkg.name if pkg is not None else target_key
    parts: list[str] = []
    sources: list[str] = []
    for edge in result.edges:
        if edge.target_key != target_key or not edge.spec:
            continue
        spec = edge.spec.strip()
        if not spec or spec[0] not in "<>=!~":
            continue
        if spec in parts:
            continue
        parts.append(spec)
        sources.append(f"{edge.source_display}: {spec}")
    if not parts:
        return "", sources
    return f"{display}{','.join(parts)}", sources
