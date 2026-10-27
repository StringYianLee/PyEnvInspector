"""环境管理:解释器安装/删除、conda 环境创建/删除、pip/conda 包装卸。

设计要点
========
- **解释器安装**: 从 python-build-standalone(独立发行版)下载 tar.gz,
  多镜像回退(gh-proxy → ghfast → 直连), sha256 校验后解压到
  ``~/PyEnvInspector/runtimes/py-<版本>`` 并写入托管标记文件;
  免管理员、免安装器、便携。
- **删除保护**: 仅允许删除带托管标记的解释器;conda base 永不可删;
  删除前用 Windows API(EnumProcesses)检测目标目录是否被运行中的
  进程占用, 占用即拒绝并列出进程。
- **包操作**: subprocess.Popen 流式读取输出(on_output 回调 → UI 日志),
  失败时按常见模式翻译为可操作的错误提示。
- 所有函数异常安全: 失败抛 ``EnvManagerError``(message 为人读文本)。
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MANAGED_MARKER = "pyenv-inspector-managed.json"
PBS_RELEASE = "20241016"

# 可安装的 Python 版本(经 2026-10-27 实测确认存在于该 release)
PYTHON_DISTRIBUTIONS = {
    "3.13": "cpython-3.13.0+20241016-x86_64-pc-windows-msvc-install_only.tar.gz",
    "3.12": "cpython-3.12.7+20241016-x86_64-pc-windows-msvc-install_only.tar.gz",
    "3.11": "cpython-3.11.10+20241016-x86_64-pc-windows-msvc-install_only.tar.gz",
    "3.10": "cpython-3.10.15+20241016-x86_64-pc-windows-msvc-install_only.tar.gz",
    "3.9": "cpython-3.9.20+20241016-x86_64-pc-windows-msvc-install_only.tar.gz",
}

# 下载镜像(顺序即优先级; gh-proxy 实测最快, GitHub 直连兜底)
_MIRROR_TEMPLATES = (
    "https://gh-proxy.com/https://github.com/astral-sh/python-build-standalone/releases/download/{release}/{file}",
    "https://ghfast.top/https://github.com/astral-sh/python-build-standalone/releases/download/{release}/{file}",
    "https://github.com/astral-sh/python-build-standalone/releases/download/{release}/{file}",
)

PIPY_INDEXES = {
    "官方": None,
    "清华": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "阿里": "https://mirrors.aliyun.com/pypi/simple/",
}

_ENV_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,49}$")


class EnvManagerError(Exception):
    """环境管理操作失败(message 为可直接展示的人读文本)。"""


# ---------------------------------------------------------------------------
# 托管目录
# ---------------------------------------------------------------------------

def get_managed_root() -> str:
    return os.path.join(os.path.expanduser("~"), "PyEnvInspector")


def get_runtimes_dir() -> str:
    return os.path.join(get_managed_root(), "runtimes")


def is_managed_interpreter(path: str) -> bool:
    """解释器目录是否由本工具安装(存在托管标记)。"""
    marker = os.path.join(os.path.dirname(path), MANAGED_MARKER)
    return os.path.isfile(marker)


def list_managed_interpreters() -> list[dict]:
    """列出本工具安装的全部解释器。"""
    runtimes = get_runtimes_dir()
    result: list[dict] = []
    if not os.path.isdir(runtimes):
        return result
    for name in sorted(os.listdir(runtimes)):
        env_dir = os.path.join(runtimes, name)
        marker = os.path.join(env_dir, MANAGED_MARKER)
        exe = os.path.join(env_dir,
                           "python.exe" if os.name == "nt" else "bin/python")
        if os.path.isfile(marker) and os.path.isfile(exe):
            try:
                with open(marker, encoding="utf-8") as fh:
                    meta = json.load(fh)
            except (OSError, json.JSONDecodeError):
                meta = {}
            result.append({
                "dir": env_dir,
                "python_exe": exe,
                "version": meta.get("python_version", name),
                "installed_at": meta.get("installed_at", ""),
            })
    return result


def _write_marker(env_dir: str, python_version: str) -> None:
    import datetime
    marker = {
        "tool": "PyEnv Inspector",
        "python_version": python_version,
        "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(env_dir, MANAGED_MARKER), "w",
              encoding="utf-8") as fh:
        json.dump(marker, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------

def download_file(url: str, dest: str, on_output=None,
                  timeout: int = 90) -> None:
    """下载文件到 dest(带进度回调), 失败抛 EnvManagerError。"""
    req = urllib.request.Request(url, headers={"User-Agent": "PyEnvInspector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(512 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if on_output is not None:
                        pct = f"{done * 100 // total}%" if total else f"{done // 1024} KB"
                        on_output(f"    已下载 {pct} ({done // 1024 // 1024} MB)")
    except urllib.error.HTTPError as exc:
        raise EnvManagerError(f"下载失败: HTTP {exc.code} ({url})") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise EnvManagerError(f"下载失败: {exc} ({url})") from exc


def _download_with_mirrors(filename: str, dest: str, on_output) -> None:
    """多镜像依次尝试下载; 全部失败抛错(含网络诊断建议)。"""
    errors: list[str] = []
    for i, tpl in enumerate(_MIRROR_TEMPLATES, start=1):
        url = tpl.format(release=PBS_RELEASE, file=filename)
        if on_output:
            on_output(f"尝试下载源 {i}/{len(_MIRROR_TEMPLATES)}: "
                      f"{url.split('/https://')[-1][:70]}…")
        try:
            download_file(url, dest, on_output=on_output)
            if on_output:
                on_output(f"下载完成: {os.path.getsize(dest) // 1024 // 1024} MB")
            return
        except EnvManagerError as exc:
            errors.append(str(exc))
            if on_output:
                on_output(f"    该源失败, 换下一个…")
    raise EnvManagerError(
        "所有下载源均失败, 可能原因:\n"
        "  · 网络不可用或防火墙拦截\n"
        "  · 镜像服务暂时不可用\n"
        "详细错误:\n" + "\n".join(errors))


def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Python 解释器: 安装 / 删除
# ---------------------------------------------------------------------------

def install_python(version: str, on_output=None) -> str:
    """安装指定版本的 Python, 返回解释器安装目录。

    步骤: 检查重复 → 多镜像下载 tar.gz → sha256 校验 → 解压 → 写托管标记。
    """
    if on_output is None:
        on_output = lambda msg: None
    if version not in PYTHON_DISTRIBUTIONS:
        raise EnvManagerError(
            f"不支持的版本 {version!r}。可安装: {', '.join(sorted(PYTHON_DISTRIBUTIONS))}")

    env_dir = os.path.join(get_runtimes_dir(), f"py-{version}")
    if os.path.isdir(env_dir):
        raise EnvManagerError(f"Python {version} 已安装于 {env_dir}")

    filename = PYTHON_DISTRIBUTIONS[version]
    on_output(f"准备安装 Python {version} …")

    with tempfile.TemporaryDirectory(prefix="pyenv-inspector-") as tmp:
        archive = os.path.join(tmp, filename)
        _download_with_mirrors(filename, archive, on_output)

        # sha256 校验(校验文件下载失败→警告跳过; 内容不匹配→中断安装)
        on_output("校验文件完整性 (sha256)…")
        sha_url = _MIRROR_TEMPLATES[0].format(
            release=PBS_RELEASE, file=filename + ".sha256")
        sha_file = archive + ".sha256"
        try:
            download_file(sha_url, sha_file)
            expected = open(sha_file, encoding="utf-8").read().split()[0].lower()
            actual = _sha256_of(archive)
            if actual != expected:
                raise EnvManagerError(
                    f"文件校验失败(sha256 不匹配: {actual[:12]}…), "
                    "已放弃安装。请重试或更换网络环境。")
            on_output("校验通过")
        except EnvManagerError as exc:
            if "sha256 不匹配" in str(exc):
                raise  # 内容被篡改/损坏: 必须中断
            on_output(f"警告: 无法下载校验文件, 跳过 sha256 校验 ({exc})")

        # 解压
        on_output("解压到目标目录…")
        extract_to = os.path.join(tmp, "extracted")
        os.makedirs(extract_to, exist_ok=True)
        try:
            with tarfile.open(archive, "r:gz") as tf:
                try:
                    tf.extractall(extract_to, filter="data")
                except TypeError:  # Python < 3.12 无 filter 参数
                    tf.extractall(extract_to)
        except tarfile.TarError as exc:
            raise EnvManagerError(f"解压失败: {exc}") from exc

        # 归位: 包内根为 python/ → 移动到 runtimes/py-<version>
        src_root = os.path.join(extract_to, "python")
        if not os.path.isdir(src_root):
            src_root = extract_to
        os.makedirs(os.path.dirname(env_dir), exist_ok=True)
        shutil.move(src_root, env_dir)

    # 探测实际版本并写标记
    exe = os.path.join(
        env_dir, "python.exe" if os.name == "nt" else os.path.join("bin", "python"))
    if not os.path.isfile(exe):
        shutil.rmtree(env_dir, ignore_errors=True)
        raise EnvManagerError("解压结果异常: 未找到 python 可执行文件")
    code, out = run_streaming([exe, "-c", "import platform; print(platform.python_version())"])
    actual_version = out.strip().splitlines()[-1] if out.strip() else version
    _write_marker(env_dir, actual_version)
    on_output(f"✔ Python {actual_version} 安装完成: {env_dir}")
    return env_dir


def remove_interpreter(env_dir: str, on_output=None) -> None:
    """删除托管解释器(含占用检测; 非托管解释器拒绝删除)。"""
    if on_output is None:
        on_output = lambda msg: None
    env_dir = os.path.normpath(os.path.abspath(env_dir))
    if not is_managed_interpreter(
            os.path.join(env_dir,
                         "python.exe" if os.name == "nt" else "bin/python")):
        raise EnvManagerError(
            "该解释器不是由本工具安装的(无托管标记), 为安全起见不支持删除。\n"
            f"路径: {env_dir}")
    blockers = find_processes_using_dir(env_dir)
    if blockers:
        detail = "\n".join(f"  PID {pid}  {name}" for pid, name, _ in blockers)
        raise EnvManagerError(
            f"该环境正被以下进程占用, 请先关闭后重试:\n{detail}")
    on_output("正在删除解释器目录…")
    shutil.rmtree(env_dir)
    on_output(f"✔ 已删除: {env_dir}")


# ---------------------------------------------------------------------------
# 进程占用检测 (Windows API; POSIX 简化为空)
# ---------------------------------------------------------------------------

def find_processes_using_dir(target_dir: str) -> list[tuple[int, str, str]]:
    """列出可执行文件位于 target_dir 之下的运行中进程 [(pid, name, path)]。"""
    target = os.path.normcase(os.path.normpath(target_dir)) + os.sep
    result: list[tuple[int, str, str]] = []
    if os.name != "nt":
        return result
    try:
        import ctypes.wintypes as wt
        psapi = ctypes.WinDLL("Psapi.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        arr = (wt.DWORD * 8192)()
        cb = wt.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr),
                                   ctypes.byref(cb)):
            return result
        count = cb.value // ctypes.sizeof(wt.DWORD)
        for i in range(count):
            pid = arr[i]
            if not pid:
                continue
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
            if not handle:
                continue
            try:
                buf = ctypes.create_unicode_buffer(2048)
                size = wt.DWORD(2048)
                if psapi.GetModuleFileNameExW(handle, None, buf, size):
                    exe_path = buf.value
                    if os.path.normcase(os.path.normpath(exe_path)).startswith(target):
                        result.append((pid, os.path.basename(exe_path), exe_path))
            finally:
                kernel32.CloseHandle(handle)
    except Exception:
        pass  # 探测失败不阻塞流程(删除时 rmtree 若遇占用会再报 PermissionError)
    return result


# ---------------------------------------------------------------------------
# 命令流式执行
# ---------------------------------------------------------------------------

def run_streaming(cmd: list[str], on_output=None, timeout: int = 1800,
                  cwd: str | None = None) -> tuple[int, str]:
    """运行命令并逐行回传输出。返回 (退出码, 合并输出)。

    超时语义: 总时长上限(含无输出挂起)。读取在独立线程进行,
    主循环 1 秒轮询——子进程挂起时按 deadline 强杀并抛错,
    避免无限阻塞导致 UI 操作卡死。
    """
    if on_output is None:
        on_output = lambda msg: None
    import threading
    import queue as _queue
    import time as _time

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        bufsize=1, cwd=cwd,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    lines: _queue.Queue = _queue.Queue()
    assert proc.stdout is not None

    def _reader() -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)  # EOF 哨兵

    threading.Thread(target=_reader, daemon=True).start()

    collected: list[str] = []
    deadline = _time.monotonic() + timeout
    while True:
        try:
            line = lines.get(timeout=1.0)
        except _queue.Empty:
            if _time.monotonic() > deadline:
                proc.kill()
                raise EnvManagerError(
                    f"命令执行超时({timeout}s), 已强制终止: {' '.join(cmd[:3])}…")
            continue
        if line is None:
            break
        line = line.rstrip()
        if line:
            collected.append(line)
            on_output(line)
    try:
        code = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = proc.returncode if proc.returncode is not None else -1
    return code, "\n".join(collected)


# ---------------------------------------------------------------------------
# conda 环境创建 / 删除
# ---------------------------------------------------------------------------

def validate_env_name(name: str) -> None:
    if not _ENV_NAME_RE.match(name or ""):
        raise EnvManagerError(
            f"环境名 {name!r} 不合法。要求: 以字母开头, 仅含字母/数字/下划线/连字符, "
            "长度 1-50。")


def create_conda_env(conda_exe: str, conda_root: str, name: str,
                     python_version: str, on_output=None) -> str:
    """创建 conda 环境(独立路径 envs/<name>), 返回环境路径。"""
    validate_env_name(name)
    env_path = os.path.join(conda_root, "envs", name)
    if os.path.isdir(env_path):
        raise EnvManagerError(f"环境已存在: {env_path}")
    cmd = [conda_exe, "create", "-p", env_path, "-y"]
    if python_version:
        cmd.append(f"python={python_version}")
    if on_output:
        on_output(f"$ {' '.join(cmd)}")
    code, out = run_streaming(cmd, on_output)
    if code != 0:
        raise EnvManagerError(
            f"conda 环境创建失败 (退出码 {code}):\n"
            + translate_error("conda", "create", out))
    return env_path


def remove_conda_env(conda_exe: str, conda_root: str, name: str,
                     env_path: str, on_output=None) -> None:
    """删除 conda 环境(保护 base + 路径一致性校验 + 占用检测)。"""
    if name.lower() == "base":
        raise EnvManagerError("base 是 conda 的基础环境, 不允许删除。")
    validate_env_name(name)
    env_path = os.path.normpath(os.path.abspath(env_path))
    if not os.path.isdir(env_path):
        raise EnvManagerError(f"环境目录不存在: {env_path}")
    # 安全校验: env_path 必须位于 <conda_root>/envs/<name>, 防止
    # name 合法但 path 指向 base/任意目录时被误删
    expected_parent = os.path.normpath(
        os.path.join(os.path.normpath(os.path.abspath(conda_root)), "envs"))
    if (os.path.dirname(env_path) != expected_parent
            or os.path.basename(env_path).lower() != name.lower()):
        raise EnvManagerError(
            "环境路径与环境名不匹配, 已阻止删除(安全保护)。\n"
            f"  期望: {expected_parent}{os.sep}{name}\n"
            f"  实际: {env_path}")
    blockers = find_processes_using_dir(env_path)
    if blockers:
        detail = "\n".join(f"  PID {pid}  {name2}" for pid, name2, _ in blockers)
        raise EnvManagerError(
            f"该环境正被以下进程占用, 请先关闭后重试:\n{detail}")
    cmd = [conda_exe, "env", "remove", "-p", env_path, "-y"]
    if on_output:
        on_output(f"$ {' '.join(cmd)}")
    code, _ = run_streaming(cmd, on_output)
    if code != 0:
        raise EnvManagerError(f"conda 环境删除失败 (退出码 {code})")
    # conda env remove 有时残留空目录, 兜底清理
    if os.path.isdir(env_path):
        shutil.rmtree(env_path, ignore_errors=True)
    if on_output:
        on_output(f"✔ 环境 {name} 已删除")


# ---------------------------------------------------------------------------
# 包安装 / 卸载 (pip 与 conda)
# ---------------------------------------------------------------------------

def pip_install(python_exe: str, spec: str, index_label: str = "官方",
                on_output=None) -> None:
    if not spec.strip():
        raise EnvManagerError("请输入要安装的包名(如 requests==2.31.0)")
    cmd = [python_exe, "-m", "pip", "install", *spec.split(),
           "--disable-pip-version-check"]
    index = PIPY_INDEXES.get(index_label)
    if index:
        cmd += ["-i", index]
    if on_output:
        on_output(f"$ {' '.join(cmd)}")
    code, out = run_streaming(cmd, on_output, timeout=3600)
    if code != 0:
        raise EnvManagerError(
            f"pip 安装失败 (退出码 {code}):\n"
            + translate_error("pip", "install", out))
    if on_output:
        on_output(f"✔ 安装成功: {spec}")


def pip_uninstall(python_exe: str, package: str, on_output=None) -> None:
    if not package.strip():
        raise EnvManagerError("请输入要卸载的包名")
    cmd = [python_exe, "-m", "pip", "uninstall", "-y", *package.split(),
           "--disable-pip-version-check"]
    if on_output:
        on_output(f"$ {' '.join(cmd)}")
    code, out = run_streaming(cmd, on_output)
    if code != 0:
        raise EnvManagerError(
            f"pip 卸载失败 (退出码 {code}):\n"
            + translate_error("pip", "uninstall", out))
    if on_output:
        on_output(f"✔ 卸载成功: {package}")


def conda_install(conda_exe: str, env_path: str, spec: str,
                  on_output=None) -> None:
    if not spec.strip():
        raise EnvManagerError("请输入要安装的包名(如 numpy 或 numpy=1.26)")
    cmd = [conda_exe, "install", "-p", env_path, "-y", *spec.split()]
    if on_output:
        on_output(f"$ {' '.join(cmd)}")
    code, out = run_streaming(cmd, on_output, timeout=3600)
    if code != 0:
        raise EnvManagerError(
            f"conda 安装失败 (退出码 {code}):\n"
            + translate_error("conda", "install", out))
    if on_output:
        on_output(f"✔ 安装成功: {spec}")


def conda_remove(conda_exe: str, env_path: str, package: str,
                 on_output=None) -> None:
    if not package.strip():
        raise EnvManagerError("请输入要卸载的包名")
    cmd = [conda_exe, "remove", "-p", env_path, "-y", *package.split()]
    if on_output:
        on_output(f"$ {' '.join(cmd)}")
    code, out = run_streaming(cmd, on_output, timeout=3600)
    if code != 0:
        raise EnvManagerError(
            f"conda 卸载失败 (退出码 {code}):\n"
            + translate_error("conda", "remove", out))
    if on_output:
        on_output(f"✔ 卸载成功: {package}")


# ---------------------------------------------------------------------------
# 错误翻译: 把工具原始报错映射为可操作建议
# ---------------------------------------------------------------------------

def translate_error(tool: str, op: str, output: str) -> str:
    """从工具输出提取关键错误并附操作建议。"""
    tail = "\n".join(output.strip().splitlines()[-12:])
    low = output.lower()
    hint = ""

    if "resolutionimpossible" in low or "conflict is caused by" in low:
        hint = ("检测到依赖冲突: 已安装的包与目标包的版本要求互相矛盾。\n"
                "建议: 降低/调整目标包版本, 或先卸载冲突的包。")
    elif "unsatisfiableerror" in low:
        hint = ("检测到依赖冲突: 频道中没有同时满足全部约束的组合。\n"
                "建议: 放宽版本约束, 或更换/添加频道。")
    elif "no matching distribution" in low or (
            "could not find a version" in low):
        hint = ("找不到匹配的发行版: 包名可能有误, 或该版本不存在/不支持当前 "
                "Python 版本。建议: 检查拼写, 或切换到其他 PyPI 镜像。")
    elif "connectionerror" in low or "timeout" in low or (
            "max retries exceeded" in low) or ("condahttperror" in low):
        hint = ("网络连接失败。建议: 检查网络/代理, 或在包管理页切换 "
                "PyPI 镜像(清华/阿里)后重试。")
    elif "ssl" in low and ("certificate" in low or "verify" in low):
        hint = "SSL 证书校验失败。建议: 检查系统时间或代理的证书配置。"
    elif "permissionerror" in low or "errno 13" in low or (
            "access is denied" in low):
        hint = ("权限不足或文件被占用: 关闭正在使用该环境的程序(编辑器/"
                "终端/应用)后重试。")
    elif "notfounderror" in low and "pip" in low:
        hint = "要卸载的包未安装。可在包列表页确认包名。"
    elif "packagesnotfounderror" in low or "packagenotfounderror" in low:
        hint = ("频道中找不到该包。建议: 确认拼写, 或用 conda-forge 频道; "
                "纯 Python 包也可改用 pip 安装。")
    elif "environmentnamenotfound" in low or "notfound" in low and "env" in low:
        hint = "指定的环境不存在, 请刷新环境列表。"

    if hint:
        return f"{hint}\n---- 工具输出(末尾) ----\n{tail}"
    return f"---- 工具输出(末尾) ----\n{tail}"
