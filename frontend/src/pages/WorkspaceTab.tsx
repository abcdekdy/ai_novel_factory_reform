/**
 * 工作台页面 — Agent 状态卡片 + 进度条 + 日志控制台
 */
import { useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useStore } from '../stores/useStore'
import { api } from '../api/client'
import type { AgentStatus } from '../types'
import type { LucideIcon } from 'lucide-react'
import {
  Globe,
  FileText,
  BookOpen,
  BarChart3,
  RefreshCw,
  Monitor,
  Pause,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Terminal,
  PenTool,
  X,
} from 'lucide-react'

// Agent 名称 → 图标映射
const AGENT_ICONS: Record<string, LucideIcon> = {
  '世界观构建': Globe,
  '大纲生成': FileText,
  '章节生成': BookOpen,
  '质量评估': BarChart3,
  '回流修订': RefreshCw,
  '多平台适配': Monitor,
}

// 状态配置
const STATUS_CONFIG: Record<AgentStatus, { color: string; bg: string; label: string; icon: LucideIcon }> = {
  idle: { color: 'text-apple-text-muted', bg: 'bg-black/5', label: '等待中', icon: Clock },
  waiting: { color: 'text-apple-text-muted', bg: 'bg-black/5', label: '等待中', icon: Clock },
  running: { color: 'text-apple-blue', bg: 'bg-apple-blue/10', label: '运行中', icon: Loader2 },
  success: { color: 'text-apple-success', bg: 'bg-apple-success/10', label: '已完成', icon: CheckCircle2 },
  error: { color: 'text-apple-error', bg: 'bg-apple-error/10', label: '出错', icon: AlertCircle },
}

// 动画变体
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.1 },
  },
}

const cardVariants = {
  hidden: { opacity: 0, y: 20, scale: 0.96 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] },
  },
}

// ===== Agent 卡片 =====
interface AgentCardProps {
  name: string
  displayName: string
  status: AgentStatus
  progress: number
  description: string
}

