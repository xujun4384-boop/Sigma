import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Excalidraw,
  exportToBlob,
  exportToSvg,
  convertToExcalidrawElements,
  type AppState,
  type BinaryFiles,
  type ExcalidrawElement,
  type ExcalidrawImperativeAPI,
  type ExcalidrawInitialDataState,
} from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'
import './CanvasPanel.css'

const DEFAULT_CANVAS_NAME = 'default'
const AUTOSAVE_DELAY = 800

function getSavedCanvasName(): string {
  try { return localStorage.getItem('sigma_canvas_name') || DEFAULT_CANVAS_NAME } catch { return DEFAULT_CANVAS_NAME }
}

// 按 id 去重：保留最后一个出现的元素（假设后面的更正确）。
// 解决流式生成中模型自我修正导致的重复元素问题。
function deduplicateById(elements: any[]): any[] {
  const seen = new Map<string, number>()
  for (let i = 0; i < elements.length; i++) {
    const id = elements[i]?.id
    if (id) seen.set(id, i)
  }
  const keepIndices = new Set(seen.values())
  return elements.filter((el, i) => !el?.id || keepIndices.has(i))
}

// 容器类型：可容纳文本的形状
const CONTAINER_TYPES = new Set(['rectangle', 'ellipse', 'diamond'])

// 给元素分配稳定唯一 id，并重建 containerId / boundElements 引用。
// convertToExcalidrawElements 的 regenerateIds 会破坏 LLM 写好的绑定关系，
// 所以这里先用确定的映射，再用 regenerateIds: false 保留。
function normalizeCanvasElements(rawElements: any[]): any[] {
  const idMap = new Map<string, string>()
  const used = new Set<string>()
  const out = rawElements.map((el, i) => {
    const copy = { ...el }
    let id = copy.id
    if (!id || used.has(id)) {
      id = `${copy.type || 'el'}-${i}-${Math.random().toString(36).slice(2, 8)}`
    }
    used.add(id)
    if (el.id) idMap.set(el.id, id)
    copy.id = id
    return copy
  })
  // 重建跨元素引用
  for (const el of out) {
    if (el.containerId && idMap.has(el.containerId)) {
      el.containerId = idMap.get(el.containerId)
    }
    if (Array.isArray(el.boundElements)) {
      el.boundElements = el.boundElements.map((b: any) =>
        b && b.id && idMap.has(b.id) ? { ...b, id: idMap.get(b.id) } : b
      )
    }
  }
  return out
}

// 用 canvas 精确测量文本渲染尺寸（与 Excalidraw 字体渲染一致）
function measureTextSize(text: string, fontSize: number, fontFamily: number): { width: number; height: number } {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  // fontFamily 1=手写(Virgil), 2=正常(Nunito), 3=代码(Cascadia)
  const fontName = fontFamily === 1 ? 'Virgil, Segoe UI Emoji' : fontFamily === 3 ? 'Cascadia, monospace' : 'Nunito, sans-serif'
  ctx.font = `${fontSize}px ${fontName}`
  const lines = text.split('\n')
  const lineHeight = fontSize * 1.25
  const width = Math.max(...lines.map(l => ctx.measureText(l).width))
  const height = lines.length * lineHeight
  return { width, height }
}

