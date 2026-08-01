/**
 * 世界观审阅对话框 — 全屏 Modal 覆盖层，展示并编辑世界观各字段
 */

import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, BookOpen, Users, Wand2, ListOrdered, Save, RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import type { WorldView, Character, OutlineChapter } from '../types'

interface Props {
  worldView: WorldView
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

export default function WorldViewReviewDialog({ worldView, onClose }: Props) {
  // 从 LLM 输出提取字段（兼容多种字段名）
  const extractSetting = (): string => {
    if (worldView.setting) return worldView.setting
    const summary = (worldView as Record<string, unknown>).summary
    if (typeof summary === 'string') return summary
    return ''
  }
  const extractMagicSystem = (): string => {
    if (worldView.magic_system) return worldView.magic_system
    const wv = (worldView as Record<string, unknown>).world_view
    if (wv && typeof wv === 'object') {
      const rules = (wv as Record<string, unknown>).rules
      if (typeof rules === 'string') return rules
    }
    return ''
  }
  const extractCharacters = (): Character[] => {
    const chars = worldView.characters ?? []
    return chars.map((c) => {
      const raw = c as Record<string, unknown>
      const desc = c.description ?? raw.desc ?? ''
      return {
        name: c.name ?? '',
        role: c.role ?? '',
        description: typeof desc === 'string' ? desc : '',
      }
    })
  }
  const extractChapterOutline = (): OutlineChapter[] => {
    const outline = worldView.chapter_outline ?? []
    return outline.map((ch) => {
      const raw = ch as Record<string, unknown>
      const detail = ch.plot_detail ?? raw.summary ?? ''
      return {
        chapter_index: ch.chapter_index,
        title: ch.title ?? '',
        plot_detail: typeof detail === 'string' ? detail : '',
      }
    })
  }

  const [title, setTitle] = useState(worldView.title ?? '')
  const [genre, setGenre] = useState(worldView.genre ?? '')
  const [setting, setSetting] = useState(extractSetting())
  const [characters, setCharacters] = useState<Character[]>(extractCharacters())
  const [magicSystem, setMagicSystem] = useState(extractMagicSystem())
  const [chapterOutline, setChapterOutline] = useState<OutlineChapter[]>(extractChapterOutline())
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

  // ESC 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const updateCharacter = (idx: number, field: keyof Character, value: string) => {
    setCharacters(prev => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)))
  }

  const updateOutlineChapter = (idx: number, field: keyof OutlineChapter, value: string) => {
    setChapterOutline(prev => prev.map((ch, i) => (i === idx ? { ...ch, [field]: value } : ch)))
  }

  const handleRegenerate = async () => {
    setRegenerating(true)
    try {
      await api.retryWorldView()
      onClose()
    } catch (err) {
      console.error('重新生成世界观失败:', err)
      alert(err instanceof Error ? err.message : '重新生成失败')
      setRegenerating(false)
    }
  }

  const handleConfirm = async () => {
    setSaving(true)
    try {
      // 把编辑后的扁平字段映射回后端 OutlineBuilderAgent 需要的嵌套结构
      const reviewedWorldView: Record<string, unknown> = {
        title,
        genre,
        summary: setting,  // setting 编辑后写回 summary
        world_view: {
          rules: magicSystem,  // 力量体系写回 world_view.rules
          era: '',
          location: '',
          factions: [],
          history: '',
        },
        characters: characters.map((c) => ({
          name: c.name,
          role: c.role,
          desc: c.description,  // description → desc
          ability: '',
        })),
        chapter_outline: chapterOutline.map((ch) => ({
          chapter_index: ch.chapter_index,
          chapter: ch.chapter_index,
          title: ch.title,
          summary: ch.plot_detail,  // plot_detail → summary
        })),
      }
      // 保留原始数据中未被编辑的字段（如 story_framework）
      const original = worldView as Record<string, unknown>
      if (original.story_framework) {
        reviewedWorldView.story_framework = original.story_framework
      }
      await api.confirmWorldView({ world_view: reviewedWorldView })
      onClose()
    } catch (err) {
      console.error('确认世界观失败:', err)
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
          className="relative w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-2xl bg-white shadow-2xl"
          variants={cardVariants}
          onClick={e => e.stopPropagation()}
        >
          {/* 头部 */}
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-200 bg-white/90 px-6 py-4 backdrop-blur supports-[backdrop-filter]:bg-white/80">
            <div className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-blue-500" />
              <h2 className="text-lg font-semibold text-gray-900">审阅世界观</h2>
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
            {/* 标题 */}
            <FieldGroup label="作品标题" icon={<BookOpen className="h-4 w-4" />}>
              <input
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2 text-sm text-gray-900 outline-none transition-colors focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-500/20"
              />
            </FieldGroup>

            {/* 题材 */}
            <FieldGroup label="题材" icon={<Wand2 className="h-4 w-4" />}>
              <input
                type="text"
                value={genre}
                onChange={e => setGenre(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2 text-sm text-gray-900 outline-none transition-colors focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-500/20"
              />
            </FieldGroup>

            {/* 设定 */}
            <FieldGroup label="世界观设定" icon={<Wand2 className="h-4 w-4" />}>
              <textarea
                value={setting}
                onChange={e => setSetting(e.target.value)}
                rows={4}
                className="w-full resize-none rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2 text-sm text-gray-900 outline-none transition-colors focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-500/20"
              />
            </FieldGroup>

            {/* 角色 */}
            <FieldGroup label="角色" icon={<Users className="h-4 w-4" />}>
              <div className="space-y-3">
                {characters.map((char, idx) => (
                  <div key={idx} className="rounded-xl border border-gray-100 bg-gray-50/30 p-3">
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="text"
                        value={char.name ?? ''}
                        onChange={e => updateCharacter(idx, 'name', e.target.value)}
                        placeholder="角色名"
                        className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                      />
                      <input
                        type="text"
                        value={char.role ?? ''}
                        onChange={e => updateCharacter(idx, 'role', e.target.value)}
                        placeholder="身份/角色"
                        className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                      />
                    </div>
                    <textarea
                      value={char.description ?? ''}
                      onChange={e => updateCharacter(idx, 'description', e.target.value)}
                      placeholder="角色描述"
                      rows={2}
                      className="mt-2 w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    />
                  </div>
                ))}
                {characters.length === 0 && (
                  <p className="text-sm text-gray-400">暂无角色</p>
                )}
              </div>
            </FieldGroup>

            {/* 魔法/力量体系 */}
            <FieldGroup label="力量体系" icon={<Wand2 className="h-4 w-4" />}>
              <textarea
                value={magicSystem}
                onChange={e => setMagicSystem(e.target.value)}
                rows={3}
                className="w-full resize-none rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2 text-sm text-gray-900 outline-none transition-colors focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-500/20"
              />
            </FieldGroup>

            {/* 章节大纲 */}
            <FieldGroup label="章节大纲" icon={<ListOrdered className="h-4 w-4" />}>
              <div className="space-y-3">
                {chapterOutline.map((ch, idx) => (
                  <div key={idx} className="rounded-xl border border-gray-100 bg-gray-50/30 p-3">
                    <input
                      type="text"
                      value={ch.title ?? ''}
                      onChange={e => updateOutlineChapter(idx, 'title', e.target.value)}
                      placeholder="章节标题"
                      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    />
                    <textarea
                      value={ch.plot_detail ?? ''}
                      onChange={e => updateOutlineChapter(idx, 'plot_detail', e.target.value)}
                      placeholder="情节详情"
                      rows={2}
                      className="mt-2 w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    />
                  </div>
                ))}
                {chapterOutline.length === 0 && (
                  <p className="text-sm text-gray-400">暂无章节大纲</p>
                )}
              </div>
            </FieldGroup>
          </div>

          {/* 底部按钮 */}
          <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-gray-200 bg-white/90 px-6 py-4 backdrop-blur supports-[backdrop-filter]:bg-white/80">
            <button
              onClick={onClose}
              className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 active:scale-[0.98]"
            >
              取消
            </button>
            <div className="flex items-center gap-3">
              <button
                onClick={handleRegenerate}
                disabled={regenerating || saving}
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RefreshCw className={`h-4 w-4 ${regenerating ? 'animate-spin' : ''}`} />
                {regenerating ? '生成中…' : '重新生成'}
              </button>
              <button
                onClick={handleConfirm}
                disabled={saving || regenerating}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:bg-blue-600 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Save className="h-4 w-4" />
                {saving ? '保存中…' : '确认并继续'}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

/** 带图标的字段分组标签 */
function FieldGroup({ label, icon, children }: { label: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-gray-700">
        <span className="text-gray-400">{icon}</span>
        {label}
      </div>
      {children}
    </div>
  )
}
