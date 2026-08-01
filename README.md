# AI 小说工厂（新版）

基于 Electron + React + TypeScript + FastAPI 重构的 AI 小说生成桌面应用。

本项目灵感来源于美团 longcat 演示的小说生成，编码完全由 Claude Code 使用 DeepSeek 完成。

## 架构

```
┌─────────────────────────────────────────┐
│  Electron (主进程)                       │
│  ├─ 启动 Python 后端子进程               │
│  └─ 窗口管理 / 系统托盘                  │
├─────────────────────────────────────────┤
│  React + TypeScript (渲染进程)           │
│  ├─ Vite 构建                           │
│  ├─ Tailwind CSS + Framer Motion        │
│  └─ Zustand 状态管理                     │
├─────────────────────────────────────────┤
│  HTTP / SSE                             │
├─────────────────────────────────────────┤
│  FastAPI (Python 后端)                   │
│  ├─ REST API                            │
│  ├─ SSE 流式事件                         │
│  └─ core/ (pipeline, agents, llm)       │
└─────────────────────────────────────────┘
```

## 开发

```bash
# 1. 安装前端依赖
cd frontend && npm install

# 2. 安装 Python 依赖
cd backend && pip install -r requirements.txt

# 3. 安装 Electron 依赖 (根目录)
npm install

# 4. 启动开发模式 (同时启动后端 + 前端 + Electron)
npm run dev
```

## 打包

```bash
npm run build
npm run make
```

## 功能

- 世界观构建 → 大纲生成 → 并行章节生成 → 质量评估 → 自动修订 → 平台适配
- 续写（分批串行生成）
- 项目库管理（创建、恢复、续写）
- 实时 Agent 监控 + 流式日志
- 毛玻璃 / Apple 风格 UI + 流畅动画
