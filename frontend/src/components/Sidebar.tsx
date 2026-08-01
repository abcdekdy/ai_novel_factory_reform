import { motion } from 'framer-motion'
import { useStore } from '../stores/useStore'
import {
  PenTool,
  Monitor,
  Eye,
  FolderOpen,
  Settings,
} from 'lucide-react'

const NAV_ITEMS = [
  { icon: PenTool, label: '创作' },
  { icon: Monitor, label: '工作台' },
  { icon: Eye, label: '预览' },
  { icon: FolderOpen, label: '项目库' },
  { icon: Settings, label: '设置' },
]

export default function Sidebar() {
  const activeTab = useStore((s) => s.activeTab)
  const setActiveTab = useStore((s) => s.setActiveTab)
  const isRunning = useStore((s) => s.isRunning)

  return (
    <aside className="glass-sidebar w-16 h-full flex flex-col items-center py-5 border-r border-white/20 shrink-0">
      {/* Logo */}
      <div className="w-9 h-9 rounded-apple bg-apple-blue flex items-center justify-center mb-6 shadow-apple">
        <span className="text-white font-bold text-sm">AI</span>
      </div>

      {/* 导航 */}
      <nav className="flex-1 flex flex-col items-center gap-1.5">
        {NAV_ITEMS.map((item, idx) => {
          const Icon = item.icon
          const isActive = activeTab === idx
          return (
            <button
              key={item.label}
              onClick={() => setActiveTab(idx)}
              className={
                'relative w-11 h-11 rounded-apple flex items-center justify-center ' +
                'transition-all duration-200 group ' +
                (isActive
                  ? 'bg-apple-blue text-white shadow-apple'
                  : 'text-apple-text-secondary hover:bg-black/5 hover:text-apple-text')
              }
            >
              <Icon size={18} className="relative z-10 pointer-events-none" />
              {/* Tooltip */}
              <span className="absolute left-full ml-2 px-2 py-1 rounded-md bg-apple-text text-white text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
                {item.label}
              </span>
            </button>
          )
        })}
      </nav>

      {/* 运行状态指示 */}
      {isRunning && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="w-2 h-2 rounded-full bg-apple-success animate-pulse-soft"
        />
      )}
    </aside>
  )
}
