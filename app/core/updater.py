"""更新检查(尽力而为, 网络不可用时静默降级)。

GitHub API 在本机网络下常被阻断, 因此按 gh-proxy → ghfast → 直连 的顺序
尝试; 全部失败时返回 ``UpdateResult(error=...)`` 而不是抛异常 ——
更新检查失败不应影响主功能。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from packaging.version import InvalidVersion, Version

REPO = "StringYianLee/PyEnvInspector"
_ENDPOINTS = (
    "https://gh-proxy.com/https://api.github.com/repos/{repo}/releases/latest",
    "https://ghfast.top/https://api.github.com/repos/{repo}/releases/latest",
    "https://api.github.com/repos/{repo}/releases/latest",
)
TIMEOUT = 12


@dataclass
class UpdateResult:
    current: str
    latest: str = ""
    url: str = ""
    notes: str = ""
    error: str = ""

    @property
    def has_update(self) -> bool:
        if not self.latest:
            return False
        try:
            return Version(self.latest.lstrip("vV")) > Version(
                self.current.lstrip("vV"))
        except InvalidVersion:
            return False


def check_latest(current_version: str, fetch=None) -> UpdateResult:
    """查询最新 Release。

    :param fetch: 可注入的 ``fetch(url) -> dict``(测试用), 默认走 urllib
    """
    result = UpdateResult(current=current_version)
    last_error = ""
    for template in _ENDPOINTS:
        url = template.format(repo=REPO)
        try:
            data = fetch(url) if fetch is not None else _urlopen_json(url)
        except (urllib.error.URLError, TimeoutError, OSError,
                json.JSONDecodeError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        if not isinstance(data, dict):
            last_error = "响应格式异常"
            continue
        tag = str(data.get("tag_name") or "").strip()
        if not tag:
            last_error = "响应缺少 tag_name"
            continue
        result.latest = tag
        result.url = str(data.get("html_url") or "")
        body = str(data.get("body") or "")
        result.notes = body[:400]
        return result
    result.error = last_error or "无法访问 GitHub"
    return result


def _urlopen_json(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "PyEnvInspector-Updater",
                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)
