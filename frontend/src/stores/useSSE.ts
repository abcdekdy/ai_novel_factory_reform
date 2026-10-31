/**
 * SSE 连接管理 — 订阅后端事件流并分发到 store
 *
 * 连接建立（含断线重连）后主动拉一次 /api/pipeline/state 回填 store：
 * SSE 只推增量，刷新页面或断线期间的事件无法重放；不回填就会出现
 * "界面空了、后端还在跑"或"停在等待审阅却看不到对话框"。
 */
import { useEffect, useRef } from 'react'
import { api, SSE_URL } from '../api/client'
import { useStore } from './useStore'
import type { PipelineStage } from '../types'

const STAGE_TO_AGENT: Record<string, string> = {
  world_building: '世界观构建',
  outline_generation: '大纲生成',
  chapter_generation: '章节生成',
  quality_evaluation: '质量评估',
  revision: '回流修订',
  adaptation: '多平台适配',
}

const STAGE_ORDER = Object.keys(STAGE_TO_AGENT)

// 后端 stage 事件里带的是中文阶段名（"世界观构建" 等）
const STAGE_NAME_TO_KEY: Record<string, string> = {
  '世界观构建': 'world_building',
  '大纲生成': 'outline_generation',
  '章节生成': 'chapter_generation',
  '质量评估': 'quality_evaluation',
  '回流修订': 'revision',
  '多平台适配': 'adaptation',
}

const PIPELINE_STAGES: PipelineStage[] = [
  'idle', 'world_building', 'outline_generation', 'chapter_generation',
  'quality_evaluation', 'revision', 'adaptation', 'completed', 'paused', 'failed',
]

function toPipelineStage(stage: string | undefined): PipelineStage {
  return PIPELINE_STAGES.includes(stage as PipelineStage)
    ? (stage as PipelineStage)
    : 'idle'
}

