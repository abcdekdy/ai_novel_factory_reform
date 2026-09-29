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
     → 质量评估(60-75%, 并发LLM打分 + rule_checker硬校验)
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
| `enable_full_rewrite_fallback` | true | patch 命中率过低时是否整章重写兜底 |
| `quality_threshold` | 7.0 | 质量通过线（满分10） |
| `default_chapter_count` | 5 | 默认章节数 |
| `default_chapter_length` | 3000 | 默认每章字数 |
| `timeout` | 300 | LLM 调用超时（秒） |
| `enable_outline_agent` | true | 大纲 Agent 开关 |
| `outline_max_tokens` | 8192 | 大纲最大 token |
| `outline_temperature` | 0.7 | 大纲温度 |
| `budget_max_cost_usd` | 0.0 | 成本上限（美元），0 = 不限制 |
| `budget_price_input_per_mtok` | 3.0 | 输入单价（美元/百万 token） |
| `budget_price_output_per_mtok` | 15.0 | 输出单价（美元/百万 token） |
| `chapter_personas` | （空） | 竞稿人格，每行「名称\|风格描述」 |

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
- `quality_threshold`（质量阈值）在后端**从未被使用**——通过/需修订完全由 LLM 的 `pass` 字段 + `rule_checker` 硬伤数决定，设置页那个滑杆目前不产生任何效果。修掉它会改变通过判定、进而影响修订轮数与成本，故留给用户决策
- `theme` 不在后端 `DEFAULT_CONFIG` 中，被 `PUT /api/config` 的白名单过滤掉，服务端不持久化
- 章节生成阶段未见端到端真实 API 验证（验证均使用假 LLM 驱动循环逻辑）

## 开发规范

- **QObject 子类属性必须静态初始化**：在 QObject 子类实例上用 `getattr(obj, name, default)` 探测**尚不存在**的属性时，PyQt6 抛的是 `RuntimeError`（"super-class `__init__()` was never called"）而非 `AttributeError`，`getattr` 的默认值兜不住。新增状态字段一律在 `__init__` 中初始化（踩坑记录见 `_persona_semaphore`）

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
| 章节生成 Agent | `backend/core/chapter_agent.py`（支持 persona 竞稿） |
| 竞稿评审 Agent | `backend/core/judge_agent.py` |
| LLM 客户端 | `backend/core/llm_client.py` |
| 项目管理 | `backend/core/project_manager.py` |
| 配置管理 | `backend/core/config.py` |
| Qt 无头模式 | `backend/core/_headless.py` |
| 运行时配置 | `backend/config.json` |
