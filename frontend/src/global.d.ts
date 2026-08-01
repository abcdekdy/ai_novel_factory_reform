/**
 * Electron preload 暴露的全局 API 类型声明
 */
interface Window {
  electronAPI?: {
    platform: string
    isPackaged: boolean
    versions: { node: string; electron: string }
    openPath: (filePath: string) => Promise<{ ok: boolean; message?: string }>
    showInFolder: (filePath: string) => Promise<{ ok: boolean; message?: string }>
  }
}
