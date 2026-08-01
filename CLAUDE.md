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

# 或手动分终端启动：
# 终端 1: cd frontend && npm run dev
# 终端 2: npx electron .

# 构建前端
cd frontend && npm run build
# 输出: frontend/dist/

# 打包 Electron（需先构建前端）
npm run build
npm run make
```

**端口约定**：后端 8765、前端 Vite 5173、均硬编码在代码中。

**注意**：无测试框架（无 pytest/vitest/jest），无 Python 格式化/lint 工具（无 ruff/black/pre-commit）。PyQt6 是代码强依赖但未列入 requirements.txt（需手动 `pip install PyQt6`）。

国内网络需配置 Electron 镜像（已写入 `package.json` 的 `config` 字段，指向 npmmirror；`.npmrc` 不再放镜像键，避免 npm 警告且 @electron/get 不识别）。

**重要**：修改后端代码后必须重启才能生效。如端口 8765 被占用，需用任务管理器结束 python.exe 进程。

## 架构

```
electron/        — Electron 主进程（启动 Python 子进程、窗口管理、系统托盘）
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

### Qt 信号桥接
- `core/_headless.py` 创建 `QCoreApplication` 使 pyqtSignal 在无 GUI 环境工作
- **`NovelPipeline` 使用自定义 `_Signal` 类替代 Qt 信号**（`core/pipeline.py`），`emit()` 直接调用 `event_broker.publish()`，避免跨线程阻塞（PyQt6 信号无事件循环时阻塞）
- `_Signal.emit()` 特例：单参数且名为 `"data"` 时直接发布值，避免 `{"data": {...}}` 嵌套
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
     → 并行章节生成(25-60%, Semaphore并发)
     → 质量评估(60-75%, LLM打分 + rule_checker硬校验)
     → 修订循环(75-90%, patch协议, 命中率<50%回退全文重写)
     → 多平台适配(90-100%) → 完成
```

### 审阅检查点
- **世界观审阅**：`world_view_review_ready` 事件 → 用户确认后调 `confirm_world_view()`
- **大纲审阅**：`outline_review_ready` 事件 → 用户确认后调 `confirm_outline()`（`OutlineReviewDialog`）
- **续写大纲审阅**：`continuation_outline_ready` 事件 → 用户确认后调 `confirm_continuation()`
- 三个审阅对话框均提供 **"重新生成"** 按钮（`api.retryWorldView()` / `api.retryOutline()`），不满意可重跑该阶段
- `_pending_outline` / `_outline_reviewing` / `_pending_resume_outline` 状态管理大纲检查点；`confirm_outline()` 依据 `_pending_resume_outline` 决定走 `_resume_chapter_generation`（补缺失章节）或 `_generate_chapters`（全新生成）

### 阶段重试
- 失败阶段记录在 `self._failed_stage`（`_handle_error()` 设置），工作台底部显示错误信息 + **"重试当前阶段"** 按钮
- `retry_world_view()` / `retry_outline()` / `retry_current_stage()`（`backend/core/pipeline.py`），对应 API `POST /retry-world-view` / `/retry-outline` / `/retry`
- 大纲生成有质量检测：`<30%` 章节含有效剧情（plot_detail ≥20字）视为失败，允许重试

### 修订机制
- **patch 协议**：RevisionAgent 输出 `[{anchor, replacement, reason}]`，精确匹配 + fuzzy 匹配（忽略空白/全半角标点）
- **命中率阈值**：patch 命中 <50% 时回退到全文重写模式
- **最大轮数**：`max_revision_rounds`（默认 3），每轮修订后重跑评估
- **手动编辑保护**：章节标记 `manually_edited` 后修订循环跳过该章节

### 续写/恢复模式
- **续写**：`continue_from_project()` → 加载遗产包 → 后台线程跑 ContinuationOutlineAgent 生成批次大纲 → 审阅 → 仅评估新章节 → 状态保持 `generating`（连载未完）
- **恢复**：`resume_from_project()` → 缺大纲补大纲，否则补缺失章节
- **时间线快照**：`build_timeline_snapshot()` 保存 `timeline_snapshot.json`，供续写时减少对长前文的依赖
- **注意**：续写大纲生成必须在后台线程执行（`_pipeline_thread`），否则会同步阻塞 HTTP 请求导致前端 30s 超时

### 项目目录结构
`projects/<灵感>_<时间戳>/`，含 `world_view.json`、`outline.json`、`summary.json`、`timeline_snapshot.json`、`outline_batch_N.json`、`chapters/chapter_NNN_{meta.json,txt}`、`exports/`

## LLM 集成

**统一使用 Anthropic Messages API 协议**，不绑定具体厂商。用户在设置页填写任意兼容服务的 API Key、Base URL（根地址，SDK 自动追加 `/v1/messages`）和模型名。`backend/core/llm_client.py` 用 `anthropic.Anthropic` 发起请求，同时带 `api_key` 与 `Authorization: Bearer` 头以兼容不同网关。

`LLMClient.chat()` 内置重试：异常时指数退避；**空/过短响应时自动提高 `max_tokens`（×1.5+2000）重试**（截断常因 token 触顶）。`chat_stream()` 有首 token 60 秒停滞警告（只提示不中断）。`initialize()` 每次启动/恢复/续写前重新 `load_config()`，设置页保存后立即生效。

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
| `temperature` | 0.8 | 采样温度 |
| `max_tokens` | 4096 | 单次最大 token |
| `concurrency` | 3 | 章节并行数 |
| `max_revision_rounds` | 3 | 最大修订轮数 |
| `quality_threshold` | 7.0 | 质量通过线（满分10） |
| `default_chapter_count` | 5 | 默认章节数 |
| `default_chapter_length` | 3000 | 默认每章字数 |
| `timeout` | 300 | LLM 调用超时（秒） |
| `enable_outline_agent` | true | 大纲 Agent 开关 |
| `outline_max_tokens` | 8192 | 大纲最大 token |
| `outline_temperature` | 0.7 | 大纲温度 |

前端设置页通过 `GET /api/config` 获取配置（API Key 脱敏返回 `api_key_masked`），`PUT /api/config` 更新配置（白名单过滤字段，api_key 非空才写入）。

## Electron 打包

`electron/forge.config.js` 配置 `extraResource: ['./backend']` 把 Python 后端打入安装包。**注意**：Python 运行时 + PyQt6 依赖需终端用户自行准备，打包安装包内不含 Python 环境。

窗口配置：1200×780、最小 900×600、Mac 隐藏 frame / Windows 保留 frame、contextIsolation:true / nodeIntegration:false。系统托盘使用 `assets/tray-icon.png`。

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
| 前端构建 | `frontend/package.json` |
| Python 依赖 | `backend/requirements.txt` |
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
| Electron 打包 | `electron/forge.config.js` |
| FastAPI 入口 | `backend/main.py` |
| SSE 事件总线 | `backend/api/events.py` |
| 流水线路由 | `backend/api/pipeline.py` |
| 项目路由 | `backend/api/projects.py` |
| 配置路由 | `backend/api/config.py` |
| 流水线引擎 | `backend/core/pipeline.py` |
| Agent 基类 | `backend/core/base_agent.py` |
| LLM 客户端 | `backend/core/llm_client.py` |
| 项目管理 | `backend/core/project_manager.py` |
| 配置管理 | `backend/core/config.py` |
| Qt 无头模式 | `backend/core/_headless.py` |
| 运行时配置 | `backend/config.json` |
