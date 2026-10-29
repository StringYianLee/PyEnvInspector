"""两个环境快照的包差异对比。

纯函数实现, 不依赖 UI 与网络:

    a = 环境 A(基准)   b = 环境 B(对照)
    added   仅在 B 中安装
    removed 仅在 A 中安装
    upgraded A 版本 < B 版本
    downgraded A 版本 > B 版本
    changed  版本不同但无法比较大小(非 PEP 440)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packaging.version import InvalidVersion, Version

from .models import EnvironmentSnapshot


@dataclass
class PackageDiff:
    name: str
    version_a: str = ""      # 空串 = A 中未安装
    version_b: str = ""
    kind: str = "same"       # added / removed / upgraded / downgraded / changed / same

    @property
    def is_difference(self) -> bool:
        return self.kind != "same"


@dataclass
class CompareResult:
    snapshot_a: EnvironmentSnapshot
    snapshot_b: EnvironmentSnapshot
    diffs: list[PackageDiff] = field(default_factory=list)

    @property
    def added(self) -> list[PackageDiff]:
        return [d for d in self.diffs if d.kind == "added"]

    @property
    def removed(self) -> list[PackageDiff]:
        return [d for d in self.diffs if d.kind == "removed"]

    @property
    def upgraded(self) -> list[PackageDiff]:
        return [d for d in self.diffs if d.kind == "upgraded"]

    @property
    def downgraded(self) -> list[PackageDiff]:
        return [d for d in self.diffs if d.kind == "downgraded"]

    @property
    def changed(self) -> list[PackageDiff]:
        return [d for d in self.diffs if d.kind == "changed"]

    @property
    def differences(self) -> list[PackageDiff]:
        return [d for d in self.diffs if d.is_difference]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "upgraded": len(self.upgraded),
            "downgraded": len(self.downgraded),
            "changed": len(self.changed),
            "same": len(self.diffs) - len(self.differences),
        }


def _index(snapshot: EnvironmentSnapshot) -> dict[str, tuple[str, str]]:
    """canonical name -> (显示名, 版本)。"""
    from packaging.utils import canonicalize_name
    result: dict[str, tuple[str, str]] = {}
    for p in snapshot.packages:
        key = canonicalize_name(p.name)
        if key not in result:
            result[key] = (p.name, p.version)
    return result


def _compare_versions(a: str, b: str) -> str:
    if not a or not b:
        return "changed"
    try:
        va, vb = Version(a), Version(b)
    except InvalidVersion:
        return "changed"
    if va < vb:
        return "upgraded"
    if va > vb:
        return "downgraded"
    return "same"


def compare_snapshots(a: EnvironmentSnapshot, b: EnvironmentSnapshot) -> CompareResult:
    """对比两个环境的包差异(A 为基准, B 为对照)。"""
    idx_a = _index(a)
    idx_b = _index(b)
    diffs: list[PackageDiff] = []

    for key in sorted(set(idx_a) | set(idx_b)):
        name_a, ver_a = idx_a.get(key, ("", ""))
        name_b, ver_b = idx_b.get(key, ("", ""))
        name = name_b or name_a
        if key not in idx_b:
            diffs.append(PackageDiff(name, ver_a, "", "removed"))
        elif key not in idx_a:
            diffs.append(PackageDiff(name, "", ver_b, "added"))
        elif ver_a == ver_b:
            diffs.append(PackageDiff(name, ver_a, ver_b, "same"))
        else:
            diffs.append(PackageDiff(
                name, ver_a, ver_b, _compare_versions(ver_a, ver_b)))

    return CompareResult(a, b, diffs)


def compare_package_maps(old: dict[str, str], new: dict[str, str]
                         ) -> tuple[list[str], list[str], list[tuple[str, str, str]]]:
    """对比两个 {包名: 版本} 映射(快照历史用)。

    :return: (新增, 移除, [(包名, 旧版本, 新版本) 变化列表])
    """
    from packaging.utils import canonicalize_name
    old_idx = {canonicalize_name(k): (k, v) for k, v in old.items()}
    new_idx = {canonicalize_name(k): (k, v) for k, v in new.items()}
    added = sorted(new_idx[k][0] for k in new_idx.keys() - old_idx.keys())
    removed = sorted(old_idx[k][0] for k in old_idx.keys() - new_idx.keys())
    changed: list[tuple[str, str, str]] = []
    for key in sorted(new_idx.keys() & old_idx.keys()):
        name, new_ver = new_idx[key]
        old_ver = old_idx[key][1]
        if old_ver != new_ver:
            changed.append((name, old_ver, new_ver))
    return added, removed, changed
