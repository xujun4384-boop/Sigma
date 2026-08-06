import { useState, useCallback, useRef, useEffect } from 'react'
import ChatPanel, { type TerminalTab } from './components/ChatPanel'
import ErrorBoundary from './components/ErrorBoundary'
import ExplorerPanel from './components/ExplorerPanel'
import PreviewPanel from './components/PreviewPanel'
import Sidebar, { loadSystemSettings } from './components/Sidebar'
import ScanningOverlay from './components/ScanningOverlay'
import Onboarding from './components/Onboarding'
import { I18nProvider, getSavedLanguage, saveLanguage } from './i18n/I18nContext'
import type { Lang } from './i18n/translations'
import type { KimiConfig, LLMEntry, FolderTreeItem } from './types/electron'
import { getBackendUrl } from './utils/config'
import { loadAgents, syncAgentsToBackend } from './utils/agentStore'
import './App.css'

export type ThemeMode = 'dark' | 'light' | 'auto'

export interface FileDiffState {
  filePath: string
  fileName: string
  fileType: string
  diffData: any
  isModifying: boolean
}

const DEFAULT_KIMI_CONFIG: KimiConfig = {
  baseUrl: 'https://api.kimi.com/coding',
  apiKey: '',
  apiKey2: '',
  model: 'kimi-for-coding',
  protocol: 'anthropic',
  activeApiKey: 'key2',
  llms: [],
  activeLLMId: '',
  skillKeys: {
      tavilyApiKey: '',
      imageGenApiKey: '',
      imageGenBaseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
      webSearchProvider: 'kimi',
      webSearchApiKey: '',
      webSearchBaseUrl: '',
      visionApiKey: '',
       visionModel: 'kimi-for-coding',
       visionBaseUrl: 'https://api.moonshot.cn/anthropic',
      wechatAppId: '',
      wechatAppSecret: '',
      wechatRelayUrl: '',
      wechatRelayKey: '',
      fengniaoApiKey: '',
      flyaiApiKey: '',
    },
}

function loadKimiConfig(): KimiConfig {
  try {
    const saved = localStorage.getItem('sigma_kimi_config')
    if (saved) {
      const parsed = JSON.parse(saved)
      // 兼容旧版本没有 llms 数组
      if (!parsed.llms) parsed.llms = []
      if (!parsed.activeLLMId) parsed.activeLLMId = ''
      // 兼容旧版本 tavilyApiKey 在顶层 → 迁移到 skillKeys
      if (!parsed.skillKeys) {
        parsed.skillKeys = { ...DEFAULT_KIMI_CONFIG.skillKeys }
        if (parsed.tavilyApiKey) {
          parsed.skillKeys.tavilyApiKey = parsed.tavilyApiKey
        }
        delete parsed.tavilyApiKey
      }
      // 深度合并 skillKeys：老配置缺少新字段时用 DEFAULT 兜底
      parsed.skillKeys = { ...DEFAULT_KIMI_CONFIG.skillKeys, ...parsed.skillKeys }
      return { ...DEFAULT_KIMI_CONFIG, ...parsed }
    }
  } catch {}
  return DEFAULT_KIMI_CONFIG
}

