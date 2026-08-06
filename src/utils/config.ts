import type { SigmaConfig } from '../types/electron'

const DEFAULT_CONFIG: SigmaConfig = { backendPort: 8765, frontendPort: 5173 }

let cachedBackendUrl: string | null = null

export async function getBackendUrl(): Promise<string> {
  if (cachedBackendUrl) return cachedBackendUrl

  if (window.electronAPI?.getBackendUrl) {
    const result = await window.electronAPI.getBackendUrl()
    if (result.success && result.data) {
      cachedBackendUrl = result.data
      return cachedBackendUrl
    }
  }

  cachedBackendUrl = `http://127.0.0.1:${DEFAULT_CONFIG.backendPort}`
  return cachedBackendUrl
}

export async function getSigmaConfig(): Promise<SigmaConfig> {
  if (window.electronAPI?.getSigmaConfig) {
    const result = await window.electronAPI.getSigmaConfig()
    if (result.success && result.data) return result.data
  }
  return { ...DEFAULT_CONFIG }
}

export async function saveSigmaConfig(config: SigmaConfig): Promise<boolean> {
  cachedBackendUrl = null // invalidate cache
  if (window.electronAPI?.saveSigmaConfig) {
    const result = await window.electronAPI.saveSigmaConfig(config)
    return result.success
  }
  return false
}
