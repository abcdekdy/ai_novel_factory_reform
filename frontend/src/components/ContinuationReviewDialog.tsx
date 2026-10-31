/**
 * 续写大纲审阅对话框 — 展示并编辑本批续写大纲，确认后开始生成
 */
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { X, FileText, ShieldCheck, Save, Sparkles } from 'lucide-react'
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

export default function ContinuationReviewDialog({ outline, onClose, onConfirmed }: Props) {
  const [chapters, setChapters] = useState<OutlineChapter[]>(outline.chapters ?? [])
  const consistencyRules = outline.consistency_rules ?? []
  const [saving, setSaving] = useState(false)

  const meta = outline.outline_meta ?? {}
  const rangeText = meta.chapter_start
    ? `第 ${meta.chapter_start}–${meta.chapter_end ?? meta.chapter_start} 章`
    : `共 ${chapters.length} 章`

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

  const handleConfirm = async () => {
    setSaving(true)
    try {
      await api.confirmContinuation({
        // 必须带上 outline_meta：章节范围、批次号都在里面，丢了后端会 KeyError
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
        className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-apple-xl glass-heavy shadow-apple-lg"
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-black/5 bg-white/85 px-6 py-4 backdrop-blur">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-apple-blue" />
            <h2 className="text-lg font-semibold text-apple-text">审阅续写大纲</h2>
            <span className="text-xs text-apple-text-muted">{rangeText}</span>
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
          {outline.batch_guidance ? (
            <div className="rounded-apple border border-apple-blue/20 bg-apple-blue/5 px-4 py-3 text-sm text-apple-text-secondary">
              <span className="font-medium text-apple-text">续写指引：</span>
              {String(outline.batch_guidance)}
            </div>
          ) : null}

          <div>
            <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-apple-text">
              <FileText size={15} className="text-apple-blue" />
              新批次章节 <span className="text-xs font-normal text-apple-text-muted">{chapters.length} 章</span>
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
                    placeholder="情节详情"
                    rows={3}
                    onChange={(e) => updateChapter(idx, 'plot_detail', e.target.value)}
                    className={`${INPUT_CLASS} resize-none leading-relaxed`}
                  />
                </div>
              ))}
              {chapters.length === 0 && (
                <p className="text-sm text-apple-text-muted">暂无章节</p>
              )}
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-apple-text">
              <ShieldCheck size={15} className="text-apple-blue" />
              一致性规则（含沿用的旧规则）
            </div>
            {consistencyRules.length > 0 ? (
              <ul className="space-y-1.5 rounded-apple border border-black/5 bg-black/[0.02] px-4 py-3">
                {consistencyRules.map((rule, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-apple-text-secondary">
                    <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-apple-blue/60" />
                    {rule}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-apple-text-muted">暂无一致性规则</p>
            )}
          </div>
        </div>

        {/* 底部 */}
        <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-black/5 bg-white/85 px-6 py-4 backdrop-blur">
          <button
            onClick={onClose}
            className="rounded-apple-sm border border-black/10 bg-white/70 px-4 py-2 text-sm font-medium text-apple-text-secondary transition-colors hover:bg-white"
          >
            稍后审阅
          </button>
          <button
            onClick={handleConfirm}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-apple-sm bg-apple-blue px-4 py-2 text-sm font-medium text-white shadow-apple transition-colors hover:bg-apple-blue-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Save className="h-4 w-4" />
            {saving ? '保存中…' : '确认并开始生成'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
