import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import hljs from 'highlight.js'
import 'highlight.js/styles/vs2015.css'
import { X, ChevronLeft, ChevronRight, Terminal } from 'lucide-react'
import type { FolderTreeItem } from '../types/electron'
import type { FileDiffState } from '../App'
import type { TerminalTab } from './ChatPanel'
import ExcelDiffViewer from './ExcelDiffViewer'
import type { ExcelDiffData } from './ExcelDiffViewer'
import CodeDiffViewer from './CodeDiffViewer'
import { useTranslation } from '../i18n/I18nContext'
import SigmaLoadingAnimation from './SigmaLoadingAnimation'
import './PreviewPanel.css'

interface Tab { path: string; name: string; type: string; isTerminal?: boolean; command?: string; content?: string }
interface Props {
  file: FolderTreeItem | null
  fileDiffState?: FileDiffState | null
  fileDiffQueueLength?: number
  onAcknowledgeDiff?: () => void
  onAcknowledgeAllDiffs?: () => void
  terminalTabs?: TerminalTab[]
  onCloseTerminal?: (id: string) => void
}

const REPLACE_WINDOW_MS = 5 * 60 * 1000
const LANG_MAP: Record<string, string> = {
  python: 'python', javascript: 'javascript', typescript: 'typescript',
  java: 'java', cpp: 'cpp', c: 'c', csharp: 'csharp', go: 'go', rust: 'rust',
  html: 'xml', css: 'css', json: 'json', xml: 'xml', yaml: 'yaml',
  shell: 'bash', powershell: 'powershell', ini: 'ini', toml: 'ini', text: 'plaintext',
}

