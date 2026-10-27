"""演示数据:构造一个含冲突/缺失/循环/未知项的假想环境, 便于无环境下查看效果。"""

from __future__ import annotations

import os

from .core.models import (
    CondaConfigFile,
    CondaEnvironment,
    CondaInfo,
    CondaPackage,
    EnvironmentSnapshot,
    InstalledPackage,
    InterpreterInfo,
)


def build_demo_interpreter() -> InterpreterInfo:
    return InterpreterInfo(
        path="C:\\Demo\\Python312\\python.exe",
        version="3.12.4",
        implementation="cpython",
        arch="64bit",
        source="common",
    )


def build_demo_managed_interpreter() -> InterpreterInfo:
    """演示: 本工具托管安装的解释器条目。"""
    return InterpreterInfo(
        path=os.path.join(os.path.expanduser("~"), "PyEnvInspector",
                          "runtimes", "py-3.12.7", "python.exe"),
        version="3.12.7",
        implementation="cpython",
        arch="64bit",
        source="common",
    )


def build_demo_snapshot() -> EnvironmentSnapshot:
    """构造演示环境快照。

    覆盖的判定情形:
    - 版本冲突: old-ml-lib 要求 numpy<1.20, 但已安装 1.26.4
    - 依赖缺失: six / scikit-learn 未安装
    - 环境标记不适用: ujson 仅限非 Windows
    - extras 未启用: requests[socks] 的 socks 依赖被跳过
    - URL 依赖: local-wheels(未知项)
    - 循环依赖: cycle-a ↔ cycle-b
    - legacy 括号约束: pretty-bad → legacy-lib
    - 非法版本号: weird-version(未知项)
    """
    interp = build_demo_interpreter()
    packages = [
        InstalledPackage("numpy", "1.26.4", []),
        InstalledPackage("pandas", "2.2.1", [
            "numpy>=1.22.0",
            "python-dateutil>=2.8.2",
            "pytz>=2020.1",
            "tzdata>=2022.7",
        ]),
        InstalledPackage("old-ml-lib", "0.9.1", [
            "numpy<1.20",          # 版本冲突: 实际 1.26.4
            "scikit-learn",        # 依赖缺失
        ]),
        InstalledPackage("python-dateutil", "2.9.0", ["six>=1.5"]),   # six 缺失
        InstalledPackage("pytz", "2024.1", []),
        InstalledPackage("tzdata", "2024.1", []),
        InstalledPackage("web-framework", "3.0", [
            "requests[socks]>=2.28",
            # 标记不适用(目标解释器 3.12, 永假) —— 平台无关, 各 OS 演示结果一致
            "ujson; python_version < '3.0'",
            "local-wheels @ file:///wheels/x.whl",   # URL 依赖 → 未知项
        ]),
        InstalledPackage("requests", "2.31.0", [
            "charset-normalizer<4,>=2",
            "idna<4,>=2.5",
            "urllib3<3,>=1.21.1",
            "certifi>=2017.4.17",
        ]),
        InstalledPackage("charset-normalizer", "3.3.2", []),
        InstalledPackage("idna", "3.6", []),
        InstalledPackage("urllib3", "2.2.1", []),
        InstalledPackage("certifi", "2024.2.2", []),
        InstalledPackage("cycle-a", "1.0", ["cycle-b>=1.0"]),
        InstalledPackage("cycle-b", "1.0", ["cycle-a>=1.0"]),
        InstalledPackage("pretty-bad", "1.0", ["legacy-lib (>=2.0)"]),  # legacy 写法
        InstalledPackage("legacy-lib", "2.3", []),
        InstalledPackage("weird-version", "final", []),               # 非法版本
        InstalledPackage("needs-weird", "1.0", ["weird-version>1"]),  # → 未知项
    ]
    return EnvironmentSnapshot(
        interpreter=interp,
        python_version="3.12",
        python_full_version="3.12.4",
        platform_machine="AMD64",
        packages=packages,
    )


