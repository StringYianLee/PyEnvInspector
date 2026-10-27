"""Conda 专属扫描:环境列表 / 已安装包 / 环境路径 / 配置文件。

设计原则:**零依赖、零子进程优先**。conda 的安装结构是纯文件系统可读的:

- 环境列表  : conda 根目录 + 各 ``envs_dirs`` 下的子目录
              (目录中存在 ``conda-meta/`` 即视为 conda 环境)
- 已安装包  : ``<env>/conda-meta/*.json`` —— conda 原生安装的每个包
              (python 本体、openssl、zlib、numpy 等)都有对应记录,
              含名称 / 版本 / 频道 / 构建串;pip 安装的包不在此列,
              由既有的 ``importlib.metadata`` 采集流程覆盖
- 环境路径  : 环境根目录 + 其中 python 解释器位置
- 配置文件  : 按优先级扫描 ``$CONDARC`` / ``~/.condarc`` /
              ``<root>/.condarc`` / 系统级 ``ProgramData\\conda\\.condarc``
              (POSIX: ``/etc/conda/.condarc``), 用内置的 YAML 子集
              解析器提取 channels / envs_dirs 等常用键(不依赖 pyyaml)

仅获取 conda 自身版本时尝试运行 ``conda --version``(10 秒超时, 失败
不影响其余扫描结果)。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from .models import (
    CondaConfigFile,
    CondaEnvironment,
    CondaInfo,
    CondaPackage,
)

_CONDA_VERSION_TIMEOUT = 10  # 秒

# condarc 中用户最常关心的键(用于内容摘要展示)
_INTERESTING_KEYS = (
    "channels", "envs_dirs", "channel_priority", "ssl_verify",
    "auto_activate_base", "default_channels", "custom_channels",
    "pkgs_dirs", "notify_outdated_conda", "restore_free_channel",
)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def scan_conda(progress=None) -> CondaInfo:
    """执行完整的 conda 扫描(永不抛异常, 错误进 errors 列表)。"""

    def report(msg: str) -> None:
        if progress is not None:
            try:
                progress(msg)
            except Exception:
                pass

    info = CondaInfo()
    report("正在定位 conda 安装…")

    # 1) 根目录(base 环境)与可执行文件 --------------------------------------
    roots = find_conda_roots()
    info.roots = roots
    if not roots:
        info.errors.append("未在本机发现 conda 安装(已检查用户目录与 ProgramData)")
        report("未发现 conda 安装")
        return info

    info.executable = _find_conda_executable(roots)
    report(f"发现 {len(roots)} 个 conda 根目录")

    # 2) 配置文件 -------------------------------------------------------------
    report("读取 .condarc 配置文件…")
    seen_paths: set[str] = set()
    merged_envs_dirs: list[str] = []
    merged_channels: list[str] = []
    for cf_path in _condarc_paths(roots):
        norm = os.path.normcase(os.path.abspath(cf_path))
        if norm in seen_paths:
            continue
        seen_paths.add(norm)
        cf = _read_condarc(cf_path)
        info.config_files.append(cf)
        if cf.exists:
            for ch in cf.channels:
                if ch not in merged_channels:
                    merged_channels.append(ch)
            for d in cf.envs_dirs:
                exp = os.path.expanduser(d)
                for resolved in _resolve_envs_dir(exp, roots):
                    if resolved not in merged_envs_dirs:
                        merged_envs_dirs.append(resolved)
    info.channels = merged_channels
    info.envs_dirs = merged_envs_dirs

    # 3) 环境列表与包 ----------------------------------------------------------
    # 搜索目录 = 各根的 envs/ + 配置文件中声明的 envs_dirs
    # (Windows 路径大小写/分隔符不敏感, 统一归一化去重, 避免重复扫描)
    def _norm(p: str) -> str:
        try:
            real = os.path.realpath(os.path.abspath(p))
        except OSError:
            real = os.path.abspath(p)
        return os.path.normcase(real)

    norm_roots = {_norm(r) for r in roots}

    search_dirs: list[str] = []
    seen_dirs: set[str] = set()

    def _add_search_dir(d: str) -> None:
        key = _norm(d)
        if key not in seen_dirs:
            seen_dirs.add(key)
            search_dirs.append(d)

    for root in roots:
        _add_search_dir(root)  # base 环境本身
        _add_search_dir(os.path.join(root, "envs"))
    for d in info.envs_dirs:
        for resolved in _resolve_envs_dir(d, roots):
            _add_search_dir(resolved)

    envs: list[CondaEnvironment] = []
    seen_env_paths: set[str] = set()
    for sd in search_dirs:
        if _norm(sd) in norm_roots:
            env = _scan_environment(sd, name="base", is_base=True)
            if env is not None and _norm(env.path) not in seen_env_paths:
                seen_env_paths.add(_norm(env.path))
                envs.append(env)
            continue
        if not os.path.isdir(sd):
            continue
        try:
            entries = sorted(os.listdir(sd))
        except OSError as exc:
            info.errors.append(f"无法读取环境目录 {sd}: {exc}")
            continue
        for name in entries:
            env_path = os.path.join(sd, name)
            if not os.path.isdir(env_path):
                continue
            env = _scan_environment(env_path, name=name, is_base=False)
            if env is not None and _norm(env.path) not in seen_env_paths:
                seen_env_paths.add(_norm(env.path))
                envs.append(env)

    envs.sort(key=lambda e: (not e.is_base, e.name.lower()))
    info.envs = envs
    report(f"共发现 {len(envs)} 个 conda 环境, "
           f"合计 {sum(e.package_count for e in envs)} 个 conda 包")

    # 4) conda 自身版本(可选, 失败不致命) ---------------------------------------
    if info.executable:
        info.version = _conda_version(info.executable)
    return info


# ---------------------------------------------------------------------------
# conda 安装定位
# ---------------------------------------------------------------------------

def find_conda_roots() -> list[str]:
    """发现本机 conda 根目录(base 环境路径)。复用解释器扫描的结果。"""
    from .scanner import find_conda_roots as _find
    return _find()


def _find_conda_executable(roots: list[str]) -> str:
    """定位 conda 可执行文件: PATH 优先, 其次各根目录。"""
    hit = shutil.which("conda")
    if hit:
        return hit
    rels = (("Scripts", "conda.exe"),) if os.name == "nt" \
        else (("bin", "conda"),)
    for root in roots:
        for rel in rels:
            candidate = os.path.join(root, *rel)
            if os.path.isfile(candidate):
                return candidate
    return ""


def _conda_version(executable: str) -> str:
    """运行 ``conda --version``;失败返回空串(不影响其余结果)。"""
    try:
        proc = subprocess.run(
            [executable, "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_CONDA_VERSION_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    out = (proc.stdout or "").strip()
    if out.startswith("conda "):
        return out.split()[1] if len(out.split()) > 1 else out
    return out


# ---------------------------------------------------------------------------
# 配置文件
# ---------------------------------------------------------------------------

def _condarc_paths(roots: list[str]) -> list[str]:
    """按优先级列出候选 .condarc 路径(环境变量 > 用户 > 根目录 > 系统)。"""
    paths: list[str] = []
    env_condarc = os.environ.get("CONDARC")
    if env_condarc:
        paths.append(env_condarc)
    paths.append(os.path.join(os.path.expanduser("~"), ".condarc"))
    for root in roots:
        paths.append(os.path.join(root, ".condarc"))
    if os.name == "nt":
        paths.append(os.path.join(
            os.environ.get("ProgramData", r"C:\ProgramData"), "conda", ".condarc"))
    else:
        paths.append("/etc/conda/.condarc")
    # 去重(保持优先级顺序)
    seen: set[str] = set()
    result: list[str] = []
    for p in paths:
        norm = os.path.normcase(os.path.abspath(p))
        if norm not in seen:
            seen.add(norm)
            result.append(p)
    return result


def _read_condarc(path: str) -> CondaConfigFile:
    """读取并解析单个 .condarc(不存在也返回记录, 供 UI 展示候选位置)。"""
    cf = CondaConfigFile(path=path)
    if not os.path.isfile(path):
        return cf
    cf.exists = True
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        cf.error = f"读取失败: {exc}"
        return cf
    except UnicodeDecodeError:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            cf.error = f"读取失败: {exc}"
            return cf
    try:
        cf.data = parse_condarc(text)
    except Exception as exc:  # 解析器兜底, 不让单文件拖垮整个扫描
        cf.error = f"解析失败: {exc}"
    return cf


def _resolve_envs_dir(envs_dir: str, roots: list[str]) -> list[str]:
    """解析 envs_dirs 条目: 绝对路径直接用; 相对路径同时尝试各 conda 根。"""
    if os.path.isabs(envs_dir):
        return [envs_dir]
    result = [envs_dir]  # 保留原样(相对 cwd), 兼容用户显式相对路径
    for root in roots:
        joined = os.path.normpath(os.path.join(root, envs_dir))
        if joined not in result:
            result.append(joined)
    return result


# ---------------------------------------------------------------------------
# 环境与包
# ---------------------------------------------------------------------------

def _scan_environment(
    env_path: str, name: str, is_base: bool
) -> CondaEnvironment | None:
    """扫描单个 conda 环境;无 conda-meta 时返回 None(非 conda 环境)。"""
    meta_dir = os.path.join(env_path, "conda-meta")
    if not os.path.isdir(meta_dir):
        return None

    env = CondaEnvironment(name=name, path=env_path, is_base=is_base)
    try:
        env.packages = _read_conda_meta_packages(meta_dir)
        env.readable = True
    except OSError as exc:
        # conda-meta 存在但不可读: 环境有效, 包列表缺失须上报
        env.packages = []
        env.readable = False
        env.error = f"conda-meta 读取失败: {exc}"
    env.python_version = _python_version_from_meta(env.packages)

    # 解释器位置
    exe = "python.exe" if os.name == "nt" else os.path.join("bin", "python")
    candidate = os.path.join(env_path, exe)
    if os.name != "nt" and not os.path.isfile(candidate):
        candidate = os.path.join(env_path, "bin", "python3")
    if os.path.isfile(candidate):
        env.interpreter = candidate
    return env


def _read_conda_meta_packages(meta_dir: str) -> list[CondaPackage]:
    """解析 conda-meta/*.json 得到该环境的 conda 原生包列表。

    目录不可读时抛 OSError(由调用方标记环境异常)。
    """
    packages: list[CondaPackage] = []
    entries = sorted(os.listdir(meta_dir))  # OSError 向上抛
    for fn in entries:
        if not fn.endswith(".json"):
            continue
        full = os.path.join(meta_dir, fn)
        try:
            with open(full, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            # 单个包记录损坏不应影响其余; 文件名兜底: name-version-build.json
            stem = fn[:-5]
            parts = stem.rsplit("-", 2)
            if len(parts) == 3:
                packages.append(CondaPackage(
                    name=parts[0], version=parts[1], build_string=parts[2]))
            continue
        if not isinstance(data, dict):
            continue
        packages.append(CondaPackage(
            name=str(data.get("name") or ""),
            version=str(data.get("version") or ""),
            channel=_channel_from_url(str(data.get("url") or ""))
                    or str(data.get("channel") or ""),
            build_string=str(data.get("build") or ""),
        ))
    return packages


def _python_version_from_meta(packages: list[CondaPackage]) -> str:
    for p in packages:
        if p.name == "python":
            return p.version
    return ""


def _channel_from_url(url: str) -> str:
    """从包的下载 URL 提取频道名。"""
    if not url:
        return ""
    # https://conda.anaconda.org/conda-forge/win-64/xxx.conda
    m = re.search(r"conda\.anaconda\.org/([^/]+)", url)
    if m:
        return m.group(1)
    # https://repo.anaconda.com/pkgs/main/win-64/xxx.conda
    m = re.search(r"repo\.anaconda\.com/(pkgs/[^/]+)", url)
    if m:
        return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# .condarc 简易 YAML 子集解析(不依赖 pyyaml)
# ---------------------------------------------------------------------------

def _strip_inline_comment(content: str) -> str:
    """剥离行内注释(引号外的 ` #...` 部分)。"""
    if "#" not in content:
        return content
    in_quote = ""
    for i, ch in enumerate(content):
        if in_quote:
            if ch == in_quote:
                in_quote = ""
        elif ch in ("'", '"'):
            in_quote = ch
        elif ch == "#" and (i == 0 or content[i - 1] in (" ", "\t")):
            return content[:i].rstrip()
    return content


def parse_condarc(text: str) -> dict:
    """解析 .condarc 的常用子集。

    支持:顶层键、一层嵌套映射、``- item`` 列表、标量(字符串/整数/
    布尔/null)、``#`` 行注释与行内注释。复杂锚点/多文档等 YAML 特性
    不在 conda 常见配置范围内, 遇到时按标量处理。
    """
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("---", "..."):  # 文档分隔符
            continue
        stripped = _strip_inline_comment(stripped)
        if not stripped:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, stripped))

    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value if isinstance(value, dict) else {}


def _parse_block(
    lines: list[tuple[int, str]], i: int, indent: int
) -> "tuple[dict | list, int]":
    """解析一个缩进层;由首行决定该层是映射还是列表。"""
    if i < len(lines) and lines[i][1].startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(
    lines: list[tuple[int, str]], i: int, indent: int
) -> "tuple[dict, int]":
    result: dict = {}
    pending_key: str | None = None  # 空值 key, 等待同缩进列表回填
    while i < len(lines):
        cur_indent, content = lines[i]
        if cur_indent < indent:
            break
        if content.startswith("- "):
            if pending_key is not None:
                # 同缩进列表是合法 YAML(channels:\n- defaults), 回填
                lst, i = _parse_list(lines, i, cur_indent)
                result[pending_key] = lst
                pending_key = None
                continue
            i += 1  # 游离列表项, 跳过
            continue
        if cur_indent > indent:
            i += 1  # 异常缩进, 跳过
            continue
        key, _, val = content.partition(":")
        key = key.strip().strip("'\"")
        val = val.strip()
        i += 1
        pending_key = None
        if val:
            result[key] = _scalar(val)
        else:
            # 空值: 由下一行缩进决定嵌套结构
            if i < len(lines) and lines[i][0] > cur_indent:
                sub, i = _parse_block(lines, i, lines[i][0])
                result[key] = sub
            else:
                result[key] = None
                pending_key = key
    return result, i


def _parse_list(
    lines: list[tuple[int, str]], i: int, indent: int
) -> "tuple[list, int]":
    result: list = []
    while i < len(lines):
        cur_indent, content = lines[i]
        if cur_indent != indent or not content.startswith("- "):
            break
        item = content[2:].strip()
        i += 1
        if item:
            # "key: value" 形式的列表项(如 custom_channels 下)按字符串处理
            result.append(_scalar(item))
        # 纯 "-" 后的嵌套结构在 condarc 中罕见, 忽略
    return result, i


def _scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def summarize_config(cf: CondaConfigFile) -> dict:
    """提取配置文件中用户关心的键值(供 UI 展示)。"""
    if not cf.exists:
        return {}
    return {k: cf.data[k] for k in cf.top_keys if k in _INTERESTING_KEYS}
