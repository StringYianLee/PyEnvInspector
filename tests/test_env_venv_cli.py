"""venv 创建/删除、CLI、设置与更新检查的测试。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app.core import env_manager as em  # noqa: E402
from app.core.updater import UpdateResult, check_latest  # noqa: E402


# ---------------------------------------------------------------------------
# venv
# ---------------------------------------------------------------------------

def test_create_and_remove_venv_real(tmp_path, monkeypatch):
    """真实创建/删除 venv(复用当前解释器, 秒级完成)。"""
    monkeypatch.setattr(em, "get_managed_root", lambda: str(tmp_path / "root"))
    target = str(tmp_path / "venv1")
    logs: list[str] = []
    created = em.create_venv(sys.executable, target, with_pip=False,
                             on_output=logs.append)
    assert os.path.normcase(created) == os.path.normcase(target)
    assert em.is_venv(target)
    exe = em._exe_of(target)
    assert os.path.isfile(exe)
    assert any("✔" in line for line in logs)
    # 登记表应有 kind=venv
    entry = em._registry_entry_of(target)
    assert entry is not None and entry["kind"] == "venv"

    em.remove_venv(target, on_output=lambda m: None)
    assert not os.path.isdir(target)
    assert em._registry_entry_of(target) is None


def test_create_venv_rejects_nonempty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "get_managed_root", lambda: str(tmp_path / "root"))
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(em.EnvManagerError) as ei:
        em.create_venv(sys.executable, str(target), with_pip=False)
    assert "非空" in str(ei.value)
    assert (target / "keep.txt").exists()   # 未破坏用户文件


def test_create_venv_rejects_missing_base(tmp_path):
    with pytest.raises(em.EnvManagerError):
        em.create_venv(str(tmp_path / "nope.exe"), str(tmp_path / "v"))


def test_remove_venv_refuses_non_venv(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(em.EnvManagerError) as ei:
        em.remove_venv(str(plain))
    assert "pyvenv.cfg" in str(ei.value)
    assert plain.exists()   # 拒绝删除, 目录仍在


# ---------------------------------------------------------------------------
# 更新检查(注入 fetch, 不联网)
# ---------------------------------------------------------------------------

def test_check_latest_has_update():
    def fake(url):
        return {"tag_name": "v9.9.9", "html_url": "https://x/y", "body": "notes"}

    result = check_latest("1.2.0", fetch=fake)
    assert not result.error
    assert result.latest == "v9.9.9"
    assert result.has_update
    assert result.url == "https://x/y"


def test_check_latest_no_update():
    result = check_latest("1.2.0", fetch=lambda url: {"tag_name": "v1.2.0"})
    assert result.latest == "v1.2.0"
    assert not result.has_update


def test_check_latest_all_endpoints_fail_gracefully():
    def boom(url):
        raise OSError("network down")

    result = check_latest("1.2.0", fetch=boom)
    assert result.error
    assert not result.has_update
    assert result.current == "1.2.0"


def test_update_result_invalid_version_safe():
    result = UpdateResult(current="1.2.0", latest="not-a-version")
    assert not result.has_update


# ---------------------------------------------------------------------------
# CLI(直接调用函数, 避免真实扫描/采集)
# ---------------------------------------------------------------------------

def test_cli_parser_structure():
    from app.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["envs", "--json"])
    assert args.command == "envs" and args.json
    args = parser.parse_args(["export", "--python", "x", "--format", "yaml"])
    assert args.format == "yaml"
    args = parser.parse_args(["analyze", "--python", "x", "--fail-on-conflict"])
    assert args.fail_on_conflict


def test_cli_envs_with_empty_scan(monkeypatch, capsys):
    import app.cli as cli
    from app.core.scanner import ScanReport
    monkeypatch.setattr(cli, "scan_interpreters", lambda: ScanReport([], []))

    class Args:
        json = True

    assert cli.cmd_envs(Args()) == 0
    out = capsys.readouterr().out
    assert out.strip() == "[]"


def test_cli_export_requirements(monkeypatch, tmp_path, capsys):
    import app.cli as cli
    from app.demo import build_demo_snapshot
    snap = build_demo_snapshot()
    monkeypatch.setattr(cli, "_snapshot", lambda *a, **k: snap)
    out_file = tmp_path / "req.txt"

    class Args:
        python = "x"
        format = "requirements"
        out = str(out_file)
        name = "env"
        only_problems = False
        no_cache = True

    assert cli.cmd_export(Args()) == 0
    text = out_file.read_text(encoding="utf-8")
    assert "numpy==" in text


def test_cli_analyze_fail_on_conflict(monkeypatch, capsys):
    import app.cli as cli
    from app.demo import build_demo_snapshot
    monkeypatch.setattr(cli, "_snapshot", lambda *a, **k: build_demo_snapshot())

    class Args:
        python = "x"
        json = True
        no_cache = True
        out = None
        fail_on_conflict = True

    assert cli.cmd_analyze(Args()) == 2   # 演示数据含冲突
    payload = json.loads(capsys.readouterr().out)
    assert payload["stats"]["conflicts"] >= 1


def test_cli_compare_json(monkeypatch, capsys):
    import app.cli as cli
    from app.core.models import EnvironmentSnapshot, InstalledPackage, InterpreterInfo

    def make(pkgs, path):
        return EnvironmentSnapshot(
            interpreter=InterpreterInfo(path=path, version="3.12"),
            python_full_version="3.12.4",
            packages=[InstalledPackage(n, v) for n, v in pkgs])

    snaps = {"a": make([("numpy", "1.0")], "C:/a/python.exe"),
             "b": make([("numpy", "2.0"), ("new", "1")], "C:/b/python.exe")}
    monkeypatch.setattr(cli, "_snapshot", lambda p, **k: snaps[p])

    class Args:
        a = "a"
        b = "b"
        json = True
        no_cache = True

    assert cli.cmd_compare(Args()) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stats"]["added"] == 1
    assert payload["stats"]["upgraded"] == 1


def test_cli_help_subprocess_smoke():
    """真实子进程: --cli --help 不导入 Qt 且退出码 0。"""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "main.py"), "--cli", "--help"],
        capture_output=True, text=True, timeout=120, cwd=root)
    assert proc.returncode == 0, proc.stderr
    assert "envs" in proc.stdout and "compare" in proc.stdout
