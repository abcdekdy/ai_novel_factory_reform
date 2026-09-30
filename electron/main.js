/**
 * Electron 主进程
 * 启动 Python 后端子进程，创建应用窗口
 */
const { app, BrowserWindow, Menu, Tray, ipcMain, shell, dialog } = require('electron')
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
let backendStartError = null

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

/**
 * 解析后端的启动方式。
 *
 * 打包态：启动 PyInstaller 冻结出的独立可执行文件。extraResource 会把
 *         backend/dist/novel-backend 复制到 resources/novel-backend，
 *         最终用户无需安装 Python。
 *         注意不能用 __dirname 拼路径——打包后它指向 app.asar 内部，
 *         而 extraResource 的内容在 resources/ 下，两者并不相同。
 * 开发态：沿用系统 Python + uvicorn。
 */
function resolveBackendCommand() {
  if (app.isPackaged) {
    const exeName = process.platform === 'win32' ? 'novel-backend.exe' : 'novel-backend'
    const exePath = path.join(process.resourcesPath, 'novel-backend', exeName)
    return { command: exePath, args: [], cwd: path.dirname(exePath) }
  }

  return {
    command: process.platform === 'win32' ? 'python' : 'python3',
    args: ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    cwd: path.join(__dirname, '..', 'backend'),
  }
}

/** 轮询等待后端就绪；返回是否在超时前拿到健康响应。 */
async function waitForBackend(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await checkBackendRunning()) return true
    // 后端进程已退出就没必要继续等
    if (pythonProcess && pythonProcess.exitCode !== null) return false
    await new Promise((r) => setTimeout(r, 400))
  }
  return false
}

async function startPythonBackend() {
  if (pythonProcess) return true

  // 先检测后端是否已运行（开发模式下可能手动启动了 uvicorn）
  if (await checkBackendRunning()) {
    console.log('[Electron] Python 后端已在运行，跳过启动')
    return true
  }

  const { command, args, cwd } = resolveBackendCommand()

  const env = {
    ...process.env,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    NOVEL_BACKEND_PORT: String(BACKEND_PORT),
  }

  if (app.isPackaged) {
    // 用户数据（config.json / projects/）放应用根目录下的 data/，
    // 绿色版整个文件夹挪走时数据跟着走；也避免写进只读的程序目录。
    env.NOVEL_DATA_DIR = path.join(path.dirname(app.getPath('exe')), 'data')
    console.log(`[Electron] 数据目录: ${env.NOVEL_DATA_DIR}`)
  }

  console.log(`[Electron] 启动后端: ${command}`)

  pythonProcess = spawn(command, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env,
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

  pythonProcess.on('error', (err) => {
    // 打包态最常见的原因：冻结产物缺失或被杀软隔离
    console.error(`[Electron] 后端进程启动失败: ${err.message}`)
    backendStartError = err.message
    pythonProcess = null
  })

  pythonProcess.on('exit', (code) => {
    console.log(`[Python] 进程退出 code=${code}`)
    pythonProcess = null
  })

  const ready = await waitForBackend()
  if (ready) {
    console.log('[Electron] Python 后端已就绪')
  } else {
    console.error('[Electron] Python 后端未在超时时间内就绪')
  }
  return ready
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

/** 后端起不来时给用户的排查提示（区分开发态与打包态）。 */
function buildBackendErrorHint() {
  if (backendStartError) {
    return '无法启动后端进程：\n\n' + backendStartError +
      '\n\n请确认安装完整，并检查安全软件是否拦截了 novel-backend.exe。'
  }
  if (!app.isPackaged) {
    return '开发模式下后端未能就绪。\n\n请先安装后端依赖：\n' +
      '    pip install -r backend/requirements.txt\n\n' +
      `并确认端口 ${BACKEND_PORT} 未被占用。`
  }
  return `后端未能在超时时间内就绪。\n\n可能原因：\n` +
    `1. 端口 ${BACKEND_PORT} 被其他程序占用\n` +
    `2. 程序目录中的后端文件缺失，或被安全软件隔离\n\n` +
    `请关闭占用该端口的程序后重试。`
}

app.whenReady().then(async () => {
  // 先等后端就绪再开窗：本地后端通常 1-3 秒起好，
  // 这样用户看到界面时它已经可用，不会出现首屏接口全红。
  const ready = await startPythonBackend()
  if (!ready) {
    dialog.showErrorBox('AI 小说工厂 — 后端启动失败', buildBackendErrorHint())
    app.quit()
    return
  }

  createWindow()

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      if (!(await checkBackendRunning())) {
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
