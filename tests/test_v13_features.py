"""v1.3.0 新增能力测试: 变更日志、批量修复、主题切换与对比度、诊断页修复计划。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app import __version__  # noqa: E402
from app.core import changelog, env_manager as em  # noqa: E402
from app.demo import build_demo_snapshot  # noqa: E402


# ---------------------------------------------------------------------------
# 变更日志 / 关于面板数据
# ---------------------------------------------------------------------------

def test_version_matches_changelog_head():
    assert __version__ == changelog.latest_version()
    assert changelog.latest_version() == "1.3.0"


def test_changelog_text_for_version():
    text = changelog.text_for_version("1.3.0")
    assert "1.3.0" in text
    assert "一键批量修复" in text
    assert "明暗主题实时切换" in text


def test_changelog_full_text_contains_recent_versions():
    text = changelog.full_text()
    for version in ("1.3.0", "1.2.0", "1.1.3"):
        assert f"v{version}" in text


def test_changelog_unknown_version():
    assert "无更新记录" in changelog.text_for_version("9.9.9")


# ---------------------------------------------------------------------------
# 批量修复
# ---------------------------------------------------------------------------

def test_pip_install_batch_all_success(monkeypatch):
    calls: list[str] = []

    def fake_install(python_exe, spec, index_label="官方", on_output=None):
        calls.append(spec)
        if on_output:
            on_output(f"installed {spec}")

    monkeypatch.setattr(em, "pip_install", fake_install)
    logs: list[str] = []
    result = em.pip_install_batch("C:/py/python.exe", ["numpy<1.20", "six>=1.5"],
                                  on_output=logs.append)
    assert calls == ["numpy<1.20", "six>=1.5"]
    assert result == {"ok": 2, "failed": 0}
    assert any("全部 2 项修复完成" in line for line in logs)


def test_pip_install_batch_partial_failure(monkeypatch):
    def fake_install(python_exe, spec, index_label="官方", on_output=None):
        if "impossible" in spec:
            raise em.EnvManagerError("pip 安装失败 (退出码 1):\n找不到满足约束的版本")

    monkeypatch.setattr(em, "pip_install", fake_install)
    with pytest.raises(em.EnvManagerError) as ei:
        em.pip_install_batch("C:/py/python.exe",
                             ["numpy<1.20", "impossible>=99", "six"])
    message = str(ei.value)
    assert "1 个成功, 1 个失败" in message or "2 个成功, 1 个失败" in message
    assert "impossible" in message
    assert "无交集" in message or "常见原因" in message


def test_pip_install_batch_rejects_empty():
    with pytest.raises(em.EnvManagerError):
        em.pip_install_batch("C:/py/python.exe", ["", "  "])


# ---------------------------------------------------------------------------
# 主题: 实时切换数据 + 深色文字对比度
# ---------------------------------------------------------------------------

def _luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def test_dark_theme_text_contrast_is_readable():
    """深色模式正文/次级文字必须足够清晰(此前反馈"文字显示不明显")。"""
    from app.ui.theme import Palette, use_dark

    use_dark(True)
    try:
        body = _contrast(Palette.text, Palette.bg)
        muted = _contrast(Palette.text_muted, Palette.bg)
        assert body >= 7.0, f"深色正文对比度过低: {body:.2f}"
        assert muted >= 4.5, f"深色次级文字对比度过低: {muted:.2f}"
        # 卡片表面上的文字同样要够亮
        assert _contrast(Palette.text, Palette.surface) >= 7.0
    finally:
        use_dark(False)


def test_light_theme_text_contrast():
    from app.ui.theme import Palette, use_dark

    use_dark(False)
    assert _contrast(Palette.text, Palette.bg) >= 7.0
    assert _contrast(Palette.text_muted, Palette.bg) >= 4.5


def test_theme_switch_updates_palette_immediately():
    from app.ui.theme import Palette, use_dark

    light_bg = None
    use_dark(False)
    light_bg = Palette.bg
    use_dark(True)
    dark_bg = Palette.bg
    assert dark_bg != light_bg
    assert Palette.is_dark is True
    use_dark(False)
    assert Palette.bg == light_bg
    assert Palette.is_dark is False