export default function PreviewPanel({ file, fileDiffState, fileDiffQueueLength, onAcknowledgeDiff, onAcknowledgeAllDiffs, terminalTabs, onCloseTerminal }: Props) {
  const { t } = useTranslation()
  const [tabs, setTabs] = useState<Tab[]>([])
  const [activePath, setActivePath] = useState<string | null>(null)
  const lastClickRef = useRef(0)
  const prevFilePathRef = useRef<string | null>(null)
  const pptxCacheRef = useRef<Map<string, string[]>>(new Map())

  useEffect(() => {
    if (!file || file.type === 'folder') return

    // 避免同一文件重复处理（对象引用可能变化但路径相同）
    if (prevFilePathRef.current === file.path) return
    prevFilePathRef.current = file.path

    const now = Date.now()
    const withinWindow = (now - lastClickRef.current) < REPLACE_WINDOW_MS
    lastClickRef.current = now

    setTabs(prev => {
      const existing = prev.find(t => t.path === file.path)
      if (existing) {
        // 已存在的标签，直接激活
        return prev
      }
      if (withinWindow && prev.length > 0) {
        // 在替换窗口内，替换当前活动标签
        return prev.map(t => t.path === activePath ? { path: file.path, name: file.name, type: file.type } : t)
      }
      // 新增标签
      return [...prev, { path: file.path, name: file.name, type: file.type }]
    })
    setActivePath(file.path)
  }, [file])

  const handleCloseTab = (path: string) => {
    // 检查是否是终端标签
    const termTab = (terminalTabs || []).find(t => t.id === path)
    if (termTab) {
      onCloseTerminal?.(path)
      if (path === activePath) {
        const remainingFileTabs = tabs.filter(t => t.path !== path)
        const remainingTermTabs = (terminalTabs || []).filter(t => t.id !== path).map(t => ({
          path: t.id, name: t.title, type: 'terminal', isTerminal: true, command: t.command, content: t.content,
        }))
        const remaining: Tab[] = [...remainingFileTabs, ...remainingTermTabs]
        const nextActive = remaining[0]?.path || null
        setActivePath(nextActive)
      }
      return
    }
    if (path === activePath) {
      // 关闭当前活动标签，需同时切换 activePath
      const remainingFileTabs = tabs.filter(t => t.path !== path)
      const remainingTermTabs = (terminalTabs || []).map(t => ({
        path: t.id, name: t.title, type: 'terminal', isTerminal: true, command: t.command, content: t.content,
      }))
      const remaining: Tab[] = [...remainingFileTabs, ...remainingTermTabs]
      const fileIdx = tabs.findIndex(t => t.path === path)
      const nextActive = remaining[Math.min(fileIdx, remaining.length - 1)]?.path || null
      setTabs(remainingFileTabs)
      setActivePath(nextActive)
    } else {
      setTabs(prev => prev.filter(t => t.path !== path))
    }
  }

  // 合并文件标签和终端标签
  const allTabs: Tab[] = [
    ...tabs,
    ...(terminalTabs || []).map(t => ({
      path: t.id,
      name: t.title,
      type: 'terminal',
      isTerminal: true,
      command: t.command,
      content: t.content,
    })),
  ]
  const activeTab = allTabs.find(t => t.path === activePath) || null

  // ── Diff Mode: 如果 fileDiffState 匹配当前活动标签，显示差异视图 ──
  const queueProps = { queueIndex: 1, queueTotal: fileDiffQueueLength || 1, onAcknowledgeAll: onAcknowledgeAllDiffs }
  const shouldShowDiff = fileDiffState && fileDiffState.diffData !== null
  if (shouldShowDiff) {
    const activeDiffType = fileDiffState!.fileType || fileDiffState!.diffData?.file_type || activeTab?.type || ''
    if (activeDiffType === 'xlsx' || activeDiffType === 'excel') {
      return (
        <div className="preview-panel">
          <ExcelDiffViewer diffData={fileDiffState!.diffData as ExcelDiffData} isModifying={fileDiffState!.isModifying} onAcknowledge={onAcknowledgeDiff} {...queueProps} />
        </div>
      )
    }
    if (activeDiffType === 'docx' || activeDiffType === 'word' || activeDiffType === 'markdown') {
      const diffData = fileDiffState!.diffData
      const lines = diffData?.lines || { added: [], removed: [], modified: [] }
      const paragraphs = diffData?.paragraphs || { added: [], removed: [], modified: [] }
      const added = lines.added.length + paragraphs.added.length
      const removed = lines.removed.length + paragraphs.removed.length
      const modified = lines.modified.length + paragraphs.modified.length
      return (
        <div className="preview-panel">
          <CodeDiffViewer
            fileName={diffData?.file_name || fileDiffState!.fileName || activeTab?.name || ''}
            fileType={activeDiffType}
            oldText={diffData?.old_text || ''}
            newText={diffData?.new_text || ''}
            addedCount={added}
            removedCount={removed}
            modifiedCount={modified}
            isModifying={fileDiffState!.isModifying}
            onAcknowledge={onAcknowledgeDiff}
            {...queueProps}
          />
        </div>
      )
    }
    // 代码文件 diff
    if (fileDiffState!.diffData?.file_type === 'code') {
      const lines = fileDiffState!.diffData?.lines || { added: [], removed: [], modified: [] }
      return (
        <div className="preview-panel">
          <CodeDiffViewer
            fileName={fileDiffState!.diffData?.file_name || fileDiffState!.fileName || activeTab?.name || ''}
            fileType={activeDiffType}
            oldText={fileDiffState!.diffData?.old_text || ''}
            newText={fileDiffState!.diffData?.new_text || ''}
            addedCount={lines.added.length}
            removedCount={lines.removed.length}
            modifiedCount={lines.modified.length}
            isModifying={fileDiffState!.isModifying}
            onAcknowledge={onAcknowledgeDiff}
            {...queueProps}
          />
        </div>
      )
    }
  }

  if (allTabs.length === 0) {
    return (
      <div className="preview-panel preview-empty">
        <SigmaLoadingAnimation />
      </div>
    )
  }

  return (
    <div className="preview-panel">
      <div className="preview-tab-bar">
        {allTabs.map(tab => (
          <div key={tab.path} className={`preview-tab ${tab.path === activePath ? 'active' : ''} ${tab.isTerminal ? 'terminal' : ''}`}
            onClick={() => { setActivePath(tab.path); lastClickRef.current = Date.now() }}>
            {tab.isTerminal && <Terminal size={11} className="preview-tab-terminal-icon" />}
            <span className="preview-tab-name">{tab.name}</span>
            <button className="preview-tab-close" onClick={(e) => { e.stopPropagation(); handleCloseTab(tab.path) }}>
              <X size={12} />
            </button>
          </div>
        ))}
      </div>
      {activeTab && <TabContent tab={activeTab} pptxCache={pptxCacheRef} />}
    </div>
  )
}