export default function App() {
  const [config, setConfig] = useState<KimiConfig>(loadKimiConfig)
  const [systemSettings, setSystemSettings] = useState(loadSystemSettings)
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    try { return (localStorage.getItem('sigma_theme') as ThemeMode) || 'dark' } catch { return 'dark' }
  })
  const [language, setLanguage] = useState<Lang>(getSavedLanguage)
  const [leftWidth, setLeftWidth] = useState(480)
  const [rightWidth, setRightWidth] = useState(300)
  const [selectedFile, setSelectedFile] = useState<FolderTreeItem | null>(null)
  const [previewKey, setPreviewKey] = useState(0)
  const [chatResetKey, setChatResetKey] = useState(0)
  const [fileDiffQueue, setFileDiffQueue] = useState<FileDiffState[]>([])
  const [terminalTabs, setTerminalTabs] = useState<TerminalTab[]>([])

  // 项目扫描状态
  const [scanningPhase, setScanningPhase] = useState<'init' | 'scanning' | 'analyzing' | 'done' | null>(null)

  // 引导流程状态
  const [onboardingDone, setOnboardingDone] = useState(false)

  // 检查是否有有效的 API key
  const hasApiKey = (() => {
    if (config.activeLLMId && config.llms.length > 0) {
      const active = config.llms.find(l => l.id === config.activeLLMId)
      if (active?.apiKey) return true
    }
    if (config.apiKey || config.apiKey2) return true
    return false
  })()

  const isDraggingLeft = useRef(false)
  const isDraggingRight = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // 项目记忆扫描
  const runProjectScan = useCallback(async (workingDir: string) => {
    const baseUrl = await getBackendUrl()

    setScanningPhase('scanning')
    try {
      const resp = await fetch(`${baseUrl}/api/init-project-memory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ working_dir: workingDir }),
      })
      const data = await resp.json()
      if (data.scanned) {
        setScanningPhase('done')
        setTimeout(() => setScanningPhase(null), 1200)
      } else {
        setScanningPhase(null)
      }
    } catch {
      setScanningPhase(null)
    }
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const containerWidth = containerRef.current?.clientWidth || window.innerWidth
      if (isDraggingLeft.current) {
        setLeftWidth(Math.max(250, Math.min(containerWidth * 0.6, e.clientX)))
      }
      if (isDraggingRight.current) {
        const right = containerWidth - e.clientX
        setRightWidth(Math.max(200, Math.min(containerWidth * 0.5, right)))
      }
    }
    const onUp = () => { isDraggingLeft.current = false; isDraggingRight.current = false }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
  }, [])

  // 切换工作目录时清空展示区、聊天，并触发新目录扫描
  useEffect(() => {
    if (!window.electronAPI?.onDirectoryChange) return
    const cleanup = window.electronAPI.onDirectoryChange(async (data: { path?: string; changed?: boolean }) => {
      setSelectedFile(null)
      setPreviewKey(k => k + 1)
      if (data?.changed) {
        setChatResetKey(k => k + 1)
        if (data.path) {
          runProjectScan(data.path)
        }
      }
    })
    return cleanup
  }, [runProjectScan])

  // 主题: 初始化 data-theme 属性 + 监听系统主题变化
  useEffect(() => {
    const resolveTheme = (mode: ThemeMode, systemIsDark: boolean): 'dark' | 'light' => {
      if (mode === 'auto') return systemIsDark ? 'dark' : 'light'
      return mode
    }

    const systemDarkQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const applyTheme = () => {
      const resolved = resolveTheme(themeMode, systemDarkQuery.matches)
      document.documentElement.setAttribute('data-theme', resolved)
    }

    applyTheme()

    const onSystemChange = () => {
      if (themeMode === 'auto') applyTheme()
    }
    systemDarkQuery.addEventListener('change', onSystemChange)

    // Electron nativeTheme 监听（优先级高于 CSS media query）
    let cleanupNative: (() => void) | undefined
    if (window.electronAPI?.onNativeThemeUpdated) {
      cleanupNative = window.electronAPI.onNativeThemeUpdated((info) => {
        if (themeMode === 'auto') {
          document.documentElement.setAttribute('data-theme', info.shouldUseDarkColors ? 'dark' : 'light')
        }
      })
    }

    return () => {
      systemDarkQuery.removeEventListener('change', onSystemChange)
      if (cleanupNative) cleanupNative()
    }
  }, [themeMode])

  // 同步 LLM 配置和 settings 到服务端（供浏览器扩展面板使用）
  useEffect(() => {
    if (config.llms.length === 0) return

    let cancelled = false
    let retryCount = 0
    const MAX_RETRIES = 5
    const RETRY_DELAYS = [500, 1000, 2000, 4000, 8000] // 指数退避

    const doSync = async () => {
      if (cancelled) return
      try {
        const baseUrl = await getBackendUrl()
        const resp = await fetch(`${baseUrl}/api/network-bridge/sync-configs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            llms: config.llms,
            vision: {
              apiKey: config.skillKeys.visionApiKey,
              model: config.skillKeys.visionModel,
              baseUrl: config.skillKeys.visionBaseUrl,
            },
            maxIterations: systemSettings.maxIterations || 10,
          }),
        })
        if (resp.ok) {
          console.log('[SyncConfigs] LLM 配置已同步到后端')
          return // 成功，不再重试
        }
      } catch {
        // 后端可能尚未启动，重试
      }

      // 重试
      if (!cancelled && retryCount < MAX_RETRIES) {
        const delay = RETRY_DELAYS[retryCount]
        retryCount++
        console.log(`[SyncConfigs] 同步失败，${delay}ms 后重试 (${retryCount}/${MAX_RETRIES})`)
        setTimeout(doSync, delay)
      }
    }

    setTimeout(doSync, 500)

    return () => { cancelled = true }
  }, [config.llms, config.skillKeys.visionApiKey, config.skillKeys.visionModel, config.skillKeys.visionBaseUrl, systemSettings.maxIterations])

  const handleSaveConfig = useCallback((c: KimiConfig) => {
    setConfig(c)
    localStorage.setItem('sigma_kimi_config', JSON.stringify(c))
  }, [])

  const handleAddLLM = useCallback((entry: LLMEntry) => {
    setConfig(prev => {
      const next = { ...prev, llms: [...prev.llms, entry], activeLLMId: entry.id }
      localStorage.setItem('sigma_kimi_config', JSON.stringify(next))
      return next
    })
  }, [])

  const handleUpdateLLM = useCallback((entry: LLMEntry) => {
    setConfig(prev => {
      const next = { ...prev, llms: prev.llms.map(l => l.id === entry.id ? entry : l) }
      localStorage.setItem('sigma_kimi_config', JSON.stringify(next))
      return next
    })
  }, [])

  const handleRemoveLLM = useCallback((id: string) => {
    setConfig(prev => {
      const llms = prev.llms.filter(l => l.id !== id)
      const activeLLMId = prev.activeLLMId === id ? '' : prev.activeLLMId
      const next = { ...prev, llms, activeLLMId }
      localStorage.setItem('sigma_kimi_config', JSON.stringify(next))
      return next
    })
  }, [])

  const handleSelectLLM = useCallback((id: string) => {
    setConfig(prev => {
      const next = { ...prev, activeLLMId: id }
      localStorage.setItem('sigma_kimi_config', JSON.stringify(next))
      return next
    })
  }, [])

  const handleAcknowledgeDiff = useCallback(() => {
    setFileDiffQueue(prev => prev.slice(1))
  }, [])

  const handleAcknowledgeAllDiffs = useCallback(() => {
    setFileDiffQueue([])
  }, [])

  const handleOpenTerminal = useCallback((tab: TerminalTab) => {
    setTerminalTabs(prev => {
      const exists = prev.find(t => t.id === tab.id)
      if (exists) return prev
      return [...prev, tab]
    })
  }, [])

  const handleCloseTerminal = useCallback((id: string) => {
    setTerminalTabs(prev => prev.filter(t => t.id !== id))
  }, [])

  const handleFileModificationStart = useCallback(({ filePath, fileName, fileType }: { filePath: string; fileName: string; fileType: string }) => {
    setSelectedFile({ path: filePath, name: fileName, type: fileType } as FolderTreeItem)
    setFileDiffQueue(prev => {
      const idx = prev.findIndex(d => d.filePath === filePath)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], isModifying: true }
        return next
      }
      return prev
    })
  }, [])

  const handleFileDiffUpdate = useCallback(({ filePath, fileName, fileType, diffData }: { filePath: string; fileName: string; fileType: string; diffData: any }) => {
    const normalizedType = fileType === 'excel' ? 'xlsx' : fileType === 'word' ? 'docx' : fileType
    setSelectedFile({ path: filePath, name: fileName, type: normalizedType } as FolderTreeItem)
    setFileDiffQueue(prev => [...prev, { filePath, fileName, fileType: normalizedType, diffData, isModifying: true }])
  }, [])

  const handleFileModificationComplete = useCallback(({ filePath }: { filePath: string }) => {
    setFileDiffQueue(prev =>
      prev.map(d => d.filePath === filePath ? { ...d, isModifying: false } : d)
    )
  }, [])

  const handleSaveSystem = useCallback((s: { maxIterations: number; subAgentMaxTurns: number; backupEnabled: boolean; notifySound: string }) => {
    setSystemSettings(s)
    localStorage.setItem('sigma_system_settings', JSON.stringify(s))
  }, [])

  const handleThemeChange = useCallback((mode: ThemeMode) => {
    setThemeMode(mode)
    localStorage.setItem('sigma_theme', mode)
  }, [])

  const handleOnboardingComplete = useCallback((entry: LLMEntry | null) => {
    if (entry) {
      const next = {
        ...config,
        llms: [entry],
        activeLLMId: entry.id,
      }
      setConfig(next)
      localStorage.setItem('sigma_kimi_config', JSON.stringify(next))
    }
    setOnboardingDone(true)
  }, [config])

  const handleLanguageChange = useCallback((lang: Lang) => {
    setLanguage(lang)
    saveLanguage(lang)
  }, [])

  const needsOnboarding = !hasApiKey && !onboardingDone

  // 启动时同步自定义 Agent 到后端
  useEffect(() => {
    if (!hasApiKey) return
    const timer = setTimeout(() => {
      syncAgentsToBackend(loadAgents()).catch(() => {})
    }, 800)
    return () => clearTimeout(timer)
  }, [hasApiKey])

  // 启动时检查并初始化项目记忆
  const scanRef = useRef(runProjectScan)
  scanRef.current = runProjectScan
  useEffect(() => {
    if (!hasApiKey) return

    let cancelled = false
    const init = async () => {
      let workingDir = ''
      for (let i = 0; i < 20; i++) {
        if (window.electronAPI?.getWorkingDirectory) {
          const result = await window.electronAPI.getWorkingDirectory()
          if (result.success && result.data) {
            workingDir = result.data
            break
          }
        }
        await new Promise(r => setTimeout(r, 500))
      }
      if (!workingDir || cancelled) return
      await scanRef.current(workingDir)
    }
    init()
    return () => { cancelled = true }
  }, [hasApiKey])

  return (
    <I18nProvider lang={language} onChange={handleLanguageChange}>
    <div className="app-layout">
      {needsOnboarding ? (
        <Onboarding onComplete={handleOnboardingComplete} />
      ) : (
        <>
          <Sidebar
            config={config}
            system={systemSettings}
            themeMode={themeMode}
            language={language}
            onSaveConfig={handleSaveConfig}
            onAddLLM={handleAddLLM}
            onUpdateLLM={handleUpdateLLM}
            onRemoveLLM={handleRemoveLLM}
            onSelectLLM={handleSelectLLM}
            onSaveSystem={handleSaveSystem}
            onThemeChange={handleThemeChange}
            onLanguageChange={handleLanguageChange}
          />
          <div className="app-main" ref={containerRef}>
            <ErrorBoundary>
              <div className="panel-left" style={{ width: leftWidth, flexShrink: 0 }}>
                <ChatPanel config={config} systemSettings={systemSettings} onSelectLLM={handleSelectLLM} resetKey={chatResetKey} onFileDiffUpdate={handleFileDiffUpdate} onFileModificationStart={handleFileModificationStart} onFileModificationComplete={handleFileModificationComplete} onOpenTerminal={handleOpenTerminal} />
              </div>
            </ErrorBoundary>

            <div className="resizer" onMouseDown={() => { isDraggingLeft.current = true }} />

            <div className="panel-center">
              <PreviewPanel file={selectedFile} key={previewKey} fileDiffState={fileDiffQueue.length > 0 ? fileDiffQueue[0] : null} fileDiffQueueLength={fileDiffQueue.length} onAcknowledgeDiff={handleAcknowledgeDiff} onAcknowledgeAllDiffs={handleAcknowledgeAllDiffs} terminalTabs={terminalTabs} onCloseTerminal={handleCloseTerminal} />
            </div>

            <div className="resizer" onMouseDown={() => { isDraggingRight.current = true }} />

            <div className="panel-right" style={{ width: rightWidth, flexShrink: 0 }}>
              <ExplorerPanel width={rightWidth} onSelectFile={setSelectedFile} highlightPath={selectedFile?.path ?? undefined} />
            </div>
          </div>

          {scanningPhase && (
            <ScanningOverlay visible={true} phase={scanningPhase} />
          )}
        </>
      )}
    </div>
      </I18nProvider>
  )
}
