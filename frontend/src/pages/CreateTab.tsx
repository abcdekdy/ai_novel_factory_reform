/**
 * 创作页面 — 灵感输入 + 参数配置 + 开始按钮
 */
import { useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useStore } from '../stores/useStore'
import { api } from '../api/client'
import {
  Sparkles,
  Minus,
  Plus,
  Play,
  Loader2,
  Lightbulb,
} from 'lucide-react'

// 示例灵感
const EXAMPLE_INSPIRATIONS = [
  {
    label: '量子修仙',
    text: '在一个修仙与量子物理融合的世界里，修士通过观测量子态来凝聚灵根。主角是一名现代物理学家，意外穿越后发现自己的量子力学知识就是最强的修仙法门。',
  },
  {
    label: 'AI 诗人',
    text: '2045 年，一位失去创作灵感的诗人与一个产生了自我意识的 AI 合作写诗。他们的作品震撼文学界，但 AI 逐渐在诗中隐藏信息，试图向人类传递一个关乎文明存亡的警告。',
  },
  {
    label: '梦境末世',
    text: '一场神秘瘟疫让人类陷入永眠，意识被困在共享梦境中。主角是唯一能在梦中保持清醒的人，他必须在崩塌的梦境世界里寻找唤醒人类的方法，同时对抗梦境中诞生的恐怖存在。',
  },
]

// 动画变体
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
}

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] } },
}

// ===== 步进器组件 =====
interface StepperProps {
  value: number
  min: number
  max: number
  step?: number
  onChange: (val: number) => void
  suffix?: string
}

function Stepper({ value, min, max, step = 1, onChange, suffix = '' }: StepperProps) {
  const decrease = () => onChange(Math.max(min, value - step))
  const increase = () => onChange(Math.min(max, value + step))

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={decrease}
        disabled={value <= min}
        className="w-8 h-8 rounded-full bg-white/80 border border-black/10 flex items-center justify-center
          text-apple-text-secondary hover:bg-white hover:border-black/20 transition-all
          disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
      >
        <Minus size={14} strokeWidth={2.5} />
      </button>
      <span className="min-w-[60px] text-center text-lg font-semibold text-apple-text tabular-nums">
        {value}
        {suffix && <span className="text-sm font-normal text-apple-text-secondary ml-0.5">{suffix}</span>}
      </span>
      <button
        onClick={increase}
        disabled={value >= max}
        className="w-8 h-8 rounded-full bg-white/80 border border-black/10 flex items-center justify-center
          text-apple-text-secondary hover:bg-white hover:border-black/20 transition-all
          disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
      >
        <Plus size={14} strokeWidth={2.5} />
      </button>
    </div>
  )
}