// ── TabContent (handles all file types) ──

function TabContent({ tab, pptxCache }: { tab: Tab; pptxCache: { current: Map<string, string[]> } }) {
  const { t } = useTranslation()
  const [state, setState] = useState<{
    loading: boolean; error: string; content: string;
    pdfData: string | null; pptxImages: string[]; videoUrl: string | null;
  }>({ loading: true, error: '', content: '', pdfData: null, pptxImages: [], videoUrl: null })

  useEffect(() => {
    let cancelled = false
    setState(s => ({ ...s, loading: true, error: '', content: '', pdfData: null, pptxImages: [] }))

    // 终端标签：内容已在 tab.content 中，无需加载文件
    if (tab.isTerminal) {
      setState(s => ({ ...s, loading: false, content: tab.content || '' }))
      return
    }

    const load = async () => {
      try {
        // 视频文件：通过 sigma-file:// 协议获取 URL，不读文件内容
        if (tab.type === 'video') {
          const urlResult = await window.electronAPI.getFileUrl(tab.path)
          if (cancelled) return
          if (urlResult.success && urlResult.data) {
            setState(s => ({ ...s, loading: false, videoUrl: urlResult.data! }))
          } else {
            setState(s => ({ ...s, loading: false, error: urlResult.error || 'Failed to load video' }))
          }
          return
        }

        const result = await window.electronAPI.readFile(tab.path)
        if (cancelled) return
        if (!result.success) { setState(s => ({ ...s, loading: false, error: result.error || 'Failed' })); return }
        const data = result.data || ''

        if (tab.type === 'pdf') {
          setState(s => ({ ...s, loading: false, pdfData: `data:application/pdf;base64,${data}` }))
        } else if (tab.type === 'docx') {
          await renderDocx(data, cancelled, setState)
        } else if (tab.type === 'xlsx') {
          await renderXlsx(data, cancelled, setState)
        } else if (tab.type === 'pptx') {
          // 先从缓存读取
          const cached = pptxCache.current.get(tab.path)
          if (cached) {
            if (!cancelled) setState(s => ({ ...s, loading: false, pptxImages: cached }))
            return
          }
          try {
            const r = await window.electronAPI.convertPptxToImages(tab.path)
            if (!cancelled) {
              if (r.success && r.images && r.images.length > 0) {
                pptxCache.current.set(tab.path, r.images)
                setState(s => ({ ...s, loading: false, pptxImages: r.images }))
              } else {
                setState(s => ({ ...s, loading: false, error: r.error || 'PPTX conversion failed: no images generated' }))
              }
            }
          } catch (e: any) {
            if (!cancelled) setState(s => ({ ...s, loading: false, error: `PPTX error: ${e.message}` }))
          }
        } else {
          if (!cancelled) setState(s => ({ ...s, loading: false, content: data }))
        }
      } catch (e: any) {
        if (!cancelled) setState(s => ({ ...s, loading: false, error: e.message }))
      }
    }
    load()
    return () => { cancelled = true }
  }, [tab.path, tab.type])

  if (state.loading) return <div className="preview-loading">{t("preview.loading")} {tab.name}...</div>
  if (state.error) return <div className="preview-error">{state.error}</div>

  // PDF
  if (tab.type === 'pdf' && state.pdfData) {
    return (
      <div className="preview-content">
        <div className="preview-pdf-container">
          <iframe src={state.pdfData} className="pdf-iframe" title={tab.name} />
        </div>
      </div>
    )
  }

  // DOCX
  if (tab.type === 'docx' && state.content) {
    return (
      <div className="preview-content">
        <div className="preview-docx" dangerouslySetInnerHTML={{ __html: state.content }} />
      </div>
    )
  }

  // Excel
  if (tab.type === 'xlsx' && state.content) {
    return (
      <div className="preview-content">
        <div className="preview-excel" dangerouslySetInnerHTML={{ __html: state.content }} />
      </div>
    )
  }

  // PPTX
  if (tab.type === 'pptx' && state.pptxImages.length > 0) {
    return <PptxViewer images={state.pptxImages} />
  }

  // Markdown
  if (tab.type === 'markdown') {
    return (
      <div className="preview-content">
        <div className="preview-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{state.content}</ReactMarkdown>
        </div>
      </div>
    )
  }

  // Video
  if (tab.type === 'video' && state.videoUrl) {
    return (
      <div className="preview-content">
        <div className="preview-video">
          <video controls autoPlay style={{ maxWidth: '100%', maxHeight: 'calc(100vh - 120px)', background: '#000' }}>
            <source src={state.videoUrl} />
            {t("preview.video_not_supported")}
          </video>
        </div>
      </div>
    )
  }

  // Terminal
  if (tab.type === 'terminal' && tab.isTerminal) {
    return <TerminalContent command={tab.command || ''} output={state.content} />
  }

  // Image
  if (tab.type === 'image') {
    const ext = tab.name.split('.').pop()?.toLowerCase() || 'png'
    const mime = { jpg: 'jpeg', jpeg: 'jpeg', png: 'png', gif: 'gif', webp: 'webp', svg: 'svg+xml' }[ext] || 'png'
    return (
      <div className="preview-content">
        <div className="preview-image">
          <img src={`data:image/${mime};base64,${state.content}`} alt={tab.name} />
        </div>
      </div>
    )
  }

  // Code
  const isCode = !['markdown', 'image', 'video', 'folder', 'file', 'docx', 'xlsx', 'pptx', 'pdf', 'text'].includes(tab.type)
  if (isCode) {
    const lines = state.content.split('\n')
    const lang = LANG_MAP[tab.type] || 'plaintext'
    const highlighted = (lang && hljs.getLanguage(lang))
      ? hljs.highlight(state.content, { language: lang }).value
      : hljs.highlightAuto(state.content).value
    return (
      <div className="preview-content">
        <div className="preview-code-header">
          <span className="preview-code-lang">{lang}</span>
          <span className="preview-code-lines">{lines.length} {t("preview.lines")}</span>
        </div>
        <div className="preview-code-viewer">
          <div className="code-gutter">
            {lines.map((_, i) => <div key={i} className="code-gutter-line">{i + 1}</div>)}
          </div>
          <div className="code-body">
            <pre className="code-highlighted" dangerouslySetInnerHTML={{ __html: highlighted }} />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="preview-content">
      <pre className="preview-code">{state.content}</pre>
    </div>
  )
}

// ── Heavy module renderers (dynamic import) ──

async function renderDocx(data: string, cancelled: boolean, setState: any) {
  try {
    const mammoth = await import('mammoth')
    const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0))
    const r = await mammoth.default.convertToHtml({ arrayBuffer: bytes.buffer })
    if (!cancelled) setState((s: any) => ({ ...s, loading: false, content: r.value || '(empty)' }))
  } catch (e: any) {
    if (!cancelled) setState((s: any) => ({ ...s, loading: false, error: `DOCX error: ${e.message}` }))
  }
}

