# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**AI 小说工厂（新版）** — 基于 Electron + React + TypeScript + FastAPI 的 AI 小说生成桌面应用。从 PyQt6 旧版重构而来，前端用 React + Framer Motion 实现流畅动画，后端用 FastAPI 封装现有 Python pipeline，通过 SSE 实时推送事件。

## 构建与运行

```bash
# 一键安装（Windows）
install.bat

# 开发模式（同时启动 Vite 前端 + Electron，Python 后端由 Electron 管理）
dev.bat
# 项目路径含中文/全角字符时，Electron 无法启动；改用：
#   dev-ascii.bat  （镜像到 %USERPROFILE%\AI-Novel-Factory-Dev 后运行）

# 或手动分终端启动：
# 终端 1: cd frontend && npm run dev
# 终端 2: npx electron .

# 构建免安装绿色版（推荐：双击 build-portable.bat 亦可）
npm run build
# 等价于三步：
#   npm run build:frontend  -> frontend/dist/
#   npm run build:backend   -> backend/dist/novel-backend/（PyInstaller 冻结）
#   npm run build:portable  -> out/AI-Novel-Factory-win32-x64(.zip)

# 打包步骤可单独重跑；产物为免安装绿色版，解压后双击
#   out/AI-Novel-Factory-win32-x64/ai-novel-factory.exe
# 即可运行，**无需安装 Python**。
# ⚠ 产物路径与解压路径必须是纯 ASCII：Electron 在含中文/全角字符的路径下
#   启动会崩溃（STATUS_BREAKPOINT，表现为双击无反应）。
```

**端口约定**：后端 8765、前端 Vite 5173、均硬编码在代码中。

**注意**：无 pytest/vitest/jest 等测试框架；后端有一份标准库 `unittest` 自检 `backend/selftest.py`（`cd backend && python selftest.py`），覆盖流水线计数、续写键位、适配落盘、配置校验等易复发逻辑。仍无 Python 格式化/lint 工具（无 ruff/black/pre-commit）。**PyQt6 已完全移除**（后端原以 Qt 当信号总线，现用 `core/signals.py`），后端依赖见 `backend/requirements.txt`。

国内网络需配置 Electron 镜像（已写入 `package.json` 的 `config` 字段，指向 npmmirror；`.npmrc` 不再放镜像键，避免 npm 警告且 @electron/get 不识别）。

**重要**：修改后端代码后必须重启才能生效。如端口 8765 被占用，需用任务管理器结束 python.exe 进程。

## 版本与发布

- **当前版本**：`2.2.1`（2026-10-31）
- **仓库**：https://github.com/abcdekdy/ai_novel_factory_reform （默认分支 `master`）
- **版本号需三处同步**：根 `package.json`、`frontend/package.json`、`backend/main.py`（`FastAPI(version=...)` 与 `/api/health`）。lockfile 顶部的根版本仅在必要时同步。
- **版本历史**：
  - `2.2.1`：修复中文/全角路径导致 Electron 崩溃；绿色版目录名改纯英文；新增 `启动绿色版.bat` / `dev-ascii.bat`
  - `2.2.0`：深度审计修复（计数/续写/审阅/开销）+ 32 项后端自检 + README 重写
  - `2.1.1`：应用图标
  - `2.1.0`：免安装绿色版、移除 PyQt6、质量阈值接入
  - `1.0.x`：Electron + React + FastAPI 重构首版
- **发布流程**：
  1. 更新三处版本号
  2. `cd backend && python selftest.py`；`cd frontend && npx tsc --noEmit && npm run build`
  3. `git add -A && git commit`
  4. `git tag vX.Y.Z && git push origin master --tags`
  5. 需要分发绿色版时另跑 `npm run build`（产物不入库）
- **文档分工**：`README.md` 面向使用者（安装/使用/部署/FAQ）；本文件面向开发者（架构、机制、字段、完整修复记录）。

## 架构

```
electron/        — Electron 主进程（启动 Python 子进程、窗口管理、后端健康检查）
frontend/        — React + TypeScript + Vite + Tailwind + Framer Motion
  src/
    pages/       — 5 个 Tab 页面（Create/Workspace/Preview/Projects/Settings）
    components/  — 通用组件（Sidebar/LaunchScreen/审阅对话框）
    stores/      — Zustand 状态管理 + SSE 连接
    api/         — REST API 客户端（硬编码 BASE_URL）
    styles/      — Tailwind + 毛玻璃 CSS
    types/       — TypeScript 类型定义
backend/         — FastAPI + Python 核心
  core/          — pipeline/agents/llm_client/project_manager
  api/           — FastAPI 路由层（events/pipeline/projects/config）
    events.py    — SSE 事件总线（EventBroker 单例）
    pipeline.py  — 路由层：启停/确认/重试流水线
  main.py        — FastAPI 应用入口
```

### 前后端通信
- **REST API**：配置读写、项目列表、流水线启停
- **SSE 事件流**：`/api/events/stream` 实时推送日志/进度/状态
- EventBroker（`api/events.py`）是 asyncio.Queue 的发布-订阅模式，QueueFull 时丢弃旧事件保持实时性
- Pipeline 用自定义 `_Signal` 类直接把事件发布到 EventBroker（见下"Qt 信号桥接"）

### 信号机制（已无 Qt）
后端是**无界面服务端**，此前却引入 PyQt6 只为当信号总线用，代价是打包时上百 MB 的 Qt 运行时。现已彻底移除：

- `core/signals.py`：极简信号类（回调列表 + 同步 emit），供 `BaseAgent` 的
  `log/progress/status/finished` 使用。**信号按实例创建**——挂在类上会让所有
  Agent 实例共享同一份回调列表，导致章节之间日志串台
- `core/pipeline.py` 的 `_Signal`：`emit()` 先 `event_broker.publish()` 再调用本地
  订阅者。单参数且名为 `"data"` 时直接发布值，避免 `{"data": {...}}` 嵌套
- `_headless.py`（起后台 Qt 事件循环让 pyqtSignal 可用）与 `PipelineSignals`
  死类（从未被实例化）已删除
- 前端 `stores/useSSE.ts` 订阅 SSE 事件并分发到 Zustand store

### 状态管理
- Zustand（`stores/useStore.ts`）单一 store 管理所有前端状态
- SSE hook（`stores/useSSE.ts`）在 App 级别初始化，全局有效
- 页面切换通过 `activeTab` 索引（0-4），无 react-router，用 `motion.div` + `key` 触发动画

### 动画系统
- **页面切换**：Framer Motion `AnimatePresence` + `motion.div` variants
- **侧边栏指示器**：`layoutId="sidebar-active"` 弹簧动画
- **卡片入场**：`staggerChildren` 交错动画
- **毛玻璃**：CSS `backdrop-filter: blur()` + 半透明白色背景

## Pipeline 流程

```
灵感 → 世界观构建(world_view.json, 0-15%) → ⏸世界观审阅(confirm_world_view)
     → 大纲生成(outline.json, 10-25%) → ⏸大纲审阅(confirm_outline)
     → 并行章节生成(25-60%, Semaphore并发；章数以大纲条数为准，失败章节留待重试)
     → 质量评估(60-75%, 并发LLM打分 + rule_checker硬校验；失败章节跳过)
     → 修订循环(75-90%, patch协议, 命中率<50%回退全文重写)
     → 多平台适配(90-100%, 适配稿落盘 exports/adaptations/) → 完成
```