// 为没有绑定的文本找到最近的容器，建立双向绑定；
// 对已有 containerId 但坐标不对的文本，按容器实际位置重新计算并居中。
// 不依赖几何重叠（LLM 经常把文字放在容器外面），直接按 containerId 或距离匹配。
function bindTextsToNearestContainers(elements: any[]): any[] {
  const containers = elements.filter(e =>
    CONTAINER_TYPES.has(e.type) && (e.width || 0) > 0 && (e.height || 0) > 0
  )
  if (containers.length === 0) return elements
  const containerById = new Map(containers.map(c => [c.id, c]))
  const texts = elements.filter(e => e.type === 'text')
  if (texts.length === 0) return elements

  for (const text of texts) {
    // 情况 1：LLM 已绑定 containerId，但 x/y/width/height 是凭直觉写的，需要按容器重新居中
    // 情况 2：LLM 没绑定 containerId，需要找最近容器并建立绑定
    let container: any = null
    if (text.containerId && containerById.has(text.containerId)) {
      container = containerById.get(text.containerId)
    } else if (!text.containerId) {
      const tx = text.x || 0
      const ty = text.y || 0
      let bestDist = Infinity
      for (const c of containers) {
        const cx = (c.x || 0) + (c.width || 0) / 2
        const cy = (c.y || 0) + (c.height || 0) / 2
        const dist = Math.sqrt((tx - cx) ** 2 + (ty - cy) ** 2)
        if (dist < bestDist) { bestDist = dist; container = c }
      }
      if (container) {
        text.containerId = container.id
      }
    } else {
      // containerId 指向的容器不存在，跳过
      continue
    }
    if (!container) continue

    // 精确测量文本尺寸，按容器居中重算 x/y
    const fontSize = text.fontSize || 16
    const fontFamily = text.fontFamily || 2
    const { width: textWidth, height: textHeight } = measureTextSize(text.text || '', fontSize, fontFamily)
    text.width = textWidth
    text.height = textHeight
    text.x = (container.x || 0) + ((container.width || 0) - textWidth) / 2
    text.y = (container.y || 0) + ((container.height || 0) - textHeight) / 2
    text.textAlign = 'center'
    text.verticalAlign = 'middle'

    // 建立/补全双向绑定
    if (!Array.isArray(container.boundElements)) container.boundElements = []
    if (!container.boundElements.some((b: any) => b.type === 'text' && b.id === text.id)) {
      container.boundElements.push({ type: 'text', id: text.id })
    }
  }
  return elements
}

type CanvasData = {
  elements: readonly ExcalidrawElement[]
  appState: Partial<AppState>
  files: BinaryFiles
}

type CanvasPanelProps = {
  onCanvasPatch?: { canvasName: string; operation: 'add' | 'replace'; elements: any[]; batchIndex?: number; batchTotal?: number; isFinal?: boolean } | null
  onCanvasPatchApplied?: () => void
}