async function renderXlsx(data: string, cancelled: boolean, setState: any) {
  try {
    const XLSX = await import('xlsx')
    const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0))
    const wb = XLSX.read(bytes, { type: 'array' })
    const name = wb.SheetNames[0] || 'Sheet1'
    const ws = wb.Sheets[name]
    const html = XLSX.utils.sheet_to_html(ws, { id: 'excel-table', editable: false })
    if (!cancelled) setState((s: any) => ({ ...s, loading: false, content: html }))
  } catch (e: any) {
    if (!cancelled) setState((s: any) => ({ ...s, loading: false, error: `XLSX error: ${e.message}` }))
  }
}

// ── PPTX Viewer ──

function PptxViewer({ images }: { images: string[] }) {
  const { t } = useTranslation()
  const [slide, setSlide] = useState(0)
  return (
    <div className="preview-content">
      <div className="preview-pdf-controls">
        <button className="pdf-nav-btn" onClick={() => setSlide(s => Math.max(0, s - 1))} disabled={slide <= 0}>
          <ChevronLeft size={16} />
        </button>
        <span className="pdf-page-info">{t("preview.slide")} {slide + 1} {t("preview.of")} {images.length}</span>
        <button className="pdf-nav-btn" onClick={() => setSlide(s => Math.min(images.length - 1, s + 1))} disabled={slide >= images.length - 1}>
          <ChevronRight size={16} />
        </button>
      </div>
      <div className="preview-pptx-container">
        <img src={`data:image/png;base64,${images[slide]}`} alt={`Slide ${slide + 1}`} className="pptx-slide-img" />
      </div>
    </div>
  )
}

