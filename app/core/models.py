"""数据模型定义。

本模块定义贯穿全程序的核心数据结构:

- ``InterpreterInfo``     一台设备上发现的一个 Python 解释器
- ``InstalledPackage``    目标环境中已安装的一个发行包(来自目标解释器的元数据)
- ``EnvironmentSnapshot`` 一次采集得到的环境快照(解释器 + 包列表 + 目标环境信息)
- ``EdgeStatus``/``DepEdge`` 依赖边及其冲突判定状态
- ``PackageInfo``         分析聚合后的包信息(含出入边)
- ``AnalysisResult``      一次完整依赖分析的结果(包表 / 边表 / 环 / 告警)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class InterpreterInfo:
    """一个被发现的 Python 解释器。"""

    path: str = ""                 # 解释器可执行文件绝对路径
    version: str = ""              # "3.13.12"
    implementation: str = ""       # "cpython" / "pypy" ...
    arch: str = ""                 # "64bit" / "32bit"
    source: str = "path"           # 发现渠道: launcher/registry/conda/store/common/path
    tag: str = ""                  # py launcher 标签, 如 "3.13"
    company: str = ""              # PEP 514 注册公司(如 PythonCore / ContinuumAnalytics)
    is_venv: bool = False          # 是否虚拟环境(sys.prefix != sys.base_prefix)
    prefix: str = ""
    base_prefix: str = ""
    env_name: str = ""             # Conda 环境名(conda 环境时非空)
    probe_error: str = ""          # 探测失败原因; 探测成功为空

    SOURCE_LABELS = {
        "launcher": "Py 启动器",
        "registry": "系统注册表",
        "conda": "Conda",
        "store": "Microsoft Store",
        "common": "常见安装路径",
        "path": "PATH 环境变量",
    }

    @property
    def source_label(self) -> str:
        if self.is_venv:
            return "虚拟环境 (venv)"
        return self.SOURCE_LABELS.get(self.source, self.source)

    @property
    def sort_key(self) -> tuple:
        """版本升序排序键。

        实际排序请配合 ``reverse=True`` 使用(见 scanner.scan_interpreters):
        此时版本高者在前, 无法解析的版本排在最后。
        使用 packaging.Version 保证 rc/post 等预发布语义正确。
        """
        from packaging.version import InvalidVersion, Version

        try:
            return (1, Version(self.version or "0"))
        except InvalidVersion:
            return (0, Version("0"))

    @property
    def display_name(self) -> str:
        impl = (self.implementation or "python").upper()
        ver = self.version or "未知版本"
        if self.is_venv:
            return f"venv · Python {ver}"
        return f"{impl} {ver}"


@dataclass
class InstalledPackage:
    """目标环境中已安装的一个发行包(元数据采集的原始结果)。"""

    name: str                                       # 元数据中的原始名称
    version: str = ""                               # 已安装版本号
    requires: list[str] = field(default_factory=list)  # Requires-Dist 原始行(PEP 508)


@dataclass
class EnvironmentSnapshot:
    """一次采集得到的环境快照。"""

    interpreter: InterpreterInfo
    python_version: str = ""        # 目标解释器主版本, 如 "3.12"
    python_full_version: str = ""   # 完整版本, 如 "3.12.4"
    platform_machine: str = ""      # 目标平台架构, 如 "AMD64"
    packages: list[InstalledPackage] = field(default_factory=list)
    is_demo: bool = False           # 演示数据标记(刷新时重建而非真实采集)


class EdgeStatus(str, Enum):
    """依赖边状态(冲突判定结果)。"""

    OK = "ok"                       # 依赖满足
    VERSION_CONFLICT = "conflict"   # 已安装版本不满足声明的约束
    MISSING = "missing"             # 依赖未安装
    UNKNOWN = "unknown"             # 无法解析/比较(元数据不规范、URL 依赖、非法版本号)
    INACTIVE = "inactive"           # 环境标记不适用(含未启用的 extras)


@dataclass
class DepEdge:
    """一条依赖边: source 依赖 target(source 的 Requires-Dist 声明)。"""

    source_key: str                 # 依赖方 canonical name
    target_key: str                 # 被依赖方 canonical name
    source_display: str             # 依赖方显示名
    target_display: str             # 被依赖方显示名
    spec: str = ""                  # 版本约束文本, 如 ">=1.20,<2.0"; 空串为无约束
    marker: str = ""                # 原始环境标记(PEP 508 marker)
    marker_applies: bool = True     # 标记在目标环境下是否适用
    status: EdgeStatus = EdgeStatus.OK
    message: str = ""               # 人读结论, 如 "要求 >=2.0, 实际 1.26.4"

    @property
    def is_problem(self) -> bool:
        return self.status in (
            EdgeStatus.VERSION_CONFLICT,
            EdgeStatus.MISSING,
            EdgeStatus.UNKNOWN,
        )


@dataclass
class PackageInfo:
    """分析聚合后的包信息。"""

    key: str                        # canonical name (PEP 503)
    name: str                       # 显示名
    version: str
    requires_raw: list[str] = field(default_factory=list)
    installed: bool = True          # False 表示因缺失依赖而生成的占位"幽灵节点"
    outgoing: list[DepEdge] = field(default_factory=list)  # 我依赖谁
    incoming: list[DepEdge] = field(default_factory=list)  # 谁依赖我

    @property
    def has_conflict(self) -> bool:
        return any(e.status == EdgeStatus.VERSION_CONFLICT for e in self.outgoing)

    @property
    def has_missing(self) -> bool:
        return any(e.status == EdgeStatus.MISSING for e in self.outgoing)

    @property
    def has_unknown(self) -> bool:
        return any(e.status == EdgeStatus.UNKNOWN for e in self.outgoing)

    @property
    def is_problematic(self) -> bool:
        """自身发出的问题边, 或被别人指出版本冲突, 都视为问题包。"""
        return (
            any(e.is_problem for e in self.outgoing)
            or any(e.status == EdgeStatus.VERSION_CONFLICT for e in self.incoming)
        )


@dataclass
class AnalysisResult:
    """一次完整依赖分析的结果。"""

    snapshot: EnvironmentSnapshot
    packages: dict[str, PackageInfo]        # canonical name -> info(含缺失占位)
    edges: list[DepEdge]                    # 所有活动边(不含 INACTIVE)
    cycles: list[list[str]]                 # 循环依赖(SCC 成员数 > 1, 或自环)
    warnings: list[str]                     # 解析告警(无法解析的 Requires-Dist 等)

    @property
    def installed_count(self) -> int:
        return sum(1 for p in self.packages.values() if p.installed)

    @property
    def conflict_edges(self) -> list[DepEdge]:
        return [e for e in self.edges if e.status == EdgeStatus.VERSION_CONFLICT]

    @property
    def missing_edges(self) -> list[DepEdge]:
        return [e for e in self.edges if e.status == EdgeStatus.MISSING]

    @property
    def unknown_edges(self) -> list[DepEdge]:
        return [e for e in self.edges if e.status == EdgeStatus.UNKNOWN]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "packages": self.installed_count,
            "edges": len(self.edges),
            "conflicts": len(self.conflict_edges),
            "missing": len(self.missing_edges),
            "unknown": len(self.unknown_edges),
            "cycles": len(self.cycles),
        }


# ===========================================================================
# Conda 专属模型
# ===========================================================================

@dataclass
class CondaPackage:
    """conda-meta 记录的一个 conda 原生安装包。"""

    name: str
    version: str = ""
    channel: str = ""           # 来源频道, 如 "pkgs/main" / "conda-forge"
    build_string: str = ""      # 构建串, 如 "py312hca03da5_0"


@dataclass
class CondaEnvironment:
    """一个 conda 环境(base 或 envs/* 子环境)。"""

    name: str                       # "base" 或环境名
    path: str                       # 环境根路径
    interpreter: str = ""           # python 可执行文件路径(可能为空)
    python_version: str = ""        # 从 conda-meta 的 python-*.json 解析
    packages: list[CondaPackage] = field(default_factory=list)  # conda 原生包
    is_base: bool = False           # 是否 base 环境
    readable: bool = True           # conda-meta 是否可读
    error: str = ""                 # 读取失败原因(readable=False 时非空)

    @property
    def package_count(self) -> int:
        return len(self.packages)


@dataclass
class CondaConfigFile:
    """一个 .condarc 配置文件的扫描结果。"""

    path: str
    exists: bool = False
    data: dict = field(default_factory=dict)   # 简易 YAML 子集解析结果
    error: str = ""                            # 解析失败原因

    @property
    def channels(self) -> list[str]:
        v = self.data.get("channels")
        return [str(x) for x in v] if isinstance(v, list) else []

    @property
    def envs_dirs(self) -> list[str]:
        v = self.data.get("envs_dirs")
        return [str(x) for x in v] if isinstance(v, list) else []

    @property
    def top_keys(self) -> list[str]:
        return list(self.data.keys())


@dataclass
class CondaInfo:
    """一次 conda 扫描的完整结果。"""

    roots: list[str] = field(default_factory=list)      # conda 根目录(base 环境路径)
    executable: str = ""                                # conda 可执行文件(若找到)
    version: str = ""                                   # conda --version 输出
    envs: list[CondaEnvironment] = field(default_factory=list)
    config_files: list[CondaConfigFile] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)   # 生效频道(合并各配置)
    envs_dirs: list[str] = field(default_factory=list)  # 环境搜索目录
    errors: list[str] = field(default_factory=list)     # 非致命错误/提示

    @property
    def total_conda_packages(self) -> int:
        return sum(e.package_count for e in self.envs)
