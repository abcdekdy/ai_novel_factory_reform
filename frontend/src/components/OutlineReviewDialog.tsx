/**
 * 大纲审阅对话框 — 全屏 Modal 覆盖层，展示并编辑详细大纲
 */

import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, FileText, ShieldCheck, Save, Sparkles, ListOrdered } from 'lucide-react'
import { api } from '../api/client'
import type { Outline, OutlineChapter } from '../types'

interface Props {
  outline: Outline
  onClose: () => void
}

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
}

const cardVariants = {
  hidden: { opacity: 0, scale: 0.92, y: 20 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { type: 'spring', damping: 25, stiffness: 300 } },
}

export default function OutlineReviewDialog({ outline, onClose }: Props) {
  const [chapters, setChapters] = useState<OutlineChapter[]>(outline.chapters ?? [])
  const consistencyRules = outline.consistency_rules ?? []
  const characterArcs = outline.character_arcs ?? {}
  const [saving, setSaving] = useState(false)

  // ESC 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const updateChapter = (idx: number, field: keyof OutlineChapter, value: string) => {
    setChapters(prev => prev.map((ch, i) => (i === idx ? { ...ch, [field]: value } : ch)))
  }

  const handleConfirm = async () => {
    setSaving(true)
    try {
      await api.confirmOutline({
        outline: {
          ...outline,
          chapters,
          consistency_rules: consistencyRules,
        },
      })
      onClose()
    } catch (err) {
      console.error('确认大纲失败:', err)
      alert(err instanceof Error ? err.message : '确认失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
        variants={overlayVariants}
        initial="hidden"
        animate="visible"
        exit="hidden"
        onClick={onClose}
      >
        <motion.div
          className="relative w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl bg-white shadow-2xl"
          variants={cardVariants}
          onClick={e => e.stopPropagation()}
        >
          {/* 头部 */}
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-200 bg-white/90 px-6 py-4 backdrop-blur supports-[backdrop-filter]:bg-white/80">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-blue-500" />
              <h2 className="text-lg font-semibold text-gray-900">审阅详细大纲</h2>
            </div>
            <button
              onClick={onClose}
              className="rounded-full p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* 内容 */}
          <div className="space-y-6 px-6 py-5">
            {/* 章节大纲 */}
            <div>
              <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                <ListOrdered className="h-4 w-4 text-gray-400" />
                章节大纲 ({chapters.length} 章)
              </div>
              <div className="space-y-3">
                {chapters.map((ch, idx) => (
                  <div key={idx} className="rounded-xl border border-gray-100 bg-gray-50/30 p-3">
                    <div className="mb-1 flex items-center gap-2">
                      <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-blue-100 text-xs font-medium text-blue-600">
                        {ch.chapter_index ?? idx + 1}
                      </span>
                      <input
                        type="text"
                        value={ch.title ?? ''}
                        onChange={e => updateChapter(idx, 'title', e.target.value)}
                        placeholder="章节标题"
                        className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-900 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                      />
                    </div>
                    <textarea
                      value={ch.plot_detail ?? ''}
                      onChange={e => updateChapter(idx, 'plot_detail', e.target.value)}
                      placeholder="情节详情（300-500字）"
                      rows={4}
                      className="mt-2 w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    />
                  </div>
                ))}
                {chapters.length === 0 && (
                  <p className="text-sm text-gray-400">暂无章节大纲</p>
                )}
              </div>
            </div>

            {/* 一致性规则 */}
            {consistencyRules.length > 0 && (
              <div>
                <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                  <ShieldCheck className="h-4 w-4 text-gray-400" />
                  一致性规则
                </div>
                <ul className="space-y-1.5 rounded-xl border border-gray-100 bg-gray-50/30 px-4 py-3">
                  {consistencyRules.map((rule, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-400" />
                      {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 角色弧线 */}
            {Object.keys(characterArcs).length > 0 && (
              <div>
                <div className="mb-3 flex items-center gap-1.5 text-sm font-medium text-gray-700">
                  <FileText className="h-4 w-4 text-gray-400" />
                  角色弧线
                </div>
                <div className="space-y-2 rounded-xl border border-gray-100 bg-gray-50/30 px-4 py-3">
                  {Object.entries(characterArcs).map(([name, arc]) => {
                    const arcObj = arc as { arc_type?: string; trajectory?: Array<Record<string, unknown>> }
                    return (
                      <div key={name} className="text-sm">
                        <span className="font-medium text-gray-800">{name}</span>
                        {arcObj.arc_type && (
                          <span className="ml-2 text-gray-400">({arcObj.arc_type})</span>
                        )}
                        {Array.isArray(arcObj.trajectory) && arcObj.trajectory.length > 0 && (
                          <span className="ml-2 text-gray-500">
                            → {arcObj.trajectory.map(t => t.state).filter(Boolean).join(' → ')}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* 底部按钮 */}
          <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t border-gray-200 bg-white/90 px-6 py-4 backdrop-blur supports-[backdrop-filter]:bg-white/80">
            <button
              onClick={onClose}
              className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 active:scale-[0.98]"
            >
              取消
            </button>
            <button
              onClick={handleConfirm}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:bg-blue-600 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Save className="h-4 w-4" />
              {saving ? '保存中…' : '确认并开始生成'}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
