"""目标环境包元数据采集。

数据获取方式:以子进程方式运行目标解释器, 通过标准库
``importlib.metadata.distributions()`` 枚举该环境 ``site-packages`` 中的
全部发行版, 导出每个包的名称、版本与 ``Requires-Dist`` 依赖声明
(PEP 508 原始文本), 以 JSON(print, ensure_ascii 默认转义为纯 ASCII)回传。

选择 ``importlib.metadata`` 而非 ``pip list`` 的原因:
- 一次性拿到包名 + 版本 + 依赖声明三元组(pip list 拿不到依赖声明);
- 只依赖目标解释器标准库(Python >= 3.8), 无需目标环境安装任何工具;
- 不受 pip 版本/镜像配置差异影响。
"""

from __future__ import annotations

import json
import subprocess

from .models import EnvironmentSnapshot, InstalledPackage, InterpreterInfo

# 在目标解释器中运行的采集脚本(仅用标准库)
COLLECT_SCRIPT = r'''
import json, sys, platform

# -I 隔离模式不含 user site-packages, 显式补回,
# 否则 pip install --user 安装的包会被静默漏采
try:
    import site
    usp = site.getusersitepackages()
    if usp and usp not in sys.path:
        sys.path.append(usp)
except Exception:
    pass

from importlib.metadata import distributions

seen = {}
for dist in distributions():
    try:
        name = dist.metadata["Name"]
    except Exception:
        continue
    if not name:
        continue
    try:
        version = dist.version or ""
    except Exception:
        version = ""
    try:
        requires = list(dist.requires or [])
    except Exception:
        requires = []
    key = name.strip().lower()
    entry = {"name": name.strip(), "version": version, "requires": requires}
    old = seen.get(key)
    if old is None:
        seen[key] = entry
    else:
        # 同名重复发行版(egg-info 与 dist-info 并存等): 按字段级合并,
        # 版本与依赖声明分别取更完整的一侧, 避免整条替换丢信息
        if not old["version"] and entry["version"]:
            old["version"] = entry["version"]
        if len(entry["requires"]) > len(old["requires"]):
            old["requires"] = entry["requires"]

payload = {
    "python_version": ".".join(str(x) for x in sys.version_info[:2]),
    "python_full_version": platform.python_version(),
    "platform_machine": platform.machine(),
    "packages": list(seen.values()),
}
print(json.dumps(payload))
'''

COLLECT_TIMEOUT = 300  # 秒; 大型环境枚举元数据可能较慢


class CollectionError(RuntimeError):
    """包采集失败。"""


def collect_packages(
    interpreter: InterpreterInfo, progress=None
) -> EnvironmentSnapshot:
    """采集目标解释器环境中已安装的全部包及其依赖声明。

    :param interpreter: 目标解释器
    :param progress:    可选回调 ``progress(str)`` 向 UI 推送进度
    :raises CollectionError: 目标解释器无法运行采集脚本(如 Python < 3.8)
    """
    if progress is not None:
        try:
            progress(f"正在读取 {interpreter.version or interpreter.path} 环境的包元数据…")
        except Exception:
            pass

    argv = [interpreter.path, "-I", "-c", COLLECT_SCRIPT]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=COLLECT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise CollectionError(
            f"采集超时(>{COLLECT_TIMEOUT} 秒), 目标环境可能异常"
        ) from exc
    except OSError as exc:
        raise CollectionError(f"无法启动解释器: {exc}") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if ("No module named 'importlib.metadata'" in stderr
                or "No module named 'importlib'" in stderr):
            raise CollectionError(
                "目标解释器缺少 importlib.metadata(需要 Python 3.8+), 无法采集"
            )
        tail = stderr.splitlines()[-1] if stderr else f"退出码 {proc.returncode}"
        raise CollectionError(f"目标解释器执行失败: {tail}")

    try:
        lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
        # 从后向前找第一条结构正确的 JSON 对象行(含 "packages" 键):
        # 目标环境 atexit 钩子可能在 print 之后又输出内容污染末行,
        # 甚至输出一行合法但不相关的 JSON —— 结构不符时继续向前扫描
        data = None
        for line in reversed(lines):
            if not line.lstrip().startswith("{"):
                continue
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and "packages" in candidate:
                data = candidate
                break
        if data is None:
            raise json.JSONDecodeError("未找到有效的采集结果", "\n".join(lines[-3:]), 0)
        raw_packages = data["packages"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CollectionError(f"采集结果解析失败: {exc}") from exc

    if not isinstance(raw_packages, list):
        raise CollectionError(
            f"采集结果结构异常: packages 不是列表({type(raw_packages).__name__})")

    packages: list[InstalledPackage] = []
    for p in raw_packages:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        version = p.get("version")
        requires = p.get("requires")
        packages.append(InstalledPackage(
            name=name,
            version="" if version is None else str(version),
            requires=[str(r) for r in (requires or [])
                      if isinstance(r, str) and r.strip()],
        ))
    packages.sort(key=lambda p: p.name.lower())

    if progress is not None:
        try:
            progress(f"采集完成, 共 {len(packages)} 个包")
        except Exception:
            pass

    return EnvironmentSnapshot(
        interpreter=interpreter,
        python_version=str(data.get("python_version", "")),
        python_full_version=str(data.get("python_full_version", "")),
        platform_machine=str(data.get("platform_machine", "")),
        packages=packages,
    )
