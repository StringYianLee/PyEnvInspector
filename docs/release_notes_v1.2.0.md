# PyEnv Inspector v1.2.0

本次为功能大版本：7 项优化 + 13 项新功能。

## 新增功能

- **环境对比**：任选两个环境对比包版本差异（仅 A / 仅 B / 升级 / 降级 / 无法比较），支持导出 CSV
- **多格式导出**：分析报告、`requirements.txt`、`environment.yml`、依赖图 PNG / SVG / Graphviz DOT、许可证汇总
- **venv 创建与删除**：复用已安装解释器，秒级创建；`pyvenv.cfg` 校验 + 进程占用保护，不影响基础解释器
- **命令行模式（CLI）**：`--cli` 提供 envs / packages / analyze / export / compare / diagnostics / licenses，
  支持 `--json` 与 `--fail-on-conflict`（CI 卡点），退出码 2 表示检出依赖问题
- **诊断与报告**：环境体检（PATH 遮蔽、非法版本号、依赖冲突/缺失/循环、许可证缺失）、
  许可证归一化聚合（宽松 / 弱著佐权 / 强著佐权 / 未声明）、采集历史变化对比
- **深色主题**：侧边栏一键切换（重启生效），所有设置持久化
- **冲突一键修复**：合并全部约束生成 pip 表达式，可复制或在目标环境直接执行
- **更新检查**：启动时静默检查新版本，网络不可用时优雅降级

## 优化与修复

- **依赖分析移入后台线程**：大环境（数千依赖边）不再阻塞界面
- **环境快照磁盘缓存**：12 小时 TTL、原子写入，重启后秒开；保留采集历史
- **采集可取消**：采集协议改为临时文件（避免数 MB 单行 JSON），支持中途取消并终止子进程
- **设置持久化**：窗口几何、上次页面、布局模式、pip 镜像、对比选择
- **日志落盘**：`%LOCALAPPDATA%\PyEnvInspector\logs\app.log`（1MB × 3 轮转）
- 修复 `_exe_of` 对 venv 布局的解析（Windows 下 `Scripts/python.exe`）
- 许可证归一化支持 “Lesser General Public License”“Affero” 等完整名称写法

## 工程化

- 新增 MIT `LICENSE`、`pyproject.toml`（pytest + ruff 配置）
- **GitHub Actions CI**：push/PR 自动跑测试；推送 `v*` 标签自动构建 MSI 并发布 Release
- 测试增至 **96 个**全部通过（新增缓存 / 对比 / 导出 / 诊断 / 许可证 / venv / CLI / 更新检查）

## 安装

下载 `PyEnvInspector-1.2.0.msi` 双击安装（需要管理员权限）；从 1.1.x 升级会自动换装。
命令行用法：`python main.py --cli --help`
