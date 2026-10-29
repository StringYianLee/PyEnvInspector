"""许可证聚合与合规概览。

许可证信息来自采集阶段的 METADATA License 字段(回退到 License :: 分类器)。
本模块只做**归一化与聚合**, 不联网、不做法律判断:

- 常见许可证归并到规范短名(MIT / Apache-2.0 / BSD-3-Clause / ...)
- 未知/空值归入「未声明」
- 给出分类统计(宽松 / 弱著佐权 / 强著佐权 / 未声明), 便于人工复核
"""

from __future__ import annotations

import re

from .models import EnvironmentSnapshot

# 归一化后所属类别(仅作提示, 不构成法律意见)
COPYLEFT_STRONG = {"GPL-2.0", "GPL-3.0", "AGPL-3.0"}
COPYLEFT_WEAK = {"LGPL-2.1", "LGPL-3.0", "MPL-2.0", "EPL-2.0", "CDDL-1.0"}
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
              "ISC", "PSF-2.0", "Unlicense", "CC0-1.0", "Zlib"}

UNKNOWN_LABEL = "未声明"

# (正则, 规范名) —— 顺序即优先级
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bAGPL|\bAffero", re.I), "AGPL-3.0"),
    (re.compile(r"Lesser\s+General\s+Public.*?3|\bLGPL[- ]?3", re.I), "LGPL-3.0"),
    (re.compile(r"Lesser\s+General\s+Public.*?2|\bLGPL[- ]?2", re.I), "LGPL-2.1"),
    (re.compile(r"\bGPL[- ]?3", re.I), "GPL-3.0"),
    (re.compile(r"\bGPL[- ]?2", re.I), "GPL-2.0"),
    (re.compile(r"\bGPL\b", re.I), "GPL-3.0"),
    (re.compile(r"\bApache\b", re.I), "Apache-2.0"),
    (re.compile(r"\bMPL[- ]?2", re.I), "MPL-2.0"),
    (re.compile(r"\bEPL[- ]?2", re.I), "EPL-2.0"),
    (re.compile(r"\bCDDL", re.I), "CDDL-1.0"),
    (re.compile(r"\bBSD[- ]?3|\bBSD\b.*3[- ]clause", re.I), "BSD-3-Clause"),
    (re.compile(r"\bBSD[- ]?2", re.I), "BSD-2-Clause"),
    (re.compile(r"\bBSD\b", re.I), "BSD-3-Clause"),
    (re.compile(r"\bMIT\b", re.I), "MIT"),
    (re.compile(r"\bISC\b", re.I), "ISC"),
    (re.compile(r"\bPSF|\bPython Software Foundation", re.I), "PSF-2.0"),
    (re.compile(r"\bUnlicense\b", re.I), "Unlicense"),
    (re.compile(r"\bCC0\b", re.I), "CC0-1.0"),
    (re.compile(r"\bZlib\b", re.I), "Zlib"),
]


def normalize_license(text: str) -> str:
    """把原始许可证文本归一化为规范短名; 无法识别时保留原文(截断)。"""
    text = (text or "").strip()
    if not text:
        return UNKNOWN_LABEL
    for pattern, name in _RULES:
        if pattern.search(text):
            return name
    # 无法识别: 保留原文摘要(去掉换行)
    brief = " ".join(text.split())
    return brief[:40] or UNKNOWN_LABEL


def license_category(normalized: str) -> str:
    if normalized in COPYLEFT_STRONG:
        return "强著佐权"
    if normalized in COPYLEFT_WEAK:
        return "弱著佐权"
    if normalized in PERMISSIVE:
        return "宽松许可"
    if normalized == UNKNOWN_LABEL:
        return "未声明"
    return "其他"


def aggregate(snapshot: EnvironmentSnapshot) -> list[dict]:
    """按许可证规范名聚合包。

    :return: [{"license": 名称, "category": 类别, "count": n, "packages": [...]}]
             按包数降序
    """
    groups: dict[str, list[str]] = {}
    for p in snapshot.packages:
        key = normalize_license(p.license_text)
        groups.setdefault(key, []).append(p.name)

    result = [
        {
            "license": key,
            "category": license_category(key),
            "count": len(names),
            "packages": sorted(names, key=str.lower),
        }
        for key, names in groups.items()
    ]
    result.sort(key=lambda g: (-g["count"], g["license"]))
    return result


def category_summary(snapshot: EnvironmentSnapshot) -> dict[str, int]:
    """各类别包数统计。"""
    summary: dict[str, int] = {}
    for group in aggregate(snapshot):
        summary[group["category"]] = summary.get(group["category"], 0) + group["count"]
    return summary


def build_license_text(snapshot: EnvironmentSnapshot) -> str:
    """许可证汇总文本(供导出)。"""
    import datetime
    lines = [
        "=" * 72,
        "PyEnv Inspector · 许可证汇总",
        "=" * 72,
        f"生成时间 : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"解释器   : {snapshot.interpreter.path}",
        "",
        "类别统计:",
    ]
    for cat, count in sorted(category_summary(snapshot).items(),
                             key=lambda kv: -kv[1]):
        lines.append(f"  {cat}: {count}")
    lines.append("")
    for group in aggregate(snapshot):
        lines.append("-" * 72)
        lines.append(f"{group['license']}  [{group['category']}] · "
                     f"{group['count']} 个包")
        for name in group["packages"]:
            lines.append(f"    {name}")
    lines.append("")
    lines.append("注: 以上为元数据声明, 仅供合规初筛, 不构成法律意见。")
    return "\n".join(lines) + "\n"
