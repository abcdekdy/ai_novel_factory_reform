/**
 * 预览页面 — 世界观 / 大纲 / 章节浏览 + 导出
 *
 * 数据来源：从 ProjectsTab 打开项目时写入 store 的 currentProject / worldView / outline / chapters。
 * 导出操作使用 currentProject.name 调用后端 API。
 */
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from '../stores/useStore'
import { api } from '../api/client'
import {
  Globe,
  ListTree,
  BookOpen,
  Download,
  FileText,
  Sparkles,
  Users,
  Wand2,
  ChevronRight,
  AlertCircle,
  X,
} from 'lucide-react'
import type { WorldView, Outline, ChapterMeta } from '../types'

type PreviewTabKey = 'world' | 'outline' | 'chapters'

const TAB_ITEMS: { key: PreviewTabKey; label: string; icon: typeof Globe }[] = [
  { key: 'world', label: '世界观', icon: Globe },
  { key: 'outline', label: '大纲', icon: ListTree },
  { key: 'chapters', label: '章节', icon: BookOpen },
]

const FADE_VARIANTS = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
}

export default function PreviewTab() {
  const currentProject = useStore((s) => s.currentProject)
  const worldView = useStore((s) => s.worldView)
  const outline = useStore((s) => s.outline)
  const chapters = useStore((s) => s.chapters)
  const setMainTab = useStore((s) => s.setActiveTab)

  const [activeTab, setActiveTab] = useState<PreviewTabKey>('world')
  const [selectedChapter, setSelectedChapter] = useState<number>(0)
  const [exporting, setExporting] = useState<'txt' | 'markdown' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const hasData = !!(worldView || outline || chapters.length > 0)

  // 确保选中索引不越界
  useEffect(() => {
    if (selectedChapter >= chapters.length) {
      setSelectedChapter(Math.max(0, chapters.length - 1))
    }
  }, [chapters.length, selectedChapter])

  // 导出处理
  const handleExport = async (format: 'txt' | 'markdown') => {
    if (!currentProject) {
      setError('请先从项目库打开一个项目')
      return
    }
    setExporting(format)
    setError(null)
    try {
      if (format === 'txt') {
        await api.exportTxt(currentProject.name)
      } else {
        await api.exportMarkdown(currentProject.name)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '导出失败')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="h-full flex flex-col px-8 py-6 overflow-hidden">
      {/* 顶部：Tab 切换 + 导出按钮 */}
      <header className="flex items-center justify-between mb-6 shrink-0">
        <div className="flex items-center gap-1 p-1 rounded-apple bg-black/5">
          {TAB_ITEMS.map((item) => {
            const Icon = item.icon
            const isActive = activeTab === item.key
            return (
              <button
                key={item.key}
                onClick={() => setActiveTab(item.key as PreviewTabKey)}
                className={`
                  relative flex items-center gap-2 px-4 py-2 rounded-apple-sm text-sm font-medium
                  transition-colors duration-200
                  ${isActive ? 'text-white' : 'text-apple-text-secondary hover:text-apple-text'}
                `}
              >
                {isActive && (
                  <motion.div
                    layoutId="preview-tab-active"
                    className="absolute inset-0 rounded-apple-sm bg-apple-blue"
                    transition={{ type: 'spring', stiffness: 500, damping: 35 }}
                  />
                )}
                <Icon size={16} className="relative z-10" />
                <span className="relative z-10">{item.label}</span>
              </button>
            )
          })}
        </div>

        {/* 导出按钮组 */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleExport('txt')}
            disabled={exporting !== null || !hasData}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-apple-sm bg-black/5
              text-apple-text text-sm font-medium hover:bg-black/10
              disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <FileText size={14} />
            导出 TXT
          </button>
          <button
            onClick={() => handleExport('markdown')}
            disabled={exporting !== null || !hasData}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-apple-sm bg-apple-blue
              text-white text-sm font-medium hover:bg-apple-blue-hover shadow-apple
              disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {exporting === 'markdown' ? (
              <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
                <Download size={14} />
              </motion.div>
            ) : (
              <Download size={14} />
            )}
            导出 Markdown
          </button>
        </div>
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
            <button onClick={() => setError(null)} className="text-apple-error/60 hover:text-apple-error">
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 内容区 */}
      <div className="flex-1 overflow-hidden relative">
        {!hasData ? (
          <EmptyState onBrowseProjects={() => setMainTab(3)} />
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              variants={FADE_VARIANTS}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
              className="h-full overflow-y-auto pr-1"
            >
              {activeTab === 'world' && worldView && <WorldViewContent data={worldView} />}
              {activeTab === 'outline' && outline && <OutlineContent data={outline} />}
              {activeTab === 'chapters' && (
                <ChaptersContent
                  chapters={chapters}
                  selectedIndex={selectedChapter}
                  onSelect={setSelectedChapter}
                />
              )}
            </motion.div>
          </AnimatePresence>
        )}
      </div>
    </div>
  )
}