### 审阅检查点
- **世界观审阅**：`world_view_review_ready` 事件 → 用户确认后调 `confirm_world_view()`
- **大纲审阅**：`outline_review_ready` 事件 → 用户确认后调 `confirm_outline()`（`OutlineReviewDialog`）
- **续写大纲审阅**：`continuation_outline_ready` 事件 → 用户确认后调 `confirm_continuation()`
- 三个审阅对话框均提供 **"重新生成"** 按钮（`api.retryWorldView()` / `api.retryOutline()`），不满意可重跑该阶段
- **关闭 ≠ 放弃**：对话框的"稍后审阅"/ESC/遮罩只把界面收起（`reviewDismissed`），待审阅内容保留；顶部横幅与工作台"等待审阅"按钮可重新打开。确认成功后才清空 `pending*`
- `_pending_outline` / `_outline_reviewing` / `_pending_resume_outline` 状态管理大纲检查点；`confirm_outline()` 依据 `_pending_resume_outline` 决定走 `_resume_chapter_generation`（补缺失章节）或 `_generate_chapters`（全新生成）
- **状态回填**：`GET /api/pipeline/state` 返回完整快照（含 `reviewing` / `pending`）。SSE 每次连接建立（含重连）后前端主动拉一次并回填 store——刷新页面不会丢界面状态，也不会出现"停在等待审阅却看不到对话框"

### 阶段重试
- 失败阶段记录在 `self._failed_stage`（`_handle_error()` 设置，同时把项目 `summary.status` 写成 `failed` + `failed_stage`），工作台底部显示错误信息 + **"重试当前阶段"** 按钮
- `retry_world_view()` / `retry_outline()` / `retry_chapter_generation()` / `retry_current_stage()`（`backend/core/pipeline.py`），对应 API `POST /retry-world-view` / `/retry-outline` / `/retry`
- 章节阶段的失败（单章异常、大纲缺章）走 `retry_chapter_generation()`：只补生成缺失章节，不需要从头再来
- 大纲生成有质量检测：`<30%` 章节含有效剧情（plot_detail ≥20字）视为失败，允许重试

### 修订机制
- **patch 协议**：RevisionAgent 输出 `[{anchor, replacement, reason}]`，精确匹配 + fuzzy 匹配（忽略空白/全半角标点）
- **命中率阈值**：patch 命中 <50% 时回退到**整章重写**（`RevisionAgent.run_rewrite()` 输出完整正文，非仅清理原文）；可用 `enable_full_rewrite_fallback` 关闭
- **最大轮数**：`max_revision_rounds`（默认 3），每轮修订后重跑评估
- **字数类问题过滤**：`word_count` 类型的 issue 不进入 patch 修订（局部替换改不了篇幅，只会产出注定落空的锚点）；若过滤后已无问题可修订，直接跳过本轮，零 token 开销
- **仅字数硬伤跳过**：仅字数 hard 硬伤（无其他问题）的章节在初评即跳过修订循环；修订轮内重评后仍存在字数硬伤 → 立即停止
- **保留最优（回滚）**：修订稿分数明显退步（< 上轮 −0.5）时回滚到本轮之前的正文与评估，避免越改越差、最后留下最差版本
- **收敛判断**：优先信**确定性信号**——硬校验 hard 问题数减少即可继续下一轮；否则要求分数提升 >0.5；patch 零命中视为收敛停止
- **评估依据统一**：初评与重评都经 `_chapter_outline_for()` 取"粗大纲 + 细大纲"合并结果，保证两次打分可比
- **版本绑定**：每条评估带正文指纹 `content_digest`（SHA-256 前 16 位）；修订前校验，正文若在评估后被改动则拒绝修订（防"对着旧版本改"）
- **手动编辑保护**：章节标记 `manually_edited` 后修订循环跳过该章节

### 成本门禁
- `LLMClient` 从每次响应的 `usage` 字段累计 token（流式取 `get_final_message()`，网关不支持则静默跳过），按配置单价估算花费
- 达 **80%** 告警一次；达 **上限** 自动请求暂停（进度无损，调高上限后可从项目库续写）
- 检查挂在 `_enforce_budget_gate()`，由 `_finalize_pause_if_requested()` 调用——于是**所有已有的安全边界自动生效**，无需在每个循环里重复插桩
- `budget_max_cost_usd` 为 0 表示不限制；成本快照写入项目摘要并随 `pipeline_finished` 回传（`cost_usd` / `llm_calls` / tokens）
- 单价需用户按所用服务填写（美元/百万 token），代码无法推断

### 多人格竞稿
- 配置 `chapter_personas`（每行「名称|风格描述」，`#` 开头为注释），≥2 个人格时启用
- 每章为每个人格并行生成候选稿 → `JudgeAgent` 逐稿打分（要求**逐字引用原文举证**）→ 中选稿成为正稿
- 同一章只占**一个**并发位（章节级信号量），避免"N 人格 × 并发章数"打满服务端
- 失败容忍：某人格**连续失败 3 次自动弃权**；只剩 1 稿时不调用 Judge；全员失败降级单 Writer
- 成本：调用次数 ≈ 人格数 + 1（Judge），建议配合成本门禁
- 留空或仅 1 个人格 → 完全走原有单 Writer 路径，零额外开销

### 续写/恢复模式
- **续写**：`continue_from_project()` → 加载遗产包 → 后台线程跑 ContinuationOutlineAgent 生成批次大纲 → 审阅 → 仅评估新章节 → 状态保持 `generating`（连载未完）
- **恢复**：`resume_from_project()` → 缺大纲补大纲，否则补缺失章节
- **时间线快照**：`build_timeline_snapshot()` 保存 `timeline_snapshot.json`，供续写时减少对长前文的依赖
- **注意**：续写大纲生成必须在后台线程执行（`_pipeline_thread`），否则会同步阻塞 HTTP 请求导致前端 30s 超时

### 项目目录结构
`projects/<灵感>_<时间戳>/`，含 `world_view.json`、`outline.json`、`summary.json`、`timeline_snapshot.json`、`outline_batch_N.json`、`chapters/chapter_NNN_{meta.json,txt}`、`exports/`（整本导出）与 `exports/adaptations/chapter_NNN_<平台>.md`（多平台适配稿）

## LLM 集成

**统一使用 Anthropic Messages API 协议**，不绑定具体厂商。用户在设置页填写任意兼容服务的 API Key、Base URL（根地址，SDK 自动追加 `/v1/messages`）和模型名。`backend/core/llm_client.py` 用 `anthropic.Anthropic` 发起请求，同时带 `api_key` 与 `Authorization: Bearer` 头以兼容不同网关。

`LLMClient.chat()` 内置重试：异常时指数退避；**响应短于 `min_length`（默认 50 字）时自动提高 `max_tokens`（×1.5+2000）重试**（截断常因 token 触顶）。连接测试显式传 `min_length=0`，避免一句"连接成功"被当成截断重试 3 次。`chat_stream()` 有首 token 60 秒停滞警告（只提示不中断）。`initialize()` 每次启动/恢复/续写前重新 `load_config()`，设置页保存后立即生效。

依赖仅 `anthropic`（`backend/requirements.txt`），无 openai SDK。

### JSON 解析鲁棒性
`BaseAgent.parse_json_response` 有 5 层策略：strict → 非严格（允许控制字符）→ 代码块提取 → 常见错误修复 → 逐步截断。失败时落盘到 `projects/_parse_failures/`。

## 配置管理

配置存储在 `backend/config.json`，由 `backend/core/config.py` 管理（与 `DEFAULT_CONFIG` 合并兼容新字段）。

