// Vite build wrapper.
//
// esbuild extracts its binary into TEMP and deletes it when the service stops.
// On this machine that delete is refused ("Access is denied"), because security
// software holds the freshly written executable, which aborts the whole build.
// Running with a project-local TEMP keeps that lifecycle inside the workspace.
const path = require('node:path')
const fs = require('node:fs')
const { spawnSync } = require('node:child_process')

const root = path.join(__dirname, '..')
const temp = path.join(root, '.build-temp')
fs.mkdirSync(temp, { recursive: true })

const vite = path.join(root, 'node_modules', 'vite', 'bin', 'vite.js')
const result = spawnSync(process.execPath, [vite, 'build', ...process.argv.slice(2)], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, TEMP: temp, TMP: temp },
})

process.exit(result.status ?? 1)
