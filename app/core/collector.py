"""目标环境包元数据采集。

数据获取方式: 以子进程运行目标解释器, 通过标准库
``importlib.metadata.distributions()`` 枚举该环境 site-packages 中的全部
发行版, 导出 名称 + 版本 + ``Requires-Dist`` 依赖声明 + License 元数据。

返回协议(1.2.0 起): 采集脚本把 JSON **写入命令行指定的临时文件**,
stdout 只输出一行 ``COLLECT_OK`` 标记 —— 避免数千包时几 MB 单行 JSON
与目标环境 atexit 输出互相污染; 同时保留 stdout 解析作为兼容回退。

可取消: ``cancel_event``(threading.Event) 置位后立即终止子进程。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading

from .models import EnvironmentSnapshot, InstalledPackage, InterpreterInfo

RESULT_MARKER = "COLLECT_OK"

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

def _license_of(meta):
    try:
        lic = (meta.get("License") or "").strip()
    except Exception:
        lic = ""
    if not lic:
        try:
            for c in meta.get_all("Classifier") or []:
                if c.startswith("License ::"):
                    lic = c.replace("License ::", "").strip(" :")
                    break
        except Exception:
            pass
    # 多行许可证全文只保留首行, 并截断, 避免快照膨胀
    lic = lic.splitlines()[0].strip() if lic else ""
    return lic[:80]

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
    lic = _license_of(dist.metadata)
    key = name.strip().lower()
    entry = {"name": name.strip(), "version": version,
             "requires": requires, "license": lic}
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
        if not old.get("license") and entry.get("license"):
            old["license"] = entry["license"]

payload = {
    "python_version": ".".join(str(x) for x in sys.version_info[:2]),
    "python_full_version": platform.python_version(),
    "platform_machine": platform.machine(),
    "packages": list(seen.values()),
}

out_path = sys.argv[1] if len(sys.argv) > 1 else ""
if out_path:
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print("COLLECT_OK")
else:
    print(json.dumps(payload))
'''

COLLECT_TIMEOUT = 300  # 秒; 大型环境枚举元数据可能较慢
_POLL_INTERVAL = 0.2


class CollectionError(RuntimeError):
    """包采集失败。"""


def _parse_payload(data) -> tuple[list[InstalledPackage], dict]:
    if not isinstance(data, dict):
        raise CollectionError(
            f"采集结果结构异常: 顶层不是对象({type(data).__name__})")
    raw_packages = data.get("packages")
    if not isinstance(raw_packages, list):
        raise CollectionError(
            f"采集结果结构异常: packages 不是列表"
            f"({type(raw_packages).__name__})")
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
            license_text=str(p.get("license") or "")[:80],
        ))
    packages.sort(key=lambda p: p.name.lower())
    return packages, data


def collect_packages(
    interpreter: InterpreterInfo, progress=None,
    cancel_event: threading.Event | None = None,
) -> EnvironmentSnapshot:
    """采集目标解释器环境中已安装的全部包及其元数据。

    :param interpreter: 目标解释器
    :param progress:    可选回调 ``progress(str)`` 向 UI 推送进度
    :param cancel_event: 置位后终止采集并抛 CollectionError("已取消")
    :raises CollectionError: 目标解释器无法运行或采集失败/被取消
    """
    if progress is not None:
        try:
            progress(f"正在读取 {interpreter.version or interpreter.path} 环境的包元数据…")
        except Exception:
            pass

    fd, out_path = tempfile.mkstemp(prefix="pyenv-collect-", suffix=".json")
    os.close(fd)
    argv = [interpreter.path, "-I", "-c", COLLECT_SCRIPT, out_path]
    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except OSError as exc:
        _safe_remove(out_path)
        raise CollectionError(f"无法启动解释器: {exc}") from exc

    # 轮询等待: 支持取消与超时(不阻塞在管道读取上)
    import time
    deadline = time.monotonic() + COLLECT_TIMEOUT
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            proc.kill()
            proc.communicate()
            _safe_remove(out_path)
            raise CollectionError("采集已取消")
        if time.monotonic() > deadline:
            proc.kill()
            proc.communicate()
            _safe_remove(out_path)
            raise CollectionError(
                f"采集超时(>{COLLECT_TIMEOUT} 秒), 目标环境可能异常")
        time.sleep(_POLL_INTERVAL)

    stdout, stderr = proc.communicate()
    try:
        if proc.returncode != 0:
            err = (stderr or "").strip()
            if ("No module named 'importlib.metadata'" in err
                    or "No module named 'importlib'" in err):
                raise CollectionError(
                    "目标解释器缺少 importlib.metadata(需要 Python 3.8+), 无法采集")
            tail = err.splitlines()[-1] if err else f"退出码 {proc.returncode}"
            raise CollectionError(f"目标解释器执行失败: {tail}")

        data = None
        # 主通道: 临时文件
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            try:
                with open(out_path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                data = None
        # 兼容回退: stdout 中最后一条结构正确的 JSON 行
        if data is None:
            for line in reversed([ln for ln in (stdout or "").splitlines()
                                  if ln.strip()]):
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
            raise CollectionError("采集结果解析失败: 未找到有效 JSON(临时文件与 stdout 均无)")
    finally:
        _safe_remove(out_path)

    packages, meta = _parse_payload(data)

    if progress is not None:
        try:
            progress(f"采集完成, 共 {len(packages)} 个包")
        except Exception:
            pass

    return EnvironmentSnapshot(
        interpreter=interpreter,
        python_version=str(meta.get("python_version", "")),
        python_full_version=str(meta.get("python_full_version", "")),
        platform_machine=str(meta.get("platform_machine", "")),
        packages=packages,
    )


def _safe_remove(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
