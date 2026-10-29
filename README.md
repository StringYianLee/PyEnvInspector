# PyEnv Inspector

**Python 环境与包依赖管理工具** —— 自动发现本机全部 Python 解释器、读取任意环境已安装的包, 分析包之间的版本依赖关系, 并以依赖图 / 冲突清单 / 冲突矩阵的形式可视化呈现版本冲突链条。

基于 **Qt (PySide6)** 开发, 现代化浅色 UI。

---

## 功能总览

| 功能 | 说明 |
|------|------|
| 🔍 解释器发现 | 自动检索本机所有 Python 版本及解释器路径, 以卡片图列表展示, 供用户点选 |
| 📦 包列表读取 | 选定解释器后读取该环境全部已安装包及版本号, 支持搜索 / 状态过滤 / 详情 |
| ⚖️ 依赖与冲突分析 | 解析 PEP 508 依赖声明, 判定版本冲突 / 依赖缺失 / 未知项 / 循环依赖 |
| 🕸 依赖图可视化 | 分层布局与力导向布局双引擎, 冲突边红色高亮, 点击冲突清单自动聚焦冲突链条 |
| 📊 冲突矩阵 | 行 = 依赖方, 列 = 被依赖方, 交叉格直观呈现依赖约束的满足状态 |
| 🐍 Conda 专属视图 | 扫描 conda 环境列表 / 原生包(conda-meta) / 环境路径 / .condarc 配置; 双击环境直接接入 pip 分析流水线 |
| 🛠 环境管理 | 安装/删除 Python 解释器(3.9-3.13, sha256 校验+多镜像下载, 可自定义安装路径/加入用户 Path); 创建/删除 conda 环境与 venv; 指定环境 pip / conda 装/卸包 |
| 🔀 环境对比 | 任选两个环境对比包版本差异(仅 A / 仅 B / 升级 / 降级 / 无法比较), 支持 CSV 导出 |
| 🩺 诊断与报告 | 环境体检(PATH 遮蔽/非法版本/依赖问题/循环/许可证缺失)、许可证聚合(宽松/弱著佐权/强著佐权/未声明)、采集历史变化 |
| 📤 多格式导出 | 分析报告 / requirements.txt / environment.yml / 依赖图 PNG·SVG·Graphviz DOT / 许可证汇总 / 对比 CSV |
| ⚡ 性能与持久化 | 依赖分析后台线程执行; 环境快照磁盘缓存(12h TTL, 跨重启复用); 采集可取消; 冲突一键生成修复命令 |
| 🖥 命令行模式 | `--cli` 提供 envs/packages/analyze/export/compare/diagnostics/licenses, 输出 JSON 可进 CI |
| 🌙 深色主题 | 侧边栏「主题」切换(重启生效), 设置自动持久化 |
| 📤 报告导出 | 一键导出文本版依赖分析报告 |
| 🎬 演示模式 | 内置演示数据(含冲突 / 缺失 / 循环示例), 无 Python 环境也能查看效果 |

---

## 快速开始

### 方式一: 一键脚本 (Windows)

```bat
install.bat    :: 首次运行: 创建 .venv 并安装依赖
run.bat        :: 之后每次: 双击启动
```

### 方式二: 命令行

```bash
pip install -r requirements.txt     # PySide6 + packaging
python main.py                      # 启动
python main.py --demo               # 直接加载演示数据
```

> 运行本工具自身的 Python 需要 **3.9+**; 被分析的目标环境需要 **3.8+**。

### 命令行模式（无 GUI，可进 CI）

```bash
python main.py --cli envs                                  # 列出解释器
python main.py --cli packages --python <python.exe>        # 列出包
python main.py --cli analyze  --python <python.exe>         # 依赖分析
python main.py --cli analyze  --python <python.exe> --json --fail-on-conflict
python main.py --cli compare  --a <pythonA> --b <pythonB>   # 环境对比
python main.py --cli diagnostics --python <python.exe>      # 环境体检
python main.py --cli licenses    --python <python.exe>      # 许可证汇总
python main.py --cli export --python <python.exe> --format requirements --out req.txt
#   --format: requirements | yaml | report | dot | licenses
```