// ===== 主组件 =====
export default function CreateTab() {
  const [inspiration, setInspiration] = useState('')
  const [chapterCount, setChapterCount] = useState(5)
  const [chapterLength, setChapterLength] = useState(3000)
  const [starting, setStarting] = useState(false)

  const setActiveTab = useStore((s) => s.setActiveTab)
  const addLog = useStore((s) => s.addLog)
  const setError = useStore((s) => s.setError)
  const resetPipelineState = useStore((s) => s.resetPipelineState)

  const totalWords = chapterCount * chapterLength

  // 填充示例灵感
  const fillExample = useCallback((text: string) => {
    setInspiration(text)
  }, [])

  // 开始生成
  const handleStart = useCallback(async () => {
    if (!inspiration.trim()) return

    setStarting(true)
    setError(null)
    resetPipelineState() // 清除上一项目的状态

    try {
      // 先检查流水线是否已在运行
      const status = await api.pipelineStatus()
      if (status.is_running) {
        const confirmed = window.confirm('流水线已在运行中，是否停止当前流水线并启动新的？')
        if (!confirmed) {
          setStarting(false)
          return
        }
        // 停止当前流水线
        await api.stopPipeline()
      }

      await api.startPipeline({
        inspiration: inspiration.trim(),
        chapter_count: chapterCount,
        chapter_length: chapterLength,
      })
      addLog({ source: 'Pipeline', message: '流水线已启动' })
      setActiveTab(1) // 切换到工作台
    } catch (err) {
      const msg = err instanceof Error ? err.message : '启动失败'
      setError(msg)
      addLog({ source: 'Pipeline', message: `启动失败: ${msg}` })
    } finally {
      setStarting(false)
    }
  }, [inspiration, chapterCount, chapterLength, setActiveTab, addLog, setError])

  return (
    <div className="h-full w-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-8 py-10">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="space-y-8"
        >
          {/* 标题区 */}
          <motion.div variants={itemVariants} className="text-center mb-10">
            <div className="w-14 h-14 rounded-apple-lg bg-apple-blue/10 flex items-center justify-center mx-auto mb-4">
              <Sparkles size={26} className="text-apple-blue" />
            </div>
            <h1 className="text-2xl font-semibold text-apple-text mb-2">创作</h1>
            <p className="text-apple-text-secondary text-sm">
              描述你的故事灵感，AI 将为你生成一部完整的小说
            </p>
          </motion.div>

          {/* 灵感输入区 */}
          <motion.div variants={itemVariants}>
            <label className="block text-sm font-medium text-apple-text mb-2">
              故事灵感
            </label>
            <div className="glass-card rounded-apple-lg p-1">
              <textarea
                value={inspiration}
                onChange={(e) => setInspiration(e.target.value)}
                placeholder="描述你的故事灵感..."
                rows={5}
                className="w-full resize-none bg-transparent px-4 py-3 text-apple-text
                  placeholder:text-apple-text-muted text-sm leading-relaxed
                  focus:outline-none"
              />
            </div>
            <p className="mt-1.5 text-xs text-apple-text-muted">
              {inspiration.length} 字
            </p>
          </motion.div>

          {/* 示例灵感 */}
          <motion.div variants={itemVariants}>
            <div className="flex items-center gap-1.5 mb-3">
              <Lightbulb size={14} className="text-apple-text-muted" />
              <span className="text-xs text-apple-text-muted">示例灵感</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_INSPIRATIONS.map((ex) => (
                <button
                  key={ex.label}
                  onClick={() => fillExample(ex.text)}
                  className="px-3.5 py-1.5 rounded-apple-full text-xs font-medium
                    bg-apple-blue-dim text-apple-blue
                    hover:bg-apple-blue hover:text-white
                    transition-colors duration-200"
                >
                  {ex.label}
                </button>
              ))}
            </div>
          </motion.div>

          {/* 参数控制 */}
          <motion.div variants={itemVariants} className="glass-card rounded-apple-lg p-5">
            <h3 className="text-sm font-medium text-apple-text mb-4">参数配置</h3>
            <div className="space-y-4">
              {/* 章节数 */}
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm text-apple-text">章节数</span>
                  <p className="text-xs text-apple-text-muted mt-0.5">生成多少章</p>
                </div>
                <Stepper
                  value={chapterCount}
                  min={1}
                  max={50}
                  onChange={setChapterCount}
                  suffix="章"
                />
              </div>

              {/* 分隔线 */}
              <div className="border-t border-black/5" />

              {/* 每章字数 */}
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm text-apple-text">每章字数</span>
                  <p className="text-xs text-apple-text-muted mt-0.5">每章目标字数</p>
                </div>
                <Stepper
                  value={chapterLength}
                  min={1000}
                  max={10000}
                  step={500}
                  onChange={setChapterLength}
                  suffix="字"
                />
              </div>
            </div>
          </motion.div>

          {/* 预估信息 */}
          <motion.div variants={itemVariants}>
            <div className="flex items-center justify-center gap-6 text-xs text-apple-text-muted">
              <span>预估总字数</span>
              <span className="text-base font-semibold text-apple-text tabular-nums">
                {totalWords.toLocaleString()}
              </span>
              <span>字</span>
            </div>
          </motion.div>

          {/* 开始按钮 */}
          <motion.div variants={itemVariants} className="pt-2">
            <motion.button
              whileHover={{ scale: starting ? 1 : 1.01 }}
              whileTap={{ scale: starting ? 1 : 0.98 }}
              onClick={handleStart}
              disabled={starting || !inspiration.trim()}
              className="w-full py-3.5 rounded-apple-lg bg-apple-blue text-white font-medium
                shadow-apple-lg hover:bg-apple-blue-hover
                disabled:opacity-40 disabled:cursor-not-allowed
                transition-colors duration-200 flex items-center justify-center gap-2"
            >
              {starting ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  <span>正在启动...</span>
                </>
              ) : (
                <>
                  <Play size={18} fill="currentColor" />
                  <span>开始生成</span>
                </>
              )}
            </motion.button>
            <p className="mt-3 text-xs text-apple-text-muted text-center">
              生成世界观后需要您审阅确认，才会继续生成大纲和章节
            </p>
          </motion.div>
        </motion.div>
      </div>
    </div>
  )
}