| 字段 | 默认值 | 用途 |
|---|---|---|
| `api_key` | （空） | LLM API Key |
| `model` | （空） | 模型名（用户填写） |
| `base_url` | （空） | Anthropic Messages 兼容服务根地址（用户填写） |
| `concurrency` | 3 | 章节并行数（1–20） |
| `max_revision_rounds` | 3 | 最大修订轮数（0–10） |
| `enable_full_rewrite_fallback` | true | patch 命中率过低时是否整章重写兜底 |
| `enable_platform_adaptation` | true | 是否执行多平台适配（每章一次大调用，关闭可显著省钱） |
| `quality_threshold` | 7.0 | 质量通过线（满分10） |
| `default_chapter_count` | 5 | 默认章节数 |
| `default_chapter_length` | 3000 | 默认每章字数 |
| `timeout` | 300 | LLM 调用超时（秒） |
| `outline_max_tokens` | 8192 | 大纲最大 token |
| `outline_temperature` | 0.7 | 大纲温度 |
| `budget_max_cost_usd` | 0.0 | 成本上限（美元），0 = 不限制 |
| `budget_price_input_per_mtok` | 3.0 | 输入单价（美元/百万 token） |
| `budget_price_output_per_mtok` | 15.0 | 输出单价（美元/百万 token） |
| `chapter_personas` | （空） | 竞稿人格，每行「名称\|风格描述」 |

`temperature` / `max_tokens` / `enable_outline_agent` / `web_monitor_port` 是历史字段：从未有任何 Agent 读取（各 Agent 自带温度与预算），设置页对应控件已移除，新配置不再写入这些键。

前端设置页通过 `GET /api/config` 获取配置（API Key 脱敏返回 `api_key_masked`），`PUT /api/config` 更新配置：白名单 + **类型/范围校验**（数值配置非数字或越界返回 422；布尔开关必须是布尔值），api_key 非空才写入。

## Electron 打包（免安装绿色版）

**一条命令**：`npm run build`（或双击 `build-portable.bat`），产物为
`out/AI-Novel-Factory-win32-x64/` 与同名 zip。解压后双击 `ai-novel-factory.exe` 即可运行，
**终端用户无需安装 Python**。

> **路径必须纯 ASCII**：Electron 在包含中文/全角字符的路径下启动会崩溃（STATUS_BREAKPOINT，双击无反应）。因此绿色版目录名固定为 `AI-Novel-Factory-win32-x64`，且要求用户解压到纯英文目录。源码目录若含中文，用 `启动绿色版.bat`（同步到**桌面** `AI-Novel-Factory` 后启动）或 `dev-ascii.bat`（镜像到 `%USERPROFILE%\AI-Novel-Factory-Dev` 后跑 dev）。

三步流程与各自职责：

| 步骤 | 命令 | 产物 | 说明 |
|---|---|---|---|
| 前端 | `npm run build:frontend` | `frontend/dist/` | Vite 构建 |
| 后端 | `npm run build:backend` | `backend/dist/novel-backend/` | PyInstaller 冻结（含 Python 运行时，约 30MB）|
| 组装 | `npm run build:portable` | `out/…` | `package_portable.py` 组装并压缩 |

产物结构：`ai-novel-factory.exe` + `resources/app/`（应用代码）+ `resources/novel-backend/`（冻结后端）+ `data/`（首次运行自动创建）。

**关键决策与踩坑**：

- **不用 electron-forge**：其依赖的 `extract-zip` 在本机环境下解压 Electron 时会在写出第一个文件后静默终止（压缩包本身完好：73 条目全部通过校验，Python 可完整解压）。改为直接复用 `node_modules/electron/dist`——npm 安装 Electron 时已解压好的完整运行时，确定性且更快。`forge.config.js` 已删除；它此前放在 `electron/` 子目录，而 Forge 只在项目根目录查找配置，**从未生效过**
- **数据目录**（`core/paths.py`）：`config.json` 与 `projects/` 必须落在可写位置。此前由 `Path(__file__).parent.parent` 推导，冻结后会指向 PyInstaller 包内部（只读，且 onefile 下是退出即删的临时目录）。现按 `NOVEL_DATA_DIR` 环境变量 → 冻结态 exe 同级 `data/` → 开发态 `backend/` 的顺序解析
- **打包态路径**：`__dirname` 指向 `app.asar` 内部，而 `extraResource` 的内容在 `resources/` 下，两者不同——`electron/main.js` 按 `app.isPackaged` 分别解析后端可执行文件位置
- **启动时序**：先等 `/api/health` 就绪再开窗（本地后端约 1–3 秒），避免首屏接口全部失败；失败时弹明确的中文排查提示而非静默白屏
- **应用图标（两处，缺一不可）**：
  - **窗口/任务栏图标** → `electron/main.js` 的 `BrowserWindow({ icon: assets/icon.png })`
  - **资源管理器里的 exe 文件图标** → 来自 PE 资源，`BrowserWindow` 管不着，必须用
    `set_exe_icon.mjs`（rcedit，ESM **命名导出**）在组装时改写。少了这步，解压后在
    文件夹里看到的还是 Electron 默认的原子标
  - 图标源：`assets/icon-source.png`（1908×1908 RGBA，由 AI 生成图抠底而来）
    → `assets/icon.png`（1024）/ `assets/icon.ico`（内嵌 16–256 七档）/ `assets/tray-icon.png`（32，圆形透明）
  - 重做图标时注意：透明图缩放要**预乘 alpha**，否则透明区颜色渗入边缘产生浅色描边

窗口配置：1200×780、最小 900×600、Mac 隐藏 frame / Windows 保留 frame、contextIsolation:true / nodeIntegration:false。托盘功能（`createTray`）此前从未被调用，已删除；`assets/tray-icon.png` 保留为素材。

## 设计 Token

- Apple 风格：`#F5F5F7` 底色、`#007AFF` 强调色、`#1D1D1F` 文字
- 毛玻璃层次：sidebar(0.85) → card(0.75) → inset(0.04)
- 圆角：`rounded-apple-sm`(4px) → `rounded-apple`(8px) → `rounded-apple-md`(10px) → `rounded-apple-lg`(14px) → `rounded-apple-xl`(20px)
- 字体：SF Pro → Inter → Segoe UI → PingFang SC → Microsoft YaHei

## 已知问题与修复记录

### 2026-07-31 修复

1. **SSE 事件丢失（关键修复）**
   - 问题：PyQt6 信号在没有事件循环时阻塞，导致 `world_view_review_ready` 等事件无法发射
   - 修复：`backend/core/pipeline.py` 中使用 `_Signal` 类替代 Qt 信号，直接调用 `event_broker.publish()`
   - 文件：`backend/core/pipeline.py`、`backend/api/events.py`

2. **API 错误处理缺失**
   - 问题：`resume_pipeline`、`delete_project` 等端点缺少 try/except，返回 generic 500
   - 修复：所有端点添加异常处理，返回具体错误信息
   - 文件：`backend/api/pipeline.py`、`backend/api/projects.py`

3. **删除功能缺失**
   - 问题：项目库页面没有删除功能
   - 修复：添加 `DELETE /api/projects/{project_name}` 端点和前端删除按钮
   - 文件：`backend/api/projects.py`、`frontend/src/api/client.ts`、`frontend/src/pages/ProjectsTab.tsx`

4. **前端状态不同步**
   - 问题：启动新项目时旧数据残留；流水线状态不显示；章节重复添加
   - 修复：添加 `resetPipelineState()`、`addChapter()` 去重、工作台状态提示
   - 文件：`frontend/src/stores/useStore.ts`、`frontend/src/pages/CreateTab.tsx`

5. **退出时进程残留**
   - 问题：关闭 Electron 后 Python 和 Vite 进程残留
   - 修复：`electron/main.js` 中添加 `killProcessOnPort()` 清理 Vite；`dev.bat` 改进进程管理
   - 文件：`electron/main.js`、`dev.bat`

6. **preload.js isPackaged 判断错误**
   - 问题：`!process.env.NODE_ENV === 'development'` 永远为 false
   - 修复：改为 `process.env.NODE_ENV !== 'development'`

### 2026-08-01 修复

