const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')

let chokidar = null
try { chokidar = require('chokidar') } catch (e) { console.error('[Electron] chokidar not available:', e.message) }

let electron, app, BrowserWindow, ipcMain, Menu, dialog, nativeTheme, protocol, net, shell, nativeImage

try {
  electron = require('electron')
  app = electron.app
  BrowserWindow = electron.BrowserWindow
  ipcMain = electron.ipcMain
  Menu = electron.Menu
  dialog = electron.dialog
  nativeTheme = electron.nativeTheme
  protocol = electron.protocol
  net = electron.net
  shell = electron.shell
  nativeImage = electron.nativeImage
} catch (error) {
  console.error('[ERROR] Failed to load Electron:', error)
  process.exit(1)
}

app.setPath('userData', path.join(process.cwd(), '.electron-user-data'))
app.commandLine.appendSwitch('no-sandbox')

let pythonProcess = null
let mainWindow = null
let splashWindow = null
let currentWorkingDir = process.cwd()
let workspaceDirs = [process.cwd()]  // 工作区目录列表（主目录 + 额外添加的）
let fileWatcher = null

const BACKEND_PORT = (() => {
  try {
    const configPath = path.join(process.cwd(), 'sigma.config.json')
    const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
    return config.backendPort || 8765
  } catch { return 8765 }
})()
const FRONTEND_PORT = (() => {
  try {
    const configPath = path.join(process.cwd(), 'sigma.config.json')
    const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
    return config.frontendPort || 5173
  } catch { return 5173 }
})()
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`

// 恢复上次保存的工作目录
const SAVED_WORKING_DIR = (() => {
  try {
    const configPath = path.join(process.cwd(), 'sigma.config.json')
    const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
    if (config.workingDirectory && fs.existsSync(config.workingDirectory)) {
      const stat = fs.statSync(config.workingDirectory)
      if (stat.isDirectory()) return config.workingDirectory
    }
  } catch {}
  return null
})()

if (SAVED_WORKING_DIR) {
  currentWorkingDir = SAVED_WORKING_DIR
  workspaceDirs = [SAVED_WORKING_DIR]
  console.log('[Electron] Restored working directory:', SAVED_WORKING_DIR)
}

const IGNORED_DIRECTORY_NAMES = new Set([
  '.git', '.vscode', '.idea', '.electron-user-data', '.sigma2.0', 'node_modules', '__pycache__', 'dist', 'build', 'logs'
])

const WATCHER_IGNORED_PATTERNS = [
  /(^|[\/\\])\../,
  ...Array.from(IGNORED_DIRECTORY_NAMES).map(name =>
    new RegExp(`(^|[\\/])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([\\/]|$)`)
  )
]

// ── Python Backend ──

function findPythonCommand() {
  // 跨平台探测可用 Python 命令: macos 通常用 python3, Windows 用 python 或 py
  const { execSync } = require('child_process')
  const candidates = process.platform === 'win32'
    ? ['python', 'py', 'python3']
    : ['python3', 'python']
  for (const cmd of candidates) {
    try {
      execSync(`${cmd} --version`, { stdio: 'ignore', timeout: 3000 })
      console.log(`[Electron] Found Python: ${cmd}`)
      return cmd
    } catch {}
  }
  // 全部失败时回退到通用逻辑: win32 用 python, 否则用 python3
  return process.platform === 'win32' ? 'python' : 'python3'
}

function findLibreOffice() {
  const binary = process.platform === 'win32' ? 'soffice.exe' : 'soffice'

  // 1. 优先用 which / where 在 PATH 中查找
  try {
    const whichCmd = process.platform === 'win32' ? 'where' : 'which'
    const result = require('child_process').execSync(`${whichCmd} ${binary}`, { encoding: 'utf-8', timeout: 3000 }).trim()
    const firstLine = result.split(/\r?\n/)[0].trim()
    if (firstLine && require('fs').existsSync(firstLine)) {
      console.log(`[LibreOffice] Found in PATH: ${firstLine}`)
      return firstLine
    }
  } catch {}

  // 2. 直接测试命令名（可能在 PATH 但 which 未找到）
  try {
    require('child_process').execFileSync(binary, ['--version'], { timeout: 5000, windowsHide: true })
    console.log(`[LibreOffice] Found via command: ${binary}`)
    return binary
  } catch {}

  // 3. 平台特定安装路径后备
  const fallbackPaths = process.platform === 'win32'
    ? [
        'C:\\Program Files\\LibreOffice\\program\\soffice.exe',
        'C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe',
      ]
    : process.platform === 'darwin'
      ? [
          '/Applications/LibreOffice.app/Contents/MacOS/soffice',
          '/opt/homebrew/bin/soffice',
          '/usr/local/bin/soffice',
        ]
      : [
          '/usr/bin/soffice',
          '/usr/local/bin/soffice',
          '/opt/libreoffice/program/soffice',
          '/snap/bin/soffice',
        ]

  for (const p of fallbackPaths) {
    try {
      require('child_process').execFileSync(p, ['--version'], { timeout: 5000 })
      console.log(`[LibreOffice] Found at: ${p}`)
      return p
    } catch {}
  }

  return null
}

function startPythonBackend() {
  const pythonCmd = findPythonCommand()
  pythonProcess = spawn(pythonCmd, ['-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', PYTHONUNBUFFERED: '1' }
  })
  pythonProcess.stdout.on('data', (data) => console.log(`[Python] ${data.toString().trim()}`))
  pythonProcess.stderr.on('data', (data) => console.log(`[Python] ${data.toString().trim()}`))
  pythonProcess.on('close', (code) => console.log(`[Electron] Python exited: ${code}`))
}

async function waitForBackend(maxRetries = 30) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 1000)
      const resp = await fetch(`${BACKEND_URL}/api/health`, { signal: controller.signal })
      clearTimeout(timeout)
      if (resp.ok) { console.log(`[Electron] Backend ready! (${i + 1})`); return true }
    } catch {}
    await new Promise(r => setTimeout(r, 500))
  }
  return false
}

// ── File Type Detection ──

function getFileType(ext) {
  if (['.docx'].includes(ext)) return 'docx'
  if (['.xlsx', '.xls'].includes(ext)) return 'xlsx'
  if (['.pptx', '.ppt'].includes(ext)) return 'pptx'
  if (['.pdf'].includes(ext)) return 'pdf'
  if (['.md', '.markdown'].includes(ext)) return 'markdown'
  if (['.py'].includes(ext)) return 'python'
  if (['.js', '.jsx'].includes(ext)) return 'javascript'
  if (['.ts', '.tsx'].includes(ext)) return 'typescript'
  if (['.java'].includes(ext)) return 'java'
  if (['.cpp', '.cc', '.cxx'].includes(ext)) return 'cpp'
  if (['.c', '.h'].includes(ext)) return 'c'
  if (['.cs'].includes(ext)) return 'csharp'
  if (['.go'].includes(ext)) return 'go'
  if (['.rs'].includes(ext)) return 'rust'
  if (['.html', '.htm'].includes(ext)) return 'html'
  if (['.css', '.scss', '.less'].includes(ext)) return 'css'
  if (['.json'].includes(ext)) return 'json'
  if (['.xml'].includes(ext)) return 'xml'
  if (['.yaml', '.yml'].includes(ext)) return 'yaml'
  if (['.sh', '.bash'].includes(ext)) return 'shell'
  if (['.ps1'].includes(ext)) return 'powershell'
  if (['.bat', '.cmd'].includes(ext)) return 'batch'
  if (['.ini'].includes(ext)) return 'ini'
  if (['.toml'].includes(ext)) return 'toml'
  if (['.txt', '.log'].includes(ext)) return 'text'
  if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico'].includes(ext)) return 'image'
  if (['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v', '.ogv'].includes(ext)) return 'video'
  return 'file'
}

// ── sigma-file:// 协议辅助 ──

const SIGMA_FILE_MIME_TYPES = {
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.mov': 'video/quicktime',
  '.avi': 'video/x-msvideo',
  '.mkv': 'video/x-matroska',
  '.m4v': 'video/x-m4v',
  '.ogv': 'video/ogg',
  '.flv': 'video/x-flv',
  '.wmv': 'video/x-ms-wmv',
  '.pdf': 'application/pdf',
}

function resolveSigmaFilePath(requestUrl) {
  const raw = requestUrl.replace(/^sigma-file:\/\//, '')
  let filePath = decodeURIComponent(raw)
  // Windows 盘符路径（/C:/... 或 /C:\...）去掉前导斜杠
  if (/^\/[a-zA-Z]:/.test(filePath)) filePath = filePath.slice(1)
  return filePath
}

// 启动时清空画布数据，让每次启动都从空白画布开始
function clearAllCanvases() {
  try {
    const canvasDir = path.join(currentWorkingDir, '.sigma2.0', 'canvases')
    if (fs.existsSync(canvasDir)) {
      fs.rmSync(canvasDir, { recursive: true, force: true })
      console.log('[Canvas] 启动时已清空画布:', canvasDir)
    }
  } catch (err) {
    console.error('[Canvas] 清空画布失败:', err.message)
  }
}

// ── File Tree Scanner ──

function scanDirectory(dirPath) {
  const result = []
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true })
    for (const entry of entries) {
      // 跳过隐藏目录（如 .git, .venv）和忽略列表中的目录，但保留隐藏文件（如 .env, .gitignore）
      if ((entry.name.startsWith('.') && entry.isDirectory()) || IGNORED_DIRECTORY_NAMES.has(entry.name)) continue
      const fullPath = path.join(dirPath, entry.name)
      if (entry.isDirectory()) {
        result.push({ name: entry.name, type: 'folder', path: fullPath, children: scanDirectory(fullPath) })
      } else {
        const ext = path.extname(entry.name).toLowerCase()
        result.push({ name: entry.name, type: getFileType(ext), path: fullPath })
      }
    }
  } catch (err) {
    console.error('[FileTree] Scan error:', err.message)
  }
  return result.sort((a, b) => {
    if (a.type === 'folder' && b.type !== 'folder') return -1
    if (a.type !== 'folder' && b.type === 'folder') return 1
    return a.name.localeCompare(b.name)
  })
}

// ── File Watcher ──

function startFileWatcher() {
  if (!chokidar) { console.log('[FileWatcher] chokidar unavailable, skipping'); return }
  stopFileWatcher()
  if (workspaceDirs.length === 0) return

  fileWatcher = chokidar.watch(workspaceDirs, {
    ignored: WATCHER_IGNORED_PATTERNS,
    persistent: true,
    ignoreInitial: true,
    awaitWriteFinish: { stabilityThreshold: 100, pollInterval: 50 },
    depth: 99
  })

  const send = (type, filePath, extra = {}) => {
    if (!mainWindow || mainWindow.isDestroyed()) return
    const fileName = path.basename(filePath)
    const ext = path.extname(fileName).toLowerCase()
    mainWindow.webContents.send('file-system-change', {
      type, path: filePath, fullPath: filePath, name: fileName,
      fileType: getFileType(ext), isDirectory: false, timestamp: new Date().toISOString(), ...extra
    })
  }

  fileWatcher.on('add', (fp) => send('add', fp))
  fileWatcher.on('addDir', (fp) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'addDir', path: fp, name: path.basename(fp), fileType: 'folder', isDirectory: true })
    }
  })
  fileWatcher.on('unlink', (fp) => send('unlink', fp))
  fileWatcher.on('unlinkDir', (fp) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'unlinkDir', path: fp, isDirectory: true })
    }
  })
  fileWatcher.on('change', (fp) => send('change', fp))
  console.log('[FileWatcher] Watching:', workspaceDirs)
}

function stopFileWatcher() {
  if (fileWatcher) { fileWatcher.close(); fileWatcher = null }
}

// ── Config Persistence ──

function saveWorkingDirectory(dir) {
  try {
    const configPath = path.join(process.cwd(), 'sigma.config.json')
    const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
    config.workingDirectory = dir
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8')
  } catch (err) {
    console.error('[Electron] Failed to save working directory:', err.message)
  }
}

// ── Splash Screen ──

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 420, height: 360,
    frame: false,
    transparent: false,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    backgroundColor: '#1a1b1e',
    icon: path.join(__dirname, '..', 'icon.png'),
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  })
  splashWindow.loadFile(path.join(__dirname, 'splash.html'))
  splashWindow.center()
}

function updateSplash(step, text, done) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('splash-status', { step, text, done })
  }
}

function closeSplash() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close()
    splashWindow = null
  }
}

// ── Window ──

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1400, height: 900, minWidth: 1000, minHeight: 600,
    title: 'Sigma AI Assistant',
    show: false,
    icon: path.join(__dirname, '..', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: false },
  })

  const isDev = process.env.NODE_ENV === 'development'
  if (isDev) {
    mainWindow.loadURL(`http://localhost:${FRONTEND_PORT}`)
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.key === 'F12' && input.type === 'keyDown') {
      mainWindow.webContents.isDevToolsOpened() ? mainWindow.webContents.closeDevTools() : mainWindow.webContents.openDevTools()
    }
  })

  // 拦截 LLM 回复、Markdown 等渲染区域中的外部链接，阻止在 Electron 内跳转，改为系统默认浏览器打开
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('mailto:')) {
      shell.openExternal(url)
    }
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (url !== mainWindow.webContents.getURL()) {
      event.preventDefault()
      if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('mailto:')) {
        shell.openExternal(url)
      }
    }
  })

  mainWindow.on('closed', () => { mainWindow = null; stopFileWatcher() })
}

