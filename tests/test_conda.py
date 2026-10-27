"""conda 扫描核心单元测试(解析器 / 环境扫描 / 集成)。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.conda_scanner import (  # noqa: E402
    _channel_from_url,
    _read_conda_meta_packages,
    _scan_environment,
    parse_condarc,
    scan_conda,
)
from app.core.models import CondaEnvironment  # noqa: E402
from app.demo import build_demo_conda_info  # noqa: E402


# ---------------------------------------------------------------------------
# .condarc 简易 YAML 子集解析器
# ---------------------------------------------------------------------------

def test_parse_condarc_basic():
    text = """
# 注释行
channels:
  - defaults
  - conda-forge
channel_priority: strict
ssl_verify: true
auto_activate_base: false
"""
    data = parse_condarc(text)
    assert data["channels"] == ["defaults", "conda-forge"]
    assert data["channel_priority"] == "strict"
    assert data["ssl_verify"] is True
    assert data["auto_activate_base"] is False


def test_parse_condarc_nested_dict():
    text = """
custom_channels:
  my_channel: https://example.com/conda
envs_dirs:
  - /opt/conda/envs
  - ~/myenvs
report_errors: null
"""
    data = parse_condarc(text)
    assert data["custom_channels"] == {"my_channel": "https://example.com/conda"}
    assert data["envs_dirs"] == ["/opt/conda/envs", "~/myenvs"]
    assert data["report_errors"] is None


def test_parse_condarc_empty_and_comments_only():
    assert parse_condarc("") == {}
    assert parse_condarc("# 只有注释\n\n") == {}


def test_parse_condarc_same_indent_list():
    # 与键同缩进的列表项也是合法 YAML
    data = parse_condarc("channels:\n- defaults\n- conda-forge\nssl_verify: true\n")
    assert data["channels"] == ["defaults", "conda-forge"]
    assert data["ssl_verify"] is True


def test_parse_condarc_inline_comments():
    data = parse_condarc(
        "channels:\n"
        "  - defaults  # 官方源\n"
        "  - conda-forge\n"
        "ssl_verify: true  # 保持校验\n"
        'name: "my # tag"\n'
    )
    assert data["channels"] == ["defaults", "conda-forge"]
    assert data["ssl_verify"] is True
    assert data["name"] == "my # tag"   # 引号内的 # 不算注释


def test_parse_condarc_quoted_scalars():
    data = parse_condarc('name: "my env"\nother: \'single\'\nnum: 42\n')
    assert data["name"] == "my env"
    assert data["other"] == "single"
    assert data["num"] == 42


# ---------------------------------------------------------------------------
# conda-meta 包解析与频道提取
# ---------------------------------------------------------------------------

def test_channel_from_url():
    assert _channel_from_url(
        "https://conda.anaconda.org/conda-forge/win-64/numpy-1.26.4-py312.conda"
    ) == "conda-forge"
    assert _channel_from_url(
        "https://repo.anaconda.com/pkgs/main/win-64/python-3.12.4-h14a1e.conda"
    ) == "pkgs/main"
    assert _channel_from_url("") == ""
    assert _channel_from_url("https://unknown.host/x/y.conda") == ""


def test_read_conda_meta_packages(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    (meta / "python-3.12.4-h14a1e_0.json").write_text(json.dumps({
        "name": "python", "version": "3.12.4", "build": "h14a1e_0",
        "url": "https://repo.anaconda.com/pkgs/main/win-64/python-3.12.4-h14a1e_0.conda",
    }), encoding="utf-8")
    (meta / "numpy-1.26.4-py312_0.json").write_text(json.dumps({
        "name": "numpy", "version": "1.26.4", "build": "py312_0",
        "channel": "defaults",
    }), encoding="utf-8")
    (meta / "broken-1.0-0.json").write_text("{ 不是 JSON", encoding="utf-8")
    (meta / "README.txt").write_text("忽略非 json", encoding="utf-8")

    pkgs = _read_conda_meta_packages(str(meta))
    names = {p.name for p in pkgs}
    assert names == {"python", "numpy", "broken"}
    python = next(p for p in pkgs if p.name == "python")
    assert python.version == "3.12.4"
    assert python.channel == "pkgs/main"
    assert python.build_string == "h14a1e_0"
    # 损坏记录回退到文件名解析
    broken = next(p for p in pkgs if p.name == "broken")
    assert broken.version == "1.0"


def test_scan_environment(tmp_path):
    env = tmp_path / "myenv"
    meta = env / "conda-meta"
    meta.mkdir(parents=True)
    (meta / "python-3.11.9-h1abb5b_0.json").write_text(json.dumps({
        "name": "python", "version": "3.11.9", "build": "h1abb5b_0",
    }), encoding="utf-8")
    exe = "python.exe" if os.name == "nt" else "bin/python"
    if os.name != "nt":
        (env / "bin").mkdir()
        exe_path = env / "bin" / "python"
    else:
        exe_path = env / "python.exe"
    exe_path.write_text("", encoding="utf-8")

    result = _scan_environment(str(env), name="myenv", is_base=False)
    assert result is not None
    assert result.name == "myenv"
    assert result.python_version == "3.11.9"
    assert result.package_count == 1
    assert os.path.normcase(result.interpreter) == os.path.normcase(str(exe_path))


def test_scan_environment_not_conda(tmp_path):
    # 无 conda-meta → 非 conda 环境
    assert _scan_environment(str(tmp_path), name="x", is_base=False) is None


# ---------------------------------------------------------------------------
# 集成: mock 根目录的完整扫描
# ---------------------------------------------------------------------------

def test_scan_conda_with_mock_roots(tmp_path, monkeypatch):
    root = tmp_path / "miniconda3"
    extra_parent = tmp_path / "extra_envs"
    base_meta = root / "conda-meta"
    base_meta.mkdir(parents=True)
    (base_meta / "python-3.12.4-h14a1e_0.json").write_text(json.dumps({
        "name": "python", "version": "3.12.4", "build": "h14a1e_0",
    }), encoding="utf-8")
    (root / ".condarc").write_text(
        "channels:\n  - defaults\n"
        f"envs_dirs:\n  - {extra_parent.as_posix()}\n",
        encoding="utf-8")

    ml = root / "envs" / "ml"
    ml_meta = ml / "conda-meta"
    ml_meta.mkdir(parents=True)
    (ml_meta / "numpy-1.26.4-py312_0.json").write_text(json.dumps({
        "name": "numpy", "version": "1.26.4", "build": "py312_0",
    }), encoding="utf-8")

    # envs_dirs 指向的额外目录也应被扫描
    extra = extra_parent / "research"
    extra_meta = extra / "conda-meta"
    extra_meta.mkdir(parents=True)
    (extra_meta / "scipy-1.13.1-py312_0.json").write_text(json.dumps({
        "name": "scipy", "version": "1.13.1", "build": "py312_0",
    }), encoding="utf-8")

    monkeypatch.setattr("app.core.conda_scanner.find_conda_roots",
                        lambda: [str(root)])

    info = scan_conda()
    assert [os.path.basename(r) for r in info.roots] == ["miniconda3"]
    env_names = [e.name for e in info.envs]
    assert "base" in env_names and "ml" in env_names and "research" in env_names
    base = next(e for e in info.envs if e.is_base)
    assert base.python_version == "3.12.4"
    ml_env = next(e for e in info.envs if e.name == "ml")
    assert ml_env.package_count == 1
    # channels / envs_dirs 从 .condarc 合并(本机可能还有真实 ~/.condarc,
    # 故用包含性断言而非全等)
    assert "defaults" in info.channels
    assert any("extra_envs" in d for d in info.envs_dirs)
    # 配置文件记录(mock root 的 .condarc 必须在列)
    assert any(
        c.exists and c.path == str(root / ".condarc")
        for c in info.config_files)
    assert info.total_conda_packages == 3


def test_scan_conda_no_conda(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.conda_scanner.find_conda_roots", lambda: [])
    info = scan_conda()
    assert info.roots == []
    assert info.envs == []
    assert info.errors  # 有提示信息


# ---------------------------------------------------------------------------
# 演示数据一致性
# ---------------------------------------------------------------------------

def test_demo_conda_info():
    info = build_demo_conda_info()
    assert info.envs[0].is_base
    assert info.total_conda_packages > 0
    assert info.version
    assert any(c.exists for c in info.config_files)
    env = info.envs[1]
    assert isinstance(env, CondaEnvironment)