/* ===== 空状态 ===== */
function EmptyState({ onBrowseProjects }: { onBrowseProjects: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      className="h-full flex flex-col items-center justify-center text-center"
    >
      <div className="w-16 h-16 rounded-apple-xl bg-apple-blue-dim flex items-center justify-center mb-5">
        <BookOpen size={28} className="text-apple-blue" />
      </div>
      <h3 className="text-lg font-semibold text-apple-text mb-2">暂无可预览的内容</h3>
      <p className="text-sm text-apple-text-secondary max-w-xs mb-5">
        从项目库打开一个项目，或开始创作新项目来查看世界观、大纲和章节内容。
      </p>
      <button
        onClick={onBrowseProjects}
        className="px-4 py-2 rounded-apple-sm bg-apple-blue text-white text-sm font-medium
          hover:bg-apple-blue-hover shadow-apple transition-colors"
      >
        浏览项目库
      </button>
    </motion.div>
  )
}

/* ===== 世界观视图 ===== */
function WorldViewContent({ data }: { data: WorldView }) {
  return (
    <div className="max-w-3xl space-y-6">
      {/* 标题区 */}
      <div className="glass-card rounded-apple-lg p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-apple bg-apple-blue-dim flex items-center justify-center">
            <Sparkles size={20} className="text-apple-blue" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-apple-text truncate">
              {data.title || '未命名世界'}
            </h2>
            {data.genre && (
              <span className="inline-block mt-1 text-xs text-apple-text-muted px-2 py-0.5 rounded-apple-full bg-black/5">
                {data.genre}
              </span>
            )}
          </div>
        </div>
        {data.setting && (
          <p className="text-sm text-apple-text-secondary leading-relaxed">{data.setting}</p>
        )}
      </div>

      {/* 角色列表 */}
      {data.characters && data.characters.length > 0 && (
        <div className="glass-card rounded-apple-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <Users size={18} className="text-apple-blue" />
            <h3 className="font-semibold text-apple-text">角色</h3>
            <span className="text-xs text-apple-text-muted">{data.characters.length} 个</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {data.characters.map((char, idx) => (
              <motion.div
                key={char.name + idx}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="p-3 rounded-apple bg-black/[0.03] border border-black/[0.04]"
              >
                <div className="font-medium text-apple-text text-sm">{char.name}</div>
                {char.role && (
                  <div className="text-xs text-apple-blue mt-0.5">{char.role}</div>
                )}
                {char.description && (
                  <div className="text-xs text-apple-text-secondary mt-1.5 leading-relaxed line-clamp-2">
                    {char.description}
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* 魔法/力量体系 */}
      {data.magic_system && (
        <div className="glass-card rounded-apple-lg p-6">
          <div className="flex items-center gap-2 mb-3">
            <Wand2 size={18} className="text-apple-blue" />
            <h3 className="font-semibold text-apple-text">力量体系</h3>
          </div>
          <p className="text-sm text-apple-text-secondary leading-relaxed whitespace-pre-wrap">
            {data.magic_system}
          </p>
        </div>
      )}
    </div>
  )
}

/* ===== 大纲视图 ===== */
function OutlineContent({ data }: { data: Outline }) {
  const chapters = data.chapters || []

  return (
    <div className="max-w-3xl space-y-4">
      {/* 元信息 */}
      {data.outline_meta && (
        <div className="glass-card rounded-apple-lg p-5 flex items-center gap-4">
          <div className="flex-1">
            <span className="text-xs text-apple-text-muted">总章节数</span>
            <div className="text-lg font-bold text-apple-text">{data.outline_meta.total_chapters}</div>
          </div>
          {data.consistency_rules && data.consistency_rules.length > 0 && (
            <div className="flex-1">
              <span className="text-xs text-apple-text-muted">一致性规则</span>
              <div className="text-lg font-bold text-apple-text">{data.consistency_rules.length}</div>
            </div>
          )}
        </div>
      )}

      {/* 章节大纲列表 */}
      {chapters.length === 0 ? (
        <div className="text-center py-12 text-apple-text-muted text-sm">暂无大纲数据</div>
      ) : (
        chapters.map((ch, idx) => (
          <motion.div
            key={ch.chapter_index ?? idx}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.04 }}
            className="glass-card rounded-apple-lg p-5"
          >
            <div className="flex items-start gap-3">
              <div className="shrink-0 w-8 h-8 rounded-apple bg-apple-blue-dim flex items-center justify-center">
                <span className="text-xs font-bold text-apple-blue">
                  {ch.chapter_index ?? idx + 1}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="font-semibold text-apple-text text-sm">
                  {ch.title || `第 ${idx + 1} 章`}
                </h4>
                {ch.plot_detail && (
                  <p className="text-xs text-apple-text-secondary mt-2 leading-relaxed">
                    {ch.plot_detail}
                  </p>
                )}
                {ch.key_events && ch.key_events.length > 0 && (
                  <div className="mt-3 space-y-1">
                    {ch.key_events.map((evt, eidx) => (
                      <div key={eidx} className="flex items-start gap-2 text-xs text-apple-text-secondary">
                        <ChevronRight size={12} className="mt-0.5 shrink-0 text-apple-text-muted" />
                        <span>{evt}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        ))
      )}

      {/* 一致性规则 */}
      {data.consistency_rules && data.consistency_rules.length > 0 && (
        <div className="glass-card rounded-apple-lg p-5">
          <h3 className="font-semibold text-apple-text text-sm mb-3">一致性规则</h3>
          <ul className="space-y-1.5">
            {data.consistency_rules.map((rule, idx) => (
              <li key={idx} className="flex items-start gap-2 text-xs text-apple-text-secondary">
                <span className="shrink-0 w-4 h-4 rounded-full bg-apple-warning/15 text-apple-warning flex items-center justify-center text-[10px] font-bold">
                  {idx + 1}
                </span>
                <span>{rule}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/* ===== 章节视图 — 左侧列表 + 右侧预览 ===== */
function ChaptersContent({
  chapters,
  selectedIndex,
  onSelect,
}: {
  chapters: ChapterMeta[]
  selectedIndex: number
  onSelect: (idx: number) => void
}) {
  if (chapters.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-apple-text-muted text-sm">
        暂无章节数据
      </div>
    )
  }

  const current = chapters[selectedIndex]

  return (
    <div className="h-full flex gap-4">
      {/* 左侧章节列表 */}
      <div className="w-56 shrink-0 overflow-y-auto space-y-1.5 pr-1">
        {chapters.map((ch, idx) => {
          const isActive = idx === selectedIndex
          return (
            <button
              key={ch.chapter_index ?? idx}
              onClick={() => onSelect(idx)}
              className={`
                w-full text-left p-3 rounded-apple-sm transition-all duration-150
                ${isActive
                  ? 'bg-apple-blue text-white shadow-apple'
                  : 'bg-black/[0.03] hover:bg-black/[0.06] text-apple-text'
                }
              `}
            >
              <div className="text-xs font-medium truncate">
                第 {ch.chapter_index ?? idx + 1} 章
              </div>
              <div className={`text-xs mt-0.5 truncate ${isActive ? 'text-white/70' : 'text-apple-text-muted'}`}>
                {ch.title || '无标题'}
              </div>
            </button>
          )
        })}
      </div>

      {/* 右侧内容预览 */}
      <div className="flex-1 overflow-y-auto">
        <AnimatePresence mode="wait">
          {current && (
            <motion.div
              key={current.chapter_index ?? selectedIndex}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.2 }}
              className="glass-card rounded-apple-lg p-8"
            >
              {/* 章节头部 */}
              <div className="mb-6 pb-4 border-b border-black/5">
                <div className="text-xs text-apple-text-muted mb-1">
                  第 {current.chapter_index ?? selectedIndex + 1} 章
                </div>
                <h2 className="text-2xl font-bold text-apple-text">
                  {current.title || '无标题'}
                </h2>
                <div className="flex items-center gap-4 mt-3 text-xs text-apple-text-muted">
                  <span>{current.word_count} 字</span>
                  {current.summary && <span>摘要已生成</span>}
                </div>
              </div>

              {/* 章节正文 */}
              <div className="text-sm text-apple-text leading-[1.85] whitespace-pre-wrap">
                {current.content || '（本章暂无内容）'}
              </div>

              {/* 摘要 */}
              {current.summary && (
                <div className="mt-8 p-4 rounded-apple bg-apple-blue-dim/50 border border-apple-blue/10">
                  <div className="text-xs font-medium text-apple-blue mb-1.5">章节摘要</div>
                  <p className="text-xs text-apple-text-secondary leading-relaxed">
                    {current.summary}
                  </p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