// ── IPC Handlers ──

ipcMain.handle('get-file-url', async (event, filePath) => {
  // 将本地路径转换为 sigma-file:// 协议 URL
  const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
  return { success: true, data: `sigma-file:///${encodeURI(fp)}` }
})

ipcMain.handle('get-backend-url', async () => ({ success: true, data: BACKEND_URL }))

ipcMain.handle('get-sigma-config', async () => {
  try {
    const configPath = path.join(process.cwd(), 'sigma.config.json')
    const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
    return { success: true, data: config }
  } catch { return { success: false, error: 'Failed to read config' } }
})

ipcMain.handle('save-sigma-config', async (event, newConfig) => {
  try {
    const configPath = path.join(process.cwd(), 'sigma.config.json')
    fs.writeFileSync(configPath, JSON.stringify(newConfig, null, 2), 'utf-8')
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('send-message', async (event, message, config) => {
  try {
    const body = { message, config, session_id: 'default', working_dir: currentWorkingDir, workspace_dirs: workspaceDirs }
    const response = await fetch(`${BACKEND_URL}/api/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    if (!response.ok) return { success: false, error: await response.text() }
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('check-backend', async () => {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/health`)
    return { success: true, data: await resp.json() }
  } catch (err) { return { success: false, error: err.message } }
})

// ── Theme ──

ipcMain.handle('get-native-theme', async () => {
  return { shouldUseDarkColors: nativeTheme.shouldUseDarkColors }
})

ipcMain.handle('on-native-theme-updated', (event) => {
  const handler = () => {
    if (event.sender && !event.sender.isDestroyed()) {
      event.sender.send('native-theme-updated', { shouldUseDarkColors: nativeTheme.shouldUseDarkColors })
    }
  }
  nativeTheme.on('updated', handler)
  event.sender.once('destroyed', () => nativeTheme.removeListener('updated', handler))
})

// ── Notification ──

ipcMain.handle('is-window-focused', async () => {
  return mainWindow && !mainWindow.isDestroyed() && mainWindow.isFocused()
})

ipcMain.handle('show-notification', async (event, title, body) => {
  try {
    const { Notification } = require('electron')
    const n = new Notification({ title, body, silent: true })
    n.show()
    return true
  } catch (err) {
    console.error('[Notification] Failed:', err.message)
    return false
  }
})

ipcMain.handle('get-system-sounds', async () => {
  try {
    if (process.platform === 'win32') {
      const dir = 'C:\\Windows\\Media'
      if (!fs.existsSync(dir)) return []
      return fs.readdirSync(dir)
        .filter(f => f.toLowerCase().endsWith('.wav'))
        .map(f => ({ name: f.replace(/\.wav$/i, ''), path: path.join(dir, f) }))
    } else if (process.platform === 'darwin') {
      const dir = '/System/Library/Sounds'
      if (!fs.existsSync(dir)) return []
      return fs.readdirSync(dir)
        .filter(f => f.toLowerCase().endsWith('.aiff') || f.toLowerCase().endsWith('.wav'))
        .map(f => ({ name: f.replace(/\.(aiff|wav)$/i, ''), path: path.join(dir, f) }))
    }
    return []
  } catch (err) {
    console.error('[Sounds] Failed to list:', err.message)
    return []
  }
})

ipcMain.handle('preview-sound', async (event, soundPath) => {
  try {
    if (process.platform === 'win32') {
      const { execSync } = require('child_process')
      execSync(
        `powershell -Command "(New-Object System.Media.SoundPlayer '${soundPath.replace(/'/g, "''")}').PlaySync()"`,
        { timeout: 10000, windowsHide: true }
      )
    } else if (process.platform === 'darwin') {
      const { execFileSync } = require('child_process')
      execFileSync('afplay', [soundPath], { timeout: 10000 })
    }
    return true
  } catch (err) {
    console.error('[Sound Preview] Failed:', err.message)
    return false
  }
})

ipcMain.handle('get-folder-tree', async () => {
  try {
    // 返回多个工作区目录的树，每个作为 workspace-folder 根节点
    const data = workspaceDirs.map(dirPath => ({
      name: path.basename(dirPath),
      type: 'workspace-folder',
      path: dirPath,
      children: scanDirectory(dirPath),
    }))
    return { success: true, data, rootPath: currentWorkingDir }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('canvas-list', async () => {
  try {
    const canvasDir = path.join(currentWorkingDir, '.sigma2.0', 'canvases')
    if (!fs.existsSync(canvasDir)) return { success: true, data: ['default'] }
    const canvases = fs.readdirSync(canvasDir)
      .filter(file => file.endsWith('.excalidraw'))
      .map(file => path.basename(file, '.excalidraw'))
    return { success: true, data: [...new Set(['default', ...canvases])] }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('canvas-load', async (event, name) => {
  try {
    const safeName = path.basename(String(name || 'default'))
    const canvasDir = path.join(currentWorkingDir, '.sigma2.0', 'canvases')
    const canvasPath = path.join(canvasDir, `${safeName}.excalidraw`)
    if (!fs.existsSync(canvasPath)) return { success: true, data: null }
    return { success: true, data: JSON.parse(fs.readFileSync(canvasPath, 'utf8')) }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('canvas-save', async (event, name, data) => {
  try {
    const safeName = path.basename(String(name || 'default'))
    const canvasDir = path.join(currentWorkingDir, '.sigma2.0', 'canvases')
    fs.mkdirSync(canvasDir, { recursive: true })
    const canvasPath = path.join(canvasDir, `${safeName}.excalidraw`)
    fs.writeFileSync(canvasPath, JSON.stringify(data), 'utf8')
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('read-file', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    const ext = path.extname(fp).toLowerCase()
    const binaryExts = ['.pdf', '.docx', '.xlsx', '.pptx', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico']
    const videoExts = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v', '.ogv']
    if (videoExts.includes(ext)) {
      // 视频文件不读内容，由前端通过 sigma-file:// 协议直接加载
      return { success: true, data: fp, isVideo: true }
    }
    if (binaryExts.includes(ext)) {
      const buf = fs.readFileSync(fp)
      return { success: true, data: buf.toString('base64'), isBinary: true }
    }
    return { success: true, data: fs.readFileSync(fp, 'utf-8'), isBinary: false }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('read-file-as-base64', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    const buf = fs.readFileSync(fp)
    return { success: true, data: buf.toString('base64') }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-write', async (event, filePath, content) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    if (typeof content !== 'string') return { success: false, error: 'content_must_be_string' }
    fs.writeFileSync(fp, content, 'utf-8')
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'change', path: fp })
    }
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('get-working-directory', async () => ({ success: true, data: currentWorkingDir }))

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
    title: 'Select Working Folder',
  })
  if (!result.canceled && result.filePaths.length > 0) {
    return { success: true, data: result.filePaths[0] }
  }
  return { success: false, error: 'No folder selected' }
})

ipcMain.handle('change-directory', async (event, newDir) => {
  try {
    if (!newDir || !require('fs').existsSync(newDir)) {
      return { success: false, error: 'Directory not found' }
    }
    currentWorkingDir = newDir
    workspaceDirs = [newDir]  // 切换目录时清空额外的文件夹
    saveWorkingDirectory(newDir)
    stopFileWatcher()
    if (pythonProcess) {
      pythonProcess.kill()
      pythonProcess = null
      await new Promise(r => setTimeout(r, 1500))
    }
    startPythonBackend()
    const ready = await waitForBackend(60)
    if (ready) startFileWatcher()
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('directory-changed', { path: newDir, changed: true })
    }
    return { success: true, data: newDir }
  } catch (err) {
    return { success: false, error: err.message }
  }
})

ipcMain.handle('add-directory', async (event, newDir) => {
  try {
    if (!newDir || !require('fs').existsSync(newDir)) {
      return { success: false, error: 'Directory not found' }
    }
    if (workspaceDirs.includes(newDir)) {
      return { success: false, error: 'Directory already in workspace' }
    }
    workspaceDirs.push(newDir)
    startFileWatcher()
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('directory-changed', { path: newDir })
    }
    console.log('[Electron] Added workspace dir:', newDir)
    return { success: true, data: newDir }
  } catch (err) {
    return { success: false, error: err.message }
  }
})

ipcMain.handle('remove-directory', async (event, dirPath) => {
  try {
    const idx = workspaceDirs.indexOf(dirPath)
    if (idx < 0) return { success: false, error: 'Directory not in workspace' }
    if (workspaceDirs.length <= 1) return { success: false, error: 'Cannot remove last workspace folder' }
    workspaceDirs.splice(idx, 1)
    startFileWatcher()
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('directory-changed', { path: dirPath })
    }
    console.log('[Electron] Removed workspace dir:', dirPath)
    return { success: true }
  } catch (err) {
    return { success: false, error: err.message }
  }
})

ipcMain.handle('get-workspace-directories', async () => {
  return { success: true, data: workspaceDirs }
})

ipcMain.handle('file-open', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    await electron.shell.openPath(fp)
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-show-in-folder', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    electron.shell.showItemInFolder(fp)
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-delete', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    const stat = fs.statSync(fp)
    if (stat.isDirectory()) {
      fs.rmSync(fp, { recursive: true, force: true })
    } else {
      fs.unlinkSync(fp)
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'delete', path: fp })
    }
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-create', async (event, parentDir, name) => {
  try {
    const dir = path.isAbsolute(parentDir) ? parentDir : path.join(currentWorkingDir, parentDir)
    const fp = path.join(dir, name)
    if (fs.existsSync(fp)) return { success: false, error: 'already_exists' }
    fs.writeFileSync(fp, '')
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'add', path: fp })
    }
    return { success: true, path: fp }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('folder-create', async (event, parentDir, name) => {
  try {
    const dir = path.isAbsolute(parentDir) ? parentDir : path.join(currentWorkingDir, parentDir)
    const fp = path.join(dir, name)
    if (fs.existsSync(fp)) return { success: false, error: 'already_exists' }
    fs.mkdirSync(fp, { recursive: true })
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'addDir', path: fp, isDirectory: true })
    }
    return { success: true, path: fp }
  } catch (err) { return { success: false, error: err.message } }
})

// 递归复制文件/文件夹，重名时自动追加序号
function copyRecursive(src, dest) {
  const stat = fs.statSync(src)
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true })
    for (const entry of fs.readdirSync(src)) {
      copyRecursive(path.join(src, entry), path.join(dest, entry))
    }
  } else {
    fs.copyFileSync(src, dest)
  }
}