function AgentCard({ name, displayName, status, progress, description }: AgentCardProps) {
  const Icon = AGENT_ICONS[name] || Monitor
  const statusCfg = STATUS_CONFIG[status]
  const StatusIcon = statusCfg.icon

  return (
    <motion.div
      variants={cardVariants}
      className="glass-card rounded-apple-lg p-4 relative overflow-hidden group"
    >
      {/* 顶部：图标 + 名称 */}
      <div className="flex items-start gap-3 mb-3">
        <div className={`w-9 h-9 rounded-apple flex items-center justify-center shrink-0 ${statusCfg.bg}`}>
          <Icon size={18} className={statusCfg.color} />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-apple-text truncate">{displayName}</h4>
          <p className="text-xs text-apple-text-muted mt-0.5 truncate">{description}</p>
        </div>
      </div>

      {/* 底部：状态 + 进度 */}
      <div className="flex items-center justify-between">
        <div className={`flex items-center gap-1.5 ${statusCfg.color}`}>
          <StatusIcon
            size={13}
            className={status === 'running' ? 'animate-spin' : ''}
          />
          <span className="text-xs font-medium">{statusCfg.label}</span>
        </div>
        <span className="text-xs text-apple-text-muted tabular-nums">
          {Math.round(progress)}%
        </span>
      </div>

      {/* 微进度条 */}
      <div className="mt-2 h-1 rounded-full bg-black/5 overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${
            status === 'success'
              ? 'bg-apple-success'
              : status === 'error'
                ? 'bg-apple-error'
                : 'bg-apple-blue'
          }`}
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
        />
      </div>

      {/* running 脉冲指示 */}
      {status === 'running' && (
        <motion.div
          className="absolute top-3 right-3 w-2 h-2 rounded-full bg-apple-blue"
          animate={{ opacity: [1, 0.4, 1] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
    </motion.div>
  )
}

// ===== 主组件 =====
export default function WorkspaceTab() {
  const overallProgress = useStore((s) => s.overallProgress)
  const isRunning = useStore((s) => s.isRunning)
  const agents = useStore((s) => s.agents)
  const logs = useStore((s) => s.logs)
  const addLog = useStore((s) => s.addLog)
  const setError = useStore((s) => s.setError)
  const pendingWorldView = useStore((s) => s.pendingWorldView)
  const pendingOutline = useStore((s) => s.pendingOutline)
  const pendingContinuationOutline = useStore((s) => s.pendingContinuationOutline)
  const pipelineError = useStore((s) => s.pipelineError)
  const setPipelineError = useStore((s) => s.setPipelineError)

  const logEndRef = useRef<HTMLDivElement>(null)
  const latestLog = logs.length > 0 ? logs[logs.length - 1] : null

  // 自动滚动日志到底部
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // 暂停流水线
  const handlePause = useCallback(async () => {
    try {
      await api.pausePipeline()
      addLog({ source: 'Pipeline', message: '已请求暂停流水线' })
    } catch (err) {
      const msg = err instanceof Error ? err.message : '暂停失败'
      setError(msg)
      addLog({ source: 'Pipeline', message: `暂停失败: ${msg}` })
    }
  }, [addLog, setError])

  // 重试当前失败阶段
  const handleRetry = useCallback(async () => {
    try {
      setPipelineError(null)
      await api.retryPipeline()
      addLog({ source: 'Pipeline', message: '正在重试失败阶段...' })
    } catch (err) {
      const msg = err instanceof Error ? err.message : '重试失败'
      setError(msg)
      addLog({ source: 'Pipeline', message: `重试失败: ${msg}` })
    }
  }, [addLog, setError, setPipelineError])

  // 强制停止流水线
  const handleStop = useCallback(async () => {
    try {
      await api.stopPipeline()
      addLog({ source: 'Pipeline', message: '流水线已强制停止' })
    } catch (err) {
      const msg = err instanceof Error ? err.message : '停止失败'
      setError(msg)
      addLog({ source: 'Pipeline', message: `停止失败: ${msg}` })
    }
  }, [addLog, setError])

  return (
    <div className="h-full w-full flex flex-col overflow-hidden">
      {/* 顶部：标题 + 进度 */}
      <div className="shrink-0 px-8 pt-8 pb-4">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="flex items-end justify-between mb-3">
            <div>
              <h1 className="text-2xl font-semibold text-apple-text">工作台</h1>
              <p className="text-sm text-apple-text-secondary mt-1">
                实时查看各 Agent 的工作状态
              </p>
            </div>
            <div className="text-right">
              <span className="text-3xl font-semibold text-apple-text tabular-nums">
                {Math.round(overallProgress)}
              </span>
              <span className="text-lg text-apple-text-secondary">%</span>
            </div>
          </div>

          {/* 整体进度条 */}
          <div className="h-2 rounded-full bg-black/5 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-apple-blue"
              initial={{ width: 0 }}
              animate={{ width: `${overallProgress}%` }}
              transition={{ duration: 0.8, ease: [0.25, 0.46, 0.45, 0.94] }}
            />
          </div>
        </motion.div>
      </div>

      {/* Agent 卡片网格 */}
      <div className="shrink-0 px-8 pb-4">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-2 lg:grid-cols-3 gap-3"
        >
          {Object.values(agents).map((agent) => (
            <AgentCard
              key={agent.name}
              name={agent.name}
              displayName={agent.displayName}
              status={agent.status}
              progress={agent.progress}
              description={agent.description}
            />
          ))}
        </motion.div>
      </div>

      {/* 日志控制台 */}
      <div className="flex-1 mx-8 mb-4 rounded-apple-lg overflow-hidden flex flex-col min-h-0">
        {/* 控制台标题 */}
        <div className="shrink-0 flex items-center justify-between px-4 py-2.5 bg-apple-text">
          <div className="flex items-center gap-2">
            <Terminal size={13} className="text-white/70" />
            <span className="text-xs font-medium text-white/90">日志</span>
          </div>
          <span className="text-xs text-white/40 tabular-nums">{logs.length} 条</span>
        </div>

        {/* 日志内容 */}
        <div className="flex-1 overflow-y-auto bg-[#1D1D1F] px-4 py-3 min-h-0 font-mono text-xs leading-relaxed">
          {logs.length === 0 ? (
            <p className="text-white/30">等待日志...</p>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="flex gap-3 py-0.5">
                <span className="text-white/30 shrink-0 tabular-nums">
                  {log.timestamp
                    ? new Date(log.timestamp).toLocaleTimeString('zh-CN', { hour12: false })
                    : '--:--:--'}
                </span>
                <span className="text-apple-blue shrink-0">[{log.source}]</span>
                <span className="text-white/80 break-all">{log.message}</span>
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* 底部操作区 */}
      <div className="shrink-0 px-8 pb-6">
        {isRunning ? (
          pendingWorldView ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="w-full py-3 rounded-apple-lg border border-apple-blue/40
                text-apple-blue font-medium bg-apple-blue/5
                flex items-center justify-center gap-2"
            >
              <motion.div
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                <BookOpen size={16} />
              </motion.div>
              <span>等待审阅世界观...</span>
            </motion.div>
          ) : pendingOutline ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="w-full py-3 rounded-apple-lg border border-apple-success/40
                text-apple-success font-medium bg-apple-success/5
                flex items-center justify-center gap-2"
            >
              <motion.div
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                <PenTool size={16} />
              </motion.div>
              <span>等待审阅详细大纲...</span>
            </motion.div>
          ) : pendingContinuationOutline ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="w-full py-3 rounded-apple-lg border border-apple-success/40
                text-apple-success font-medium bg-apple-success/5
                flex items-center justify-center gap-2"
            >
              <motion.div
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                <PenTool size={16} />
              </motion.div>
              <span>等待审阅续写大纲...</span>
            </motion.div>
          ) : (
            <div className="space-y-2">
              {/* 显示最新日志状态 */}
              {latestLog && latestLog.message.includes('等待模型响应') && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2 px-3 py-2 rounded-apple-sm bg-apple-blue/5 text-apple-blue text-xs"
                >
                  <Loader2 size={12} className="animate-spin" />
                  <span>正在等待 LLM 响应... (可能需要几分钟)</span>
                </motion.div>
              )}
              <div className="flex gap-2">
              <motion.button
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                onClick={handlePause}
                className="flex-1 py-3 rounded-apple-lg border border-apple-warning/40
                  text-apple-warning font-medium
                  hover:bg-apple-warning/10 transition-colors
                  flex items-center justify-center gap-2"
              >
                <Pause size={16} />
                <span>暂停并保存</span>
              </motion.button>
              <motion.button
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleStop}
                className="py-3 px-4 rounded-apple-lg border border-apple-error/40
                  text-apple-error font-medium
                  hover:bg-apple-error/10 transition-colors
                  flex items-center justify-center gap-2"
              >
                <X size={16} />
                <span>停止</span>
              </motion.button>
              </div>
            </div>
          )
        ) : pipelineError ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-2"
          >
            <div className="w-full py-3 rounded-apple-lg border border-apple-error/40
              text-apple-error bg-apple-error/5
              flex items-center justify-center gap-2 text-sm"
            >
              <AlertCircle size={16} />
              <span>
                {pipelineError.stage ? `[${pipelineError.stage}] ` : ''}
                {pipelineError.message}
              </span>
            </div>
            <motion.button
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleRetry}
              className="w-full py-3 rounded-apple-lg border border-apple-blue/40
                text-apple-blue font-medium
                hover:bg-apple-blue/10 transition-colors
                flex items-center justify-center gap-2"
            >
              <RefreshCw size={16} />
              <span>重试当前阶段</span>
            </motion.button>
          </motion.div>
        ) : (
          <div className="text-center text-xs text-apple-text-muted py-3">
            流水线未运行
          </div>
        )}
      </div>
    </div>
  )
}
