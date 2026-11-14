// Electron dev startup script - reads sigma.config.json and orchestrates Vite + Electron
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')

const ROOT = path.join(__dirname, '..')

function loadConfig() {
  try {
    const configPath = path.join(ROOT, 'sigma.config.json')
    return JSON.parse(fs.readFileSync(configPath, 'utf-8'))
  } catch {
    return { backendPort: 8765, frontendPort: 5173 }
  }
}

const config = loadConfig()
const frontendPort = config.frontendPort || 5173

console.log(`[Dev] Frontend port: ${frontendPort}, Backend port: ${config.backendPort || 8765}`)

// Start Vite dev server
const vite = spawn('npx', ['vite', '--port', String(frontendPort)], {
  cwd: ROOT,
  stdio: 'inherit',
  shell: true,
  env: { ...process.env },
})

// Poll until Vite is ready, then start Electron
const viteUrl = `http://localhost:${frontendPort}`
const maxRetries = 60
let retries = 0

async function waitForVite() {
  while (retries < maxRetries) {
    try {
      const resp = await fetch(viteUrl)
      if (resp.ok) {
        console.log(`[Dev] Vite ready at ${viteUrl}`)
        startElectron()
        return
      }
    } catch {}
    await new Promise(r => setTimeout(r, 1000))
    retries++
  }
  console.error('[Dev] Vite failed to start')
  process.exit(1)
}

function startElectron() {
  // Electron 30 in this project's node_modules fails to boot on some machines
  // (the browser process aborts before app code runs). A working distribution
  // can be supplied through SIGMA_ELECTRON_DIST; Electron's own resolver then
  // uses that directory instead of the project-pinned binary.
  const override = process.env.SIGMA_ELECTRON_DIST
  const env = { ...process.env, NODE_ENV: 'development' }
  if (override) {
    env.ELECTRON_OVERRIDE_DIST_PATH = override
    console.log(`[Dev] Electron dist override: ${override}`)
  }
  const electron = spawn('npx', ['electron', '.'], {
    cwd: ROOT,
    stdio: 'inherit',
    shell: true,
    env,
  })

  electron.on('close', (code) => {
    vite.kill()
    process.exit(code)
  })
}

waitForVite()

process.on('SIGINT', () => {
  vite.kill()
  process.exit(0)
})
process.on('SIGTERM', () => {
  vite.kill()
  process.exit(0)
})