function uniqueDestPath(destDir, name) {
  let candidate = path.join(destDir, name)
  if (!fs.existsSync(candidate)) return candidate
  const ext = path.extname(name)
  const base = path.basename(name, ext)
  for (let i = 1; ; i++) {
    candidate = path.join(destDir, `${base} (${i})${ext}`)
    if (!fs.existsSync(candidate)) return candidate
  }
}

// ── Drag & Drop ──

ipcMain.on('ondragstart', (event, filePath) => {
  // Electron 17+ 要求 icon 必须提供，用一个 1x1 透明 PNG 占位
  // Windows 会自动替换成系统文件图标
  const icon = nativeImage.createFromBuffer(Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    'base64'
  ))
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    if (fs.existsSync(fp)) {
      // 用 event.sender 而不是 mainWindow，确保在正确的 webContents 上同步执行
      event.sender.startDrag({ file: fp, icon })
    }
  } catch (err) {
    console.error('[DragOut] startDrag failed:', err)
  }
})

// 外部文件复制/移动到工作区（处理同盘 rename 和跨盘 copy 两种情况）
ipcMain.handle('file-copy', async (event, sourcePaths, targetDir) => {
  try {
    const sources = Array.isArray(sourcePaths) ? sourcePaths : [sourcePaths]
    const target = path.isAbsolute(targetDir) ? targetDir : path.join(currentWorkingDir, targetDir)
    if (!fs.existsSync(target) || !fs.statSync(target).isDirectory()) {
      return { success: false, error: 'target_not_found' }
    }

    const resolvedSources = sources.map(s =>
      path.isAbsolute(s) ? s : path.join(currentWorkingDir, s)
    )

    // 校验所有源文件
    for (const src of resolvedSources) {
      if (!fs.existsSync(src)) return { success: false, error: 'source_not_found' }
    }

    // 检查同名冲突
    const conflicts = resolvedSources
      .map(src => path.join(target, path.basename(src)))
      .filter(dest => fs.existsSync(dest))
    if (conflicts.length > 0) {
      return { success: false, error: 'already_exists', conflicts }
    }

    // 同盘 rename（快）/ 跨盘 copy+delete（递归）
    for (const src of resolvedSources) {
      const dest = path.join(target, path.basename(src))
      try {
        fs.renameSync(src, dest)
      } catch {
        copyRecursive(src, dest)
        if (fs.statSync(src).isDirectory()) {
          fs.rmSync(src, { recursive: true, force: true })
        } else {
          fs.unlinkSync(src)
        }
      }
    }

    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', {
        type: 'move', paths: resolvedSources, targetDir: target,
      })
    }
    return { success: true, count: resolvedSources.length }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-paste', async (event, sourcePath, targetDir) => {
  try {
    const src = path.isAbsolute(sourcePath) ? sourcePath : path.join(currentWorkingDir, sourcePath)
    const dir = path.isAbsolute(targetDir) ? targetDir : path.join(currentWorkingDir, targetDir)
    if (!fs.existsSync(src)) return { success: false, error: 'source_not_found' }
    const dest = uniqueDestPath(dir, path.basename(src))
    copyRecursive(src, dest)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'add', path: dest })
    }
    return { success: true, path: dest }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('copy-path', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    electron.clipboard.writeText(fp)
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-rename', async (event, filePath, newName) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    const newPath = path.join(path.dirname(fp), newName)
    fs.renameSync(fp, newPath)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', { type: 'rename', path: newPath, oldPath: fp })
    }
    return { success: true, newPath }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-move', async (event, sourcePaths, targetDir) => {
  try {
    const sources = Array.isArray(sourcePaths) ? sourcePaths : [sourcePaths]
    const target = path.isAbsolute(targetDir) ? targetDir : path.join(currentWorkingDir, targetDir)
    if (!fs.existsSync(target) || !fs.statSync(target).isDirectory()) {
      return { success: false, error: 'target_not_found' }
    }

    const resolvedSources = sources.map(sourcePath => (
      path.isAbsolute(sourcePath) ? sourcePath : path.join(currentWorkingDir, sourcePath)
    ))

    for (const source of resolvedSources) {
      if (!fs.existsSync(source)) return { success: false, error: 'source_not_found' }
      if (path.resolve(source) === path.resolve(target)) return { success: false, error: 'same_location' }
      if (fs.statSync(source).isDirectory()) {
        const relativeTarget = path.relative(source, target)
        if (relativeTarget && !relativeTarget.startsWith('..') && !path.isAbsolute(relativeTarget)) {
          return { success: false, error: 'invalid_target' }
        }
      }
    }

    const conflicts = resolvedSources
      .map(source => path.join(target, path.basename(source)))
      .filter(destination => fs.existsSync(destination))
    if (conflicts.length > 0) {
      return { success: false, error: 'already_exists', conflicts }
    }

    for (const source of resolvedSources) {
      fs.renameSync(source, path.join(target, path.basename(source)))
    }

    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('file-system-change', {
        type: 'move', paths: resolvedSources, targetDir: target,
      })
    }
    return { success: true, count: resolvedSources.length }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('file-add-to-chat', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    const stat = fs.statSync(fp)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('add-file-to-chat', {
        path: filePath, fullPath: fp, name: path.basename(fp),
        type: stat.isDirectory() ? 'folder' : 'file', isDirectory: stat.isDirectory()
      })
    }
    return { success: true }
  } catch (err) { return { success: false, error: err.message } }
})

