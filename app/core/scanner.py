"""本机 Python 解释器扫描。

数据获取方式(按发现渠道, Windows 优先并兼容其他平台):

1. ``py`` 启动器      : ``py --list-paths`` 列出已注册解释器
2. 系统注册表 (PEP 514): HKLM/HKCU ``SOFTWARE\\Python\\PythonCore`` 及
                        ``SOFTWARE\\Python\\ContinuumAnalytics`` 等分支
3. PATH 环境变量     : 遍历 PATH 中各目录查找 python/python3 可执行文件
4. 常见安装目录     : ``C:\\Python*``、``%LOCALAPPDATA%\\Programs\\Python\\Python*``、
                        ``C:\\Program Files\\Python*`` 等
5. Conda            : ``~/anaconda3``、``~/miniconda3``、``~/miniforge3``、
                        ``%ProgramData%\\*conda*`` 及其 ``envs/*`` 子环境
6. Microsoft Store  : ``%LOCALAPPDATA%\\Microsoft\\WindowsApps`` 下的
                        ``PythonSoftwareFoundation.Python.*`` 真实入口

每个候选解释器都会被实际启动一次(``python -I -c "<探测脚本>"``)以确认
版本、实现、体系结构与 venv 归属;探测失败的候选(如 Store 未安装占位
stub)会被丢弃并记入日志。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from .models import InterpreterInfo

# 实际启动解释器执行的探测脚本(纯 ASCII 输出, 无编码问题)
PROBE_SCRIPT = (
    "import sys, json, platform; "
    "print(json.dumps({"
    "'version': platform.python_version(), "
    "'implementation': sys.implementation.name, "
    "'arch': platform.architecture()[0], "
    "'prefix': sys.prefix, "
    "'base_prefix': sys.base_prefix, "
    "'executable': sys.executable}))"
)

PROBE_TIMEOUT = 20  # 秒


@dataclass
class ScanReport:
    """一次扫描的结果。"""

    interpreters: list[InterpreterInfo] = field(default_factory=list)
    log: list[str] = field(default_factory=list)  # 扫描过程日志(供调试/展示)


def _is_windows() -> bool:
    return os.name == "nt"


def scan_interpreters(progress=None) -> ScanReport:
    """扫描本机所有 Python 解释器。

    :param progress: 可选回调 ``progress(str)``, 用于向 UI 推送进度文本
    :return: ``ScanReport``, interpreters 按版本降序排列
    """

    def report(msg: str) -> None:
        if progress is not None:
            try:
                progress(msg)
            except Exception:
                pass

    report("开始扫描本机 Python 解释器…")
    candidates: dict[str, dict] = {}  # 规范化路径 -> {"sources": [...], "tag", "company"}

    def add(path: str, source: str, tag: str = "", company: str = "",
            env_name: str = "") -> None:
        try:
            full = os.path.normpath(os.path.abspath(path))
        except (OSError, ValueError):
            return
        # Windows 大小写不敏感: 去重键归一, 显示保留原始大小写
        norm = os.path.normcase(full) if _is_windows() else full
        if not norm.lower().endswith(".exe") and _is_windows():
            return
        if not os.path.isfile(full):
            return
        entry = candidates.setdefault(
            norm, {"display": full, "sources": [], "tag": tag,
                   "company": company, "env_name": env_name}
        )
        if source not in entry["sources"]:
            entry["sources"].append(source)
        if env_name and not entry.get("env_name"):
            entry["env_name"] = env_name

    # 1) py 启动器 --------------------------------------------------------
    py = shutil.which("py") or shutil.which("py.exe")
    if py:
        report("查询 py 启动器…")
        try:
            proc = subprocess.run(
                [py, "--list-paths"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=20,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    m = re.match(r"\s*-V:([^\s*]+)\s+(\*\s*)?(.+?)\s*$", line)
                    if m and m.group(3).lower().endswith(".exe"):
                        add(m.group(3), "launcher", tag=m.group(1))
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        report("未检测到 py 启动器, 跳过")

    # 2) 系统注册表 (PEP 514) ---------------------------------------------
    report("查询系统注册表 (PEP 514)…")
    _scan_registry(add)

    # 3) PATH 环境变量 ------------------------------------------------------
    report("扫描 PATH 环境变量…")
    names = ("python.exe", "python3.exe", "python3", "python") if _is_windows() \
        else ("python3", "python3.13", "python3.12", "python3.11", "python3.10",
              "python3.9", "python3.8", "python", "pypy3")
    seen_dirs: set[str] = set()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip().strip('"')
        if not d or d in seen_dirs:
            continue
        seen_dirs.add(d)
        for name in names:
            add(os.path.join(d, name), "path")

    # 4) 常见安装目录 -------------------------------------------------------
    report("扫描常见安装目录…")
    for pattern in _common_patterns():
        import glob as _glob
        for hit in _glob.glob(pattern):
            add(hit, "common")

    # 5) Conda --------------------------------------------------------------
    report("扫描 Conda 安装与子环境…")
    conda_roots = find_conda_roots()
    # POSIX 上 conda 的解释器位于 bin/ 子目录
    conda_exe_rel = (
        ("python.exe",) if _is_windows()
        else (os.path.join("bin", "python"), os.path.join("bin", "python3"))
    )
    for root in conda_roots:
        for rel in conda_exe_rel:
            add(os.path.join(root, rel), "conda")
        envs_dir = os.path.join(root, "envs")
        if os.path.isdir(envs_dir):
            try:
                for env_name in os.listdir(envs_dir):
                    for rel in conda_exe_rel:
                        add(os.path.join(envs_dir, env_name, rel), "conda",
                            env_name=env_name)
            except OSError:
                pass

    # 6) Microsoft Store ----------------------------------------------------
    store_dir = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WindowsApps"
    )
    if os.path.isdir(store_dir):
        report("扫描 Microsoft Store 入口…")
        import glob as _glob
        for hit in _glob.glob(os.path.join(store_dir, "PythonSoftwareFoundation*.exe")):
            if os.path.basename(hit).lower().startswith("pythonsoftwarefoundation.python"):
                add(hit, "store")
        # Store 别名(python3.12.exe 等真实入口)
        for hit in _glob.glob(os.path.join(store_dir, "python*.exe")):
            base = os.path.basename(hit).lower()
            if re.fullmatch(r"python(\d+(\.\d+)?)?\.exe", base):
                add(hit, "store")

    # ---- 逐个探测, 去重 -----------------------------------------------------
    report(f"共发现 {len(candidates)} 个候选路径, 逐一验证…")
    interpreters: list[InterpreterInfo] = []
    log: list[str] = []
    for _norm, meta in candidates.items():
        info = probe_interpreter(
            meta["display"],
            meta["sources"][0] if meta["sources"] else "path",
            tag=meta.get("tag", ""), company=meta.get("company", ""),
            env_name=meta.get("env_name", ""),
        )
        if info.probe_error:
            log.append(f"跳过 {meta['display']}: {info.probe_error}")
            continue
        if info not in interpreters:
            interpreters.append(info)

    # 稳定两步排序: 先路径升序, 再按版本降序(同版本时保持路径顺序)
    interpreters.sort(key=lambda i: i.path.lower())
    interpreters.sort(key=lambda i: i.sort_key, reverse=True)
    report(f"扫描完成, 共 {len(interpreters)} 个可用解释器")
    return ScanReport(interpreters=interpreters, log=log + ["扫描完成"])


def probe_interpreter(
    path: str, source: str, tag: str = "", company: str = "",
    env_name: str = "",
) -> InterpreterInfo:
    """实际启动解释器, 采集版本/实现/架构/venv 信息。

    探测失败时返回 ``probe_error`` 非空的对象(调用方据此丢弃该候选)。
    """
    info = InterpreterInfo(path=path, source=source, tag=tag, company=company,
                           env_name=env_name)
    argv = [path, "-I", "-c", PROBE_SCRIPT]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PROBE_TIMEOUT,
        )
        if proc.returncode != 0:
            # 老版本可能不支持 -I, 退回普通模式再试一次
            proc = subprocess.run(
                [path, "-c", PROBE_SCRIPT], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=PROBE_TIMEOUT,
            )
    except subprocess.TimeoutExpired:
        info.probe_error = "启动超时"
        return info
    except OSError as exc:
        info.probe_error = f"无法启动: {exc}"
        return info

    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        info.probe_error = tail[-1] if tail else f"退出码 {proc.returncode}"
        return info

    try:
        lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
        data = json.loads(lines[-1])
        if not isinstance(data, dict):
            raise ValueError(f"探测输出不是 JSON 对象: {type(data).__name__}")
        info.version = str(data.get("version", ""))
        info.implementation = str(data.get("implementation", ""))
        info.arch = str(data.get("arch", ""))
        info.prefix = str(data.get("prefix", ""))
        info.base_prefix = str(data.get("base_prefix", ""))
        info.is_venv = bool(info.prefix and info.base_prefix
                            and info.prefix != info.base_prefix)
        if info.version.startswith("Python "):
            info.version = info.version[len("Python "):]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
        info.probe_error = f"输出解析失败: {exc}"
    return info


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _scan_registry(add) -> None:
    """遍历 PEP 514 注册表分支, 将发现的解释器交给 add()。"""
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return

    branches = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Python\PythonCore", "PythonCore"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Python\PythonCore", "PythonCore"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Python\PythonCore", "PythonCore"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Python\ContinuumAnalytics", "Anaconda"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Python\ContinuumAnalytics", "Anaconda"),
    ]
    for hive, subkey, company in branches:
        try:
            root = winreg.OpenKey(hive, subkey)
        except OSError:
            continue
        with root:
            index = 0
            while True:
                try:
                    ver = winreg.EnumKey(root, index)
                    index += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(root, ver + r"\InstallPath") as ip:
                        exe = ""
                        try:
                            exe = winreg.QueryValueEx(ip, "ExecutablePath")[0]
                        except OSError:
                            pass
                        if not exe:
                            try:
                                base_dir = winreg.QueryValueEx(ip, "")[0]
                                exe = os.path.join(base_dir, "python.exe")
                            except OSError:
                                continue
                        add(exe, "registry", tag=ver, company=company)
                except OSError:
                    continue


def _common_patterns() -> list[str]:
    """常见安装目录的 glob 模式。"""
    if _is_windows():
        pats = [
            r"C:\Python*\python.exe",
            r"C:\Program Files\Python*\python.exe",
            r"C:\Program Files (x86)\Python*\python.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python*\python.exe"),
        ]
        home = os.path.expanduser("~")
        for name in ("anaconda3", "miniconda3", "miniforge3", "mambaforge"):
            pats.append(os.path.join(home, name, "python.exe"))
        for name in ("anaconda3", "miniconda3", "miniforge3"):
            pats.append(os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), name, "python.exe"))
        return [p for p in pats if "%" not in p]
    # POSIX 兜底
    return [
        "/usr/bin/python3", "/usr/local/bin/python3",
        os.path.expanduser("~/.pyenv/versions/*/bin/python"),
    ]


def find_conda_roots() -> list[str]:
    """发现本机 conda 根目录(base 环境路径)。

    探测渠道: 常见安装位置 / PATH 中的 conda 命令 / CONDA_PREFIX 等
    环境变量 / PEP 514 注册表 ContinuumAnalytics 分支(覆盖自定义盘符安装)。
    """
    roots: list[str] = []

    def consider(candidate: str) -> None:
        if not candidate:
            return
        norm = os.path.normpath(os.path.abspath(candidate))
        if _is_windows():
            norm = os.path.normcase(norm)  # Windows 路径大小写不敏感
        if norm in roots:
            return
        # conda 根的标志: 含解释器或 conda-meta 目录
        if (os.path.isfile(os.path.join(norm, "python.exe"))
                or os.path.isfile(os.path.join(norm, "bin", "python3"))
                or os.path.isdir(os.path.join(norm, "conda-meta"))):
            roots.append(norm)

    # 1) 常见安装位置
    candidates = [
        os.path.expanduser("~/anaconda3"),
        os.path.expanduser("~/miniconda3"),
        os.path.expanduser("~/miniforge3"),
        os.path.expanduser("~/mambaforge"),
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "anaconda3"),
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "miniconda3"),
    ]
    for c in candidates:
        consider(c)

    # 2) PATH / 环境变量中的 conda
    conda_exe = shutil.which("conda") or shutil.which("conda.exe")
    env_hints: list[str] = []
    if conda_exe:
        env_hints.append(conda_exe)
    for var in ("CONDA_EXE", "CONDA_PREFIX", "_CONDA_ROOT"):
        v = os.environ.get(var)
        if v:
            env_hints.append(v)
    for hint in env_hints:
        # CONDA_PREFIX / _CONDA_ROOT 本身就是目录(根或活跃环境), 直接考虑;
        # 只有可执行文件才需要 dirname 上溯
        if os.path.isdir(hint):
            consider(hint)
            continue
        d = os.path.dirname(os.path.abspath(hint))
        base = os.path.basename(d).lower()
        # <root>/Scripts/conda.exe 或 <root>/bin/conda → 上溯到根
        if base in ("scripts", "bin", "condabin"):
            consider(os.path.dirname(d))
        else:
            consider(d)

    # 3) 注册表(PEP 514 ContinuumAnalytics, 覆盖自定义盘符安装)
    _scan_conda_registry(consider)

    return roots


def _scan_conda_registry(consider) -> None:
    """遍历注册表 ContinuumAnalytics 分支, 将安装根目录交给 consider。"""
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return
    branches = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Python\ContinuumAnalytics"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Python\ContinuumAnalytics"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Python\ContinuumAnalytics"),
    ]
    for hive, subkey in branches:
        try:
            root_key = winreg.OpenKey(hive, subkey)
        except OSError:
            continue
        with root_key:
            index = 0
            while True:
                try:
                    ver = winreg.EnumKey(root_key, index)
                    index += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(
                            root_key, ver + r"\InstallPath") as ip:
                        install_dir = winreg.QueryValueEx(ip, "")[0]
                        if install_dir:
                            consider(install_dir)
                except OSError:
                    continue


# 向后兼容别名
_conda_roots = find_conda_roots
