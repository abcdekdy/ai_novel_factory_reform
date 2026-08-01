import { motion } from 'framer-motion'
import { Sparkles } from 'lucide-react'

interface Props {
  onLaunch: () => void
}

export default function LaunchScreen({ onLaunch }: Props) {
  return (
    <div className="h-full w-full flex items-center justify-center bg-apple-bg">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="text-center"
      >
        {/* Logo */}
        <motion.div
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
          className="w-20 h-20 rounded-apple-xl bg-apple-blue flex items-center justify-center mx-auto mb-6 shadow-apple-lg"
        >
          <Sparkles size={36} className="text-white" />
        </motion.div>

        <h1 className="text-2xl font-semibold text-apple-text mb-2">AI 小说工厂</h1>
        <p className="text-apple-text-secondary mb-8">将灵感转化为完整小说</p>

        <motion.button
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          onClick={onLaunch}
          className="px-8 py-3 rounded-apple bg-apple-blue text-white font-medium shadow-apple hover:bg-apple-blue-hover transition-colors"
        >
          开始创作
        </motion.button>
      </motion.div>
    </div>
  )
}
