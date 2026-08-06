import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

function loadConfigPort(): number {
  try {
    const configPath = path.resolve(__dirname, 'sigma.config.json')
    const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
    return config.frontendPort || 5173
  } catch { return 5173 }
}

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
  },
  server: {
    port: loadConfigPort(),
    strictPort: true,
  },
  optimizeDeps: {
    include: ['mammoth', 'xlsx'],
  },
})
