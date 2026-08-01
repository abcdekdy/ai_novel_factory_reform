/**
 * Zustand 全局状态管理
 */
import { create } from 'zustand'
import type {
  PipelineStage,
  AgentStatus,
  LogEntry,
  AgentCardState,
  WorldView,
  Outline,
  ChapterMeta,
  ProjectSummary,
} from '../types'

interface AppState {
  // 当前激活的 Tab
  activeTab: number
  setActiveTab: (tab: number) => void

  // 流水线状态
  isRunning: boolean
  currentStage: PipelineStage
  overallProgress: number
  projectDir: string | null

  // 日志
  logs: LogEntry[]
  addLog: (entry: LogEntry) => void
  clearLogs: () => void

  // Agent 卡片
  agents: Record<string, AgentCardState>
  setAgentStatus: (name: string, status: AgentStatus, progress?: number) => void
  initAgents: () => void

  // 当前打开的项目（用于跨页面共享项目名）
  currentProject: ProjectSummary | null
  setCurrentProject: (p: ProjectSummary | null) => void

  // 世界观
  worldView: WorldView | null
  setWorldView: (wv: WorldView | null) => void
  pendingWorldView: WorldView | null
  setPendingWorldView: (wv: WorldView | null) => void

  // 大纲
  outline: Outline | null
  setOutline: (o: Outline | null) => void
  pendingOutline: Outline | null
  setPendingOutline: (o: Outline | null) => void

  // 章节
  chapters: ChapterMeta[]
  addChapter: (ch: ChapterMeta) => void
  setChapters: (chapters: ChapterMeta[]) => void

  // 错误
  error: string | null
  setError: (err: string | null) => void
  pipelineError: { stage: string; message: string } | null
  setPipelineError: (err: { stage: string; message: string } | null) => void

  // 续写
  pendingContinuationOutline: Outline | null
  setPendingContinuationOutline: (o: Outline | null) => void

  // 重置
  resetPipelineState: () => void
}

const DEFAULT_AGENTS: Record<string, AgentCardState> = {
  '世界观构建': { name: '世界观构建', displayName: '世界观构建', status: 'idle', progress: 0, description: '构建故事世界框架' },
  '大纲生成': { name: '大纲生成', displayName: '大纲生成', status: 'idle', progress: 0, description: '生成详细章节大纲' },
  '章节生成': { name: '章节生成', displayName: '章节生成', status: 'idle', progress: 0, description: '并行生成各章内容' },
  '质量评估': { name: '质量评估', displayName: '质量评估', status: 'idle', progress: 0, description: '评估+硬校验' },
  '回流修订': { name: '回流修订', displayName: '回流修订', status: 'idle', progress: 0, description: '自动修订不达标章节' },
  '多平台适配': { name: '多平台适配', displayName: '多平台适配', status: 'idle', progress: 0, description: '格式适配输出' },
}

export const useStore = create<AppState>((set, get) => ({
  activeTab: 0,
  setActiveTab: (tab) => set({ activeTab: tab }),

  isRunning: false,
  currentStage: 'idle',
  overallProgress: 0,
  projectDir: null,

  logs: [],
  addLog: (entry) => set((state) => ({
    logs: [...state.logs.slice(-499), { ...entry, timestamp: Date.now() }],
  })),
  clearLogs: () => set({ logs: [] }),

  agents: { ...DEFAULT_AGENTS },
  setAgentStatus: (name, status, progress) => set((state) => {
    const existing = state.agents[name] || { name, displayName: name, status: 'idle', progress: 0, description: '' }
    // success 默认 progress=100
    const nextProgress = progress ?? (status === 'success' ? 100 : existing.progress)
    return {
      agents: {
        ...state.agents,
        [name]: { ...existing, status, progress: nextProgress },
      },
    }
  }),
  initAgents: () => set({ agents: { ...DEFAULT_AGENTS } }),
  // 重置流水线相关状态（启动新项目时调用）
  resetPipelineState: () => set({
    isRunning: false,
    currentStage: 'idle',
    overallProgress: 0,
    agents: { ...DEFAULT_AGENTS },
    worldView: null,
    outline: null,
    chapters: [],
    pendingWorldView: null,
    pendingOutline: null,
    pendingContinuationOutline: null,
    error: null,
    pipelineError: null,
  }),

  currentProject: null,
  setCurrentProject: (p) => set({ currentProject: p }),

  worldView: null,
  setWorldView: (wv) => set({ worldView: wv }),
  pendingWorldView: null,
  setPendingWorldView: (wv) => set({ pendingWorldView: wv }),

  outline: null,
  setOutline: (o) => set({ outline: o }),
  pendingOutline: null,
  setPendingOutline: (o) => set({ pendingOutline: o }),

  chapters: [],
  addChapter: (ch: ChapterMeta) => set((state) => {
    // 按 chapter_index 去重，避免重复添加
    const idx = ch.chapter_index
    const exists = idx !== undefined && state.chapters.some((c) => c.chapter_index === idx)
    if (exists) return state
    return { chapters: [...state.chapters, ch] }
  }),
  setChapters: (chapters) => set({ chapters }),

  error: null,
  setError: (err) => set({ error: err }),
  pipelineError: null,
  setPipelineError: (err) => set({ pipelineError: err }),

  pendingContinuationOutline: null,
  setPendingContinuationOutline: (o) => set({ pendingContinuationOutline: o }),
}))