export default function CanvasPanel({ onCanvasPatch, onCanvasPatchApplied }: CanvasPanelProps) {
  const [initialData, setInitialData] = useState<ExcalidrawInitialDataState | null>(null)
  const [canvasName, setCanvasName] = useState(getSavedCanvasName)
  const [canvasNames, setCanvasNames] = useState<string[]>([DEFAULT_CANVAS_NAME])
  const [theme, setTheme] = useState<'light' | 'dark'>(() => document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'saved' | 'error'>('loading')
  const [showNewCanvasDialog, setShowNewCanvasDialog] = useState(false)
  const [exportPreviewUrl, setExportPreviewUrl] = useState<string | null>(null)
  const [canvasKey, setCanvasKey] = useState(0)
  const latestDataRef = useRef<CanvasData | null>(null)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null)
  // 流式补丁状态：跟踪当前流式会话中已累积的原始元素，避免逐批转换破坏绑定关系
  const rawElementsRef = useRef<any[]>([])
  // 流式会话开始时的画布基准元素（add 保留已有元素，replace 清空）
  const baseElementsRef = useRef<readonly ExcalidrawElement[]>([])

  const saveCanvas = useCallback(async (data: CanvasData) => {
    if (!window.electronAPI?.saveCanvas) return
    setStatus('saving')
    const result = await window.electronAPI.saveCanvas(canvasName, {
      elements: data.elements,
      appState: {
        viewBackgroundColor: data.appState.viewBackgroundColor,
        scrollX: data.appState.scrollX,
        scrollY: data.appState.scrollY,
        zoom: data.appState.zoom,
      },
      files: data.files,
    })
    setStatus(result.success ? 'saved' : 'error')
  }, [canvasName])

  const scheduleSave = useCallback((data: CanvasData) => {
    latestDataRef.current = data
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      if (latestDataRef.current) saveCanvas(latestDataRef.current)
    }, AUTOSAVE_DELAY)
  }, [saveCanvas])

  useEffect(() => {
    const root = document.documentElement
    const syncTheme = () => setTheme(root.dataset.theme === 'light' ? 'light' : 'dark')
    const observer = new MutationObserver(syncTheme)
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    try { localStorage.setItem('sigma_canvas_name', canvasName) } catch {}
  }, [canvasName])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!window.electronAPI?.loadCanvas) {
        setStatus('ready')
        setInitialData({ elements: [], appState: { viewBackgroundColor: 'transparent' }, files: {} })
        return
      }
      const listResult = await window.electronAPI.listCanvases?.()
      if (listResult?.success && listResult.data) setCanvasNames(listResult.data)
      const result = await window.electronAPI.loadCanvas(canvasName)
      if (cancelled) return
      if (result.success && result.data) {
        setInitialData(result.data as ExcalidrawInitialDataState)
      } else {
        setInitialData({ elements: [], appState: { viewBackgroundColor: 'transparent' }, files: {} })
      }
      setStatus('ready')
    }
    load().catch(() => {
      if (!cancelled) {
        setInitialData({ elements: [], appState: { viewBackgroundColor: 'transparent' }, files: {} })
        setStatus('error')
      }
    })
    return () => {
      cancelled = true
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    }
  }, [canvasKey, canvasName])

  const handleChange = useCallback((elements: readonly ExcalidrawElement[], appState: AppState, files: BinaryFiles) => {
    scheduleSave({ elements, appState, files })
  }, [scheduleSave])

  const applyCanvasPatch = useCallback(() => {
    if (!onCanvasPatch || onCanvasPatch.elements.length === 0) return
    if (!apiRef.current) return

    // 流式批次：累积原始元素，最后统一转换，确保容器-文本绑定不被逐批转换破坏
    const isFirstBatch = onCanvasPatch.batchIndex === 0 || onCanvasPatch.batchIndex === undefined
    if (isFirstBatch) {
      rawElementsRef.current = []
      // 保存画布基准元素：add 保留已有元素，replace 清空
      baseElementsRef.current = onCanvasPatch.operation === 'replace'
        ? []
        : apiRef.current.getSceneElements()
    }
    rawElementsRef.current = [...rawElementsRef.current, ...onCanvasPatch.elements]

    // 对整个累积列表统一做：按 id 去重 → 绑定文字到最近容器 → id 规范化 → 转换
    // 不依赖几何重叠，确保文字始终绑定到容器内并居中
    const deduped = deduplicateById(rawElementsRef.current)
    const bound = bindTextsToNearestContainers(deduped)
    const normalized = normalizeCanvasElements(bound)
    const allElements = convertToExcalidrawElements(normalized, { regenerateIds: false })

    // 基准元素 + 累积的新元素，避免逐批重复累积
    const merged = [...baseElementsRef.current, ...allElements]
    apiRef.current.updateScene({ elements: merged, commitToHistory: true })

    // 最后一批重置累积状态并触发回调
    if (onCanvasPatch.isFinal !== false) {
      rawElementsRef.current = []
      onCanvasPatchApplied?.()
    }
  }, [canvasName, onCanvasPatch, onCanvasPatchApplied])

  useEffect(() => {
    applyCanvasPatch()
  }, [applyCanvasPatch])

  const getCurrentCanvasData = useCallback((): CanvasData | null => {
    const api = apiRef.current
    if (!api) return latestDataRef.current
    return {
      elements: api.getSceneElements(),
      appState: api.getAppState(),
      files: api.getFiles(),
    }
  }, [])

  const handleSave = useCallback(async () => {
    const data = getCurrentCanvasData()
    if (!data) {
      setStatus('error')
      return
    }
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    await saveCanvas(data)
  }, [getCurrentCanvasData, saveCanvas])

  const handlePreviewExport = useCallback(async () => {
    const elements = apiRef.current?.getSceneElements()
    if (!elements) return
    const svg = await exportToSvg({
      elements,
      appState: { exportBackground: true, viewBackgroundColor: '#ffffff' },
      files: apiRef.current?.getFiles() ?? {},
    })
    const url = URL.createObjectURL(new Blob([svg.outerHTML], { type: 'image/svg+xml' }))
    setExportPreviewUrl(previousUrl => {
      if (previousUrl) URL.revokeObjectURL(previousUrl)
      return url
    })
  }, [])

  const downloadExport = useCallback(async (format: 'png' | 'svg') => {
    const data = getCurrentCanvasData()
    if (!data) return
    const appState = { exportBackground: true, viewBackgroundColor: '#ffffff' }
    const blob = format === 'png'
      ? await exportToBlob({ elements: data.elements, appState, files: data.files, mimeType: 'image/png' })
      : new Blob([(await exportToSvg({ elements: data.elements, appState, files: data.files })).outerHTML], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${canvasName}.${format}`
    link.click()
    URL.revokeObjectURL(url)
  }, [canvasName, getCurrentCanvasData])

  const createNewCanvas = useCallback(async (saveCurrent: boolean) => {
    if (saveCurrent) {
      const data = getCurrentCanvasData()
      if (data) await saveCanvas(data)
    }
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    const newCanvasName = `canvas-${new Date().toISOString().replace(/[:.]/g, '-')}`
    latestDataRef.current = null
    setShowNewCanvasDialog(false)
    setInitialData(null)
    setCanvasNames(names => [...names, newCanvasName])
    setCanvasName(newCanvasName)
    setCanvasKey(key => key + 1)
  }, [getCurrentCanvasData, saveCanvas])

  const closeExportPreview = useCallback(() => {
    setExportPreviewUrl(previousUrl => {
      if (previousUrl) URL.revokeObjectURL(previousUrl)
      return null
    })
  }, [])

  if (!initialData) {
    return <div className="canvas-panel-loading">正在加载画布...</div>
  }

  return (
    <div className="canvas-panel">
      <div className="canvas-panel-toolbar">
        <span className={`canvas-save-status ${status}`}>
          {status === 'saving' ? '保存中...' : status === 'saved' ? '已保存' : status === 'error' ? '保存失败' : '自动保存'}
        </span>
        <select className="canvas-selector" value={canvasName} onChange={(event) => { setInitialData(null); setCanvasName(event.target.value); setCanvasKey(key => key + 1) }} aria-label="选择画布">
          {canvasNames.map(name => <option key={name} value={name}>{name === DEFAULT_CANVAS_NAME ? '默认画布' : name}</option>)}
        </select>
        <button className="canvas-new-button" onClick={() => setShowNewCanvasDialog(true)}>
          新建画布
        </button>
        <button className="canvas-export-preview-button" onClick={handlePreviewExport}>
          导出预览
        </button>
        <button className="canvas-save-button" onClick={handleSave} disabled={status === 'saving'}>
          保存画布
        </button>
      </div>
      <div className="canvas-panel-body">
        <Excalidraw
          key={canvasKey}
          initialData={initialData}
          theme={theme}
          onChange={handleChange}
          excalidrawAPI={(api) => { apiRef.current = api; applyCanvasPatch() }}
          UIOptions={{ canvasActions: { saveToActiveFile: false, loadScene: false } }}
        />
      </div>
      {showNewCanvasDialog && (
        <div className="canvas-modal-backdrop" role="dialog" aria-modal="true" aria-label="新建画布确认">
          <div className="canvas-modal">
            <h3>新建画布</h3>
            <p>新建前是否保存当前画布？</p>
            <div className="canvas-modal-actions">
              <button onClick={() => setShowNewCanvasDialog(false)}>取消</button>
              <button onClick={() => createNewCanvas(false)}>不保存新建</button>
              <button className="primary" onClick={() => createNewCanvas(true)}>保存并新建</button>
            </div>
          </div>
        </div>
      )}
      {exportPreviewUrl && (
        <div className="canvas-export-preview" role="dialog" aria-modal="true" aria-label="导出预览">
          <div className="canvas-export-preview-header">
            <div>
              <strong>导出预览</strong>
              <span>统一按浅色背景导出</span>
            </div>
            <div className="canvas-export-preview-actions">
              <button onClick={() => downloadExport('png')}>导出 PNG</button>
              <button onClick={() => downloadExport('svg')}>导出 SVG</button>
              <button onClick={closeExportPreview}>返回编辑</button>
            </div>
          </div>
          <div className="canvas-export-preview-body">
            <img src={exportPreviewUrl} alt="画布浅色导出预览" />
          </div>
        </div>
      )}
    </div>
  )
}
