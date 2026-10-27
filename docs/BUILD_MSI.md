# MSI 安装包构建指南

本文档说明如何把 **PyEnv Inspector** 封装为标准 Windows MSI 安装包（含开始菜单/桌面快捷方式、添加/删除程序入口、标准安装/卸载/自动升级流程）。

技术路线：**PyInstaller**（把 Python 解释器 + 依赖 + 源码打包为独立应用）→ **WiX Toolset 3.14**（把应用目录封装为 MSI）。

---

## 一、环境准备（构建机，一次性）

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Python 3.9+ | 运行构建脚本与源码 | 官网安装；勾选 "Add to PATH" |
| PyInstaller | 打包应用 | `pip install pyinstaller` |
| Pillow | 生成应用图标 | `pip install pillow` |
| WiX Toolset 3.14 | 生成 MSI | 下载 `wix314-binaries.zip` 解压到 `tools/wix314/`（免安装） |

一条命令装齐 Python 侧依赖：

```bash
pip install -r requirements.txt pyinstaller pillow
```

WiX 下载（约 39 MB）：

```bash
curl -L -o tools/wix314-binaries.zip ^
  "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"
unzip tools/wix314-binaries.zip -d tools/wix314
# 校验: tools/wix314/candle.exe、light.exe、heat.exe 存在
```

> 网络受限时可使用任意 GitHub 加速镜像，仅需保证三个 exe 可用。

## 二、一键构建

```bat
:: 项目根目录执行 (默认版本 1.0.0, perMachine 全机安装)
python scripts\build_msi.py

:: 指定版本号
python scripts\build_msi.py --version 1.1.0

:: perUser 模式: 免管理员, 安装到 %LOCALAPPDATA%(适合受限环境)
python scripts\build_msi.py --version 1.1.0 --scope perUser

:: 复用已有 dist 打包产物, 只重做 MSI
python scripts\build_msi.py --version 1.1.0 --skip-pack
```

产物：**`build\PyEnvInspector-<版本>.msi`**（perMachine）/ `...-user.msi`（perUser）

脚本内部依次执行：

