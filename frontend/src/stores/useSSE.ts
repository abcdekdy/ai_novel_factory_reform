/**
 * SSE 连接管理 — 订阅后端事件流并分发到 store
 */
import { useEffect, useRef } from 'react'
import { useStore } from './useStore'

const SSE_URL = 'http://127.0.0.1:8765/api/events/stream'

export function useSSE() {
  const esRef = useRef<EventSource | null>(null)
  const addLog = useStore((s) => s.addLog)
  const setAgentStatus = useStore((s) => s.setAgentStatus)
  const setWorldView = useStore((s) => s.setWorldView)
  const setPendingWorldView = useStore((s) => s.setPendingWorldView)
  const setOutline = useStore((s) => s.setOutline)
  const addChapter = useStore((s) => s.addChapter)
  const setActiveTab = useStore((s) => s.setActiveTab)
  const setPendingOutline = useStore((s) => s.setPendingOutline)
  const setPendingContinuationOutline = useStore((s) => s.setPendingContinuationOutline)

  useEffect(() => {
    const es = new EventSource(SSE_URL)
    esRef.current = es

    es.onopen = () => {
      console.log('[SSE] 已连接')
    }

    es.onerror = () => {
      console.warn('[SSE] 连接断开，将自动重连')
    }

    // 注册所有事件处理器
    es.addEventListener('log', (e) => {
      try {
        const data = JSON.parse(e.data)
        console.log('[SSE] log event:', data.source, data.message) // DEBUG
        addLog({ source: data.source, message: data.message })
        // 不再从日志文本猜测 Agent 状态（改用 stage 事件）
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
        console.log('[SSE] stage event:', data) // DEBUG
        const stageMap: Record<string, string> = {
          '世界观构建': 'world_building',
          '大纲生成': 'outline_generation',
          '章节生成': 'chapter_generation',
          '质量评估': 'quality_evaluation',
          '回流修订': 'revision',
          '多平台适配': 'adaptation',
        }
        const agentName = data.stage
        if (data.status === 'started') {
          useStore.setState({ isRunning: true, currentStage: (stageMap[agentName] || 'idle') as any })
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
        console.log('[SSE] outline_review_ready:', data.outline_meta?.total_chapters, '章')
        setPendingOutline(data)
      } catch (err) { console.warn('[SSE] outline_review_ready error:', err) }
    })

    es.addEventListener('chapter_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.chapter_index !== undefined) {
          addChapter(data)
          // 更新章节生成 Agent 进度
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
      } catch { /* ignore */ }
    })

    es.addEventListener('world_view_review_ready', (e) => {
      try {
        const data = JSON.parse(e.data)
        console.log('[SSE] world_view_review_ready:', data.title) // DEBUG
        setPendingWorldView(data)
      } catch (err) { console.warn('[SSE] world_view_review_ready error:', err) }
    })

    es.addEventListener('pipeline_finished', (e) => {
      try {
        const data = JSON.parse(e.data)
        // 区分正常完成 / 错误 / 暂停
        if (data.error) {
          useStore.setState({ error: data.error, isRunning: false })
          addLog({ source: 'Pipeline', message: `错误: ${data.error}` })
        } else if (data.paused) {
          useStore.setState({ isRunning: false, currentStage: 'idle' })
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
        useStore.setState({ error: data.error, isRunning: false })
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
    es.addEventListener('evaluation_ready', (e) => {
      try {
        setAgentStatus('质量评估', 'running')
      } catch (err) { console.warn('[SSE] evaluation_ready error:', err) }
    })

    es.addEventListener('revision_ready', (e) => {
      try {
        setAgentStatus('回流修订', 'running')
      } catch (err) { console.warn('[SSE] revision_ready error:', err) }
    })

    es.addEventListener('adaptation_ready', (e) => {
      try {
        setAgentStatus('多平台适配', 'running')
      } catch (err) { console.warn('[SSE] adaptation_ready error:', err) }
    })

    return () => {
      es.close()
      esRef.current = null
    }
  }, [])
}