7. **审阅流程断裂（关键）**
   - 问题：生成世界观/大纲后不交用户审阅，用户被迫手写；且 `_generate_chapters` 等 6 个方法被调用但从未定义，流水线走不完
   - 修复：补全缺失方法；新增大纲审阅检查点 `outline_review_ready` / `confirm_outline()`；新增 `OutlineReviewDialog`；修复 `WorldViewReviewDialog` 字段映射
   - 文件：`backend/core/pipeline.py`、`backend/api/pipeline.py`、`frontend/src/components/*ReviewDialog.tsx`

8. **修订循环问题**
   - 问题：修订串行执行慢；且仅字数偏离、分数无提升的章节也反复进循环直到 max_rounds
   - 修复：修订改为并行（Semaphore + worker 线程）；仅字数类问题跳过循环；新增收敛判断（分数提升 <0.3 停止）
   - 文件：`backend/core/pipeline.py`

9. **阶段无法重试**
   - 问题：某阶段出错即 `is_running=False` 终止，无法退回上一步重跑
   - 修复：`retry_world_view()` / `retry_outline()` / `retry_current_stage()` + API + 前端"重试当前阶段"按钮 + 审阅对话框"重新生成"按钮
   - 文件：`backend/core/pipeline.py`、`backend/api/pipeline.py`、`frontend/src/*`

10. **终端中文乱码（两层）**
    - 问题：① Python 输出 GBK 而 Node 按 UTF-8 解码 → 锟斤拷；② Node 输出 UTF-8 而 cmd 代码页是 GBK → 鍚庣宸插惎
    - 修复：① `electron/main.js` spawn 注入 `PYTHONIOENCODING=utf-8` + `backend/main.py` 强制 stdout UTF-8；② `dev.bat` 顶部 `chcp 65001`
    - 文件：`electron/main.js`、`backend/main.py`、`dev.bat`

11. **LLM 接入重构**
    - 问题：绑定 LongCat/DeepSeek 具体厂商
    - 修复：统一为 Anthropic Messages API，用户填任意兼容服务的 key/base_url/model；`load_config()` 自动移除旧 `provider` 字段；设置页改为"Anthropic 接口配置"
    - 文件：`backend/core/llm_client.py`、`backend/core/config.py`、`frontend/src/pages/SettingsTab.tsx`

12. **续写超时 / 预览章节空 / 导出无效**
    - 续写：`continue_from_project()` 同步阻塞 HTTP → 前端 30s 超时，改为后台线程
    - 预览：`GET /chapters` 返回字典，前端 `Array.isArray` 判断失败 → 改为返回排序数组
    - 导出：文件写入后前端无交付动作 → 新增 IPC `open-path`，导出后用系统默认程序打开
    - 文件：`backend/core/pipeline.py`、`backend/api/projects.py`、`electron/main.js`、`electron/preload.js`、`frontend/src/pages/PreviewTab.tsx`

13. **`.npmrc` 镜像警告**
    - 问题：自定义键 `electron_mirror` 触发 npm 警告，且 @electron/get 只读 `npm_config_electron_mirror`
    - 修复：镜像移入 `package.json` 的 `config` 字段（npm 认识且 @electron/get 读取 `npm_package_config_electron_mirror`）
    - 文件：`package.json`、`.npmrc`

14. **续写确认后无法进入章节生成（关键）**
    - 问题：确认续写大纲后立即 `pipeline_error` + `pipeline_finished`，且"重试当前阶段"返回 400。根因是 `ContinuationReviewDialog` 确认时只回传 `{chapters, consistency_rules}`，丢了 `outline_meta`；后端 `_generate_continuation_chapters` 用 `outline["outline_meta"]` 直接下标访问抛 `KeyError`，同时 `save_batch_outline` 把被剥离的（无 `outline_meta`）大纲覆盖落盘
    - 修复：① 续写审阅对话框回传改为 `{...outline, chapters, consistency_rules}` 保留 `outline_meta`（与 `OutlineReviewDialog` 一致）；② `confirm_continuation` 兜底恢复 `outline_meta`（先读磁盘批次大纲，再按 `_continuation_old_count` 重建）；③ `_generate_continuation_chapters` 改用 `outline.get("outline_meta") or {}` 安全访问
    - 文件：`frontend/src/components/ContinuationReviewDialog.tsx`、`backend/core/pipeline.py`

### 2026-08-09 修复

15. **回流修订空转满 3 轮（关键，token 浪费）**
    - 问题：字数严重偏离（>30%）被 rule_checker 判为 hard → `quality_agent.py` 因 hard_count>0 强制 `pass=false`；但 patch 修订物理上改不了篇幅，而收敛判断依赖波动极大的两次独立 LLM 分数（阈值 +0.3）→ 字数不符的章节必然空转满 3 轮，每轮都重发完整章节+世界观上下文，大量烧 token 和时间
    - 修复：① 新增 `_has_word_count_hard` / `_only_word_count_hard` 判定，仅字数硬伤章节在初始评估直接跳过修订；② 修订轮内重评后仍存在字数硬伤 → 立即停止；③ 本轮 patch 零命中 → 收敛停止；④ 分数提升阈值 +0.3 → +0.5
    - 效果：实测 6 章中 4 章需修订，全部只修 1 轮即停，不再空转
    - 文件：`backend/core/pipeline.py`

16. **生成字数超写与 token 预算**
    - 问题：章节生成模型系统性超写（目标 3000 字实际 3171~6371，第 6 章超 1 倍）；且修订/评估 max_tokens 预算过大，思考模型共享预算导致单次响应慢、偶发截断触发"响应为空提高预算重试"
    - 修复：① 章节生成 prompt 强化目标字数硬约束（±10% + 写完自检）；② `max_tokens` 从固定 6000 改为 `max(6000, target_length*2)` 动态扩展；③ 评估 8192→6144、修订 16384→8192（字数偏差按正常现象接受，未做压缩校准）
    - 文件：`backend/core/chapter_agent.py`、`backend/core/quality_agent.py`、`backend/core/revision_agent.py`

### 2026-09-29 修复（回流修订专项，借鉴开源同类项目）

17. **规则校验器一半是死代码（关键）**
    - 问题：`key_events` / `characters_present` / `cliffhanger` 由 `OutlineBuilderAgent`（细大纲）产出，而 `WorldBuilderAgent` 的 `chapter_outline` 只有 `{chapter, title, summary}`。`confirm_outline()` 从未设置 `_outline_for_chapters`，导致主流程评估退回粗大纲 → `rule_checker` 的**关键事件覆盖**与**出场人物**两项永远 `total=0`、无条件通过。生成器拿到的是细大纲，评估器拿到的是粗大纲——"按 A 写，按 B 评"
    - 修复：新增 `_chapter_outline_for(chapter_index)` 作为唯一入口，返回「粗大纲兜底基础字段 + 细大纲覆盖可校验字段」的合并结果；`confirm_outline()` / `_generate_outline()` 显式设置 `_outline_for_chapters`
    - 文件：`backend/core/pipeline.py`

18. **初评与重评依据不一致，收敛判断失真（关键）**
    - 问题：初评用 `_outline_for_chapters`（续写批次大纲），重评却用 `world_view["chapter_outline"]` 且按 `chapter_index-1` 取——续写第 11 章会去读原始粗大纲第 11 项（越界得 `{}`）。两次打分依据不同、分数不可比，"提升 >0.5 才继续"的判断失去意义
    - 修复：重评改走 `_chapter_outline_for()`；位置回退增加"仅当大纲确为 1 基编号"的守卫，杜绝续写批次大纲按位置错配
    - 文件：`backend/core/pipeline.py`（该错配由单元验证脚本捕获）

