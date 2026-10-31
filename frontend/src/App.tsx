import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from './stores/useStore'
import { useSSE } from './stores/useSSE'
import Sidebar from './components/Sidebar'
import CreateTab from './pages/CreateTab'
import WorkspaceTab from './pages/WorkspaceTab'
import PreviewTab from './pages/PreviewTab'
import ProjectsTab from './pages/ProjectsTab'
import SettingsTab from './pages/SettingsTab'
import WorldViewReviewDialog from './components/WorldViewReviewDialog'
import OutlineReviewDialog from './components/OutlineReviewDialog'
import ContinuationReviewDialog from './components/ContinuationReviewDialog'
import LaunchScreen from './components/LaunchScreen'
import { AlertCircle, X, Bell, BookOpen, PenTool } from 'lucide-react'

const TAB_COMPONENTS = [CreateTab, WorkspaceTab, PreviewTab, ProjectsTab, SettingsTab]

export default function App() {
  const activeTab = useStore((s) => s.activeTab)
  const pendingWorldView = useStore((s) => s.pendingWorldView)
  const pendingOutline = useStore((s) => s.pendingOutline)
  const pendingContinuationOutline = useStore((s) => s.pendingContinuationOutline)
  const reviewDismissed = useStore((s) => s.reviewDismissed)
  const setPendingWorldView = useStore((s) => s.setPendingWorldView)
  const setPendingOutline = useStore((s) => s.setPendingOutline)
  const setPendingContinuationOutline = useStore((s) => s.setPendingContinuationOutline)
  const dismissReview = useStore((s) => s.dismissReview)
  const showReview = useStore((s) => s.showReview)
  const error = useStore((s) => s.error)
  const setError = useStore((s) => s.setError)
  const [launched, setLaunched] = useState(false)

  // 启动 SSE 连接（连接建立后会回填一次流水线状态）
  useSSE()

  if (!launched) {
    return <LaunchScreen onLaunch={() => setLaunched(true)} />
  }

  const ActiveComponent = TAB_COMPONENTS[activeTab]

  return (
    <div className="flex h-full w-full overflow-hidden bg-apple-bg">
      {/* 侧边栏 */}
      <Sidebar />

      {/* 主内容区 */}
      <main className="flex-1 overflow-hidden relative">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="h-full w-full"
        >
          <ActiveComponent />
        </motion.div>
      </main>

      {/* 全局错误提示 */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-3 px-5 py-3 rounded-apple-lg bg-apple-error text-white shadow-apple-lg max-w-md"
        >
          <AlertCircle size={18} className="shrink-0" />
          <span className="text-sm flex-1">{error}</span>
          <button onClick={() => setError(null)} className="shrink-0 opacity-70 hover:opacity-100">
            <X size={16} />
          </button>
        </motion.div>
      )}

      {/* 审阅提醒：只在用户把对话框收起后出现，点击可重新打开 */}
      <AnimatePresence>
        {pendingWorldView && reviewDismissed.world && (
          <motion.button
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-[90] flex items-center gap-3 px-5 py-3 rounded-apple-lg bg-apple-blue text-white shadow-apple-lg max-w-md"
            onClick={() => showReview('world')}
          >
            <motion.div
              animate={{ scale: [1, 1.2, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              <Bell size={18} />
            </motion.div>
            <span className="text-sm flex-1">世界观待审阅，点击继续</span>
            <BookOpen size={16} />
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {pendingOutline && reviewDismissed.outline && (
          <motion.button
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-[90] flex items-center gap-3 px-5 py-3 rounded-apple-lg bg-apple-success text-white shadow-apple-lg max-w-md"
            onClick={() => showReview('outline')}
          >
            <motion.div
              animate={{ scale: [1, 1.2, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              <Bell size={18} />
            </motion.div>
            <span className="text-sm flex-1">详细大纲待审阅，点击继续</span>
            <PenTool size={16} />
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {pendingContinuationOutline && reviewDismissed.continuation && (
          <motion.button
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-[90] flex items-center gap-3 px-5 py-3 rounded-apple-lg bg-apple-success text-white shadow-apple-lg max-w-md"
            onClick={() => showReview('continuation')}
          >
            <motion.div
              animate={{ scale: [1, 1.2, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              <Bell size={18} />
            </motion.div>
            <span className="text-sm flex-1">续写大纲待审阅，点击继续</span>
            <PenTool size={16} />
          </motion.button>
        )}
      </AnimatePresence>

      {/* 审阅对话框：关闭 = 暂时收起，可从横幅/工作台重新打开 */}
      {pendingWorldView && !reviewDismissed.world && (
        <WorldViewReviewDialog
          worldView={pendingWorldView}
          onClose={() => dismissReview('world')}
          onConfirmed={() => setPendingWorldView(null)}
        />
      )}
      {pendingOutline && !reviewDismissed.outline && (
        <OutlineReviewDialog
          outline={pendingOutline}
          onClose={() => dismissReview('outline')}
          onConfirmed={() => setPendingOutline(null)}
        />
      )}
      {pendingContinuationOutline && !reviewDismissed.continuation && (
        <ContinuationReviewDialog
          outline={pendingContinuationOutline}
          onClose={() => dismissReview('continuation')}
          onConfirmed={() => setPendingContinuationOutline(null)}
        />
      )}
    </div>
  )
}
