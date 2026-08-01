/**
 * API 客户端 — 封装所有后端 REST 调用
 */
import type { ProjectSummary } from '../types'

const BASE_URL = 'http://127.0.0.1:8765'
const DEFAULT_TIMEOUT = 30000 // 30 秒默认超时

async function request<T>(path: string, options?: RequestInit, timeout = DEFAULT_TIMEOUT): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
      signal: controller.signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `请求失败: ${res.status}`)
    }
    return res.json()
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') {
      throw new Error('请求超时，请检查后端是否运行')
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  // 健康检查
  health: () => request<{ status: string }>('/api/health'),

  // 流水线控制
  startPipeline: (data: { inspiration: string; chapter_count?: number; chapter_length?: number; api_key?: string }) =>
    request<{ ok: boolean }>('/api/pipeline/start', { method: 'POST', body: JSON.stringify(data) }),

  resumePipeline: (data: { project_dir: string }) =>
    request<{ ok: boolean }>('/api/pipeline/resume', { method: 'POST', body: JSON.stringify(data) }),

  continuePipeline: (data: { project_dir: string; guidance: string; batch_chapter_count?: number }) =>
    request<{ ok: boolean }>('/api/pipeline/continue', { method: 'POST', body: JSON.stringify(data) }),

  confirmWorldView: (data: { world_view: unknown }) =>
    request<{ ok: boolean }>('/api/pipeline/confirm-world-view', { method: 'POST', body: JSON.stringify(data) }),

  confirmOutline: (data: { outline: unknown }) =>
    request<{ ok: boolean }>('/api/pipeline/confirm-outline', { method: 'POST', body: JSON.stringify(data) }),

  confirmContinuation: (data: { outline: unknown }) =>
    request<{ ok: boolean }>('/api/pipeline/confirm-continuation', { method: 'POST', body: JSON.stringify(data) }),

  pausePipeline: () =>
    request<{ ok: boolean }>('/api/pipeline/pause', { method: 'POST' }),

  stopPipeline: () =>
    request<{ ok: boolean }>('/api/pipeline/stop', { method: 'POST' }),

  pipelineStatus: () =>
    request<{ is_running: boolean; current_stage: string; project_dir: string | null }>('/api/pipeline/status'),

  // 项目管理
  listProjects: () =>
    request<{ projects: ProjectSummary[] }>('/api/projects'),

  getProjectSummary: (name: string) =>
    request<Record<string, unknown>>(`/api/projects/${encodeURIComponent(name)}/summary`),

  getWorldView: (name: string) =>
    request<Record<string, unknown>>(`/api/projects/${encodeURIComponent(name)}/world-view`),

  getOutline: (name: string) =>
    request<Record<string, unknown>>(`/api/projects/${encodeURIComponent(name)}/outline`),

  getChapters: (name: string) =>
    request<Record<string, unknown>>(`/api/projects/${encodeURIComponent(name)}/chapters`),

  exportTxt: (name: string) =>
    request<{ ok: boolean; path: string }>(`/api/projects/${encodeURIComponent(name)}/export/txt`, { method: 'POST' }),

  exportMarkdown: (name: string) =>
    request<{ ok: boolean; path: string }>(`/api/projects/${encodeURIComponent(name)}/export/markdown`, { method: 'POST' }),

  // 删除项目
  deleteProject: (name: string) =>
    request<{ ok: boolean }>(`/api/projects/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  // 配置
  getConfig: () =>
    request<Record<string, unknown>>('/api/config'),

  updateConfig: (data: Record<string, unknown>) =>
    request<{ ok: boolean }>('/api/config', { method: 'PUT', body: JSON.stringify(data) }),

  testConnection: () =>
    request<{ ok: boolean; message: string }>('/api/config/test-connection', { method: 'POST' }),
}

// ProjectSummary 类型重新导出（定义在 types/index.ts）
export type { ProjectSummary }