19. **修订稿无条件采纳，越改越差也不回滚**
    - 问题：`chapter["content"] = revised_content` 在重评之前就写入，之后发现分数下降也只是"停止"，从不回滚 → 用户最终拿到的是最后一轮（可能最差）的稿子
    - 修复：引入"保留最优"——修订稿分数下降超 0.5 时回滚正文、`revision_log`、字数与评估结论，并落盘。对应 PaperOrchestra `REVERT_OVERALL_DECREASED` / LoopGain `argmin(error)` 的 best-so-far 语义
    - 文件：`backend/core/pipeline.py`

20. **收敛判断只信噪声分数，不用确定性信号**
    - 问题：唯一判据是两次独立 LLM 打分（temperature 0.3，噪声 ±0.5 以上），而硬校验的确定性增减完全没被利用
    - 修复：新增 `_rule_hard_count()`；硬伤数减少即可继续下一轮，否则才看分数提升 >0.5。确定性信号优先
    - 文件：`backend/core/pipeline.py`

21. **"全文重写回退"名不副实**
    - 问题：`_fallback_full_rewrite()` 声称"回退到全文重写"（CLAUDE.md 亦如此记载），实际只做 `re.sub` 清理 HTML 注释后**返回原文**，等于 patch 命中率低时静默放弃
    - 修复：实现真正的 `RevisionAgent.run_rewrite()`（整章重写，独立 system prompt，只输出正文，剥代码围栏），并由 `enable_full_rewrite_fallback` 控制；异常或返回过短（疑似截断）时保守保留原文。回滚机制使其风险可控
    - 文件：`backend/core/revision_agent.py`、`backend/core/pipeline.py`、`backend/core/config.py`

22. **字数类问题仍在喂给 patch 修订**
    - 问题：只要 LLM 同时报了一个 style 问题，字数 hard 就会留在 `issues` 里发给 RevisionAgent → 模型试图用局部替换改篇幅，必然产出落空的锚点，白烧一次修订（8192）+ 重评（6144）
    - 修复：`word_count` 类型 issue 一律从修订列表中过滤（并记录条数）；过滤后无问题可修订则直接跳过本轮，零 token 开销
    - 文件：`backend/core/pipeline.py`

23. **评估结论未绑定正文版本（借鉴 novel-studio 的 digest 机制）**
    - 问题：评估、修订、回滚之间没有版本校验，正文一旦被改动，旧评估仍会被拿去做修订决策——"对着旧版本改"，锚点大面积落空
    - 修复：`QualityEvaluatorAgent.content_digest()` 计算正文 SHA-256 前 16 位并写入评估；修订前比对，版本不符即拒绝本轮修订并提示重跑评估
    - 文件：`backend/core/quality_agent.py`、`backend/core/pipeline.py`

24. **重评结果未回写 `self.evaluations`**
    - 问题：修订后的新分数只用于本轮判断，最终汇总（均分）与前端展示仍是修订前的旧分数
    - 修复：重评后回写 `self.evaluations`（回滚时一并还原）；不额外发 `evaluation_ready`，避免误改前端 Agent 状态
    - 文件：`backend/core/pipeline.py`

**验证**：以假 LLM 端到端驱动修订循环，覆盖 6 个场景（退步回滚 / 有提升续轮 / 字数硬伤停止 / 无提升收敛 / 硬伤减少续轮 / 版本不符拒绝）全部通过；`_chapter_outline_for`、`_rule_hard_count`、`content_digest`、`_apply_patches` 的确定性用例亦全部通过。

**当时列出的三项待办**（并发评估 / 成本门禁 / 多人格竞稿）已在下方迭代中实现。

### 2026-09-29 迭代（承接上条，实现三项增强）

25. **质量评估改为并发**
    - 问题：`_evaluate_chapters` 逐章串行调用 LLM（纯 I/O 等待），20 章需 10–20 分钟
    - 修复：受 `concurrency` 限制的并发评估。分类在各 worker 内完成以保证进度实时推进，**汇总时按章节顺序遍历**，因此 `needs_revision` 顺序稳定可复现，不受线程完成先后影响；每章异常仅跳过该章
    - 实测：6 章（含 1 章 0.4s 慢响应）从串行 ~0.9s 降到 0.40s，并发峰值严格等于上限
    - 文件：`backend/core/pipeline.py`

26. **成本门禁**（借鉴 ainovel-cli 的 `budget.max_cost_usd`）
    - 问题：长跑无花费上限，竞稿/多轮修订会成倍放大成本
    - 修复：`LLMClient` 累计 token 并按单价估算花费；80% 告警一次、达上限自动暂停且进度无损。检查挂在 `_finalize_pause_if_requested` 上，**所有已有安全边界自动生效**
    - 容错：网关不返回 `usage`、字段异常、`budget_status` 抛错——一律静默降级，绝不因统计问题中断生成
    - 文件：`backend/core/llm_client.py`、`backend/core/pipeline.py`

27. **多人格竞稿 + Judge 选优**（借鉴 ainovel-cli 的多人格竞稿 / Judge 选优）
    - 新增 `JudgeAgent`：逐稿独立打分，要求**逐字引用原文举证**；编号越界/解析失败一律保底选第 1 稿，不让评审环节拖垮流水线
    - `ChapterGeneratorAgent` 支持 `persona`，在通用规范外注入风格要求
    - 失败容忍：连续失败 3 次自动弃权、单稿不评审、全员失败降级单 Writer
    - 成本控制：同一章只占一个并发位（章节级信号量），避免人格数 × 并发章数打满服务端
    - 文件：`backend/core/judge_agent.py`（新增）、`backend/core/chapter_agent.py`、`backend/core/pipeline.py`

28. **清理历史脚本**：删除 `backend/core/fix_pipeline{,2,3}.py`（已确认无任何模块引用）

**验证**：新增 3 组验证脚本（成本门禁 18 项、并发评估 12 项、竞稿与人格解析 15 项）全部通过；前端 `tsc --noEmit` 通过。验证脚本为一次性搭建，已清理，未入库。

**已知遗留（未处理）**：
- 章节生成阶段未见端到端真实 API 验证（验证均使用假 LLM 驱动循环逻辑）

### 2026-09-30 收尾

29. **`quality_threshold` 接入评估 prompt**
    - 问题：该配置在后端**从未被使用**——"总分 ≥ 7.0" 是写死在评估 system prompt 里的字符串，设置页滑杆拖到任何值行为都不变
    - 修复：prompt 中的通过线改为 `__PASS_THRESHOLD__` 占位符（prompt 内含 JSON 花括号，不能用 `str.format` 注入），由 `build_system_prompt(threshold)` 按配置渲染；pipeline 在初评与重评两处都传 `quality_threshold`
    - **刻意不做**服务端硬卡（`if overall_score < threshold: pass=False`）：LLM 总分噪声 ±0.5 以上，卡硬线会让同一份稿子时而通过时而不通过，制造不稳定的修订触发。通过与否仍由 LLM 的 `pass` 字段 + 硬伤数决定
    - 文件：`backend/core/quality_agent.py`、`backend/core/pipeline.py`

30. **移除不生效的「主题」切换**
    - 问题：设置页的浅色/深色按钮完全不生效——`theme` 被 `PUT /api/config` 白名单过滤（后端 `DEFAULT_CONFIG` 无此键），且前端除设置页外**无任何文件读取它**：既不应用到界面，也不持久化，是个纯装饰控件
    - 修复：删除该区块及 `theme` 的全部前后端引用，避免"看着能调、其实没用"的死控件
    - 深色模式确认是**从零的功能**：`tailwind.config.js` 无 `darkMode`、`index.css` 无 `.dark` 选择器、无 `dark:` 变体。真要做需先起 CSS 变量层（毛玻璃层次 + Apple 设计 token 的深色版本），应单独排期
    - 文件：`frontend/src/pages/SettingsTab.tsx`