ipcMain.handle('convert-pptx', async (event, filePath) => {
  try {
    const fp = path.isAbsolute(filePath) ? filePath : path.join(currentWorkingDir, filePath)
    console.log('[PPTX] Converting:', fp)

    // ── 方案1: node-pptx-png-v2 (纯 JS, 更可靠的 slide 渲染) ──
    try {
      const { PptxImageRenderer } = await import('node-pptx-png-v2')
      const os = require('os')
      const crypto = require('crypto')
      const tempDir = path.join(os.tmpdir(), 'sigma-pptx-' + crypto.randomBytes(8).toString('hex'))
      fs.mkdirSync(tempDir, { recursive: true })

      const renderer = new PptxImageRenderer()
      const result = await renderer.renderPresentation(fp, {
        outputDir: tempDir,
        format: 'png',
        scale: 2
      })

      if (result.slides && result.slides.length > 0) {
        const images = []
        for (const slide of result.slides) {
          if (slide.success && slide.imageData) {
            images.push(slide.imageData.toString('base64'))
          } else {
            console.warn(`[PPTX] Slide ${slide.slideNumber} failed:`, slide.errorMessage || 'unknown error')
          }
        }
        try { fs.rmSync(tempDir, { recursive: true, force: true }) } catch {}
        if (images.length > 0) {
          console.log('[PPTX] Converted', images.length, 'slides via node-pptx-png-v2')
          return { success: true, images }
        }
      }
    } catch (e1) {
      console.log('[PPTX] node-pptx-png-v2 failed:', e1.message)
    }

    // ── 方案2: LibreOffice 降级 (跨平台, 需要预装) ──
    try {
      const { execFileSync } = require('child_process')
      const os = require('os')
      const crypto = require('crypto')
      const tempDir = path.join(os.tmpdir(), 'sigma-pptx-' + crypto.randomBytes(8).toString('hex'))
      fs.mkdirSync(tempDir, { recursive: true })

      const libreCmd = findLibreOffice()
      if (!libreCmd) throw new Error('LibreOffice not found')

      execFileSync(libreCmd, ['--headless', '--convert-to', 'png', '--outdir', tempDir, fp], { timeout: 120000, windowsHide: true })

      const files = fs.readdirSync(tempDir)
        .filter(f => f.toLowerCase().endsWith('.png'))
        .sort((a, b) => {
          const na = parseInt(a.match(/\d+/)?.[0] || '0')
          const nb = parseInt(b.match(/\d+/)?.[0] || '0')
          return na - nb
        })
      const images = files.map(f => fs.readFileSync(path.join(tempDir, f)).toString('base64'))
      try { fs.rmSync(tempDir, { recursive: true, force: true }) } catch {}

      if (images.length > 0) {
        console.log('[PPTX] Converted', images.length, 'slides via LibreOffice')
        return { success: true, images }
      }
    } catch (e2) {
      console.log('[PPTX] LibreOffice failed:', e2.message)
    }

    return { success: false, error: 'PPTX conversion failed: no converter available (node-pptx-png-v2 or LibreOffice required)' }
  } catch (err) {
    console.error('[PPTX] Error:', err.message)
    return { success: false, error: err.message }
  }
})

