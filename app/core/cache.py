"""环境快照磁盘缓存与历史记录。

目的:
- 重启应用后不必重新采集大型环境(采集通常 5-30 秒);
- 保留采集历史, 支持"与上次采集对比"。

存储位置(用户级可写目录):
    %LOCALAPPDATA%\\PyEnvInspector\\cache\\   (Windows)
    ~/.cache/pyenv-inspector/                 (POSIX)
        snapshots/<key>.json   最近一次快照
        history/<key>.jsonl    历史采集记录(每次一行, 最多保留 HISTORY_LIMIT 条)

快照键 = 解释器路径的归一化哈希(Windows 大小写不敏感)。
缓存有 TTL(默认 12 小时), 过期后调用方应重新采集; force=True 可忽略。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os

from .models import EnvironmentSnapshot, InstalledPackage, InterpreterInfo

CACHE_SCHEMA = 2
SNAPSHOT_TTL_SECONDS = 12 * 3600
HISTORY_LIMIT = 30


def cache_root() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    name = "PyEnvInspector" if os.name == "nt" else "pyenv-inspector"
    return os.path.join(base, name, "cache")


def _key(interp_path: str) -> str:
    norm = os.path.normcase(os.path.normpath(os.path.abspath(interp_path)))
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _snapshot_file(interp_path: str) -> str:
    return os.path.join(cache_root(), "snapshots", _key(interp_path) + ".json")


def _history_file(interp_path: str) -> str:
    return os.path.join(cache_root(), "history", _key(interp_path) + ".jsonl")


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------

def snapshot_to_dict(snap: EnvironmentSnapshot) -> dict:
    from dataclasses import asdict
    interp = asdict(snap.interpreter)
    return {
        "schema": CACHE_SCHEMA,
        "collected_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "interpreter": interp,
        "python_version": snap.python_version,
        "python_full_version": snap.python_full_version,
        "platform_machine": snap.platform_machine,
        "packages": [asdict(p) for p in snap.packages],
    }


def snapshot_from_dict(data: dict) -> EnvironmentSnapshot | None:
    try:
        if not isinstance(data, dict) or data.get("schema") != CACHE_SCHEMA:
            return None
        interp = InterpreterInfo(**{
            k: v for k, v in (data.get("interpreter") or {}).items()
            if k in InterpreterInfo.__dataclass_fields__
        })
        packages = [
            InstalledPackage(
                name=str(p.get("name", "")),
                version=str(p.get("version", "")),
                requires=[str(r) for r in (p.get("requires") or [])],
                license_text=str(p.get("license_text", "")),
            )
            for p in (data.get("packages") or []) if isinstance(p, dict)
            and p.get("name")
        ]
        return EnvironmentSnapshot(
            interpreter=interp,
            python_version=str(data.get("python_version", "")),
            python_full_version=str(data.get("python_full_version", "")),
            platform_machine=str(data.get("platform_machine", "")),
            packages=packages,
        )
    except (TypeError, ValueError, KeyError):
        return None


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------

def load_snapshot(interp_path: str, ttl: int = SNAPSHOT_TTL_SECONDS
                  ) -> EnvironmentSnapshot | None:
    """读取缓存快照; 不存在/损坏/过期时返回 None。"""
    path = _snapshot_file(interp_path)
    try:
        mtime = os.path.getmtime(path)
        if ttl > 0 and (datetime.datetime.now().timestamp() - mtime) > ttl:
            return None
        with open(path, encoding="utf-8") as fh:
            return snapshot_from_dict(json.load(fh))
    except (OSError, json.JSONDecodeError):
        return None


def save_snapshot(snap: EnvironmentSnapshot) -> None:
    """写入最近快照, 并向历史追加一条精简记录。"""
    data = snapshot_to_dict(snap)
    path = _snapshot_file(snap.interpreter.path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)   # 原子替换, 避免半写文件

    entry = {
        "collected_at": data["collected_at"],
        "python_full_version": snap.python_full_version,
        "packages": {p.name: p.version for p in snap.packages},
    }
    hist = _history_file(snap.interpreter.path)
    os.makedirs(os.path.dirname(hist), exist_ok=True)
    lines: list[str] = []
    if os.path.isfile(hist):
        try:
            with open(hist, encoding="utf-8") as fh:
                lines = [ln for ln in fh if ln.strip()]
        except OSError:
            lines = []
    lines.append(json.dumps(entry, ensure_ascii=False))
    lines = lines[-HISTORY_LIMIT:]
    with open(hist, "w", encoding="utf-8") as fh:
        fh.writelines(line if line.endswith("\n") else line + "\n"
                      for line in lines)


def load_history(interp_path: str) -> list[dict]:
    """历史采集记录(时间升序)。"""
    hist = _history_file(interp_path)
    result: list[dict] = []
    try:
        with open(hist, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and "packages" in item:
                    result.append(item)
    except OSError:
        return []
    return result


def invalidate(interp_path: str) -> None:
    """删除该环境的最近快照(保留历史)。"""
    try:
        os.remove(_snapshot_file(interp_path))
    except OSError:
        pass


def clear_all() -> None:
    """清空全部快照缓存(历史保留)。"""
    snap_dir = os.path.join(cache_root(), "snapshots")
    if not os.path.isdir(snap_dir):
        return
    for name in os.listdir(snap_dir):
        if name.endswith(".json"):
            try:
                os.remove(os.path.join(snap_dir, name))
            except OSError:
                pass


def cached_environments() -> list[dict]:
    """所有已缓存环境(供跨环境搜索/对比选择)。"""
    snap_dir = os.path.join(cache_root(), "snapshots")
    result: list[dict] = []
    if not os.path.isdir(snap_dir):
        return result
    for name in os.listdir(snap_dir):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(snap_dir, name), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        interp = data.get("interpreter") or {}
        result.append({
            "path": str(interp.get("path", "")),
            "version": str(interp.get("version", "")),
            "env_name": str(interp.get("env_name", "")),
            "python_full_version": str(data.get("python_full_version", "")),
            "package_count": len(data.get("packages") or []),
            "collected_at": str(data.get("collected_at", "")),
        })
    return result
