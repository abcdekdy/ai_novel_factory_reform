# AI 小说工厂（新版）

<p align="center">
  <img src="assets/icon.png" width="120" alt="AI 小说工厂图标" />
</p>

<p align="center">
  基于 Electron + React + TypeScript + FastAPI 的 AI 长篇小说生成桌面应用
</p>

<p align="center">
  <b>当前版本：2.2.1</b> · <a href="https://github.com/abcdekdy/ai_novel_factory_reform">GitHub 仓库</a>
</p>

---

## 目录

- [1. 项目简介](#1-项目简介)
- [2. 功能特性](#2-功能特性)
- [3. 技术栈与架构](#3-技术栈与架构)
- [4. 环境要求](#4-环境要求)
- [5. 快速开始](#5-快速开始)
- [6. 使用指南](#6-使用指南)
- [7. 数据与目录](#7-数据与目录)
- [8. 构建与部署](#8-构建与部署)
- [9. API 与调试](#9-api-与调试)
- [10. 常见问题](#10-常见问题)
- [11. 代码结构](#11-代码结构)
- [12. 版本记录与更多文档](#12-版本记录与更多文档)

---

## 1. 项目简介

AI 小说工厂把"一句话灵感"变成一部结构完整的小说。它不绑定任何模型厂商，只要求目标服务兼容 **Anthropic Messages API**：填入 Base URL、API Key 和模型名即可使用任意兼容服务。

生成流程是一条带人工检查点的流水线：

```
灵感
 → 世界观构建（设定 / 角色 / 故事框架 / 粗大纲）
 → 世界观审阅（人工确认或修改）
 → 详细大纲生成（细纲 / 关键事件 / 伏笔 / 角色弧线）
 → 大纲审阅（人工确认或修改）
 → 并行章节生成
 → 质量评估（LLM 打分 + 程序化硬校验）
 → 自动修订（patch 局部修订 / 整章重写兜底 / 退步回滚）
 → 多平台适配（可选）
 → 预览 / 导出 / 续写
```

桌面端负责界面与动画，Python 后端负责流水线编排与文件落盘，两者通过 REST + SSE 通信。

---

## 2. 功能特性

**创作与质量控制**

- 世界观、大纲、章节三阶段生成，世界观和大纲各有一个**人工审阅检查点**，可逐字段修改后继续
- 每个检查点支持**重新生成**，不满意可原地重跑该阶段
- 质量评估双层：程序化硬校验（字数、禁用句式、章尾钩子、关键事件覆盖、出场人物）+ LLM 主观打分
- 自动修订循环：patch 锚点精确/模糊匹配；命中率过低自动整章重写；修订稿明显退步自动回滚到上一版
- 失败章节跳过评估，可只补生成缺失章节，不必从头再来

**长篇与续写**

- 项目库支持打开、恢复（补齐缺失章节）、续写（按批次追加）、删除
- 续写时携带前文遗产包（最近章节摘要、角色状态、未回收伏笔、历史批次），并可审阅本批大纲
- 每章只评估/适配本批新增内容，不重复消耗旧章节

**成本与并发**

- 章节生成、质量评估、修订、竞稿候选全部按 `concurrency` 限流
- 成本门禁：按 token 用量与单价估算花费，80% 告警、达上限自动暂停并保存（进度无损）
- 多平台适配可一键关闭；patch 命中率过低时的整章重写兜底也可关闭

**其他**

- 多人格竞稿：≥2 个人格时每章各写一稿，评审 Agent 评分选优，可设置连续失败自动弃权
- 实时 SSE 日志与 6 个 Agent 状态卡片；刷新/重连后自动回填后端状态
- Apple 风格毛玻璃界面、Framer Motion 动画、可选中复制正文与日志
- 免安装绿色版：PyInstaller 冻结后端，终端用户无需安装 Python

---

## 3. 技术栈与架构

| 层 | 技术 |
|---|---|
| 桌面壳 | Electron 32（主进程管理 Python 子进程、窗口、健康检查） |
| 前端 | React 18 + TypeScript（strict）+ Vite 5 + Tailwind CSS + Framer Motion + Zustand |
| 后端 | FastAPI + uvicorn + Pydantic + sse-starlette |
| LLM 接入 | `anthropic` SDK（Anthropic Messages API 协议，厂商无关） |
| 打包 | PyInstaller（后端）+ 复用 `node_modules/electron/dist`（运行时）+ rcedit（exe 图标） |

```
┌──────────────────────────────────────────────────┐
│ Electron 主进程                                   │
│  ├─ 启动/回收 Python 后端（开发态 python，打包态 exe）│
│  ├─ 等待 /api/health 就绪后再开窗                  │
│  └─ IPC：open-path / show-in-folder               │
├──────────────────────────────────────────────────┤
│ React 渲染进程（Vite 构建）                        │
│  ├─ 5 个页面：创作 / 工作台 / 预览 / 项目库 / 设置   │
│  ├─ Zustand 单一 store + SSE 事件分发              │
│  └─ 三个审阅对话框                                 │
├──────────────────────────────────────────────────┤
│ HTTP REST + SSE（127.0.0.1:8765）                  │
├──────────────────────────────────────────────────┤
│ FastAPI 后端                                      │
│  ├─ api/：events（SSE 总线）/ pipeline / projects / config │
│  └─ core/：pipeline 状态机 + 各 Agent + LLMClient  │
└──────────────────────────────────────────────────┘
```

后端是**无界面服务端**：信号用 `core/signals.py` 的极简实现，不再依赖 PyQt6。

---

## 4. 环境要求

### 使用绿色版（普通用户）

- Windows 10 / 11（x64）
- 无需安装 Node.js、Python 或任何依赖

### 源码运行 / 二次开发

- **Windows 10 / 11**（脚本为 `.bat`；代码本身可在 macOS/Linux 运行，需手动执行等价命令）
- **Node.js 18+**（含 npm）
- **Python 3.10+**（后端使用 `str | None` 等 3.10 语法）
- 可访问 npm / PyPI 的网络（国内建议先看 `package.json` 里的 Electron 镜像配置）

### 自行构建绿色版

在"源码运行"要求之外，还需要：

```bash
pip install pyinstaller
```

---

## 5. 快速开始

### 5.1 使用免安装绿色版（推荐）

> **路径必须是纯英文！** Electron 在包含中文、全角字符（如 `（` `）`）的路径下会在初始化阶段崩溃，表现为双击后完全没反应。请把程序放到类似 `桌面\AI-Novel-Factory`、`C:\AINovelFactory` 或 `D:\AI-Novel-Factory` 的目录，不要放在 `桌面\小说生成助手（新版）\...` 这类路径下。

1. 获取 `AI-Novel-Factory-win32-x64.zip`：从 GitHub Releases 下载（若已发布绿色版），或按 [第 8 节](#8-构建与部署) 自行构建
2. 解压到**纯英文且可写**的目录（例如 `C:\AI-Novel-Factory`；**不要**放 `C:\Program Files` 等只读目录）
3. 双击目录内的 `ai-novel-factory.exe`
4. 首次启动会自动在 exe 同级创建 `data/`，并拉起本地后端（约 1–3 秒）
5. 进入 **设置** 页填写接口信息，点击「测试连接」通过后即可开始创作

> 升级时替换 `ai-novel-factory.exe` 与 `resources/`，**保留 `data/`** 即可保留配置与作品。
> 整个文件夹可以整体搬移，数据跟着走。
>
> 如果从源码目录启动：双击根目录的 `启动绿色版.bat`，它会把绿色版同步到**桌面上的 `AI-Novel-Factory` 文件夹**（纯英文、容易找到）再启动，避免中文路径问题。

### 5.2 源码安装与开发模式

一键安装（项目根目录双击，或在终端执行）：

```bat
install.bat
```

手动分步：

```bash
# 1. 根目录依赖（Electron / 打包脚本）
npm install

# 2. 前端依赖
cd frontend
npm install
cd ..

# 3. Python 后端依赖
cd backend
pip install -r requirements.txt
cd ..
```

启动开发模式（推荐双击 `dev.bat`，或执行 `npm run dev`）：

```bash
npm run dev
```

> **开发模式的路径要求**：`dev.bat` 会从项目当前路径启动 Electron，因此项目路径同样必须是纯英文。如果项目在中文目录（例如 `桌面\小说生成助手（新版）`），请改用根目录的 `dev-ascii.bat`：它会把项目同步到 `%USERPROFILE%\AI-Novel-Factory-Dev`（纯英文、用户目录下容易找到）后运行，配置与作品仍指向原项目 `backend\`。

`npm run dev` 会并行启动三个进程：

| 进程 | 端口 | 说明 |
|---|---|---|
| Vite 前端 | 5173 | 支持热更新 |
| Python 后端 | 8765 | `uvicorn main:app --reload` |
| Electron | — | 自动加载 `http://localhost:5173` |

也可以分开启动（便于看各自日志）：

```bash
# 终端 1
cd frontend && npm run dev

# 终端 2
cd backend && uvicorn main:app --reload --port 8765

# 终端 3
npx electron .
```

> 开发模式修改**前端**代码会热更新；修改**后端**代码必须重启后端（`--reload` 通常会自动重启，若未生效请手动重启）。

### 5.3 首次配置

打开应用左侧「设置」，填写三样必填项：

| 配置项 | 说明 |
|---|---|
| **Base URL** | 服务根地址，例如 `https://api.example.com`。**不要**在末尾附加 `/v1/messages` |
| **API Key** | 服务商提供的密钥；保存后 GET 接口只返回脱敏值 |
| **模型名称** | 服务商文档中的模型 ID，例如某个兼容 Anthropic 协议的模型名 |

点击「测试连接」：成功显示模型回复；401/403/404 分别提示 Key 无效、无权限、接口或模型不存在。

其余参数可按需调整：

- **并发数**：默认 3，受服务端限流时调低
- **质量阈值**：评估模型判定"通过"的分数线（默认 7.0），调高会增加修订次数与成本
- **最大修订轮数**：默认 3
- **成本门禁**：上限（美元）+ 输入/输出单价（美元/百万 token），0 表示不限制
- **多人格竞稿**：每行「名称|风格描述」，配置 ≥2 个才启用
- **多平台适配**：每章额外一次大调用，只想要原始章节时关闭可显著省钱
- **patch 命中率过低时整章重写**：关闭后锚点大面积落空时保留原文

---

## 6. 使用指南

### 6.1 创作流程

1. **创作页**：输入灵感（可点示例标签快速填充），设置章节数与每章目标字数，点击「开始生成」
2. 自动跳到**工作台**：6 张 Agent 卡片 + 总进度 + 实时日志
3. 世界观生成完成后弹出**审阅对话框**：
   - 可修改标题、题材、简介、时代/地理/世界规则/势力/历史、故事框架、角色（含能力）、章节大纲
   - 「确认并继续」→ 开始生成详细大纲
   - 「重新生成」→ 重跑世界观
   - 「稍后审阅」/ESC/点遮罩 → 暂时收起，顶部横幅与工作台按钮可随时重新打开
4. **大纲审阅**：逐章修改标题与细纲；可查看一致性规则与角色弧线；确认后开始并行写章节
5. **章节生成** → **质量评估** → **自动修订**（日志会显示每章评分、修订轮次、命中率、回滚情况）
6. **多平台适配**（若开启）→ 完成，自动进入预览页查看结果

### 6.2 工作台操作

- **暂停并保存**：当前模型调用结束后停下，进度落盘；之后可在项目库「恢复」
- **停止**：立即结束本次流水线（不会删除已生成内容）
- **重试当前阶段**：失败时出现，世界观/大纲阶段重跑该阶段，章节阶段只补缺失章节
- **等待审阅**提示条：点击即可重新打开被收起的审阅对话框

### 6.3 项目库

每个项目卡片显示状态（生成中 / 已完成 / 已暂停 / 已失败）、章节数、平均评分与完成时间。

| 操作 | 说明 |
|---|---|
| **打开** | 加载世界观、大纲、全部章节到预览页 |
| **恢复** | 从断点继续：缺大纲先补大纲，否则只补缺失章节 |
| **续写** | 输入续写指引与本批章数，生成批次大纲 → 审阅 → 只写新章节 |
| **删除** | 删除整个项目目录，不可恢复（二次确认） |

### 6.4 预览与导出

- **世界观**：简介、时代/地理/规则/势力/历史、故事框架、角色（含能力）
- **大纲**：逐章细纲、关键事件、一致性规则
- **章节**：左侧章节列表 + 右侧正文（可选中复制）

导出按钮位于右上角：

- **导出 TXT / Markdown**：写入项目 `exports/` 下，并用系统默认程序打开
- 多平台适配稿单独保存在 `exports/adaptations/`

### 6.5 高级功能

**成本门禁**

- 每次调用后累计 token，按设置的单价估算花费
- 达 80% 在日志告警一次；达上限自动暂停并保存，调高上限后可从项目库恢复
- 若网关不返回 `usage`，花费统计会静默跳过，不影响生成

**多人格竞稿**

- 每章按人格并行生成候选稿，评审 Agent 要求逐字引用原文后打分选优
- 同一章只占一个并发位；某人格连续失败 3 次自动弃权；只剩一稿不评审；全部失败降级单 Writer

**续写**

- 续写会携带前文摘要、角色当前状态、未回收伏笔与历史批次
- 状态保持"生成中"（连载未完结），可反复追加批次
- 已完成章节不会被重写或重复评估

---

## 7. 数据与目录

所有用户数据都在**可写数据目录**下：

| 运行方式 | 数据目录 |
|---|---|
| 绿色版 | `ai-novel-factory.exe` 同级的 `data/` |
| 开发模式 | `backend/` |
| 自定义 | 环境变量 `NOVEL_DATA_DIR` 指定的目录（优先级最高） |

```
data/
├─ config.json                 # 接口与运行配置（含 API Key，注意不要提交到仓库）
└─ projects/
   └─ <灵感前20字>_<时间戳>/
      ├─ world_view.json       # 世界观
      ├─ outline.json          # 详细大纲
      ├─ outline_batch_N.json  # 续写批次大纲
      ├─ summary.json          # 状态 / 统计 / 成本 / 批次记录
      ├─ timeline_snapshot.json# 时间线快照
      ├─ chapters/
      │  ├─ chapter_001_meta.json  # 完整章节数据（正文/摘要/修订记录）
      │  └─ chapter_001.txt        # 纯正文
      └─ exports/
         ├─ <项目名>.txt / .md     # 整本导出
         └─ adaptations/           # 多平台适配稿
```

> 备份作品 = 备份 `data/` 目录。`.gitignore` 已忽略 `config.json` 与项目数据，避免密钥/作品误入仓库。

---

## 8. 构建与部署

### 8.1 一键构建绿色版

```bash
npm run build
```

或直接双击 `build-portable.bat`。产物：

```
out/
├─ AI-Novel-Factory-win32-x64/          # 免安装目录
└─ AI-Novel-Factory-win32-x64.zip       # 分发用压缩包
```

解压后双击目录内的 `ai-novel-factory.exe` 即可运行。**产物目录名保持纯英文**，但解压时选择的父目录也必须是纯英文（例如 `C:\AI-Novel-Factory`），否则 Electron 仍会因路径含中文而崩溃。

### 8.2 构建步骤拆解

`npm run build` 等价于依次执行：

| 步骤 | 命令 | 产物 | 说明 |
|---|---|---|---|
| 前端 | `npm run build:frontend` | `frontend/dist/` | `tsc -b && vite build` |
| 后端 | `npm run build:backend` | `backend/dist/novel-backend/` | PyInstaller `--onedir --noconsole` 冻结，约 30MB |
| 组装 | `npm run build:portable` | `out/…` | 复制 Electron 运行时、应用代码、冻结后端；写 exe 图标；压缩 zip |

任一步失败可单独重跑。常见前置检查：

```bash
node --version          # >= 18
python --version        # >= 3.10
python -m PyInstaller --version   # 未安装则 pip install pyinstaller
```

### 8.3 产物结构与升级

```
AI-Novel-Factory-win32-x64/
├─ ai-novel-factory.exe        # 入口（PE 图标已写入）
├─ resources/
│  ├─ app/                     # Electron 应用代码（main/preload/frontend）
│  └─ novel-backend/           # 冻结的 Python 后端
└─ data/                       # 首次运行自动创建（配置 + 项目）
```

- **升级**：用新版本替换 `ai-novel-factory.exe` 与 `resources/`，保留 `data/`
- **迁移**：整个文件夹拷走即可（数据跟着走）
- **自定义数据位置**：启动前设置环境变量 `NOVEL_DATA_DIR=<绝对路径>`
- **路径要求**：exe 所在路径必须是纯英文（不能含中文、全角括号、日文等非 ASCII 字符）

### 8.4 开发模式部署

```bat
dev.bat
```

若项目路径含中文，改用：

```bat
dev-ascii.bat
```

或手动：

```bash
npm run dev
```

- **项目路径必须是纯英文**：Electron 从含中文/全角字符的路径启动会直接崩溃；`dev-ascii.bat` 会先把项目镜像到 `%USERPROFILE%\AI-Novel-Factory-Dev` 再启动，并通过 `NOVEL_DATA_DIR` 继续使用原项目的配置与作品
- 后端端口固定 `8765`，前端 Vite 固定 `5173`（均在代码中硬编码）
- Electron 会先等 `/api/health` 通过再开窗；若 30 秒内未就绪会弹中文排查提示
- 关闭窗口时 Electron 会回收 Python 后端（开发模式还会清理占用 5173 的进程）

### 8.5 自检

后端自带一份**标准库 unittest** 自检，不发真实网络请求：

```bash
cd backend
python selftest.py
```

覆盖：章节 worker 计数、续写缓存键、续写/恢复状态隔离、失败章节处理、适配落盘与跳过、完成统计口径、批次记录、失败状态、配置校验、LLM 短响应重试、字数统计、审阅状态快照等。

前端类型检查与构建：

```bash
cd frontend
npx tsc --noEmit
npm run build
```

---

## 9. API 与调试

后端启动后可访问：

| 地址 | 用途 |
|---|---|
| `http://127.0.0.1:8765/api/health` | 健康检查（Electron 用它判断就绪） |
| `http://127.0.0.1:8765/docs` | FastAPI 自动生成的接口文档 |
| `http://127.0.0.1:8765/api/events/stream` | SSE 事件流（`log` / `progress` / `stage` / `chapter_ready` / `pipeline_finished` 等） |

主要端点：

- 配置：`GET/PUT /api/config`、`POST /api/config/test-connection`
- 流水线：`POST /api/pipeline/start|resume|continue|pause|stop|retry|retry-world-view|retry-outline`、`POST /api/pipeline/confirm-world-view|confirm-outline|confirm-continuation`、`GET /api/pipeline/status|state`
- 项目：`GET /api/projects`、`GET /api/projects/{name}/{summary|world-view|outline|chapters|batches}`、`POST /api/projects/{name}/export/{txt|markdown}`、`DELETE /api/projects/{name}`

调试建议：

- 前端控制台会打印 SSE 连接与解析错误
- 后端解析失败样本落盘在 `data/projects/_parse_failures/`
- Electron 主进程会把后端 stdout/stderr 转发到终端（`[Python]` / `[Python ERR]`）

---

## 10. 常见问题

**Q1. 双击 exe 完全没反应 / 窗口一闪而过**

**先检查路径**：程序所在路径是否包含中文或全角字符（例如 `桌面\小说生成助手（新版）`）。Electron 在这种路径下会在初始化阶段崩溃（Windows 事件查看器里是 `0x80000003` / BEX64），且不会弹窗。把整个绿色版目录移动到纯英文路径（如 `桌面\AI-Novel-Factory`）后重试；从源码目录可直接双击 `启动绿色版.bat`。

如果路径是纯英文仍打不开：

1. 打开任务管理器，确认是否有残留的 `ai-novel-factory.exe` / `novel-backend.exe`，结束它们后重试
2. 端口 `8765` 是否被其他程序（包括旧的 python.exe）占用：结束占用进程或重启电脑
3. 程序是否被杀毒软件隔离 / 解压不完整：重新解压，给解压目录加白名单
4. 是否放在只读目录：换到用户目录下的英文路径再试

**Q2. 设置页测试连接失败**

- `401`：API Key 错误或失效
- `403`：Key 无权访问该模型
- `404`：Base URL 或模型名不对（Base URL 填根地址，不要带 `/v1/messages`）
- 超时：检查网络或代理；服务端可能不支持所选模型

**Q3. 终端中文乱码**

开发模式请用 `dev.bat`（顶部已 `chcp 65001`）；Electron 启动 Python 时会注入 `PYTHONIOENCODING=utf-8`。若自行起后端，请设置同样的环境变量。

**Q4. 生成卡住不动 / 一直显示某阶段**

- 看工作台日志最后一行在做什么；大模型长响应可能需要数分钟
- 若成本校验触发上限，会显示"成本已达预算上限"并自动暂停
- 失败时底部会显示错误与「重试当前阶段」，章节阶段只会补缺失章节

**Q5. 章节字数与目标偏差较大**

生成模型对字数只有软约束，目标 ±10%，程序硬校验容忍 ±30%。偏差过大时可：
- 调低目标字数或提高 `max_tokens` 相关预算（大纲预算在配置中）
- 在预览页手动修改后使用「导出」；或重跑该项目

**Q6. 成本比预期高**

- 关闭「多平台适配」（每章一次完整正文调用）
- 关闭「整章重写兜底」，或把最大修订轮数调低
- 降低并发不会减少总 token，但能避免服务端限流导致的重试
- 多人格竞稿会让章节调用数按人格数放大，按需开启
- 确认设置里的输入/输出单价与实际计费一致

**Q7. 构建绿色版失败**

- 关闭正在运行的 `ai-novel-factory.exe` / `novel-backend.exe`（文件占用会导致清理失败）
- 确认已 `pip install pyinstaller`、`npm install` 完成
- 项目路径过长时，Windows 可能超过 MAX_PATH：把仓库移到较短的路径再构建
- 可单独重跑 `npm run build:backend` 或 `npm run build:portable` 定位步骤

**Q8. 我的作品/配置在哪？怎么备份？**

见 [第 7 节](#7-数据与目录)。备份 `data/`（绿色版）或 `backend/config.json` + `backend/projects/`（开发模式）。

**Q9. 修改设置后需要重启吗？**

设置保存后，下一次启动/恢复/续写会重新加载配置，无需重启应用；修改**代码**后必须重启后端。

---

## 11. 代码结构

```
.
├─ electron/
│  ├─ main.js               # 主进程：后端子进程、窗口、IPC、健康检查
│  └─ preload.js            # contextBridge 暴露 electronAPI
├─ frontend/
│  ├─ src/
│  │  ├─ pages/             # 创作 / 工作台 / 预览 / 项目库 / 设置
│  │  ├─ components/        # 侧边栏、启动页、三个审阅对话框
│  │  ├─ stores/            # Zustand store + SSE 连接与状态回填
│  │  ├─ api/client.ts      # REST 客户端（BASE_URL / SSE_URL）
│  │  ├─ types/             # 前后端共享类型
│  │  └─ styles/            # Tailwind + 毛玻璃
│  ├─ vite.config.ts
│  └─ tailwind.config.js
├─ backend/
│  ├─ main.py               # FastAPI 入口（CORS、统一异常、路由注册）
│  ├─ api/                  # events / pipeline / projects / config
│  ├─ core/
│  │  ├─ pipeline.py        # 流水线状态机（编排、并发、修订、适配）
│  │  ├─ llm_client.py      # Anthropic Messages 客户端 + 用量/成本
│  │  ├─ world_agent.py / outline_agent.py / chapter_agent.py
│  │  ├─ quality_agent.py / rule_checker.py / revision_agent.py
│  │  ├─ judge_agent.py     # 竞稿评审
│  │  ├─ adapter_agent.py   # 多平台适配
│  │  ├─ project_manager.py # 项目文件读写、导出、时间线快照
│  │  ├─ config.py / paths.py / signals.py / base_agent.py
│  │  └─ continuation_outline_agent.py
│  ├─ selftest.py           # 标准库 unittest 自检
│  ├─ requirements.txt
│  ├─ build_backend.py      # PyInstaller 冻结脚本
│  └─ run_server.py         # 冻结产物入口
├─ assets/                  # 应用图标
├─ package_portable.py      # 绿色版组装 + 压缩（目录名纯英文）
├─ set_exe_icon.mjs         # 写入 exe PE 图标
├─ install.bat / dev.bat / build-portable.bat
├─ 启动绿色版.bat           # 从中文路径源码目录启动绿色版（自动同步到英文路径）
├─ dev-ascii.bat            # 从中文路径启动开发模式（自动同步到英文路径）
├─ CLAUDE.md                # 开发文档与完整修复记录
└─ README.md
```

---

## 12. 版本记录与更多文档

| 版本 | 日期 | 主要内容 |
|---|---|---|
| **2.2.1** | 2026-10-31 | 修复中文/全角路径导致 Electron 无法启动：绿色版目录改为纯英文、新增 `启动绿色版.bat` 与 `dev-ascii.bat`、README 补充路径要求 |
| 2.2.0 | 2026-10-31 | 深度审计修复：章节计数/续写键位、世界观审阅丢字段、项目库字段层级、适配落盘、章节提示词、配置校验、审阅重开与状态回填、预览页字段；新增 32 项后端自检 |
| 2.1.1 | 2026-09-30 | 应用图标（窗口 + exe PE 资源） |
| 2.1.0 | 2026-09-30 | 免安装绿色版打包、移除 PyQt6、质量阈值接入评估 prompt |
| 1.0.x | — | 从 PyQt6 旧版重构为 Electron + React + FastAPI |

- 每个版本的详细问题、根因与修复文件见 [CLAUDE.md](CLAUDE.md) 的「已知问题与修复记录」
- 构建、测试、配置字段、内部机制等开发信息同样以 CLAUDE.md 为准

---

## 13. 致谢

- 项目灵感来源于美团 LongCat 的小说生成演示
- 界面设计参考 Apple Human Interface Guidelines 的排版与材质语言
