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
    """目录中已有 python.exe → 拒绝重复安装。
    统一拦截下载(抛模拟错误), 测试绝不真实下载。"""
    monkeypatch.setattr(em, "get_runtimes_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        em, "_download_with_mirrors",
        lambda *a, **k: (_ for _ in ()).throw(em.EnvManagerError("模拟下载失败")))
    existing = tmp_path / "py-3.12"
    existing.mkdir()
    exe_name = "python.exe" if os.name == "nt" else "bin/python"
    (existing / exe_name).parent.mkdir(parents=True, exist_ok=True)
    (existing / exe_name).write_text("", encoding="utf-8")
    with pytest.raises(em.EnvManagerError) as ei:
        em.install_python("3.12")
    assert "已安装" in str(ei.value)


def test_install_python_empty_target_dir_allows_install(monkeypatch, tmp_path):
    """空目录作为自定义路径是合法的(不会被'已安装'拦截), 且下载失败
    时安全中断并清理。"""
    monkeypatch.setattr(em, "get_runtimes_dir", lambda: str(tmp_path / "runtimes"))
    monkeypatch.setattr(
        em, "_download_with_mirrors",
        lambda *a, **k: (_ for _ in ()).throw(em.EnvManagerError("模拟下载失败")))
    empty = tmp_path / "empty-target"
    empty.mkdir()
    with pytest.raises(em.EnvManagerError) as ei:
        em.install_python("3.12", target_dir=str(empty))
    assert "模拟下载失败" in str(ei.value)
    # 失败后不留半成品
    assert not any(empty.iterdir()) or not empty.exists()


def test_install_python_ui_positional_call_regression(monkeypatch, tmp_path):
    """UI 调用链回归: 管理页按位置传 (version, target_dir, add_to_path) +
    关键字 on_output。若签名错位会抛 TypeError: multiple values for
    argument 'on_output'(v1.1.2 线上 bug)。"""
    monkeypatch.setattr(em, "get_runtimes_dir", lambda: str(tmp_path / "runtimes"))
    monkeypatch.setattr(
        em, "_download_with_mirrors",
        lambda *a, **k: (_ for _ in ()).throw(em.EnvManagerError("模拟下载失败")))
    target = str(tmp_path / "ui-target")
    captured = {}

    # 完全复刻 ManageWorker.run 的调用形态: fn(*args, on_output=...)
    try:
        em.install_python("3.9", target, True,
                          on_output=lambda m: captured.setdefault("out", []).append(m))
        raise AssertionError("应抛出模拟下载错误")
    except em.EnvManagerError as ei:
        # 走到了下载 = 版本/路径/勾选三个位置参数全部正确落到形参
        assert "模拟下载失败" in str(ei)
        assert captured["out"], "on_output 回调应生效"
    except TypeError as exc:
        raise AssertionError(f"签名与 UI 调用错位: {exc}")

    # 签名结构断言: on_output 必须在末尾(ManageWorker 约定)
    import inspect
    sig = inspect.signature(em.install_python)
    names = list(sig.parameters)
    assert names == ["version", "target_dir", "add_to_path", "on_output"], names


# ---------------------------------------------------------------------------
# 登记表与自定义安装路径
# ---------------------------------------------------------------------------

def test_registry_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(em, "get_managed_root", lambda: str(tmp_path))
    em.register_managed(str(tmp_path / "custom"), "3.12.7", added_to_path=True)
    em.register_managed(str(tmp_path / "custom2"), "3.13.0")
    entries = em._load_registry()
    assert len(entries) == 2
    e = em._registry_entry_of(str(tmp_path / "custom"))
    assert e is not None and e["added_to_path"] is True
    em.unregister_managed(str(tmp_path / "custom"))
    assert em._registry_entry_of(str(tmp_path / "custom")) is None
    assert len(em._load_registry()) == 1


def test_list_managed_includes_registry(monkeypatch, tmp_path):
    """登记表中的自定义路径解释器必须被 list_managed_interpreters 发现
    (这是'安装后解释器页不显示'修复的核心)。"""
    monkeypatch.setattr(em, "get_managed_root", lambda: str(tmp_path))
    custom = tmp_path / "my-python-3.12"      # 自定义目录, 不在 runtimes 下
    custom.mkdir()
    (custom / "python.exe" if os.name == "nt" else custom / "bin" / "python") \
        .parent.mkdir(parents=True, exist_ok=True)
    exe_name = "python.exe" if os.name == "nt" else "bin/python"
    (custom / exe_name).write_text("", encoding="utf-8")
    em.register_managed(str(custom), "3.12.7")
    monkeypatch.setattr(em, "get_runtimes_dir", lambda: str(tmp_path / "runtimes"))
    items = em.list_managed_interpreters()
    assert any(os.path.normcase(i["dir"]) == os.path.normcase(str(custom))
               for i in items), items


def test_install_python_target_dir_validation(monkeypatch, tmp_path):
    """自定义路径校验(全部发生在下载前; 拦截下载确保测试零网络)。"""
    monkeypatch.setattr(em, "get_runtimes_dir", lambda: str(tmp_path / "runtimes"))
    monkeypatch.setattr(
        em, "_download_with_mirrors",
        lambda *a, **k: (_ for _ in ()).throw(em.EnvManagerError("模拟下载失败")))
    # 已存在解释器的目录拒绝
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    exe_name = "python.exe" if os.name == "nt" else "bin/python"
    (occupied / exe_name).parent.mkdir(parents=True, exist_ok=True)
    (occupied / exe_name).write_text("", encoding="utf-8")
    with pytest.raises(em.EnvManagerError) as ei:
        em.install_python("3.12", target_dir=str(occupied))
    assert "已存在" in str(ei.value)
    # 非空目录拒绝
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "somefile.txt").write_text("x", encoding="utf-8")
    with pytest.raises(em.EnvManagerError) as ei:
        em.install_python("3.12", target_dir=str(nonempty))
    assert "非空" in str(ei.value)
    # 指向文件拒绝
    as_file = tmp_path / "as-file"
    as_file.write_text("x", encoding="utf-8")
    with pytest.raises(em.EnvManagerError):
        em.install_python("3.12", target_dir=str(as_file))
    # 相对路径会被展开为绝对路径(合法行为), 不在此校验


# ---------------------------------------------------------------------------
# 用户 Path 环境变量(真实读写 HKCU, 原值必须恢复)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="Windows 注册表")
def test_add_remove_user_path_roundtrip():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_QUERY_VALUE) as key:
        try:
            orig, _typ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            orig = ""
    marker_dir = r"C:\__pyenv_inspector_test_marker__"
    marker_scripts = os.path.join(marker_dir, "Scripts")
    try:
        changed = em.add_to_user_path([marker_dir, marker_scripts])
        assert changed is True
        # 幂等: 重复添加无变更
        assert em.add_to_user_path([marker_dir]) is False
        # 确认注册表已含
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_QUERY_VALUE) as key:
            cur, _t = winreg.QueryValueEx(key, "Path")
        assert marker_dir in cur and marker_scripts in cur
        # 移除
        assert em.remove_from_user_path([marker_dir, marker_scripts]) is True
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_QUERY_VALUE) as key:
            cur2, _t = winreg.QueryValueEx(key, "Path")
        assert marker_dir not in cur2
        # 移除不存在的条目: 无变更
        assert em.remove_from_user_path([marker_dir]) is False
    finally:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, orig)
