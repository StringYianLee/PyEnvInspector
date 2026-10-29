"""一键构建 PyEnv Inspector MSI 安装包。

流程: 图标 -> 许可文件 -> PyInstaller 打包 -> heat 收割 -> candle 编译 -> light 链接

用法(项目根目录, 需先 pip install pyinstaller pillow):
    python scripts/build_msi.py                 # 版本默认 1.0.0
    python scripts/build_msi.py --version 1.2.3 # 指定版本号
产物: build/PyEnvInspector-<version>.msi

WiX 工具链: 下载 wix314-binaries.zip 解压到 tools/wix314/
  https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

# CI/无中文控制台(如 GitHub runner 的 cp1252)下打印中文会抛
# UnicodeEncodeError 导致构建"假失败"——强制 UTF-8 且不可编码时替换
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIX_BIN = os.path.join(ROOT, "tools", "wix314")
APP_DIR = os.path.join(ROOT, "dist", "PyEnvInspector")
BUILD_DIR = os.path.join(ROOT, "build")
INSTALLER_ASSETS = os.path.join(ROOT, "assets", "installer")

# 许可文本(MIT 风格, 安装向导许可页展示)
_LICENSE_TEXT = """PyEnv Inspector - Python 环境与包依赖管理工具

版权所有 (c) 2026 PyEnvInspector Project

本软件按"现状"提供, 不附带任何明示或暗示的担保, 包括但不限于对适销性和特定用途适用性的暗示担保。在任何情况下, 版权持有人均不对任何索赔、损害或其他责任负责, 无论该等责任源于合同、侵权或其他行为。

特此免费授予任何获得本软件副本的人使用、复制、修改、合并、发布、分发、再许可和/或销售本软件副本的权利, 但须在所有副本中包含上述版权声明与本许可声明。

Copyright (c) 2026 PyEnvInspector Project. MIT License.

本软件依赖的开源组件: PySide6 (LGPLv3)、packaging (Apache-2.0/BSD-2)、PyInstaller (GPL with bootloader exception, 仅构建期使用)。
"""


def _rtf_escape(text: str) -> str:
    """把 UTF-8 文本转成 RTF 安全内容。

    RTF 的 \\uN 是**有符号 16 位**值: 码点 > 32767 的字符(绝大多数
    常用汉字)必须写成负数 N-65536, 否则许可页显示乱码。
    """
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if code > 127:
            signed = code - 65536 if code > 32767 else code
            out.append(f"\\u{signed}?")
        elif ch in "\\{}":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\par\n")
        else:
            out.append(ch)
    return "".join(out)


def ensure_license() -> str:
    """生成安装向导的许可文件 license.rtf。"""
    path = os.path.join(INSTALLER_ASSETS, "license.rtf")
    # 按空行分段; _rtf_escape 会把 \n 转为 \par
    paragraphs = [
        _rtf_escape(p).replace("\n\n", "") for p in _LICENSE_TEXT.split("\n\n")
    ]
    body = "\\par\\line\n".join(paragraphs)
    rtf = (
        r"{\rtf1\ansi\ansicpg936\deff0"
        r"{\fonttbl{\f0\fnil\fcharset134 Microsoft YaHei UI;}}"
        r"\fs18\line "
        r"{\b\fs22 " + _rtf_escape("PyEnv Inspector 软件许可协议") + r"}\par\line "
        + body
        + r"}"
    )
    with open(path, "w", encoding="ascii", errors="strict") as fh:
        fh.write(rtf)
    return path


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, **kw)
    if proc.returncode != 0:
        sys.exit(f"[错误] 命令失败(退出码 {proc.returncode}): {cmd[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 PyEnv Inspector MSI")
    parser.add_argument("--version", default="1.0.0",
                        help="产品版本号, 如 1.0.0 (默认)")
    parser.add_argument("--scope", choices=("perMachine", "perUser"),
                        default="perMachine",
                        help="安装范围: perMachine=全机(需管理员, 默认) / "
                             "perUser=当前用户(免管理员)")
    parser.add_argument("--skip-pack", action="store_true",
                        help="跳过 PyInstaller 打包(复用已有 dist 产物)")
    args = parser.parse_args()
    version = args.version
    if not all(part.isdigit() for part in version.split(".")):
        sys.exit(f"[错误] 版本号格式应为 a.b.c, 收到: {version!r}")
    suffix = "" if args.scope == "perMachine" else "-user"

    # ---- 0) 工具检查 ----
    for exe in ("candle.exe", "light.exe", "heat.exe"):
        if not os.path.isfile(os.path.join(WIX_BIN, exe)):
            sys.exit(
                f"[错误] 缺少 {exe}。请下载 WiX 3.14 binaries 并解压到 tools/wix314/:\n"
                "  https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"
            )

    # ---- 1) 图标 ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from make_icon import build_icon
    build_icon(os.path.join(ROOT, "assets", "pyenv.ico"))

    # ---- 2) 许可文件 ----
    ensure_license()
    print("LICENSE_OK:", os.path.join(INSTALLER_ASSETS, "license.rtf"))

    # ---- 3) PyInstaller 打包 ----
    if not args.skip_pack:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "PyEnvInspector.spec"])
    else:
        print("[跳过] PyInstaller 打包")
    exe_path = os.path.join(APP_DIR, "PyEnvInspector.exe")
    if not os.path.isfile(exe_path):
        sys.exit(f"[错误] 打包产物缺失: {exe_path}")

    # ---- 4) heat: 收割文件清单 ----
    files_wxs = os.path.join(INSTALLER_ASSETS, "files.wxs")
    run([
        os.path.join(WIX_BIN, "heat.exe"), "dir", APP_DIR,
        "-gg",          # 自动生成组件 GUID
        "-srd",         # 去掉根目录 Directory 元素(由 main.wxs 定义)
        "-dr", "INSTALLDIR", "-cg", "AppFiles",
        "-g64",         # 64 位组件
        "-var", "var.BuildDir",
        "-out", files_wxs,
    ])

    # ---- 5) candle: 编译 wxs ----
    os.makedirs(BUILD_DIR, exist_ok=True)
    run([
        os.path.join(WIX_BIN, "candle.exe"),
        "-arch", "x64",
        f"-dVersion={version}",
        f"-dInstallScope={args.scope}",
        "-dBuildDir=dist\\PyEnvInspector",
        "-dRootDir=.",
        "-out", os.path.join(BUILD_DIR, ""),  # 尾分隔符 = 输出目录
        os.path.join(INSTALLER_ASSETS, "main.wxs"),
        files_wxs,
    ])

    # ---- 6) light: 链接生成 MSI ----
    msi_path = os.path.join(
        BUILD_DIR, f"PyEnvInspector-{version}{suffix}.msi")
    run([
        os.path.join(WIX_BIN, "light.exe"),
        "-ext", "WixUIExtension",
        "-ext", "WixUtilExtension",
        "-cultures:zh-CN",
        "-sval",           # 跳过 ICE 校验(构建提速; 正式发布可去掉)
        "-out", msi_path,
        os.path.join(BUILD_DIR, "main.wixobj"),
        os.path.join(BUILD_DIR, "files.wixobj"),
    ])

    size_mb = os.path.getsize(msi_path) / 1024 / 1024
    print(f"\nMSI_OK: {msi_path} ({size_mb:.1f} MB)")
    print("安装验证: msiexec /i \"{0}\" /qn   (静默安装, 需管理员权限)".format(msi_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