`--fail-on-conflict` 在检出冲突/缺失时返回退出码 **2**，可直接用于流水线卡点；
`--json` 输出机器可读结构。首次采集会写入缓存（`%LOCALAPPDATA%\PyEnvInspector\cache`），
后续命令秒开；`--no-cache` 强制重新采集。

### 运行测试

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

> 已配置 GitHub Actions（`.github/workflows/ci.yml`）：push/PR 自动跑测试；
> 推 `v*` 标签时自动构建 MSI 并创建 Release（无需手工上传）。

### 封装为 MSI 安装包

完整程序 + 依赖 + 开始菜单/桌面快捷方式 + 安装/卸载/自动升级：

```bat
pip install pyinstaller pillow
python scripts\build_msi.py          :: 生成 build\PyEnvInspector-1.0.0.msi
```

详细说明（含 WiX 工具链准备、升级发布流程、perUser 免管理员模式与验证）见 [docs/BUILD_MSI.md](docs/BUILD_MSI.md)。

---

## 整体交互流程

```
启动
 │  ① 自动后台扫描本机解释器(不阻塞 UI)
 ▼
[解释器页] 卡片图列表(版本 / 路径 / 来源 / venv 标记)
 │  ② 单击选中 → 双击 / 「查看已安装包」确认
 ▼
[包列表页] 表格: 包名 / 当前版本 / 依赖数 / 被依赖数 / 状态彩点
 │        点击行 → 右侧详情面板(依赖 + 被依赖逐条约束与判定)
 │  ③ 分析自动完成(毫秒级)
 ▼
[依赖分析页]
   ├─ 顶部统计卡片: 包 / 依赖边 / 冲突 / 缺失 / 未知 / 循环
   ├─ 依赖图: 节点拖拽 / 滚轮缩放 / 悬停高亮邻域 / 搜索定位
   ├─ 冲突清单: 点击任意一行 → 图中聚焦该冲突链条
   ├─ 循环依赖: 强连通分量列表
   └─ 冲突矩阵: 问题包交叉矩阵, 悬浮查看约束详情
```

**跨页联动**: 包列表双击任意包 → 依赖图自动定位并高亮该包。

---

## 数据获取方式

### 1. 解释器发现 (`app/core/scanner.py`)

| 渠道 | 方法 |
|------|------|
| Py 启动器 | 执行 `py --list-paths` 解析已注册解释器 |
| 系统注册表 | PEP 514: `HKLM/HKCU\SOFTWARE\Python\PythonCore` 及 Conda 分支 |
| PATH 变量 | 遍历 PATH 各目录查找 `python.exe / python3.exe` |
| 常见目录 | `C:\Python*`、`%LOCALAPPDATA%\Programs\Python\Python*`、Program Files 等 |
| Conda | `~/anaconda3|miniconda3|miniforge3`、`%ProgramData%\*conda*` 及 `envs/*` 子环境 |
| MS Store | `WindowsApps` 下 `PythonSoftwareFoundation.Python.*` 真实入口 |

每个候选解释器都会被**实际启动一次**(子进程执行 `python -I -c "<探测脚本>"`)确认版本 / 实现 / 体系结构 / venv 归属; 探测失败的候选(如 Store 未安装时的占位 stub)自动丢弃。按真实路径去重, 版本降序排列。

### 2. 包与依赖元数据采集 (`app/core/collector.py`)

以子进程在**目标解释器**中运行采集脚本, 通过标准库 `importlib.metadata.distributions()` 一次性导出:

- 包名 + 版本号(等同 `pip list`, 但更快且不依赖 pip 配置)
- 每个包的 `Requires-Dist` 依赖声明原文(PEP 508, `pip list` 拿不到)

