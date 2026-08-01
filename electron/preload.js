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
})