// ── ANSI 转义码转 HTML ──

function ansiToHtml(text: string): string {
  const colorMap: Record<string, string> = {
    '30': '#111', '31': '#e06c75', '32': '#98c379', '33': '#e5c07b',
    '34': '#61afef', '35': '#c678dd', '36': '#56b6c2', '37': '#abb2bf',
    '90': '#5c6370', '91': '#e06c75', '92': '#98c379', '93': '#e5c07b',
    '94': '#61afef', '95': '#c678dd', '96': '#56b6c2', '97': '#ffffff',
  }
  const bgMap: Record<string, string> = {
    '40': '#1e1e1e', '41': '#e06c75', '42': '#98c379', '43': '#e5c07b',
    '44': '#61afef', '45': '#c678dd', '46': '#56b6c2', '47': '#abb2bf',
    '100': '#5c6370',
  }

  // 替换 & 和 < > 防止 XSS
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  let result = ''
  let i = 0
  let currentColor = ''
  let currentBg = ''
  let bold = false

  const flushSpan = () => {
    if (!currentColor && !currentBg && !bold) return
    const styles: string[] = []
    if (bold) styles.push('font-weight:bold')
    if (currentColor) styles.push(`color:${currentColor}`)
    if (currentBg) styles.push(`background:${currentBg}`)
    result += `<span style="${styles.join(';')}">`
  }
  const closeSpan = () => {
    if (currentColor || currentBg || bold) result += '</span>'
  }

  while (i < escaped.length) {
    if (escaped[i] === '\x1b' && escaped[i + 1] === '[') {
      const end = escaped.indexOf('m', i + 2)
      if (end === -1) { result += escaped[i]; i++; continue }
      const codes = escaped.substring(i + 2, end).split(';').map(Number)
      if (codes.length === 1 && codes[0] === 0) {
        closeSpan()
        currentColor = ''; currentBg = ''; bold = false
      } else {
        for (const c of codes) {
          if (c === 1) bold = true
          else if (c === 22) bold = false
          else if (colorMap[String(c)]) { closeSpan(); currentColor = colorMap[String(c)]; flushSpan() }
          else if (bgMap[String(c)]) { currentBg = bgMap[String(c)] }
        }
      }
      i = end + 1
    } else if (escaped[i] === '\n') {
      closeSpan()
      currentColor = ''; currentBg = ''; bold = false
      result += '\n'
      i++
    } else {
      result += escaped[i]
      i++
    }
  }
  closeSpan()
  return result
}

// ── Terminal Content ──

function TerminalContent({ command, output }: { command: string; output: string }) {
  const { t } = useTranslation()
  return (
    <div className="terminal-container">
      <div className="terminal-header">
        <Terminal size={14} />
        <span className="terminal-command">{command}</span>
      </div>
      <pre className="terminal-output" dangerouslySetInnerHTML={{ __html: ansiToHtml(output) }} />
    </div>
  )
}