选择 `importlib.metadata` 而非 `pip` 的原因: 只依赖目标环境标准库、不受 pip 版本与镜像配置影响、一次拿到"包-版本-依赖"三元组。同名重复发行版(egg-info 与 dist-info 并存)自动合并。

### 3. 依赖分析与冲突判定 (`app/core/analyzer.py`)

对每个包的每条 `Requires-Dist` 声明执行四步判定:

```
① 解析 PEP 508
     名字 N + 版本约束 S + 环境标记 M (legacy 括号写法先规范化)
     解析失败 ──────────────→ [未知项 UNKNOWN]
② 评估环境标记 M
     以目标解释器环境评估(python_version 等来自采集快照);
     extra == "x" 的 extras 依赖视为未启用
     不适用 ────────────────→ 直接忽略(不计入图, 不算冲突)
③ 定位被依赖方 N
     N 未安装 ─────────────→ [依赖缺失 MISSING]  (链条断开)
     N 无版本约束 ─────────→ [满足 OK]
④ 校验版本约束 S (SpecifierSet.contains, 宽松 pre-release)
     已安装版本 V ∈ S ─────→ [满足 OK]
     V ∉ S ───────────────→ [版本冲突 VERSION_CONFLICT]  ←—— 核心
     V 非 PEP 440 合法版本 ─→ [未知项 UNKNOWN]
     URL/本地路径依赖 ─────→ [未知项 UNKNOWN]
```

**循环依赖**: 对全部活动边做 Tarjan 强连通分量检测, 成员数 > 1(或自环)即为一组循环。

**冲突链条呈现**: 点击冲突清单中的某条 `A → B` 时, 依赖图会同时高亮 **B 的全部入边**(即所有对 B 提出版本要求的包), 让"到底是谁在逼谁"一目了然。

### 4. Conda 专属扫描 (`app/core/conda_scanner.py`)

**零依赖、零子进程优先** —— conda 的安装结构是纯文件系统可读的:

| 内容 | 获取方式 |
|------|----------|
| conda 根目录 | 常见位置 + PATH 中的 conda 命令 + `CONDA_PREFIX/CONDA_EXE` 环境变量 + PEP 514 注册表 ContinuumAnalytics 分支(覆盖自定义盘符安装) |
| 环境列表 | 各根目录自身(base) + `<root>/envs/*` + `.condarc` 中声明的 `envs_dirs`(相对路径按 conda 根解析) |
| 已安装包 | `<env>/conda-meta/*.json` —— 每个 conda 原生包(python/openssl/numpy 等)的名称、版本、频道(URL 提取)、构建串; pip 包由既有 `importlib.metadata` 流程覆盖 |
| 环境路径 | 环境根目录 + python 解释器位置; Python 版本从 `python-*.json` 文件名解析(无子进程) |
| 配置文件 | 按优先级扫描 `$CONDARC` / `~/.condarc` / `<root>/.condarc` / 系统级 `ProgramData\conda\.condarc`, 内置 YAML 子集解析器(不依赖 pyyaml)提取 channels / envs_dirs 等常用键 |

仅获取 conda 自身版本时尝试运行 `conda --version`(10 秒超时, 失败不影响其余结果)。Conda 页中双击任意环境 → 直接接入既有解释器 → 包采集 → 依赖分析流水线。

### 5. 环境管理（`app/core/env_manager.py`，写入操作）

