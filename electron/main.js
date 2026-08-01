/**
 * Electron 主进程
 * 启动 Python 后端子进程，创建应用窗口
 */
const { app, BrowserWindow, Menu, Tray, ipcMain, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')

// 开发模式检测
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged
const BACKEND_PORT = 8765
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`

let mainWindow = null
let pythonProcess = null
let tray = null

// ===== Python 后端管理 =====

function checkBackendRunning() {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/api/health`, { timeout: 2000 }, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => { req.destroy(); resolve(false) })
  })
}

async function startPythonBackend() {
  if (pythonProcess) return

  // 先检测后端是否已运行（开发模式下可能手动启动了 uvicorn）
  const running = await checkBackendRunning()
  if (running) {
    console.log('[Electron] Python 后端已在运行，跳过启动')
    return
  }

  const pythonExe = process.platform === 'win32' ? 'python' : 'python3'

  pythonProcess = spawn(pythonExe, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)], {
    cwd: path.join(__dirname, '..', 'backend'),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
  })

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] ${data.toString().trim()}`)
  })

  pythonProcess.stderr.on('data', (data) => {
    const line = data.toString().trim()
    // 过滤掉 uvicorn 的 INFO 噪音
    if (line && !line.match(/^INFO:\s+(Will watch|Uvicorn running|Started|Waiting|Application)/)) {
      console.error(`[Python ERR] ${line}`)
    }
  })

  pythonProcess.on('exit', (code) => {
    console.log(`[Python] 进程退出 code=${code}`)
    pythonProcess = null
  })

  console.log('[Electron] Python 后端已启动')
}

function stopPythonBackend() {
  if (!pythonProcess) return

  const pid = pythonProcess.pid
  console.log(`[Electron] 正在停止 Python 后端 (PID: ${pid})...`)

  if (process.platform === 'win32') {
    // Windows: 使用 taskkill /T 杀死整个进程树（包括 uvicorn worker 子进程）
    // /F 强制终止 /T 终止子进程
    const { execSync } = require('child_process')
    try {
      execSync(`taskkill /PID ${pid} /T /F`, { stdio: 'ignore' })
      console.log('[Electron] Python 后端进程树已终止')
    } catch (e) {
      // 进程可能已退出，回退到 kill()
      pythonProcess.kill('SIGKILL')
    }
  } else {
    // macOS/Linux: 使用进程组信号杀死整个进程组
    try {
      // 发送信号给进程组（负 PID）
      process.kill(-pid, 'SIGKILL')
    } catch (e) {
      pythonProcess.kill('SIGKILL')
    }
  }

  pythonProcess = null
  console.log('[Electron] Python 后端已停止')
}

function killProcessOnPort(port) {
  // 通过端口号杀死进程（用于清理 Vite 等外部进程）
  if (process.platform !== 'win32') return

  const { execSync } = require('child_process')
  try {
    // 查找占用端口的 PID
    const output = execSync(`netstat -ano | findstr ":${port}" | findstr "LISTENING"`, { encoding: 'utf-8' })
    const lines = output.trim().split('\n')
    for (const line of lines) {
      const parts = line.trim().split(/\s+/)
      const pid = parts[parts.length - 1]
      if (pid && pid !== '0') {
        try {
          execSync(`taskkill /PID ${pid} /F`, { stdio: 'ignore' })
          console.log(`[Electron] Killed process on port ${port} (PID: ${pid})`)
        } catch (e) {
          // 进程可能已退出
        }
      }
    }
  } catch (e) {
    // 端口未被占用或命令失败
  }
}

// ===== IPC — 导出文件操作 =====

ipcMain.handle('open-path', async (event, filePath) => {
  // 用系统默认程序打开文件（导出 txt/md 后用）
  if (!filePath || typeof filePath !== 'string') {
    return { ok: false, message: '无效的文件路径' }
  }
  try {
    const result = await shell.openPath(filePath)
    return result ? { ok: false, message: result } : { ok: true }
  } catch (e) {
    return { ok: false, message: String(e) }
  }
})

ipcMain.handle('show-in-folder', async (event, filePath) => {
  // 在文件管理器中显示文件
  if (!filePath || typeof filePath !== 'string') {
    return { ok: false, message: '无效的文件路径' }
  }
  try {
    shell.showItemInFolder(filePath)
    return { ok: true }
  } catch (e) {
    return { ok: false, message: String(e) }
  }
})

// ===== 窗口管理 =====

function createWindow() {
  const isMac = process.platform === 'darwin'
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 780,
    minWidth: 900,
    minHeight: 600,
    show: false,
    // macOS: 隐藏标题栏但保留交通灯按钮
    // Windows: 保留标题栏（可关闭/最小化）
    frame: isMac ? false : true,
    titleBarStyle: isMac ? 'hiddenInset' : 'default',
    backgroundColor: '#F5F5F7',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // 加载页面
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'))
  }

  // 准备好后显示（避免白屏）
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // 拦截关闭按钮点击，确保先停止后端再退出
  mainWindow.on('close', (event) => {
    if (pythonProcess) {
      console.log('[Electron] 窗口关闭，先停止后端...')
      stopPythonBackend()
    }
    // 开发模式下清理 Vite 前端进程
    if (isDev) {
      killProcessOnPort(5173)
    }
  })
}

// ===== 托盘 =====

function createTray() {
  if (tray) return
  try {
    tray = new Tray(path.join(__dirname, '..', 'assets', 'tray-icon.png'))
    const contextMenu = Menu.buildFromTemplate([
      { label: '显示主窗口', click: () => mainWindow && mainWindow.show() },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ])
    tray.setToolTip('AI 小说工厂')
    tray.setContextMenu(contextMenu)
  } catch (e) {
    // 托盘图标可选，失败不影响
  }
}

// ===== 应用生命周期 =====

app.whenReady().then(async () => {
  await startPythonBackend()
  createWindow()

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      // 重新激活时，如果后端未运行，先启动后端
      const running = await checkBackendRunning()
      if (!running) {
        await startPythonBackend()
      }
      createWindow()
    }
  })
})

app.on('before-quit', () => {
  stopPythonBackend()
  // 开发模式下清理 Vite 前端进程
  if (isDev) {
    killProcessOnPort(5173)
  }
})

// 防止多实例
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })
}
