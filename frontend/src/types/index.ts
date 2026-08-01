/**
 * 前后端共享类型定义
 */

export type PipelineStage =
  | 'idle'
  | 'world_building'
  | 'outline_generation'
  | 'chapter_generation'
  | 'quality_evaluation'
  | 'revision'
  | 'adaptation'
  | 'completed'

export type AgentStatus = 'idle' | 'running' | 'success' | 'error' | 'waiting'

export interface LogEntry {
  source: string
  message: string
  timestamp?: number
}

export interface AgentCardState {
  name: string
  displayName: string
  status: AgentStatus
  progress: number
  description: string
}

export interface ChapterMeta {
  chapter_index: number
  title: string
  content: string
  word_count: number
  summary?: string
}

export interface WorldView {
  title: string
  genre?: string
  setting?: string
  characters?: Character[]
  magic_system?: string
  chapter_outline?: OutlineChapter[]
  [key: string]: unknown
}

export interface Character {
  name: string
  role?: string
  description?: string
  [key: string]: unknown
}

export interface OutlineChapter {
  chapter_index?: number
  title?: string
  plot_detail?: string
  key_events?: string[]
  characters_present?: string[]
  [key: string]: unknown
}

export interface Outline {
  chapters?: OutlineChapter[]
  consistency_rules?: string[]
  character_arcs?: Record<string, unknown>[]
  outline_meta?: { total_chapters: number; batch?: number }
  [key: string]: unknown
}

export interface ProjectSummary {
  name: string
  path: string
  title?: string
  status?: string
  chapter_count?: number
  avg_quality_score?: number
  completed_at?: string
  [key: string]: unknown
}

export interface PipelineState {
  isRunning: boolean
  currentStage: PipelineStage
  overallProgress: number
  projectDir: string | null
  logs: LogEntry[]
  agents: Record<string, AgentCardState>
  worldView: WorldView | null
  outline: Outline | null
  chapters: ChapterMeta[]
  error: string | null
}