| 操作 | 实现方式 | 安全措施 |
|------|----------|----------|
| 安装 Python | python-build-standalone 独立发行版, 多镜像回退(gh-proxy → ghfast → 直连), sha256 校验后解压到 `~/PyEnvInspector/runtimes/py-<版本>` 并写托管标记 | 已装版本拒绝重复安装; 下载失败自动换源并给出网络诊断 |
| 删除 Python | 仅允许删除带托管标记的目录; `shutil.rmtree` 前置占用检测 | 外部解释器(系统 Python 等)拒绝删除; 被进程占用时列出 PID 并阻止 |
| 创建 conda 环境 | `conda create -p <root>/envs/<名> python=<版本> -y` | 环境名校验(字母开头/无空格); 重名拒绝 |
| 删除 conda 环境 | `conda env remove -p <路径> -y` + 残留目录兜底清理 | **base 环境永不删除**; 占用检测; 当前浏览环境阻止 |
| pip 装/卸包 | `<目标python> -m pip install/uninstall`, PyPI 镜像可选(官方/清华/阿里) | 退出码判定 + 失败时按模式翻译错误(依赖冲突/网络/拼写/权限) |
| conda 装/卸包 | `conda install/remove -p <路径> -y <包>` | 同上(UnsatisfiableError / CondaHTTPError / PackagesNotFound 等翻译) |

所有操作在后台线程执行, 输出实时写入"操作日志"面板; 成功/失败均有弹窗与状态卡片反馈; 包操作完成后自动重新采集对应环境快照。删除保护通过 Windows API(EnumProcesses)枚举进程可执行路径实现, 无第三方依赖。

### 6. 可视化引擎 (`app/ui/graph_view.py` + `app/core/layout.py`)

**布局比例自适应**:
- 分层布局按每节点的估算宽度累积排布(长名不重叠、短名不浪费), 层间垂直距离随最宽层温和自适应(上限收敛, 避免整图过高导致 fit 后缩得过小);
- 力导向布局的理想边长乘 1.15 松弛系数, 迭代次数按规模缩放; 画布 1500x850 宽扁比例匹配典型视口;
- 视图适配: 留白按视口比例(7%), 缩放上限 1.5(小图适度放大), 平滑过渡到目标; 窗口尺寸变化自动重新适应, 用户手动缩放/拖拽后停止。

**动效**:
- **节点入场**: 波浪式错峰动画(缩放 0.55→1 + 淡入), 单动画驱动全部元素, 边随两端节点渐入; 节点 > 350 时自动跳过(性能保护);
- **悬停高亮**: 邻域淡化与恢复均为 160ms 平滑渐变, 节点悬停微放大(1.06, 120ms);
- **连线过渡**: 版本冲突边呈红色流动虚线(30fps 共享时钟推进, 仅冲突边参与); 边曲率按边标识奇偶交替, 避免同源/汇聚边重叠;
- 视口平移/聚焦定位/适应视图均为 240ms 缓动动画, 滚轮缩放与拖拽即时打断。

- **分层布局**(默认): SCC 折叠 → 凝聚 DAG 最长路径分层 → 同层水平排列。依赖方向自上而下, 确定性、毫秒级。
- **力导向布局**(可选): Fruchterman-Reingold 算法, 节点 > 60 时自动转后台线程计算; > 120 节点启用空间网格加速。
- **着色语义**: 红边/红框 = 版本冲突, 橙虚线/橙框 = 依赖缺失(幽灵节点显示"未安装"), 灰点线 = 未知项。
- **交互**: 滚轮缩放(光标锚定)、拖拽平移、节点拖动(邻边实时跟随)、悬停高亮邻域并淡化无关元素、边悬停显示约束、搜索定位脉冲高亮。

---

## 项目结构