export function useSSE() {
  const esRef = useRef<EventSource | null>(null)
  const openedOnce = useRef(false)
  const syncing = useRef(false)

  const addLog = useStore((s) => s.addLog)
  const setAgentStatus = useStore((s) => s.setAgentStatus)
  const setWorldView = useStore((s) => s.setWorldView)
  const setPendingWorldView = useStore((s) => s.setPendingWorldView)
  const setOutline = useStore((s) => s.setOutline)
  const addChapter = useStore((s) => s.addChapter)
  const setActiveTab = useStore((s) => s.setActiveTab)
  const setPendingOutline = useStore((s) => s.setPendingOutline)
  const setPendingContinuationOutline = useStore((s) => s.setPendingContinuationOutline)

  /** 用后端完整快照回填 store（只在连接建立/重连时调用） */
  const syncPipelineState = async () => {
    if (syncing.current) return
    syncing.current = true
    try {
      const state = await api.pipelineState()
      const store = useStore.getState()

      if (state.world_view) setWorldView(state.world_view)
      if (state.outline) setOutline(state.outline)

      if (Array.isArray(state.chapters) && state.chapters.length > 0) {
        const sorted = [...state.chapters].sort(
          (a, b) => (a.chapter_index ?? 0) - (b.chapter_index ?? 0))
        useStore.setState({ chapters: sorted })
      }

      // 待审阅内容：只在本地还没有时写入，避免覆盖用户正在编辑的草稿
      if (state.reviewing?.world && state.pending?.world && !store.pendingWorldView) {
        setPendingWorldView(state.pending.world)
      }
      if (state.reviewing?.outline && state.pending?.outline && !store.pendingOutline) {
        setPendingOutline(state.pending.outline)
      }
      if (state.reviewing?.continuation && state.pending?.continuation
        && !store.pendingContinuationOutline) {
        setPendingContinuationOutline(state.pending.continuation)
      }

      if (state.is_running) {
        const stage = toPipelineStage(state.current_stage)
        useStore.setState({ isRunning: true, currentStage: stage })
        const currentIndex = STAGE_ORDER.indexOf(state.current_stage)
        STAGE_ORDER.forEach((name, idx) => {
          if (currentIndex >= 0 && idx < currentIndex) setAgentStatus(STAGE_TO_AGENT[name], 'success')
          else if (idx === currentIndex) setAgentStatus(STAGE_TO_AGENT[name], 'running')
        })
        const total = state.total_chapters || 0
        const done = state.completed_chapters || 0
        if (total > 0 && done > 0) {
          useStore.setState({ overallProgress: Math.min(95, Math.round((done / total) * 55) + 25) })
        }
        useStore.setState({ projectDir: state.project_dir ?? null })
        addLog({ source: 'System', message: '已从后端恢复流水线状态' })
      }
    } catch {
      // 后端不可用时不打扰用户：SSE 会继续重连
    } finally {
      syncing.current = false
    }
  }

  useEffect(() => {
    const es = new EventSource(SSE_URL)
    esRef.current = es

    es.onopen = () => {
      console.log('[SSE] 已连接')
      if (openedOnce.current) addLog({ source: 'System', message: '事件流已重新连接' })
      openedOnce.current = true
      void syncPipelineState()
    }

    es.onerror = () => {
      console.warn('[SSE] 连接断开，将自动重连')
    }

    // 注册所有事件处理器
    es.addEventListener('log', (e) => {
      try {
        const data = JSON.parse(e.data)
        addLog({ source: data.source, message: data.message })
      } catch (err) { console.warn('[SSE] log parse error:', err) }
    })

    es.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data)
        useStore.setState({ overallProgress: data.overall || 0 })
      } catch { /* ignore */ }
    })

    es.addEventListener('stage', (e) => {
      try {
        const data = JSON.parse(e.data)
        const agentName = data.stage
        if (data.status === 'started') {
          useStore.setState({
            isRunning: true,
            currentStage: toPipelineStage(STAGE_NAME_TO_KEY[agentName]),
          })
          if (agentName) setAgentStatus(agentName, 'running')
          setActiveTab(1) // 自动切到工作台
        } else if (data.status === 'completed') {
          if (agentName) setAgentStatus(agentName, 'success', 100)
        }
      } catch (err) { console.warn('[SSE] stage parse error:', err) }
    })

    es.addEventListener('world_view_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        setWorldView(data)
      } catch { /* ignore */ }
    })

    es.addEventListener('outline_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        setOutline(data)
      } catch { /* ignore */ }
    })

    es.addEventListener('outline_review_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        setPendingOutline(data)
        useStore.getState().showReview('outline')
      } catch (err) { console.warn('[SSE] outline_review_ready error:', err) }
    })

    es.addEventListener('chapter_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.chapter_index !== undefined) {
          addChapter(data)
          const total = useStore.getState().outline?.outline_meta?.total_chapters || 0
          if (total > 0) {
            const pct = Math.round((useStore.getState().chapters.length / total) * 100)
            setAgentStatus('章节生成', 'running', pct)
          }
        }
      } catch { /* ignore */ }
    })

    es.addEventListener('continuation_outline_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        setPendingContinuationOutline(data)
        useStore.getState().showReview('continuation')
      } catch { /* ignore */ }
    })

    es.addEventListener('world_view_review_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        setPendingWorldView(data)
        useStore.getState().showReview('world')
      } catch (err) { console.warn('[SSE] world_view_review_ready error:', err) }
    })

    es.addEventListener('pipeline_finished', (e) => {
      try {
        const data = JSON.parse(e.data)
        // 区分正常完成 / 错误 / 暂停
        if (data.error) {
          useStore.setState({
            error: data.error,
            isRunning: false,
            currentStage: 'failed',
            pipelineError: { stage: data.stage || '', message: data.error },
          })
          addLog({ source: 'Pipeline', message: `错误: ${data.error}` })
        } else if (data.paused) {
          useStore.setState({ isRunning: false, currentStage: 'paused' })
          addLog({ source: 'Pipeline', message: '流水线已暂停' })
        } else {
          useStore.setState({ isRunning: false, currentStage: 'completed', overallProgress: 100 })
          setAgentStatus('多平台适配', 'success', 100)
        }
        // 通知其他组件流水线已完成
        window.dispatchEvent(new CustomEvent('pipeline_finished'))
      } catch (err) { console.warn('[SSE] pipeline_finished parse error:', err) }
    })

    es.addEventListener('pipeline_error', (e) => {
      try {
        const data = JSON.parse(e.data)
        useStore.setState({
          error: data.error,
          isRunning: false,
          currentStage: 'failed',
          pipelineError: { stage: data.stage || '', message: data.error },
        })
        addLog({ source: 'Pipeline', message: `错误: ${data.error}` })
        // 将所有运行中的 Agent 标记为错误
        const agents = useStore.getState().agents
        for (const [name, agent] of Object.entries(agents)) {
          if (agent.status === 'running') {
            setAgentStatus(name, 'error')
          }
        }
      } catch (err) { console.warn('[SSE] pipeline_error parse error:', err) }
    })

    // 评估/修订/适配完成事件（更新 Agent 状态）
    es.addEventListener('evaluation_ready', () => {
      setAgentStatus('质量评估', 'running')
    })

    es.addEventListener('revision_ready', () => {
      setAgentStatus('回流修订', 'running')
    })

    es.addEventListener('adaptation_ready', () => {
      setAgentStatus('多平台适配', 'running')
    })

    return () => {
      es.close()
      esRef.current = null
    }
    // store 的 action 引用稳定；syncPipelineState 只依赖 store 内部状态
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
