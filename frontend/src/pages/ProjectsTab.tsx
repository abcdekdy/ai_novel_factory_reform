/**
 * 项目库页面 — 项目列表 + 恢复 / 续写操作
 */
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from '../stores/useStore'
import { api } from '../api/client'
import {
  FolderOpen,
  RefreshCw,
  Play,
  PenTool,
  PlusCircle,
  BookOpen,
  Clock,
  Star,
  AlertCircle,
  Loader2,
  X,
  Minus,
  Check,
  Trash2,
} from 'lucide-react'
import type { ProjectSummary, WorldView, Outline, ChapterMeta } from '../types'

const CARD_STAGGER = {
  initial: { opacity: 0, y: 16 },
  animate: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.05, duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] },
  }),
}

export default function ProjectsTab() {
  const setCurrentProject = useStore((s) => s.setCurrentProject)
  const setWorldView = useStore((s) => s.setWorldView)
  const setOutline = useStore((s) => s.setOutline)
  const setChapters = useStore((s) => s.setChapters)
  const setActiveTab = useStore((s) => s.setActiveTab)
  const resetPipelineState = useStore((s) => s.resetPipelineState)

  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 续写对话框
  const [continuationTarget, setContinuationTarget] = useState<ProjectSummary | null>(null)
  const [guidance, setGuidance] = useState('')
  const [batchCount, setBatchCount] = useState(5)
  const [submitting, setSubmitting] = useState(false)

  // 恢复中的项目名
  const [resumingName, setResumingName] = useState<string | null>(null)

  // 待删除的项目
  const [deletingProject, setDeletingProject] = useState<ProjectSummary | null>(null)
  const [deleting, setDeleting] = useState(false)

  // 加载项目列表
  const loadProjects = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { projects: list } = await api.listProjects()
      setProjects(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载项目列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // 每次切换到这个 tab 时重新加载
  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  // 监听 SSE 的流水线完成事件，自动刷新
  useEffect(() => {
    const handler = () => {
      // 流水线完成后延迟刷新项目列表
      setTimeout(loadProjects, 2000)
    }
    window.addEventListener('pipeline_finished', handler)
    return () => window.removeEventListener('pipeline_finished', handler)
  }, [loadProjects])

  // 打开项目 — 加载数据并跳转到预览
  const handleOpen = async (project: ProjectSummary) => {
    setError(null)
    try {
      const name = project.name
      const [wv, oc, ch] = await Promise.all([
        api.getWorldView(name) as Promise<WorldView>,
        api.getOutline(name) as Promise<Outline>,
        api.getChapters(name) as unknown as ChapterMeta[],
      ])
      setCurrentProject(project)
      setWorldView(wv)
      setOutline(oc)
      setChapters(Array.isArray(ch) ? ch : [])
      setActiveTab(2) // 跳转到预览 tab
    } catch (e) {
      setError(`打开项目 "${project.title || project.name}" 失败: ${e instanceof Error ? e.message : '未知错误'}`)
    }
  }

  // 恢复项目流水线
  const handleResume = async (project: ProjectSummary) => {
    setResumingName(project.name)
    setError(null)
    resetPipelineState() // 清除上一项目的状态
    try {
      // 先检查流水线是否已在运行
      const status = await api.pipelineStatus()
      if (status.is_running) {
        const confirmed = window.confirm('流水线已在运行中，是否停止当前流水线并恢复新的项目？')
        if (!confirmed) {
          setResumingName(null)
          return
        }
        await api.stopPipeline()
      }

      await api.resumePipeline({ project_dir: project.path })
      // 恢复成功后跳转到工作台
      setActiveTab(1)
    } catch (e) {
      setError(`恢复项目失败: ${e instanceof Error ? e.message : '未知错误'}`)
    } finally {
      setResumingName(null)
    }
  }

  // 删除项目
  const handleDelete = async (project: ProjectSummary) => {
    setDeleting(true)
    setError(null)
    try {
      await api.deleteProject(project.name)
      setDeletingProject(null)
      // 从列表中移除
      setProjects((prev) => prev.filter((p) => p.path !== project.path))
    } catch (e) {
      setError(`删除项目失败: ${e instanceof Error ? e.message : '未知错误'}`)
    } finally {
      setDeleting(false)
    }
  }

  // 提交续写
  const handleConfirmContinuation = async () => {
    if (!continuationTarget) return
    if (!guidance.trim()) {
      setError('请输入续写指引')
      return
    }
    setSubmitting(true)
    setError(null)
    resetPipelineState() // 清除上一项目的状态
    try {
      // 先检查流水线是否已在运行
      const status = await api.pipelineStatus()
      if (status.is_running) {
        const confirmed = window.confirm('流水线已在运行中，是否停止当前流水线并启动续写？')
        if (!confirmed) {
          setSubmitting(false)
          return
        }
        await api.stopPipeline()
      }

      await api.continuePipeline({
        project_dir: continuationTarget.path,
        guidance: guidance.trim(),
        batch_chapter_count: batchCount,
      })
      setContinuationTarget(null)
      setGuidance('')
      setBatchCount(5)
      // 跳转到工作台
      setActiveTab(1)
    } catch (e) {
      setError(`启动续写失败: ${e instanceof Error ? e.message : '未知错误'}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="h-full flex flex-col px-8 py-6 overflow-hidden">
      {/* 顶部 */}
      <header className="flex items-center justify-between mb-6 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-apple bg-apple-blue-dim flex items-center justify-center">
            <FolderOpen size={20} className="text-apple-blue" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-apple-text">项目库</h1>
            <p className="text-xs text-apple-text-muted">共 {projects.length} 个项目</p>
          </div>
        </div>

        <button
          onClick={loadProjects}
          disabled={loading}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-apple-sm bg-black/5
            text-apple-text text-sm font-medium hover:bg-black/10
            disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </header>

      {/* 错误提示 */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-4 py-3 rounded-apple bg-apple-error/10 text-apple-error text-sm shrink-0"
          >
            <AlertCircle size={16} />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-apple-error/60 hover:text-apple-error ml-2">
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 项目网格 */}
      <div className="flex-1 overflow-y-auto pr-1">
        {loading && projects.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <Loader2 size={24} className="animate-spin text-apple-text-muted" />
          </div>
        ) : projects.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <div className="w-16 h-16 rounded-apple-xl bg-apple-blue-dim flex items-center justify-center mb-5">
              <FolderOpen size={28} className="text-apple-blue" />
            </div>
            <h3 className="text-lg font-semibold text-apple-text mb-2">还没有项目</h3>
            <p className="text-sm text-apple-text-secondary max-w-xs">
              前往「创作」页面输入灵感，开始生成你的第一部小说。
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map((project, idx) => (
              <ProjectCard
                key={project.path}
                project={project}
                index={idx}
                resumingName={resumingName}
                onOpen={() => handleOpen(project)}
                onResume={() => handleResume(project)}
                onContinue={() => setContinuationTarget(project)}
                onDelete={() => setDeletingProject(project)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 删除确认对话框 */}
      <AnimatePresence>
        {deletingProject && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
            onClick={() => !deleting && setDeletingProject(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 12 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-heavy w-full max-w-sm rounded-apple-xl p-6 shadow-apple-lg"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-apple bg-apple-error/10 flex items-center justify-center">
                  <Trash2 size={20} className="text-apple-error" />
                </div>
                <h2 className="text-lg font-bold text-apple-text">删除项目</h2>
              </div>
              <p className="text-sm text-apple-text-secondary mb-6">
                确定要删除「<span className="font-medium text-apple-text">{deletingProject.title || deletingProject.name}</span>」吗？此操作不可恢复。
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setDeletingProject(null)}
                  disabled={deleting}
                  className="flex-1 py-2.5 rounded-apple-sm bg-black/5 text-apple-text text-sm font-medium hover:bg-black/10 disabled:opacity-40 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={() => handleDelete(deletingProject)}
                  disabled={deleting}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-apple-sm bg-apple-error text-white text-sm font-medium hover:bg-apple-error/90 disabled:opacity-40 transition-colors"
                >
                  {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  确认删除
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 续写对话框 */}
      <AnimatePresence>
        {continuationTarget && (
          <ContinuationModal
            projectName={continuationTarget.title || continuationTarget.name}
            guidance={guidance}
            batchCount={batchCount}
            submitting={submitting}
            onGuidanceChange={setGuidance}
            onBatchCountChange={setBatchCount}
            onConfirm={handleConfirmContinuation}
            onCancel={() => {
              setContinuationTarget(null)
              setGuidance('')
              setBatchCount(5)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

/* ===== 项目卡片 ===== */
function ProjectCard({
  project,
  index,
  resumingName,
  onOpen,
  onResume,
  onContinue,
  onDelete,
}: {
  project: ProjectSummary
  index: number
  resumingName: string | null
  onOpen: () => void
  onResume: () => void
  onContinue: () => void
  onDelete: () => void
}) {
  const status = project.status || 'generating'
  const isResuming = resumingName === project.name

  const statusMap: Record<string, { label: string; color: string }> = {
    generating: { label: '生成中', color: 'bg-apple-blue/10 text-apple-blue' },
    completed: { label: '已完成', color: 'bg-apple-success/10 text-apple-success' },
    paused: { label: '已暂停', color: 'bg-apple-warning/10 text-apple-warning' },
  }
  const statusConfig = statusMap[status] || { label: '生成中', color: 'bg-apple-blue/10 text-apple-blue' }

  return (
    <motion.div
      custom={index}
      variants={CARD_STAGGER}
      initial="initial"
      animate="animate"
      className="glass-card rounded-apple-lg p-5 flex flex-col"
    >
      {/* 头部 */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-apple-text text-sm truncate">
            {project.title || project.name}
          </h3>
          <p className="text-xs text-apple-text-muted mt-0.5 truncate">{project.name}</p>
        </div>
        <span className={`shrink-0 ml-2 px-2 py-0.5 rounded-apple-full text-[11px] font-medium ${statusConfig.color}`}>
          {statusConfig.label}
        </span>
      </div>

      {/* 统计信息 */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="text-center p-2 rounded-apple-sm bg-black/[0.03]">
          <BookOpen size={13} className="mx-auto text-apple-text-muted mb-1" />
          <div className="text-xs font-medium text-apple-text">
            {project.chapter_count ?? 0}
          </div>
          <div className="text-[10px] text-apple-text-muted">章节</div>
        </div>
        <div className="text-center p-2 rounded-apple-sm bg-black/[0.03]">
          <Star size={13} className="mx-auto text-apple-text-muted mb-1" />
          <div className="text-xs font-medium text-apple-text">
            {project.avg_quality_score != null ? project.avg_quality_score.toFixed(1) : '—'}
          </div>
          <div className="text-[10px] text-apple-text-muted">评分</div>
        </div>
        <div className="text-center p-2 rounded-apple-sm bg-black/[0.03]">
          <Clock size={13} className="mx-auto text-apple-text-muted mb-1" />
          <div className="text-xs font-medium text-apple-text">
            {project.completed_at ? formatDate(project.completed_at) : '—'}
          </div>
          <div className="text-[10px] text-apple-text-muted">完成</div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex items-center gap-2 mt-auto">
        <button
          onClick={onOpen}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-apple-sm
            bg-apple-blue text-white text-xs font-medium hover:bg-apple-blue-hover
            shadow-apple transition-colors"
        >
          <BookOpen size={13} />
          打开
        </button>
        <button
          onClick={onResume}
          disabled={isResuming}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-apple-sm
            bg-black/5 text-apple-text text-xs font-medium hover:bg-black/10
            disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isResuming ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          恢复
        </button>
        <button
          onClick={onContinue}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-apple-sm
            bg-apple-success/10 text-apple-success text-xs font-medium
            hover:bg-apple-success/20 transition-colors"
        >
          <PenTool size={13} />
          续写
        </button>
        <button
          onClick={onDelete}
          className="flex items-center justify-center w-8 py-2 rounded-apple-sm
            text-apple-text-muted hover:text-apple-error hover:bg-apple-error/10
            transition-colors"
          title="删除项目"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </motion.div>
  )
}

/* ===== 续写对话框 ===== */
function ContinuationModal({
  projectName,
  guidance,
  batchCount,
  submitting,
  onGuidanceChange,
  onBatchCountChange,
  onConfirm,
  onCancel,
}: {
  projectName: string
  guidance: string
  batchCount: number
  submitting: boolean
  onGuidanceChange: (v: string) => void
  onBatchCountChange: (v: number) => void
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
      onClick={onCancel}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 12 }}
        transition={{ type: 'spring', stiffness: 400, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
        className="glass-heavy w-full max-w-md rounded-apple-xl p-6 shadow-apple-lg"
      >
        {/* 标题 */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <PlusCircle size={20} className="text-apple-blue" />
            <h2 className="text-lg font-bold text-apple-text">续写项目</h2>
          </div>
          <button
            onClick={onCancel}
            className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-black/5 text-apple-text-muted transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <p className="text-sm text-apple-text-secondary mb-5">
          为「<span className="font-medium text-apple-text">{projectName}</span>」生成新的章节批次。
        </p>

        {/* 续写指引输入 */}
        <div className="mb-4">
          <label className="block text-xs font-medium text-apple-text mb-1.5">
            续写指引
          </label>
          <textarea
            value={guidance}
            onChange={(e) => onGuidanceChange(e.target.value)}
            placeholder="描述接下来的故事走向、关键事件或角色发展..."
            rows={4}
            className="w-full px-3.5 py-2.5 rounded-apple border border-black/10 bg-white/80
              text-sm text-apple-text placeholder:text-apple-text-muted
              focus:outline-none focus:border-apple-blue focus:ring-2 focus:ring-apple-blue/20
              resize-none transition-all"
          />
        </div>

        {/* 章节数步进器 */}
        <div className="mb-6">
          <label className="block text-xs font-medium text-apple-text mb-1.5">
            批次章节数
          </label>
          <div className="flex items-center gap-3">
            <button
              onClick={() => onBatchCountChange(Math.max(1, batchCount - 1))}
              className="w-9 h-9 rounded-apple flex items-center justify-center
                bg-black/5 hover:bg-black/10 text-apple-text transition-colors"
            >
              <Minus size={14} />
            </button>
            <div className="w-16 text-center text-lg font-bold text-apple-text tabular-nums">
              {batchCount}
            </div>
            <button
              onClick={() => onBatchCountChange(Math.min(20, batchCount + 1))}
              className="w-9 h-9 rounded-apple flex items-center justify-center
                bg-black/5 hover:bg-black/10 text-apple-text transition-colors"
            >
              <PlusCircle size={14} />
            </button>
            <span className="text-xs text-apple-text-muted">章（1-20）</span>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-3">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="flex-1 py-2.5 rounded-apple-sm bg-black/5 text-apple-text text-sm font-medium
              hover:bg-black/10 disabled:opacity-40 transition-colors"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={submitting || !guidance.trim()}
            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-apple-sm
              bg-apple-blue text-white text-sm font-medium hover:bg-apple-blue-hover
              shadow-apple disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Check size={14} />
            )}
            确认续写
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

/* ===== 工具函数 ===== */
function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    const month = d.getMonth() + 1
    const day = d.getDate()
    return `${month}/${day}`
  } catch {
    return dateStr
  }
}
