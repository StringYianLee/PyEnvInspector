# PyEnv Inspector v1.1.3 发布说明

> 复制以下内容到 GitHub Release 的描述框。

---

## PyEnv Inspector v1.1.3

### 修复的问题

- **修复安装 Python 时报 `TypeError: install_python() got multiple values for argument 'on_output'`**：`install_python` 的函数签名与「管理」页的参数传递错位（`on_output` 位于第二位，而 UI 按位置传入的 `target_dir` 落到了该形位），导致**所有版本、任何路径配置**的界面安装操作都会失败。现已将 `on_output` 移至参数列表末尾，与全部管理函数及后台任务约定保持一致
- 该修复覆盖 3.9–3.13 全部版本、默认目录与自定义目录、含/不含 Path 勾选的所有安装组合

### 验证

- 新增 UI 位置传参链路回归测试（复刻后台线程的真实调用形态 + 签名结构断言）
- 真机复刻用户场景：安装 Python 3.9（默认路径 + 勾选 Path）→ Path 写入 → 扫描器发现 → 删除清理，全链路通过
- 65 个单元/集成测试全部通过

### 安装

下载 `PyEnvInspector-1.1.3.msi` 双击安装（需要管理员权限）；从 v1.1.x 升级自动换装。

---
