/**
 * Electron Preload 脚本 — 暴露安全的 API 给渲染进程
 */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  isPackaged: process.env.NODE_ENV !== 'development',
  versions: {
    node: process.versions.node,
    electron: process.versions.electron,
  },
  // 用系统默认程序打开文件 / 在文件管理器中显示
  openPath: (filePath) => ipcRenderer.invoke('open-path', filePath),
  showInFolder: (filePath) => ipcRenderer.invoke('show-in-folder', filePath),
})
