// Packaged-mode launcher: `electron .` serves dist/index.html (the file:// origin
// that holds the user's saved configuration).
//
// The project-pinned Electron fails to boot on this machine, so a working
// distribution is selected through SIGMA_ELECTRON_DIST and forwarded to
// Electron's own resolver via ELECTRON_OVERRIDE_DIST_PATH.
const path = require('node:path')
const fs = require('node:fs')
const { spawn } = require('node:child_process')

const root = path.join(__dirname, '..')
const env = { ...process.env }

const override = process.env.SIGMA_ELECTRON_DIST
if (override && fs.existsSync(override)) {
  env.ELECTRON_OVERRIDE_DIST_PATH = override
  console.log(`[Electron] dist override: ${override}`)
}

const electronCli = path.join(root, 'node_modules', 'electron', 'cli.js')
const child = spawn(process.execPath, [electronCli, '.', ...process.argv.slice(2)], {
  cwd: root,
  stdio: 'inherit',
  env,
})

child.on('exit', (code) => process.exit(code ?? 0))
child.on('error', (error) => {
  console.error(`[Electron] launch failed: ${error.message}`)
  process.exit(1)
})