**验证**：`build_system_prompt` 占位符替换、阈值端到端传递（配置 → 评估 Agent 入参）、非法/缺省值回退全部通过；前端 `tsc --noEmit` 通过、无 `theme` 残留引用。

### 2026-09-30 打包专项（做成点击即用的绿色版）

31. **打包态后端根本起不来（两个独立原因）**
    - 问题①：`electron/main.js` 用 `path.join(__dirname, '..', 'backend')` 定位后端，打包后 `__dirname` 指向 `app.asar` 内部，而 `extraResource` 的内容在 `resources/` 下——两者不同，后端永远定位不到
    - 问题②：后端靠 `spawn('python', ...)` 启动，要求终端用户自行安装 Python + PyQt6，谈不上"点击即用"
    - 修复：按 `app.isPackaged` 分别解析；打包态启动 PyInstaller 冻结的独立可执行文件。另加 `/api/health` 就绪等待（先等后端可用再开窗，避免首屏接口全红），失败时弹明确的中文排查提示
    - 文件：`electron/main.js`

32. **移除 PyQt6（为打包扫清最大障碍）**
    - 问题：一个无界面服务端引入 GUI 框架 Qt，只为当信号总线用；冻结后多出上百 MB，且 PyInstaller 打包 Qt 需额外处理插件
    - 现状核查：`PipelineSignals(QObject)` 是**从未被实例化**的死类；`api/pipeline.py` 的 `_connect_signals()` 同样从未被调用，且内部引用了未定义的 `publish`（真跑会 NameError）；真正在用 PyQt 的只有 `BaseAgent` 的 4 个 pyqtSignal
    - 修复：新增 `core/signals.py`（约 30 行），`BaseAgent` / `NovelPipeline` 去掉 QObject 基类，删除死代码与 `_headless.py`。**信号按实例创建**——挂类上会让所有 Agent 共享回调列表导致日志串台
    - 顺带收益：`_Signal.connect` 原只保留最后一个订阅者（隐患），现支持多个且订阅者异常互不影响
    - 效果：冻结产物 **29MB**（含 PyQt 时会是 200MB+）
    - 文件：`backend/core/signals.py`（新增）、`base_agent.py`、`pipeline.py`、`api/pipeline.py`

33. **用户数据会被写进只读的程序目录**
    - 问题：`config.json` 与 `projects/` 均由 `Path(__file__).parent.parent` 推导（即 backend/）。冻结后该路径指向 PyInstaller 包内部：只读；onefile 模式下更是退出即删的临时目录，等于用户作品凭空消失
    - 修复：新增 `core/paths.py` 统一解析——`NOVEL_DATA_DIR`（Electron 打包态注入，指向应用根目录下的 `data/`，绿色版整包挪走数据跟着走）→ 冻结态 exe 同级 `data/` → 开发态 `backend/`（保持既有行为，老项目与老配置不失效）
    - 附带修正：`base_agent.py` 落盘解析失败样本用的是相对 cwd 的裸路径 `Path("projects")`，打包后 cwd 不固定 → 改走统一入口
    - 文件：`backend/core/paths.py`（新增）、`config.py`、`project_manager.py`、`api/projects.py`、`base_agent.py`

34. **打包链路的两个"从未生效"与一个不可用**
    - 问题①：`forge.config.js` 一直放在 `electron/` 子目录，而 Forge 只在项目根目录查找配置 —— 它**从未被加载过**（首次运行 `make` 直接报"没有为 win32 配置任何 make 目标"）
    - 问题②：该配置引用的 `assets/icon.ico` 根本不存在（`assets/` 下只有 81 字节的 `tray-icon.png`）
    - 问题③：改用根目录配置后，`electron-forge` 依赖的 `extract-zip` 解压 Electron 时会在写出第一个文件后静默终止。已确认压缩包完好（73 条目全部通过校验，Python 可完整解压），是解压环节在本机环境下的问题
    - 修复：放弃 forge，新增 `package_portable.py` 直接复用 `node_modules/electron/dist`（npm 安装 Electron 时已解压好的完整运行时）组装绿色版并压缩；`build-portable.bat` 与 `npm run build` 串起三步
    - 文件：`package_portable.py`（新增）、`build-portable.bat`（新增）、`backend/build_backend.py`（新增）、`backend/run_server.py`（新增）、`package.json`；`forge.config.js` 删除

**验证**：实际构建出 123.8 MB 的 zip；解压后直接双击 `ai-novel-factory.exe`，后端进程自动拉起、`/api/health` 返回正常、`data/`（含 config.json 与 projects/）在 exe 同级自动创建、渲染进程与 8765 建立 SSE 长连接（证明界面确实加载并发起了请求）、退出时后端进程被正确回收。**全程未使用系统 Python**。

### 2026-09-30 应用图标

35. **补上应用图标（此前 exe 用的是 Electron 默认原子标）**
    - 素材：AI 生成的 2048×2048 方图，浅灰渐变背景（非纯色，边缘标准差 16.5，简单色键会留噪边）
    - 抠底：用**连通域**从画面边缘泛洪判定背景（`scipy.ndimage.label`），而非按颜色直接键出——后者会把图形内部的白色书页一并删掉。腐触 1px 去掉抗锯齿残留的浅色描边后轻微羽化
    - 缩放：透明图必须**预乘 alpha** 再 resize，否则透明区残留的颜色会渗进边缘，形成一圈浅色描边
    - 两处图标缺一不可：`BrowserWindow({icon})` 管窗口与任务栏；**资源管理器显示的 exe 文件图标来自 PE 资源**，需用 rcedit 改写（`set_exe_icon.mjs`）。踩坑：rcedit v5 是 ESM 且为**命名导出**，写成 `import rcedit from 'rcedit'` 直接抛 SyntaxError
    - 解决 `shutil.rmtree` 删不掉产物目录：Electron 目录嵌套深 + 项目路径长，超过 MAX_PATH；已加系统命令（`rmdir /s /q`）兜底
    - 顺带修正 `electron/main.js` 的 stderr 过滤：原先匹配行首 `^INFO:`，而 uvicorn 日志常带时间戳前缀，导致正常启动日志被打成 `[Python ERR]`，排查时误导人。改为按行内是否含级别标记判断
    - 文件：`assets/icon*.png`、`assets/icon.ico`、`assets/tray-icon.png`、`set_exe_icon.mjs`（新增）、`electron/main.js`、`package_portable.py`

**验证**：用系统 API（`Icon.ExtractAssociatedIcon`）把 exe 内嵌图标提取出来与 `assets/icon.png` 比对，平均像素差仅 5.6（Electron 默认图标会差很多），确认已生效；应用重新打包后启动、健康检查、数据目录、退出回收后端进程均正常。

### 2026-10-31 深度审计修复（计数 / 续写 / 审阅 / 开销）

36. **章节 worker 计数与实际线程数不一致（会卡死或重复评估）**
    - 问题：`_pending_chapter_workers` 用"用户请求的章数"初始化，而线程按 `world_view.chapter_outline` 的条数创建。模型被要求写 5 章却返回 3 章时，计数永远归不了零，流水线永久停在章节生成（实测 pending 停在 2、收尾触发 0 次）；返回 6 章时，计数归零后第 5、6 章完成又会各触发一次收尾——评估与适配重复跑（实测触发 3 次）
    - 修复：计划章数以**大纲条数**为准（并同步 `_chapter_count` / `_total_chapters`），收尾抽成 `_maybe_finalize_chapters()`，用 `_chapters_finalized` + `_evaluation_started` 双重幂等守卫
    - 文件：`backend/core/pipeline.py`

