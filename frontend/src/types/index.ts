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
  | 'paused'
  | 'failed'

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
  status?: string
  revised?: boolean
  revision_rounds?: number
  manually_edited?: boolean
  [key: string]: unknown
}

export interface Character {
  name: string
  role?: string
  /** 后端真正使用的字段 */
  desc?: string
  ability?: string
  /** 旧数据/对话框里的别名 */
  description?: string
  [key: string]: unknown
}

export interface OutlineChapter {
  chapter_index?: number
  chapter?: number
  title?: string
  /** 细大纲字段 */
  plot_detail?: string
  /** 世界观阶段的粗大纲字段 */
  summary?: string
  key_events?: string[]
  characters_present?: string[]
  foreshadowing?: string[]
  cliffhanger?: string
  [key: string]: unknown
}

export interface StoryFramework {
  premise?: string
  conflict?: string
  climax?: string
  ending_type?: string
  [key: string]: unknown
}

export interface WorldViewDetail {
  era?: string
  location?: string
  rules?: string
  factions?: string[]
  history?: string
  [key: string]: unknown
}

export interface WorldView {
  title?: string
  genre?: string
  summary?: string
  world_view?: WorldViewDetail
  story_framework?: StoryFramework
  characters?: Character[]
  chapter_outline?: OutlineChapter[]
  /** 旧版扁平字段（只读兼容） */
  setting?: string
  magic_system?: string
  [key: string]: unknown
}

export interface Outline {
  chapters?: OutlineChapter[]
  consistency_rules?: string[]
  character_arcs?: Record<string, unknown>
  outline_meta?: { total_chapters?: number; batch?: number; chapter_start?: number; chapter_end?: number }
  [key: string]: unknown
}

export interface ProjectSummary {
  name: string
  path: string
  title?: string
  status?: string
  chapter_count?: number
  chapters_count?: number
  total_words?: number
  avg_quality_score?: number
  completed_at?: string
  paused_stage?: string
  failed_stage?: string
  cost_usd?: number
  llm_calls?: number
  summary?: Record<string, unknown>
  [key: string]: unknown
}

/** GET /api/pipeline/state 的返回（前端重连后回填 store） */
export interface PipelineStateSnapshot {
  is_running: boolean
  current_stage: string
  failed_stage?: string | null
  total_chapters?: number
  completed_chapters?: number
  world_view?: WorldView | null
  outline?: Outline | null
  chapters?: ChapterMeta[]
  evaluations?: Record<string, unknown>
  project_dir?: string | null
  reviewing?: { world?: boolean; outline?: boolean; continuation?: boolean }
  pending?: {
    world?: WorldView | null
    outline?: Outline | null
    continuation?: Outline | null
  }
}
