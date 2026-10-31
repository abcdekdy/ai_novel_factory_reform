/**
 * 世界观审阅对话框 — 展示并编辑世界观，确认后继续生成详细大纲
 *
 * 关键约束：确认时必须在**原始对象上合并**，只覆盖用户真正编辑过的字段。
 * 历史实现是"按表单重建对象"，把没做输入框的 era/location/factions/history
 * 写成空、把每个角色的 ability 写成空——用户点一次确认，世界观就被削掉一半。
 */
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { X, BookOpen, Users, Wand2, ListOrdered, Save, RefreshCw, Landmark } from 'lucide-react'
import { api } from '../api/client'
import type { Character, OutlineChapter, WorldView } from '../types'

interface Props {
  worldView: WorldView
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
const LABEL_CLASS = 'block text-sm font-medium text-apple-text-secondary mb-1.5'

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export default function WorldViewReviewDialog({ worldView, onClose, onConfirmed }: Props) {
  const detail = worldView.world_view ?? {}
  const framework = worldView.story_framework ?? {}

  const [title, setTitle] = useState(asString(worldView.title))
  const [genre, setGenre] = useState(asString(worldView.genre))
  const [summary, setSummary] = useState(
    asString(worldView.summary) || asString(worldView.setting))
  const [era, setEra] = useState(asString(detail.era))
  const [location, setLocation] = useState(asString(detail.location))
  const [rules, setRules] = useState(
    asString(detail.rules) || asString(worldView.magic_system))
  const [factions, setFactions] = useState(
    Array.isArray(detail.factions) ? detail.factions.join('、') : '')
  const [history, setHistory] = useState(asString(detail.history))
  const [premise, setPremise] = useState(asString(framework.premise))
  const [conflict, setConflict] = useState(asString(framework.conflict))
  const [climax, setClimax] = useState(asString(framework.climax))
  const [endingType, setEndingType] = useState(asString(framework.ending_type))

  const [characters, setCharacters] = useState<Character[]>(
    (worldView.characters ?? []).map((c) => ({
      ...c,
      name: asString(c.name),
      role: asString(c.role),
      desc: asString(c.desc) || asString(c.description),
      ability: asString(c.ability),
    })))
  const [chapterOutline, setChapterOutline] = useState<OutlineChapter[]>(
    (worldView.chapter_outline ?? []).map((ch) => ({
      ...ch,
      title: asString(ch.title),
      summary: asString(ch.summary) || asString(ch.plot_detail),
    })))

  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const updateCharacter = (idx: number, field: 'name' | 'role' | 'desc' | 'ability', value: string) => {
    setCharacters((prev) => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)))
  }

  const updateOutlineChapter = (idx: number, field: 'title' | 'summary', value: string) => {
    setChapterOutline((prev) => prev.map((ch, i) => (i === idx ? { ...ch, [field]: value } : ch)))
  }

  const handleRegenerate = async () => {
    setRegenerating(true)
    try {
      await api.retryWorldView()
      onConfirmed()
    } catch (err) {
      alert(err instanceof Error ? err.message : '重新生成失败')
      setRegenerating(false)
    }
  }

  const handleConfirm = async () => {
    setSaving(true)
    try {
      // 以原始对象为基底合并，保住所有没被编辑的字段（含未知扩展字段）
      const reviewed: Record<string, unknown> = {
        ...worldView,
        title,
        genre,
        summary,
        world_view: {
          ...detail,
          era,
          location,
          rules,
          factions: factions.split(/[、,，]/).map((s) => s.trim()).filter(Boolean),
          history,
        },
        story_framework: {
          ...framework,
          premise,
          conflict,
          climax,
          ending_type: endingType,
        },
        characters: characters.map((c) => ({
          ...c,
          name: c.name,
          role: c.role,
          desc: c.desc,
          ability: c.ability,
        })),
        chapter_outline: chapterOutline.map((ch, idx) => ({
          ...ch,
          chapter_index: ch.chapter_index ?? idx + 1,
          chapter: ch.chapter ?? ch.chapter_index ?? idx + 1,
          title: ch.title,
          summary: ch.summary,
        })),
      }
      await api.confirmWorldView({ world_view: reviewed })
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
            <BookOpen className="h-5 w-5 text-apple-blue" />
            <h2 className="text-lg font-semibold text-apple-text">审阅世界观</h2>
            <span className="text-xs text-apple-text-muted">确认后开始生成详细大纲</span>
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
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={LABEL_CLASS}>作品标题</label>
              <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT_CLASS} />
            </div>
            <div>
              <label className={LABEL_CLASS}>题材</label>
              <input type="text" value={genre} onChange={(e) => setGenre(e.target.value)} className={INPUT_CLASS} />
            </div>
          </div>

          <div>
            <label className={LABEL_CLASS}>世界观简介</label>
            <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={4}
              className={`${INPUT_CLASS} resize-none leading-relaxed`} />
          </div>

          <div className="rounded-apple border border-black/5 bg-black/[0.02] p-4 space-y-4">
            <div className="flex items-center gap-2 text-sm font-medium text-apple-text">
              <Landmark size={15} className="text-apple-blue" />
              世界设定
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={LABEL_CLASS}>时代背景</label>
                <input type="text" value={era} onChange={(e) => setEra(e.target.value)} className={INPUT_CLASS} />
              </div>
              <div>
                <label className={LABEL_CLASS}>地理设定</label>
                <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} className={INPUT_CLASS} />
              </div>
            </div>
            <div>
              <label className={LABEL_CLASS}>世界规则 / 力量体系</label>
              <textarea value={rules} onChange={(e) => setRules(e.target.value)} rows={3}
                className={`${INPUT_CLASS} resize-none leading-relaxed`} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={LABEL_CLASS}>主要势力（用、分隔）</label>
                <input type="text" value={factions} onChange={(e) => setFactions(e.target.value)} className={INPUT_CLASS} />
              </div>
              <div>
                <label className={LABEL_CLASS}>历史背景</label>
                <input type="text" value={history} onChange={(e) => setHistory(e.target.value)} className={INPUT_CLASS} />
              </div>
            </div>
          </div>

          <div className="rounded-apple border border-black/5 bg-black/[0.02] p-4 space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-apple-text">
              <Wand2 size={15} className="text-apple-blue" />
              故事框架
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={LABEL_CLASS}>故事开端</label>
                <input type="text" value={premise} onChange={(e) => setPremise(e.target.value)} className={INPUT_CLASS} />
              </div>
              <div>
                <label className={LABEL_CLASS}>核心冲突</label>
                <input type="text" value={conflict} onChange={(e) => setConflict(e.target.value)} className={INPUT_CLASS} />
              </div>
              <div>
                <label className={LABEL_CLASS}>高潮设计</label>
                <input type="text" value={climax} onChange={(e) => setClimax(e.target.value)} className={INPUT_CLASS} />
              </div>
              <div>
                <label className={LABEL_CLASS}>结局方向</label>
                <input type="text" value={endingType} onChange={(e) => setEndingType(e.target.value)} className={INPUT_CLASS} />
              </div>
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-apple-text">
              <Users size={15} className="text-apple-blue" />
              角色 <span className="text-xs font-normal text-apple-text-muted">{characters.length} 个</span>
            </div>
            <div className="space-y-3">
              {characters.map((char, idx) => (
                <div key={idx} className="rounded-apple border border-black/5 bg-black/[0.02] p-3 space-y-2">
                  <div className="grid grid-cols-3 gap-2">
                    <input type="text" value={char.name ?? ''} placeholder="角色名"
                      onChange={(e) => updateCharacter(idx, 'name', e.target.value)} className={INPUT_CLASS} />
                    <input type="text" value={char.role ?? ''} placeholder="身份"
                      onChange={(e) => updateCharacter(idx, 'role', e.target.value)} className={INPUT_CLASS} />
                    <input type="text" value={char.ability ?? ''} placeholder="核心能力"
                      onChange={(e) => updateCharacter(idx, 'ability', e.target.value)} className={INPUT_CLASS} />
                  </div>
                  <textarea value={char.desc ?? ''} placeholder="角色描述" rows={2}
                    onChange={(e) => updateCharacter(idx, 'desc', e.target.value)}
                    className={`${INPUT_CLASS} resize-none`} />
                </div>
              ))}
              {characters.length === 0 && (
                <p className="text-sm text-apple-text-muted">暂无角色</p>
              )}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-apple-text">
              <ListOrdered size={15} className="text-apple-blue" />
              章节大纲 <span className="text-xs font-normal text-apple-text-muted">{chapterOutline.length} 章</span>
            </div>
            <div className="space-y-3">
              {chapterOutline.map((ch, idx) => (
                <div key={idx} className="rounded-apple border border-black/5 bg-black/[0.02] p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-apple-blue-dim px-1.5 text-xs font-medium text-apple-blue">
                      {ch.chapter_index ?? idx + 1}
                    </span>
                    <input type="text" value={ch.title ?? ''} placeholder="章节标题"
                      onChange={(e) => updateOutlineChapter(idx, 'title', e.target.value)} className={INPUT_CLASS} />
                  </div>
                  <textarea value={ch.summary ?? ''} placeholder="情节概要" rows={2}
                    onChange={(e) => updateOutlineChapter(idx, 'summary', e.target.value)}
                    className={`${INPUT_CLASS} resize-none`} />
                </div>
              ))}
              {chapterOutline.length === 0 && (
                <p className="text-sm text-apple-text-muted">暂无章节大纲</p>
              )}
            </div>
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
              {saving ? '保存中…' : '确认并继续'}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