37. **续写章节缓存键冲突，内存章节表被覆盖（关键）**
    - 问题：续写用批次内下标 `i` 作 `_chapter_results` 的键，而旧章节占用的正是 0..N-1。10 章后续写 5 章，第 11-15 章直接覆盖第 1-5 章：内存章节表缺章、`total_words` / `chapter_count` 统计错、适配对象错、进度冲到 95%。实测内存章节号为 `[11,12,13,14,15,6,7,8,9,10]`
    - 修复：缓存键统一用**全书 0 基章号**（`chapter_index - 1`）；进度与总数按全书算（`已有章数 + 本批章数`），`_chapter_completed_count` 从已有章数起算
    - 文件：`backend/core/pipeline.py`

38. **续写/恢复未清理实例状态，会串上一部作品**
    - 问题：`continue_from_project` 不加载 `self.outline`、不清 `evaluations/adaptations`。于是新章节拿到的是**上一部小说的角色弧线**（或空），均分把上一部书的评分算进来
    - 修复：续写/恢复/新建入口统一重置 `outline / _outline_for_chapters / evaluations / adaptations / 章节缓存 / _failed_stage`；续写弧线改取本批大纲（`_generate_continuation_chapters` 显式钉住 `_outline_for_chapters`）；`_finish_pipeline` 的均分只统计本书章节
    - 文件：`backend/core/pipeline.py`

39. **世界观审阅对话框把生成结果清空（关键，已用真实项目数据验证）**
    - 问题：`WorldViewReviewDialog.handleConfirm` 是按表单**重建**对象：没做输入框的 `era / location / history` 写成空串、`factions` 写成空数组、每个角色的 `ability` 写成空串。仓库里两个历史项目的 `world_view.json` 全部是 `era='' location='' factions=0 history='' ability=''`——用户点一次"确认"，世界观就被削掉一半，后续大纲/章节 prompt 跟着变差
    - 修复：改为"以原始对象为基底合并"，只覆盖用户编辑过的字段；同时把 era/location/factions/history 与角色 ability 都做成可编辑项（既然要保留，就别让它们不可见）
    - 文件：`frontend/src/components/WorldViewReviewDialog.tsx`

40. **项目库卡片永远显示"生成中 / 0 章节 / —"**
    - 问题：后端 `list_projects` 返回 `{name, path, summary:{...}}`，而前端 `ProjectSummary` 类型与卡片按扁平字段读（`title/status/chapter_count/avg_quality_score/completed_at`），全部取到 `undefined`
    - 修复：后端把 summary 摊平到顶层（同时保留嵌套字段兼容旧调用），并跳过 `_parse_failures` 这类内部目录
    - 文件：`backend/core/project_manager.py`、`frontend/src/types/index.ts`

41. **`GET /api/projects/{name}/batches` 调用未定义函数**
    - 问题：端点到不存在的 `load_batch_outlines`，一旦请求即 NameError；返回的批次结构还是裸元组
    - 修复：改用 `list_batch_outlines`，返回 `[{batch_number, outline}]`
    - 文件：`backend/api/projects.py`

42. **续写批次记录从未真正落盘**
    - 问题：`_finish_pipeline` 先调 `update_project_batches` 写盘，再用更早读取的 `previous_summary` 覆盖整个 `summary.json`——批次记录写进去又被立刻抹掉
    - 修复：批次信息直接并入本次汇总的 `batches`，完成后清掉 `paused_*` / `failed_*` 残留标记；删除不再使用的 `update_project_batches`
    - 文件：`backend/core/pipeline.py`、`backend/core/project_manager.py`

43. **多平台适配：每章一次全文调用，结果不落盘**
    - 问题：`_adapt_chapters` 对每章发一次完整正文的 LLM 调用，结果只进内存 + SSE，不写文件、不进摘要，导出用的仍是原始章节；续写时还会把旧章节全部重新适配一遍
    - 修复：适配稿落盘到 `exports/adaptations/chapter_NNN_<平台>.md`（正文 + 适配说明）；重跑/续写时跳过已有适配稿；只适配本批新章节；新增 `enable_platform_adaptation` 开关（设置页可关，直接省掉这一阶段）
    - 文件：`backend/core/pipeline.py`、`backend/core/project_manager.py`、`frontend/src/pages/SettingsTab.tsx`

44. **"前情提要"永远是空的**
    - 问题：`_generate_chapters` 在建线程时读 `_chapter_results[position-2]`，而全新任务此时该表必为空——`previous_chapter_summary` 从来没进过 prompt
    - 修复：改为取大纲里上一章的 `plot_detail`（立即可得），续写场景按全书章号取上一章细纲/缓存
    - 文件：`backend/core/pipeline.py`

45. **章节 prompt 的全局弧线与远章清单**
    - 问题：`_format_surrounding_chapters` 标题写着"全局弧线结构"却从不输出 `global_arc`；"后续远章"把**前面**的章节也列进去；50 章的书每章 prompt 都塞 46 个标题
    - 修复：输出三幕结构（setup/confrontation/resolution）+ `core_thread`；前情/后续各限 3 章，其余只报省略数量
    - 文件：`backend/core/chapter_agent.py`

46. **失败章节仍被送进评估与适配**
    - 问题：正文是 `[生成失败: ...]` 的章节照样调用一次评估 LLM，把均分拉低；还会被送去"适配"
    - 修复：评估前排除 `status == "error"` 的章节并提示（全部失败则报错终止）；适配阶段同样跳过；新增 `retry_chapter_generation()`，可只补缺失章节
    - 文件：`backend/core/pipeline.py`

47. **"测试连接"一次点击发 3 次请求**
    - 问题：`chat()` 把 `<50 字` 一律当"空/过短响应"提额重试，而连接测试本来只回 4 个字——实测 `calls=3`
    - 修复：`chat()` 增加 `min_length` 参数，连接测试传 0；空响应时给出明确提示
    - 文件：`backend/core/llm_client.py`

48. **字数统计把换行/空白也算进去**
    - 问题：`rule_checker` 用 `len(content)`，长章节能虚高 3%–5%，让"字数达标"判定偏松
    - 修复：新增 `count_words()` 按非空白字符统计；前端 `word_count` 仍按原始长度展示（两套口径的差异已在文档注明）
    - 文件：`backend/core/rule_checker.py`

49. **设置页两个死控件 + 配置无校验**
    - 问题：`Temperature` 与「最大 Token」写进配置后**没有任何 Agent 读取**（各 Agent 自带温度/预算），与已删除的"主题"是同一类死控件；同时 `PUT /api/config` 只做白名单，`concurrency: "abc"` 也能存，随后 `threading.Semaphore("abc")` 在工作线程抛错、流水线无声卡住
    - 修复：删除两个控件与对应配置键（`temperature` / `max_tokens` / `enable_outline_agent` / `web_monitor_port`）；`PUT /api/config` 增加类型 + 范围校验（422）；新增「多平台适配」「整章重写兜底」两个真实生效的开关
    - 文件：`frontend/src/pages/SettingsTab.tsx`、`backend/core/config.py`、`backend/api/config.py`

50. **审阅对话框关掉就再也打不开**
    - 问题：`onClose` 直接清空 store 里的 `pending*`，而后端仍在等待审阅——工作台只显示"等待审阅…"却没有入口，只能停止重来
    - 修复：区分"收起"（`reviewDismissed`，保留待审内容，横幅/工作台按钮可重开）与"确认"（清空）；新增 `GET /api/pipeline/state` 完整快照，SSE 每次连接建立/重连后回填 store（刷新页面不再丢状态）；`confirm_*` 在流水线已停止时返回 False，API 返回 409，前端能提示"已停止"而不是假装成功
    - 文件：`frontend/src/App.tsx`、`frontend/src/pages/WorkspaceTab.tsx`、`frontend/src/stores/*`、`backend/api/pipeline.py`、`backend/core/pipeline.py`

