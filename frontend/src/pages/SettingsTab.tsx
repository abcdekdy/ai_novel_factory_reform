import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { api } from '../api/client'
import {
  Settings,
  Key,
  Zap,
  Sliders,
  Palette,
  Check,
  X,
  Loader2,
  Eye,
  EyeOff,
  AlertCircle,
  ShieldCheck,
} from 'lucide-react'

interface ConfigState {
  provider: string
  api_key: string
  api_key_set: boolean
  api_key_masked: string
  base_url: string
  model: string
  temperature: number
  max_tokens: number
  concurrency: number
  max_revision_rounds: number
  quality_threshold: number
  default_chapter_count: number
  default_chapter_length: number
  theme: string
}

const DEFAULT_CONFIG: Partial<ConfigState> = {
  provider: 'longcat',
  base_url: '',
  model: 'LongCat-2.0',
  temperature: 0.7,
  max_tokens: 8192,
  concurrency: 3,
  max_revision_rounds: 3,
  quality_threshold: 7,
  default_chapter_count: 5,
  default_chapter_length: 3000,
  theme: 'light',
  api_key_set: false,
  api_key_masked: '',
}

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06 },
  },
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
}

export default function SettingsTab() {
  const [config, setConfig] = useState<ConfigState>(DEFAULT_CONFIG as ConfigState)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    loadConfig()
  }, [])

  async function loadConfig() {
    try {
      const data = await api.getConfig()
      setConfig({
        provider: (data.provider as string) || DEFAULT_CONFIG.provider!,
        api_key: '',
        api_key_set: (data.api_key_set as boolean) || false,
        api_key_masked: (data.api_key_masked as string) || '',
        base_url: (data.base_url as string) || '',
        model: (data.model as string) || DEFAULT_CONFIG.model!,
        temperature: (data.temperature as number) ?? DEFAULT_CONFIG.temperature!,
        max_tokens: (data.max_tokens as number) ?? DEFAULT_CONFIG.max_tokens!,
        concurrency: (data.concurrency as number) ?? DEFAULT_CONFIG.concurrency!,
        max_revision_rounds: (data.max_revision_rounds as number) ?? DEFAULT_CONFIG.max_revision_rounds!,
        quality_threshold: (data.quality_threshold as number) ?? DEFAULT_CONFIG.quality_threshold!,
        default_chapter_count: (data.default_chapter_count as number) ?? DEFAULT_CONFIG.default_chapter_count!,
        default_chapter_length: (data.default_chapter_length as number) ?? DEFAULT_CONFIG.default_chapter_length!,
        theme: (data.theme as string) || 'light',
      })
    } catch (e) {
      console.error('加载配置失败:', e)
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setSaved(false)
    setTestResult(null)
    try {
      // 只发送有值的字段，api_key 只在非空时发送
      const payload: Record<string, unknown> = {
        provider: config.provider,
        base_url: config.base_url,
        model: config.model,
        temperature: config.temperature,
        max_tokens: config.max_tokens,
        concurrency: config.concurrency,
        max_revision_rounds: config.max_revision_rounds,
        quality_threshold: config.quality_threshold,
        default_chapter_count: config.default_chapter_count,
        default_chapter_length: config.default_chapter_length,
        theme: config.theme,
      }
      if (config.api_key) {
        payload.api_key = config.api_key
      }
      await api.updateConfig(payload)
      setSaved(true)
      // 重新加载以获取最新状态
      await loadConfig()
      setTimeout(() => setSaved(false), 3000)
    } catch (e: any) {
      console.error('保存失败:', e)
      setTestResult({ ok: false, message: e.message || '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  async function handleTest() {
    setTesting(true)
    setTestResult(null)
    try {
      // 先保存当前配置（确保测试用的是最新 key）
      const payload: Record<string, unknown> = {
        provider: config.provider,
        base_url: config.base_url,
        model: config.model,
      }
      if (config.api_key) {
        payload.api_key = config.api_key
      }
      await api.updateConfig(payload)
      // 然后测试
      const result = await api.testConnection()
      setTestResult({ ok: result.ok, message: result.message })
    } catch (e: any) {
      setTestResult({ ok: false, message: e.message || '连接测试失败' })
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-apple-blue" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-8">
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="max-w-2xl mx-auto space-y-6"
      >
        {/* 标题 */}
        <motion.div variants={item} className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-apple bg-apple-blue/10 flex items-center justify-center">
            <Settings size={20} className="text-apple-blue" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-apple-text">设置</h1>
            <p className="text-sm text-apple-text-secondary">配置 API 和生成参数</p>
          </div>
        </motion.div>

        {/* API 配置 */}
        <motion.section variants={item} className="glass-card rounded-apple-lg p-6 space-y-4">
          <h2 className="text-base font-semibold text-apple-text flex items-center gap-2">
            <Key size={16} className="text-apple-blue" />
            API 配置
          </h2>

          {/* Provider */}
          <div>
            <label className="block text-sm text-apple-text-secondary mb-1.5">服务商</label>
            <div className="flex gap-2">
              {['longcat', 'deepseek'].map((p) => (
                <button
                  key={p}
                  onClick={() => setConfig({ ...config, provider: p })}
                  className={`px-4 py-2 rounded-apple text-sm font-medium transition-all ${
                    config.provider === p
                      ? 'bg-apple-blue text-white shadow-apple'
                      : 'glass-inset text-apple-text-secondary hover:text-apple-text'
                  }`}
                >
                  {p === 'longcat' ? 'LongCat' : 'DeepSeek'}
                </button>
              ))}
            </div>
          </div>

          {/* API Key */}
          <div>
            <label className="block text-sm text-apple-text-secondary mb-1.5">API Key</label>
            {/* 已设置状态提示 */}
            {config.api_key_set && !config.api_key && (
              <div className="flex items-center gap-2 mb-2 px-3 py-2 rounded-apple-sm bg-apple-success/10 text-apple-success text-xs">
                <ShieldCheck size={13} />
                <span>已设置：{config.api_key_masked}</span>
                <span className="text-apple-text-muted ml-1">（留空则保持不变）</span>
              </div>
            )}
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={config.api_key}
                onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
                placeholder={config.api_key_set ? "输入新 API Key（留空保持不变）" : "输入 API Key..."}
                className="w-full px-4 py-2.5 rounded-apple glass-inset text-sm pr-10 focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-apple-text-muted hover:text-apple-text"
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Base URL */}
          <div>
            <label className="block text-sm text-apple-text-secondary mb-1.5">Base URL（可选）</label>
            <input
              type="text"
              value={config.base_url}
              onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
              placeholder="https://api.example.com/v1"
              className="w-full px-4 py-2.5 rounded-apple glass-inset text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
            />
          </div>

          {/* Model */}
          <div>
            <label className="block text-sm text-apple-text-secondary mb-1.5">模型</label>
            <input
              type="text"
              value={config.model}
              onChange={(e) => setConfig({ ...config, model: e.target.value })}
              className="w-full px-4 py-2.5 rounded-apple glass-inset text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
            />
          </div>

          {/* 测试连接 */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleTest}
              disabled={testing || (!config.api_key && !config.api_key_set)}
              className="px-4 py-2 rounded-apple bg-apple-blue/10 text-apple-blue text-sm font-medium hover:bg-apple-blue/20 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {testing ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
              测试连接
            </button>
            {testResult && (
              <span className={`text-sm flex items-center gap-1 ${testResult.ok ? 'text-apple-success' : 'text-apple-error'}`}>
                {testResult.ok ? <Check size={14} /> : <X size={14} />}
                {testResult.message}
              </span>
            )}
          </div>
        </motion.section>

        {/* 生成参数 */}
        <motion.section variants={item} className="glass-card rounded-apple-lg p-6 space-y-4">
          <h2 className="text-base font-semibold text-apple-text flex items-center gap-2">
            <Sliders size={16} className="text-apple-blue" />
            生成参数
          </h2>

          {/* Temperature */}
          <div>
            <div className="flex justify-between mb-1.5">
              <label className="text-sm text-apple-text-secondary">Temperature</label>
              <span className="text-sm font-medium text-apple-text">{config.temperature.toFixed(1)}</span>
            </div>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={config.temperature}
              onChange={(e) => setConfig({ ...config, temperature: parseFloat(e.target.value) })}
              className="w-full accent-apple-blue"
            />
          </div>

          {/* Quality Threshold */}
          <div>
            <div className="flex justify-between mb-1.5">
              <label className="text-sm text-apple-text-secondary">质量阈值</label>
              <span className="text-sm font-medium text-apple-text">{config.quality_threshold.toFixed(1)}</span>
            </div>
            <input
              type="range"
              min="0"
              max="10"
              step="0.5"
              value={config.quality_threshold}
              onChange={(e) => setConfig({ ...config, quality_threshold: parseFloat(e.target.value) })}
              className="w-full accent-apple-blue"
            />
          </div>

          {/* 数值输入网格 */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-apple-text-secondary mb-1.5">最大 Token</label>
              <input
                type="number"
                value={config.max_tokens}
                onChange={(e) => setConfig({ ...config, max_tokens: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 rounded-apple glass-inset text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
              />
            </div>
            <div>
              <label className="block text-sm text-apple-text-secondary mb-1.5">并发数</label>
              <input
                type="number"
                min="1"
                max="10"
                value={config.concurrency}
                onChange={(e) => setConfig({ ...config, concurrency: parseInt(e.target.value) || 1 })}
                className="w-full px-3 py-2 rounded-apple glass-inset text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
              />
            </div>
            <div>
              <label className="block text-sm text-apple-text-secondary mb-1.5">最大修订轮数</label>
              <input
                type="number"
                min="0"
                max="10"
                value={config.max_revision_rounds}
                onChange={(e) => setConfig({ ...config, max_revision_rounds: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-2 rounded-apple glass-inset text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
              />
            </div>
            <div>
              <label className="block text-sm text-apple-text-secondary mb-1.5">默认章节数</label>
              <input
                type="number"
                min="1"
                max="100"
                value={config.default_chapter_count}
                onChange={(e) => setConfig({ ...config, default_chapter_count: parseInt(e.target.value) || 5 })}
                className="w-full px-3 py-2 rounded-apple glass-inset text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
              />
            </div>
            <div>
              <label className="block text-sm text-apple-text-secondary mb-1.5">默认每章字数</label>
              <input
                type="number"
                min="500"
                max="20000"
                step="500"
                value={config.default_chapter_length}
                onChange={(e) => setConfig({ ...config, default_chapter_length: parseInt(e.target.value) || 3000 })}
                className="w-full px-3 py-2 rounded-apple glass-inset text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
              />
            </div>
          </div>
        </motion.section>

        {/* 主题 */}
        <motion.section variants={item} className="glass-card rounded-apple-lg p-6 space-y-4">
          <h2 className="text-base font-semibold text-apple-text flex items-center gap-2">
            <Palette size={16} className="text-apple-blue" />
            主题
          </h2>
          <div className="flex gap-2">
            {[
              { id: 'light', label: '浅色' },
              { id: 'dark', label: '深色' },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setConfig({ ...config, theme: t.id })}
                className={`px-4 py-2 rounded-apple text-sm font-medium transition-all ${
                  config.theme === t.id
                    ? 'bg-apple-blue text-white shadow-apple'
                    : 'glass-inset text-apple-text-secondary hover:text-apple-text'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </motion.section>

        {/* 保存按钮 */}
        <motion.div variants={item} className="pt-2 pb-8">
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full py-3 rounded-apple bg-apple-blue text-white font-medium shadow-apple hover:bg-apple-blue-hover transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {saving ? (
              <Loader2 size={16} className="animate-spin" />
            ) : saved ? (
              <>
                <Check size={16} />
                已保存
              </>
            ) : (
              '保存设置'
            )}
          </button>
        </motion.div>
      </motion.div>
    </div>
  )
}
