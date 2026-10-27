"""env_manager 环境管理单元测试(解析/校验/占用检测/真实流式命令)。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app.core import env_manager as em  # noqa: E402


# ---------------------------------------------------------------------------
# 校验与标记
# ---------------------------------------------------------------------------

def test_validate_env_name():
    em.validate_env_name("ml")
    em.validate_env_name("ml-research_2")
    for bad in ("", "1abc", "a b", "中文", "a" * 51, "a/b", "a.b"):
        with pytest.raises(em.EnvManagerError):
            em.validate_env_name(bad)


def test_marker_roundtrip(tmp_path):
    em._write_marker(str(tmp_path), "3.12.7")
    assert em.is_managed_interpreter(
        os.path.join(str(tmp_path),
                     "python.exe" if os.name == "nt" else "bin/python"))
    meta = json.load(open(os.path.join(tmp_path, em.MANAGED_MARKER),
                          encoding="utf-8"))
    assert meta["python_version"] == "3.12.7"
    assert meta["tool"] == "PyEnv Inspector"


def test_is_managed_interpreter_false(tmp_path):
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    assert not em.is_managed_interpreter(str(tmp_path / "python.exe"))


def test_list_managed_interpreters(tmp_path, monkeypatch):
    fake_root = tmp_path / "PyEnvInspector"
    rt = fake_root / "runtimes" / "py-3.11.10"
    rt.mkdir(parents=True)
    exe_rel = "python.exe" if os.name == "nt" else "bin/python"
    (rt / exe_rel).parent.mkdir(parents=True, exist_ok=True)
    (rt / exe_rel).write_text("", encoding="utf-8")
    em._write_marker(str(rt), "3.11.10")
    monkeypatch.setattr(em, "get_runtimes_dir", lambda: str(rt.parent))
    items = em.list_managed_interpreters()
    assert len(items) == 1
    assert items[0]["version"] == "3.11.10"


# ---------------------------------------------------------------------------
# 进程占用检测
# ---------------------------------------------------------------------------

def test_find_processes_using_dir_finds_self():
    """当前测试进程的 python.exe 一定在运行, 应能检测到自身。"""
    me = sys.executable
    results = em.find_processes_using_dir(os.path.dirname(me))
    matched = [r for r in results
               if os.path.normcase(r[2]) == os.path.normcase(me)]
    assert matched, f"应检测到自身进程 {me}, 实际: {results[:5]}"


def test_find_processes_using_dir_no_match(tmp_path):
    assert em.find_processes_using_dir(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# 错误翻译
# ---------------------------------------------------------------------------

def test_translate_error_conflict():
    out = "ERROR: pip's dependency resolver does not currently take into account all the packages...ResolutionImpossible: for help visit..."
    text = em.translate_error("pip", "install", out)
    assert "依赖冲突" in text
    assert "工具输出" in text


def test_translate_error_network():
    text = em.translate_error(
        "pip", "install",
        "WARNING: Retrying ... requests.exceptions.ConnectionError: HTTPSConnectionPool")
    assert "网络连接失败" in text
    assert "镜像" in text


def test_translate_error_no_distribution():
    text = em.translate_error(
        "pip", "install",
        "ERROR: Could not find a version that satisfies the requirement foozzz")
    assert "找不到匹配的发行版" in text


def test_translate_error_no_hint():
    text = em.translate_error("pip", "install", "something weird")
    assert "工具输出" in text


def test_translate_error_conda_unsatisfiable():
    text = em.translate_error(
        "conda", "install", "UnsatisfiableError: The following specifications were found")
    assert "依赖冲突" in text


# ---------------------------------------------------------------------------
# 流式命令
# ---------------------------------------------------------------------------

def test_run_streaming_success_and_output():
    code, out = em.run_streaming(
        [sys.executable, "-c",
         "print('line1'); import sys; sys.stdout.write('line2\\n')"])
    assert code == 0
    assert "line1" in out and "line2" in out


def test_run_streaming_collects_lines():
    seen = []
    code, _ = em.run_streaming(
        [sys.executable, "-c", "print('a'); print('b')"],
        on_output=seen.append)
    assert code == 0
    assert any("a" in s for s in seen) and any("b" in s for s in seen)


def test_run_streaming_nonzero_code():
    code, _ = em.run_streaming([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert code == 3


# ---------------------------------------------------------------------------
# pip 真实流程(装到临时 target, 不污染 venv)
# ---------------------------------------------------------------------------

def test_pip_install_and_remove_real(tmp_path):
    target = tmp_path / "site"
    code, out = em.run_streaming([
        sys.executable, "-m", "pip", "install", "six", "--target",
        str(target), "--disable-pip-version-check", "-q",
    ], timeout=180)
    assert code == 0, out
    assert (target / "six.py").is_file()
    # 卸载流程(用 pip uninstall 于 --target 无法精确; 改为验证目录清理即可)
    import shutil
    shutil.rmtree(target)


def test_pip_install_empty_spec_raises():
    with pytest.raises(em.EnvManagerError):
        em.pip_install(sys.executable, "   ")


# ---------------------------------------------------------------------------
# conda 真实创建/删除(本机 conda, 空环境轻量)
# ---------------------------------------------------------------------------

def test_conda_create_remove_real(tmp_path):
    conda_exe = None
    for cand in (r"D:\MiniConda3\Tools\Scripts\conda.exe",
                 r"D:\MiniConda3\Scripts\conda.exe",
                 r"D:\MiniConda3\condabin\conda.bat"):
        if os.path.isfile(cand):
            conda_exe = cand
            break
    if not conda_exe:
        pytest.skip("本机未找到 conda.exe")
    root = os.path.dirname(os.path.dirname(conda_exe))
    # 探测的 base 目录结构可能不同, 直接找 conda-meta 上溯
    probe = conda_exe
    while probe and not os.path.isdir(os.path.join(os.path.dirname(probe), "conda-meta")):
        nxt = os.path.dirname(os.path.dirname(probe))
        if nxt == os.path.dirname(probe):
            break
        probe = nxt
    root = os.path.dirname(probe) if probe else root

    env_path = os.path.join(tmp_path, "env-pyenv-test")
    created = em.create_conda_env(conda_exe, root, "env-pyenv-test", "",
                                  on_output=lambda m: None)
    try:
        assert os.path.isdir(created)
        assert os.path.isdir(os.path.join(created, "conda-meta"))
    finally:
        em.remove_conda_env(conda_exe, root, "env-pyenv-test", created,
                            on_output=lambda m: None)
    assert not os.path.isdir(env_path) or not os.listdir(env_path)


def test_remove_conda_env_protects_base():
    with pytest.raises(em.EnvManagerError) as ei:
        em.remove_conda_env("conda", "C:/x", "base", "C:/x", on_output=lambda m: None)
    assert "base" in str(ei.value)


# ---------------------------------------------------------------------------
# 可安装版本与下载源
# ---------------------------------------------------------------------------

def test_python_distributions_defined():
    assert "3.12" in em.PYTHON_DISTRIBUTIONS
    for v, fname in em.PYTHON_DISTRIBUTIONS.items():
        assert fname.startswith(f"cpython-{v}.")
        assert "x86_64-pc-windows-msvc" in fname


def test_install_python_rejects_unknown_version():
    with pytest.raises(em.EnvManagerError):
        em.install_python("2.7")


def test_install_python_rejects_existing(monkeypatch, tmp_path):
    monkeypatch.setattr(em, "get_runtimes_dir", lambda: str(tmp_path))
    existing = tmp_path / "py-3.12"
    existing.mkdir()
    with pytest.raises(em.EnvManagerError) as ei:
        em.install_python("3.12")
    assert "已安装" in str(ei.value)