51. **预览页世界观几乎空白 / 正文不能选中复制**
    - 问题：`PreviewTab` 读 `setting / magic_system / char.description`，真实 schema 是 `summary / world_view.rules / char.desc`，所以只显示标题、题材与角色名；全局 `user-select: none` 让正文与日志无法复制
    - 修复：按真实 schema 渲染简介、世界设定、故事框架、角色（含能力）；正文/日志加 `select-text`
    - 文件：`frontend/src/pages/PreviewTab.tsx`、`frontend/src/pages/WorkspaceTab.tsx`

52. **失败项目永远显示"生成中"、日志刷屏、死代码**
    - 问题：`_handle_error` 不改项目状态；`EventBroker` 每个事件打两条 INFO；`createTray` 从未调用；`models/schemas.py`、`run_all_platforms`、`LLMClient.set_connection` 等无人引用；README 仍写 `npm run make`、构建脚本产物路径还是 forge 时代的
    - 修复：失败时写 `status=failed + failed_stage`（项目卡显示失败态与停在哪一阶段）；事件追踪日志降为 DEBUG；删除死代码（含整个 `backend/models/`、托盘函数）；同步 README / build-portable.bat / 本文件
    - 文件：`backend/core/pipeline.py`、`backend/api/events.py`、`electron/main.js`、`README.md`、`build-portable.bat`

**验证**：新增 `backend/selftest.py`（标准库 unittest，32 项），覆盖章节计数两种错配、续写键位/总数/弧线、失败章节跳过、适配落盘与跳过、均分口径、批次记录、失败状态、配置校验、短响应重试、字数统计、审阅状态快照、停止后确认被拒绝等；`python selftest.py` 全部通过。前端 `npx tsc --noEmit` 与 `npm run build` 通过。

### 2026-10-31 路径兼容修复（2.2.1）

53. **中文/全角路径导致 Electron 启动即崩溃（用户无法打开应用）**
    - 现象：双击绿色版无窗口、无报错；`dev.bat` 同样打不开。任务计划程序运行 exe 的 `Last Result` 为 `-2147483645`（`0x80000003`，STATUS_BREAKPOINT）；事件日志无应用错误。
    - 排查：`electron.exe --version` 返回 `0x80000003`；`--no-sandbox --version` 可正常输出；最小 Electron 应用在项目路径下 `app.whenReady` 不触发。把同一份 Electron 32/44 二进制与最小应用复制到 `%TEMP%\aitest`（纯 ASCII）后立即正常（ wrote ok.txt），**确认与 Electron 版本无关，是路径问题**。`subst` 映射盘符、目录 junction 都会被解析回中文真实路径，无效。
    - 根因：Electron/Chromium 在包含中文与全角括号（`小说生成助手（新版）`）的路径下初始化崩溃。
    - 修复：① 绿色版组装目录名改为纯 ASCII `AI-Novel-Factory-win32-x64`（`package_portable.py`），避免解压后目录自带中文；② 新增 `启动绿色版.bat`：把 `out` 同步到**桌面上的 `AI-Novel-Factory`**（纯英文、容易找到）后启动，保留 `data/`；③ 新增 `dev-ascii.bat`：把项目镜像到 `%USERPROFILE%\AI-Novel-Factory-Dev` 后运行 `dev.bat`，并用 `NOVEL_DATA_DIR` 继续使用原项目的配置/作品；④ README/CLAUDE 明确“路径必须纯英文”，解压与开发均按此校验。
    - 后续调整（按用户反馈）：安装位置从 `%LOCALAPPDATA%\AINovelFactory\app` 改为桌面 `AI-Novel-Factory`，并在文件夹内附 `使用说明.txt`；开发镜像从 `%LOCALAPPDATA%\AINovelFactoryDev` 改为 `%USERPROFILE%\AI-Novel-Factory-Dev`，避免"藏在 AppData 里找不到"。
    - 验证：在桌面 `AI-Novel-Factory` 启动新构建，窗口标题“AI 小说工厂”、自带后端 `/api/health` 返回 2.2.1、`config.json` 与 2 个历史项目可见；桌面快捷方式可正常打开。
    - 文件：`package_portable.py`、`启动绿色版.bat`（新增）、`dev-ascii.bat`（新增）、`build-portable.bat`、`README.md`、`CLAUDE.md`

## 开发规范


- **中文 UI**：所有界面文字使用中文
- **无 emoji**：不在 UI 中使用 emoji（日志内容除外）
- **TypeScript 严格模式**：`strict: true`
- **Python 类型提示**：后端函数使用类型注解
- **文件 I/O**：始终使用 `with open()` 确保关闭，统一 UTF-8 编码
- **错误处理**：API 路由用 try/except + HTTPException

## 文件路径速查

| 关注点 | 路径 |
|---|---|
| 根构建命令 | `package.json`（含 `config` 字段存 Electron 镜像） |
| 用户文档（安装/使用/部署） | `README.md` |
| 前端构建 | `frontend/package.json` |
| Python 依赖 | `backend/requirements.txt` |
| 后端自检（unittest） | `backend/selftest.py` |
| 一键安装 | `install.bat` |
| 开发启动 | `dev.bat`（顶部 `chcp 65001` 防乱码） |
| 前端入口 | `frontend/src/main.tsx` |
| 根组件 | `frontend/src/App.tsx` |
| Zustand store | `frontend/src/stores/useStore.ts` |
| SSE 连接 | `frontend/src/stores/useSSE.ts` |
| API 客户端 | `frontend/src/api/client.ts` |
| 类型定义 | `frontend/src/types/index.ts` |
| 全局声明 | `frontend/src/global.d.ts`（window.electronAPI 类型） |
| 设置页 | `frontend/src/pages/SettingsTab.tsx` |
| 预览页 | `frontend/src/pages/PreviewTab.tsx`（含导出） |
| 项目库 | `frontend/src/pages/ProjectsTab.tsx` |
| 侧边栏 | `frontend/src/components/Sidebar.tsx` |
| 世界观审阅对话框 | `frontend/src/components/WorldViewReviewDialog.tsx` |
| 大纲审阅对话框 | `frontend/src/components/OutlineReviewDialog.tsx` |
| 续写审阅对话框 | `frontend/src/components/ContinuationReviewDialog.tsx` |
| 毛玻璃 CSS | `frontend/src/styles/index.css` |
| Tailwind 配置 | `frontend/tailwind.config.js` |
| Electron 主进程 | `electron/main.js`（含 IPC: open-path / show-in-folder） |
| Electron preload | `electron/preload.js`（暴露 electronAPI） |
| 绿色版组装/压缩 | `package_portable.py` |
| 一键构建绿色版 | `build-portable.bat` |
| 绿色版启动器（中文路径可用） | `启动绿色版.bat` |
| 开发模式启动器（中文路径可用） | `dev-ascii.bat` |
| FastAPI 入口 | `backend/main.py` |
| SSE 事件总线 | `backend/api/events.py` |
| 流水线路由 | `backend/api/pipeline.py` |
| 项目路由 | `backend/api/projects.py` |
| 配置路由 | `backend/api/config.py` |
| 流水线引擎 | `backend/core/pipeline.py` |
| Agent 基类 | `backend/core/base_agent.py` |
| 章节生成 Agent | `backend/core/chapter_agent.py`（支持 persona 竞稿） |
| 竞稿评审 Agent | `backend/core/judge_agent.py` |
| LLM 客户端 | `backend/core/llm_client.py` |
| 项目管理 | `backend/core/project_manager.py` |
| 配置管理 | `backend/core/config.py` |
| 后端信号（替代 Qt） | `backend/core/signals.py` |
| 可写数据目录解析 | `backend/core/paths.py` |
| 打包专用后端入口 | `backend/run_server.py` |
| 后端冻结脚本 | `backend/build_backend.py` |
| 运行时配置 | `backend/config.json` |