def build_demo_env_snapshot(env: CondaEnvironment) -> EnvironmentSnapshot:
    """为演示 conda 环境构造配套的 pip 包快照(双击环境时可无缝联动)。"""
    catalog = {
        "base": [
            InstalledPackage("pip", "24.0", []),
            InstalledPackage("setuptools", "69.5.1", []),
            InstalledPackage("wheel", "0.43.0", []),
        ],
        "ml": [
            InstalledPackage("numpy", "1.26.4", []),
            InstalledPackage("scipy", "1.13.1", ["numpy>=1.22.4,<2.3"]),
        ],
        "web": [
            InstalledPackage("requests", "2.32.3", [
                "charset-normalizer<4,>=2", "idna<4,>=2.5",
                "urllib3<3,>=1.21.1", "certifi>=2017.4.17",
            ]),
            InstalledPackage("certifi", "2024.6.2", []),
            InstalledPackage("charset-normalizer", "3.3.2", []),
            InstalledPackage("idna", "3.7", []),
            InstalledPackage("urllib3", "2.2.2", []),
        ],
    }
    packages = catalog.get(env.name, [
        InstalledPackage("pip", "24.0", []),
    ])
    version = env.python_version or "3.12.0"
    return EnvironmentSnapshot(
        interpreter=InterpreterInfo(
            path=env.interpreter or env.path, version=version,
            implementation="cpython", arch="64bit",
            source="conda", env_name=env.name,
        ),
        python_version=version.rsplit(".", 1)[0],
        python_full_version=version,
        platform_machine="AMD64",
        packages=packages,
    )


def build_demo_conda_info() -> CondaInfo:
    """构造演示用 conda 扫描结果(与演示解释器同路径, 便于联动)。"""
    base_pkgs = [
        CondaPackage("conda", "24.5.0", "pkgs/main", "py312_0"),
        CondaPackage("python", "3.12.4", "pkgs/main", "h14a1e_0"),
        CondaPackage("openssl", "3.0.14", "pkgs/main", "h2bbff1b_0"),
        CondaPackage("sqlite", "3.45.3", "pkgs/main", "h2bbff1b_0"),
        CondaPackage("zlib", "1.2.13", "pkgs/main", "h2bbff1b_0"),
    ]
    ml_pkgs = [
        CondaPackage("python", "3.12.4", "pkgs/main", "h14a1e_0"),
        CondaPackage("numpy", "1.26.4", "conda-forge", "py312h8753938_0"),
        CondaPackage("scipy", "1.13.1", "conda-forge", "py312h8753938_0"),
        CondaPackage("openssl", "3.0.14", "pkgs/main", "h2bbff1b_0"),
    ]
    web_pkgs = [
        CondaPackage("python", "3.11.9", "pkgs/main", "h1abb5b_0"),
        CondaPackage("pip", "24.0", "pkgs/main", "py311_0"),
        CondaPackage("setuptools", "69.5.1", "pkgs/main", "py311_0"),
    ]
    envs = [
        CondaEnvironment(
            name="base", path="C:\\Demo\\Miniconda3",
            interpreter="C:\\Demo\\Miniconda3\\python.exe",
            python_version="3.12.4", packages=base_pkgs, is_base=True,
        ),
        CondaEnvironment(
            name="ml", path="C:\\Demo\\Miniconda3\\envs\\ml",
            interpreter="C:\\Demo\\Miniconda3\\envs\\ml\\python.exe",
            python_version="3.12.4", packages=ml_pkgs,
        ),
        CondaEnvironment(
            name="web", path="C:\\Demo\\Miniconda3\\envs\\web",
            interpreter="C:\\Demo\\Miniconda3\\envs\\web\\python.exe",
            python_version="3.11.9", packages=web_pkgs,
        ),
    ]
    user_cfg = CondaConfigFile(
        path=os.path.join(os.path.expanduser("~"), ".condarc"),
        exists=False,
    )
    demo_cfg = CondaConfigFile(
        path="C:\\Demo\\Miniconda3\\.condarc",
        exists=True,
        data={
            "channels": ["defaults", "conda-forge"],
            "envs_dirs": ["C:/Demo/Miniconda3/envs"],
            "channel_priority": "strict",
            "ssl_verify": True,
            "auto_activate_base": False,
        },
    )
    return CondaInfo(
        roots=["C:\\Demo\\Miniconda3"],
        executable="C:\\Demo\\Miniconda3\\Scripts\\conda.exe",
        version="24.5.0",
        envs=envs,
        config_files=[demo_cfg, user_cfg],
        channels=["defaults", "conda-forge"],
        envs_dirs=["C:/Demo/Miniconda3/envs"],
    )