```
pyenv-inspector/
├── main.py                     # 入口 (GUI / --demo / --cli)
├── requirements.txt            # 运行依赖: PySide6, packaging
├── LICENSE                     # MIT
├── pyproject.toml              # 项目元数据 + pytest/ruff 配置
├── .github/workflows/ci.yml    # CI: 测试 + tag 触发构建 MSI 并发布 Release
├── install.bat / run.bat       # Windows 一键安装/启动
├── app/
│   ├── core/                   # ── 数据与算法层(零 UI 依赖, 可独立复用) ──
│   │   ├── models.py           #   数据模型(解释器/包/边/分析结果/conda)
│   │   ├── scanner.py          #   解释器扫描(7 大渠道 + 实探验证)
│   │   ├── conda_scanner.py    #   conda 专属扫描(环境/包/路径/.condarc)
│   │   ├── env_manager.py      #   装/删解释器、建/删 conda 环境与 venv、包装卸、Path 集成
│   │   ├── collector.py        #   包元数据采集(子进程 + 临时文件协议 + 可取消)
│   │   ├── analyzer.py         #   PEP 508 解析 + 冲突判定 + 修复建议
│   │   ├── scc.py              #   Tarjan 强连通分量(循环依赖)
│   │   ├── layout.py           #   分层/力导向布局引擎
│   │   ├── cache.py            #   快照磁盘缓存 + 采集历史
│   │   ├── compare.py          #   环境差异 / 历史差异
│   │   ├── exporter.py         #   requirements / environment.yml / 报告 / DOT / JSON
│   │   ├── diagnostics.py      #   环境体检(PATH 遮蔽/版本/依赖)
│   │   ├── licenses.py         #   许可证归一化与聚合
│   │   ├── updater.py          #   Release 更新检查(失败静默)
│   │   └── appsettings.py      #   日志 + QSettings 设置
│   ├── cli.py                  # 命令行接口(无 Qt)
│   ├── ui/                     # ── 界面层 ──
│   │   ├── theme.py            #   浅色/深色双主题(QSS 色板)
│   │   ├── widgets.py          #   FlowLayout/徽章/统计卡/忙碌遮罩
│   │   ├── interpreters_page.py#   页1: 解释器卡片选择
│   │   ├── packages_page.py    #   页2: 包表格 + 详情面板
│   │   ├── analysis_page.py    #   页3: 图/清单/循环/矩阵 + 多格式导出 + 冲突修复
│   │   ├── conda_page.py       #   页4: Conda 环境/包/配置
│   │   ├── manage_page.py      #   页5: 环境管理(解释器/venv/conda/包)
│   │   ├── compare_page.py     #   页6: 环境对比
│   │   ├── reports_page.py     #   页7: 诊断 / 许可证 / 历史变化
│   │   ├── graph_view.py       #   依赖图(QGraphicsView 节点/边/动效)
│   │   └── main_window.py      #   主窗口与流程编排
│   ├── workers.py              # QThread 后台任务(扫描/采集/分析/布局/更新检查)
│   └── demo.py                 # 演示数据
├── tests/                      # pytest 单元 + 集成测试(96 个)
└── scripts/ui_screenshot.py    # 离屏渲染截图验证
```

**架构原则**: `core` 层零 UI 依赖, 可被 CLI/脚本/服务直接复用; 扫描、采集、依赖分析、布局、更新检查全部在 `QThread` 后台执行, UI 永不阻塞; 采集结果落盘缓存(12h TTL)并保留历史, 「重新加载」强制重采并更新历史。所有网络访问(下载/更新检查)失败都会优雅降级。

---

## 常见问题

**Q: 为什么有的包显示"未安装"?**
它被其他包声明为依赖, 但目标环境的 site-packages 中确实不存在 —— 即"依赖缺失", 通常意味着该环境安装不完整或用了 `--no-deps`。

**Q: "未知项"是什么?**
三类情况: ① 依赖声明本身不符合 PEP 508(老 setuptools 写法残留); ② 被依赖包的版本号不符合 PEP 440(如 `final`), 无法比较; ③ URL/本地路径依赖, 没有版本约束可比。均需人工确认。

**Q: extras 依赖(如 `requests[socks]`)会误报吗?**
不会。`extra == "socks"` 标记的依赖视为未启用, 直接忽略, 与 pip 实际安装行为一致。

**Q: 分析另一个用户的 conda 环境可以吗?**
可以, 只要该环境的 `python.exe` 当前用户可执行。扫描会自动发现 Conda 根环境与 `envs/*` 全部子环境。

**Q: 环境标记(platform_system 等)按谁评估?**
`python_version / python_full_version / platform_machine` 按目标解释器实际值(采集快照带回); 其余(sys_platform 等)按本机 —— 同机场景下完全一致。
