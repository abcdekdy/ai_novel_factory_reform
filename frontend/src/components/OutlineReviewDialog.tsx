/**
 * 大纲审阅对话框 — 展示并编辑详细大纲，确认后开始章节生成
 */
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { X, ShieldCheck, Save, Sparkles, ListOrdered, RefreshCw, Route } from 'lucide-react'
import { api } from '../api/client'
import type { Outline, OutlineChapter } from '../types'

interface Props {
  outline: Outline
  /** 收起对话框（内容保留，可从横幅重新打开） */
  onClose: () => void
  /** 已确认并提交，清空待审阅内容 */
  onConfirmed: () => void
}

const cardVariants = {
  hidden: { opacity: 0, scale: 0.94, y: 16 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { type: 'spring', damping: 26, stiffness: 320 } },
}

const INPUT_CLASS =
  'w-full rounded-apple glass-inset px-3 py-2 text-sm text-apple-text ' +
  'focus:outline-none focus:ring-2 focus:ring-apple-blue/30'

export default function OutlineReviewDialog({ outline, onClose, onConfirmed }: Props) {
  const [chapters, setChapters] = useState<OutlineChapter[]>(outline.chapters ?? [])
  const consistencyRules = outline.consistency_rules ?? []
  const characterArcs = outline.character_arcs ?? {}
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const updateChapter = (idx: number, field: 'title' | 'plot_detail', value: string) => {
    setChapters((prev) => prev.map((ch, i) => (i === idx ? { ...ch, [field]: value } : ch)))
  }

  const handleRegenerate = async () => {
    setRegenerating(true)
    try {
      await api.retryOutline()
      onConfirmed()
    } catch (err) {
      alert(err instanceof Error ? err.message : '重新生成失败')
      setRegenerating(false)
    }
  }

  const handleConfirm = async () => {
    setSaving(true)
    try {
      await api.confirmOutline({
        // 保留 outline_meta / global_arc / character_arcs 等未编辑字段
        outline: { ...outline, chapters, consistency_rules: consistencyRules },
      })
      onConfirmed()
    } catch (err) {
      alert(err instanceof Error ? err.message : '确认失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      onClick={onClose}
    >
      <motion.div
        className="relative w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-apple-xl glass-heavy shadow-apple-lg"
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-black/5 bg-white/85 px-6 py-4 backdrop-blur">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-apple-blue" />
            <h2 className="text-lg font-semibold text-apple-text">审阅详细大纲</h2>
            <span className="text-xs text-apple-text-muted">
              {chapters.length} 章 · 确认后开始生成正文
            </span>
          </div>
          <button
            onClick={onClose}
            title="暂时收起，可从顶部横幅重新打开"
            className="rounded-full p-1.5 text-apple-text-muted transition-colors hover:bg-black/5 hover:text-apple-text"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 内容 */}
        <div className="space-y-6 px-6 py-5">
          <div>
            <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-apple-text">
              <ListOrdered size={15} className="text-apple-blue" />
              章节大纲
            </div>
            <div className="space-y-3">
              {chapters.map((ch, idx) => (
                <div key={idx} className="rounded-apple border border-black/5 bg-black/[0.02] p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-apple-blue-dim px-1.5 text-xs font-medium text-apple-blue">
                      {ch.chapter_index ?? idx + 1}
                    </span>
                    <input
                      type="text"
                      value={ch.title ?? ''}
                      placeholder="章节标题"
                      onChange={(e) => updateChapter(idx, 'title', e.target.value)}
                      className={`${INPUT_CLASS} font-medium`}
                    />
                  </div>
                  <textarea
                    value={ch.plot_detail ?? ''}
                    placeholder="情节详情（300-500字）"
                    rows={4}
                    onChange={(e) => updateChapter(idx, 'plot_detail', e.target.value)}
                    className={`${INPUT_CLASS} resize-none leading-relaxed`}
                  />
                  {ch.key_events && ch.key_events.length > 0 && (
                    <div className="mt-2 text-xs text-apple-text-muted">
                      关键事件：{ch.key_events.join('；')}
                    </div>
                  )}
                </div>
              ))}
              {chapters.length === 0 && (
                <p className="text-sm text-apple-text-muted">暂无章节大纲</p>
              )}
            </div>
          </div>

          {consistencyRules.length > 0 && (
            <div>
              <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-apple-text">
                <ShieldCheck size={15} className="text-apple-blue" />
                一致性规则 <span className="text-xs font-normal text-apple-text-muted">{consistencyRules.length} 条</span>
              </div>
              <ul className="space-y-1.5 rounded-apple border border-black/5 bg-black/[0.02] px-4 py-3">
                {consistencyRules.map((rule, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-apple-text-secondary">
                    <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-apple-blue/60" />
                    {rule}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(characterArcs).length > 0 && (
            <div>
              <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-apple-text">
                <Route size={15} className="text-apple-blue" />
                角色弧线
              </div>
              <div className="space-y-2 rounded-apple border border-black/5 bg-black/[0.02] px-4 py-3">
                {Object.entries(characterArcs).map(([name, arc]) => {
                  const arcObj = arc as { arc_type?: string; trajectory?: Array<Record<string, unknown>> }
                  return (
                    <div key={name} className="text-sm">
                      <span className="font-medium text-apple-text">{name}</span>
                      {arcObj.arc_type && (
                        <span className="ml-2 text-apple-text-muted">({arcObj.arc_type})</span>
                      )}
                      {Array.isArray(arcObj.trajectory) && arcObj.trajectory.length > 0 && (
                        <span className="ml-2 text-apple-text-secondary">
                          → {arcObj.trajectory.map((t) => t.state).filter(Boolean).join(' → ')}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* 底部 */}
        <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-black/5 bg-white/85 px-6 py-4 backdrop-blur">
          <button
            onClick={onClose}
            className="rounded-apple-sm border border-black/10 bg-white/70 px-4 py-2 text-sm font-medium text-apple-text-secondary transition-colors hover:bg-white"
          >
            稍后审阅
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={handleRegenerate}
              disabled={regenerating || saving}
              className="inline-flex items-center gap-1.5 rounded-apple-sm border border-apple-warning/40 bg-apple-warning/10 px-4 py-2 text-sm font-medium text-apple-warning transition-colors hover:bg-apple-warning/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${regenerating ? 'animate-spin' : ''}`} />
              {regenerating ? '生成中…' : '重新生成'}
            </button>
            <button
              onClick={handleConfirm}
              disabled={saving || regenerating}
              className="inline-flex items-center gap-1.5 rounded-apple-sm bg-apple-blue px-4 py-2 text-sm font-medium text-white shadow-apple transition-colors hover:bg-apple-blue-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Save className="h-4 w-4" />
              {saving ? '保存中…' : '确认并开始生成'}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
