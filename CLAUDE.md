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

国内网络需配置 Electron 镜像（已写入 `.npmrc`，指向 npmmirror）。

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
    pipeline.py  — 信号桥接：Qt pyqtSignal → event_broker.publish()
  main.py        — FastAPI 应用入口
```

### 前后端通信
- **REST API**：配置读写、项目列表、流水线启停
- **SSE 事件流**：`/api/events/stream` 实时推送日志/进度/状态
- EventBroker（`api/events.py`）是 asyncio.Queue 的发布-订阅模式，QueueFull 时丢弃旧事件保持实时性
- Pipeline 的 Qt 信号通过 `_connect_signals()` 桥接到 EventBroker

### Qt 信号桥接
- `core/_headless.py` 创建 `QCoreApplication` 使 pyqtSignal 在无 GUI 环境工作
- `api/pipeline.py::_connect_signals()` 将每个 pyqtSignal 连接到 `event_broker.publish()`
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
灵感 → 世界观构建(world_view.json, 0-15%) → ⏸审阅检查点(confirm_world_view)
     → 大纲生成(outline.json, 10-25%) → 并行章节生成(25-60%, Semaphore并发)
     → 质量评估(60-75%, LLM打分 + rule_checker硬校验)
     → 修订循环(75-90%, patch协议, 命中率<50%回退全文重写)
     → 多平台适配(90-100%) → 完成
```

### 审阅检查点
- **世界观审阅**：`world_view_review_ready` 事件 → 用户确认后调 `confirm_world_view()`
- **续写大纲审阅**：`continuation_outline_ready` 事件 → 用户确认后调 `confirm_continuation()`

### 修订机制
- **patch 协议**：RevisionAgent 输出 `[{anchor, replacement, reason}]`，精确匹配 + fuzzy 匹配（忽略空白/全半角标点）
- **命中率阈值**：patch 命中 <50% 时回退到全文重写模式
- **最大轮数**：`max_revision_rounds`（默认 3），每轮修订后重跑评估
- **手动编辑保护**：章节标记 `manually_edited` 后修订循环跳过该章节

### 续写/恢复模式
- **续写**：`continue_from_project()` → 加载遗产包 → ContinuationOutlineAgent 生成批次大纲 → 审阅 → 仅评估新章节 → 状态保持 `generating`（连载未完）
- **恢复**：`resume_from_project()` → 缺大纲补大纲，否则补缺失章节
- **时间线快照**：`build_timeline_snapshot()` 保存 `timeline_snapshot.json`，供续写时减少对长前文的依赖

### 项目目录结构
`projects/<灵感>_<时间戳>/`，含 `world_view.json`、`outline.json`、`summary.json`、`timeline_snapshot.json`、`outline_batch_N.json`、`chapters/chapter_NNN_{meta.json,txt}`、`exports/`

## LLM 集成

默认使用 **LongCat**（Anthropic 兼容接口），可选 **DeepSeek**（OpenAI 兼容）。

| provider | base_url | SDK | 认证方式 |
|---|---|---|---|
| longcat | https://api.longcat.chat/anthropic | anthropic.Anthropic | `auth_token`（Bearer <REDACTED>） |
| deepseek | https://api.deepseek.com/v1 | openai.OpenAI | `api_key` |

`LLMClient` 内置 3 次重试 + 15 秒心跳日志，空响应自动提高预算重试；`chat_stream()` 有 60 秒停滞检测。

### JSON 解析鲁棒性
`BaseAgent.parse_json_response` 有 5 层策略：strict → 非严格（允许控制字符）→ 代码块提取 → 常见错误修复 → 逐步截断。失败时落盘到 `projects/_parse_failures/`。

## 配置管理

配置存储在 `backend/config.json`，由 `backend/core/config.py` 管理（与 `DEFAULT_CONFIG` 合并兼容新字段）。

| 字段 | 默认值 | 用途 |
|---|---|---|
| `api_key` | （空） | LLM API Key |
| `provider` | `longcat` | 服务商：longcat / deepseek |
| `model` | `LongCat-2.0` | 模型名 |
| `base_url` | `https://api.longcat.chat/anthropic` | 接入点 |
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
| 根构建命令 | `package.json` |
| 前端构建 | `frontend/package.json` |
| Python 依赖 | `backend/requirements.txt` |
| 一键安装 | `install.bat` |
| 开发启动 | `dev.bat` |
| 前端入口 | `frontend/src/main.tsx` |
| 根组件 | `frontend/src/App.tsx` |
| Zustand store | `frontend/src/stores/useStore.ts` |
| SSE 连接 | `frontend/src/stores/useSSE.ts` |
| API 客户端 | `frontend/src/api/client.ts` |
| 类型定义 | `frontend/src/types/index.ts` |
| 设置页 | `frontend/src/pages/SettingsTab.tsx` |
| 侧边栏 | `frontend/src/components/Sidebar.tsx` |
| 毛玻璃 CSS | `frontend/src/styles/index.css` |
| Tailwind 配置 | `frontend/tailwind.config.js` |
| Electron 主进程 | `electron/main.js` |
| Electron preload | `electron/preload.js` |
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