// ── App Lifecycle ──

app.whenReady().then(async () => {
  // 注册 sigma-file:// 自定义协议，用于视频/PDF 等大型二进制文件流式加载
  // 手动处理 MIME 类型 + Range 请求，保证 <video> 能正常播放/拖动进度，以及 PDF 大文件能被 iframe 加载
  protocol.handle('sigma-file', (request) => {
    try {
      const filePath = resolveSigmaFilePath(request.url)
      if (!fs.existsSync(filePath)) {
        return new Response('File not found', { status: 404 })
      }
      const stat = fs.statSync(filePath)
      const mime = SIGMA_FILE_MIME_TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream'
      const rangeHeader = request.headers.get('range')

      if (rangeHeader) {
        const m = rangeHeader.match(/bytes=(\d*)-(\d*)/)
        if (m) {
          let start = m[1] ? parseInt(m[1], 10) : 0
          let end = m[2] ? parseInt(m[2], 10) : stat.size - 1
          if (Number.isNaN(start)) start = 0
          if (Number.isNaN(end) || end >= stat.size) end = stat.size - 1
          if (start > end || start >= stat.size) {
            return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${stat.size}` } })
          }
          const chunkSize = end - start + 1
          const fd = fs.openSync(filePath, 'r')
          const buf = Buffer.alloc(chunkSize)
          fs.readSync(fd, buf, 0, chunkSize, start)
          fs.closeSync(fd)
          return new Response(new Uint8Array(buf), {
            status: 206,
            headers: {
              'Content-Type': mime,
              'Content-Length': String(chunkSize),
              'Content-Range': `bytes ${start}-${end}/${stat.size}`,
              'Accept-Ranges': 'bytes',
            },
          })
        }
      }

      const data = fs.readFileSync(filePath)
      return new Response(new Uint8Array(data), {
        headers: {
          'Content-Type': mime,
          'Content-Length': String(stat.size),
          'Accept-Ranges': 'bytes',
        },
      })
    } catch (err) {
      return new Response('Error: ' + err.message, { status: 500 })
    }
  })

  Menu.setApplicationMenu(null)

  // 启动时清空画布，让每次启动都从空白画布开始
  clearAllCanvases()

  // Show splash screen
  createSplashWindow()

  // Start backend BEFORE creating main window, so frontend doesn't fail on first fetch
  updateSplash('backend', 'Starting Python backend...', false)
  startPythonBackend()

  // Wait for backend
  updateSplash('wait', 'Waiting for backend...', false)
  await waitForBackend(30)
  updateSplash('wait', 'Backend ready', true)

  // Create main window (hidden) — backend is already ready
  createMainWindow()
  let splashDone = false
  const splashMinTime = new Promise(r => setTimeout(r, 5000))
  mainWindow.once('ready-to-show', async () => {
    await splashMinTime
    if (!splashDone) {
      splashDone = true
      closeSplash()
      mainWindow.show()
      mainWindow.focus()
    }
  })
  // Safety: force close splash after 15s even if ready-to-show doesn't fire
  setTimeout(async () => {
    if (!splashDone) {
      splashDone = true
      closeSplash()
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show()
    }
  }, 15000)

  // Start services
  updateSplash('frontend', 'Loading user interface...', false)
  startFileWatcher()

  // Frontend loading is handled by ready-to-show event above
  updateSplash('frontend', 'User interface loaded', true)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow()
  })
})

app.on('window-all-closed', () => {
  saveWorkingDirectory(currentWorkingDir)
  stopFileWatcher()
  if (pythonProcess) pythonProcess.kill()
  if (process.platform !== 'darwin') app.quit()
})