1. 生成图标 `assets\pyenv.ico`（多尺寸）与许可文件 `assets\installer\license.rtf`
2. `PyInstaller PyEnvInspector.spec` → `dist\PyEnvInspector\`（onedir 独立应用）
3. `heat.exe` 收割应用目录 → `files.wxs`（文件清单 + 组件 GUID）
4. `candle.exe` 编译 `main.wxs + files.wxs` → `.wixobj`
5. `light.exe` 链接（中文向导 UI + 压缩）→ `build\PyEnvInspector-<版本>.msi`

## 三、安装包内容与行为

| 项 | 说明 |
|----|------|
| 安装位置 | perMachine：`C:\Program Files\PyEnvInspector Project\PyEnv Inspector\`（向导中可改）；perUser：`%LOCALAPPDATA%\PyEnvInspector Project\PyEnv Inspector\` |
| 开始菜单 | `开始菜单 → PyEnv Inspector →` 主程序 + 卸载入口 |
| 桌面快捷方式 | 自动创建（卸载时清理） |
| 添加/删除程序 | 名称、版本、图标、卸载按钮（控制面板可见） |
| 安装向导 | 中文界面，含许可协议页 + 自定义目录页 + 完成页"立即运行"复选框 |
| 安装权限 | perMachine 全机安装，**需要管理员权限**（UAC 弹窗） |
| 运行时 | PyInstaller 已内置全部依赖（PySide6/packaging），目标机器**无需安装 Python** |

## 四、升级与卸载

- **升级**：固定 `UpgradeCode = 7A1C64F2-3B8D-4E29-9C55-0E1D2F3A4B5C`，`Product Id="*"` 每次构建自动生成。发布新版本时只需用**更高版本号**重新构建：

  ```bash
  python scripts/build_msi.py --version 1.1.0
  ```

  用户在新 MSI 上双击安装，`MajorUpgrade` 元素会**自动卸载旧版本再安装新版本**（保留用户数据）；尝试降级会被拒绝并提示。

- **卸载**：三种入口——「设置 → 应用」、控制面板"程序和功能"、开始菜单"卸载 PyEnv Inspector"。均调用标准 `msiexec /x`，移除程序文件、快捷方式与注册表项。

- **静默部署（企业批量）**：

  ```bat
  msiexec /i PyEnvInspector-1.1.0.msi /qn              :: 静默安装
  msiexec /i PyEnvInspector-1.1.0.msi /qn INSTALLDIR=D:\Tools\PyEnv   :: 自定义目录
  msiexec /x PyEnvInspector-1.1.0.msi /qn              :: 静默卸载
  msiexec /i PyEnvInspector-1.1.0.msi /l*v install.log :: 记录详细日志
  ```

## 五、文件清单与配置说明

```
assets/installer/main.wxs     MSI 主配置: 产品信息/升级策略/目录/快捷方式/UI
assets/installer/license.rtf  向导许可页(构建时自动生成)
assets/pyenv.ico              应用图标(构建时自动生成)
PyEnvInspector.spec           PyInstaller 配置(excludes 裁剪未使用的 Qt 大模块)
scripts/build_msi.py          一键构建编排
scripts/make_icon.py          图标生成
tools/wix314/                 WiX 3.14 工具链(免安装)
build/                        构建中间产物 + 最终 MSI
dist/PyEnvInspector/          PyInstaller 应用目录
```

关键配置位置：

- **产品名/厂商/UpgradeCode**：`main.wxs` 顶部 `<?define ?>` 与 `<Product UpgradeCode>`
- **快捷方式**：`main.wxs` 中 `StartMenuShortcuts` / `DesktopShortcut` 组件
- **安装目录默认值**：`ProgramFiles64Folder → VendorDir → INSTALLDIR` 三层定义
- **依赖裁剪**：`PyEnvInspector.spec` 的 `excludes` 列表（已裁剪 QtWebEngine/QtQuick/Qt3D 等，MSI 体积约 60-80 MB）

## 六、验证清单（发布前）

**自动化验证**（perUser 模式免管理员，推荐先跑一遍）：

```powershell
# 构建 perUser 双版本后执行, 结果输出到 build\verify_user_result.txt
python scripts\build_msi.py --version 1.0.0 --scope perUser --skip-pack
python scripts\build_msi.py --version 1.0.1 --scope perUser --skip-pack
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_msi_user.ps1
```

2026-10-27 实测结果（全部通过）：

```
INSTALL_100_EXIT=0            EXE_EXISTS=True        FILE_COUNT=211
STARTMENU_LNK=True            DESKTOP_LNK=True       UNINSTALL_LNK=True
ARP_VERSION=1.0.0             APP_RUNNING=True
UPGRADE_101_EXIT=0            ARP_VERSION_AFTER_UPGRADE=1.0.1   EXE_AFTER_UPGRADE=True
UNINSTALL_EXIT=0              EXE_AFTER_UNINSTALL=False  INSTALLDIR_AFTER_UNINSTALL=False
STARTMENU_AFTER_UNINSTALL=False  DESKTOP_AFTER_UNINSTALL=False  ARP_AFTER_UNINSTALL=False
```

**perMachine 手工验证清单**（需管理员，双击 MSI 按 UAC 提示即可）：

```bat
:: 1. 静默安装到自定义目录
msiexec /i build\PyEnvInspector-1.1.0.msi /qn INSTALLDIR=%TEMP%\pyenv_test /l*v install.log

:: 2. 验证文件与快捷方式
dir "%TEMP%\pyenv_test\PyEnvInspector.exe"
dir "%Public%\Desktop\PyEnv Inspector.lnk"
dir "%ProgramData%\Microsoft\Windows\Start Menu\Programs\PyEnv Inspector"

:: 3. 启动应用确认可用; 控制面板"程序和功能"应出现条目

:: 4. 卸载并确认清理
msiexec /x build\PyEnvInspector-1.1.0.msi /qn
```

## 七、常见问题

**Q: light 报 LGHT0204 / ICE 校验失败？**
构建脚本默认 `-sval` 跳过 ICE；若需要严格校验，去掉该参数并确保安装了 Windows SDK 的 msival 组件。

**Q: 双击 MSI 提示"需要管理员权限"？**
perMachine 安装写入 Program Files 与 HKLM，正常现象。若目标场景无管理员权限，把 `main.wxs` 中 `InstallScope="perMachine"` 改为 `perUser`、`ProgramFiles64Folder` 改为 `LocalAppDataFolder` 并移除 `Root="HKLM"` 的注册表值（改为 HKCU），重新构建即可。

**Q: 杀毒软件误报？**
PyInstaller onedir 应用偶有误报，可对构建产物做代码签名（`signtool sign /fd SHA256 ...`），在 `light` 生成 MSI 后对 MSI 文件本身签名。

**Q: 如何修改图标？**
替换 `scripts/make_icon.py` 中的绘制逻辑或直接放置现成 `.ico` 后跳过生成步骤；exe 图标由 `PyEnvInstaller.spec` 的 `icon=` 决定，MSI 快捷方式图标取自 exe 资源。
