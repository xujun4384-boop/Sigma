import { useEffect, useRef, useState, useCallback } from 'react'
import { X, ExternalLink } from 'lucide-react'
import './AgentAppModal.css'

interface AgentAppModalProps {
  url: string
  title?: string
  onClose: () => void
}

/** 窗口宽高比（移动端 H5 页面按手机比例展示体验最佳） */
const ASPECT_RATIO = 420 / 760
const MIN_W = 320
const MAX_W = 720

function getInitialSize() {
  const maxW = Math.min(MAX_W, window.innerWidth * 0.9)
  const maxH = window.innerHeight * 0.88
  let w = Math.min(420, maxW)
  let h = w / ASPECT_RATIO
  if (h > maxH) {
    h = maxH
    w = h * ASPECT_RATIO
  }
  return { w: Math.max(MIN_W, w), h: Math.max(MIN_W / ASPECT_RATIO, h) }
}

/** 嵌入第三方 H5 智能体页面的弹窗（iframe 渲染，可拖动、按比例缩放） */
export default function AgentAppModal({ url, title = '智能体', onClose }: AgentAppModalProps) {
  const [size, setSize] = useState(getInitialSize)
  const [pos, setPos] = useState(() => {
    const s = getInitialSize()
    return { x: (window.innerWidth - s.w) / 2, y: (window.innerHeight - s.h) / 2 }
  })

  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)
  const resizeRef = useRef<{ startX: number; startY: number; origW: number } | null>(null)

  // ESC 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // ── 拖动（标题栏）──
  const onDragStart = useCallback((e: React.MouseEvent) => {
    // 点按钮不触发拖动
    if ((e.target as HTMLElement).closest('button')) return
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y }

    const onMove = (ev: MouseEvent) => {
      const d = dragRef.current
      if (!d) return
      setPos({
        x: d.origX + ev.clientX - d.startX,
        y: Math.max(0, d.origY + ev.clientY - d.startY),
      })
    }
    const onUp = () => {
      dragRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [pos])

  // ── 缩放（右下角手柄，锁定宽高比）──
  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    resizeRef.current = { startX: e.clientX, startY: e.clientY, origW: size.w }

    const onMove = (ev: MouseEvent) => {
      const r = resizeRef.current
      if (!r) return
      const dw = ev.clientX - r.startX
      const dh = ev.clientY - r.startY
      // 取位移较大的一轴，按宽高比换算宽度
      const newW = Math.abs(dw) > Math.abs(dh * ASPECT_RATIO)
        ? r.origW + dw
        : r.origW + dh * ASPECT_RATIO
      const w = Math.max(MIN_W, Math.min(MAX_W, Math.min(newW, window.innerWidth * 0.95)))
      setSize({ w, h: w / ASPECT_RATIO })
    }
    const onUp = () => {
      resizeRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [size.w])

  return (
    <div className="agent-app-backdrop" onClick={onClose}>
      <div
        className="agent-app-modal"
        style={{ width: size.w, height: size.h, left: pos.x, top: pos.y }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="agent-app-header" onMouseDown={onDragStart}>
          <span className="agent-app-title">{title}</span>
          <div className="agent-app-header-actions">
            <button
              className="agent-app-btn"
              title="在浏览器中打开"
              onClick={() => {
                try {
                  // Electron 环境下经 will-navigate/windowOpen 拦截走系统浏览器
                  window.open(url, '_blank')
                } catch { /* 静默失败 */ }
              }}
            >
              <ExternalLink size={16} />
            </button>
            <button className="agent-app-btn" title="关闭" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </div>
        <iframe
          className="agent-app-frame"
          src={url}
          title={title}
          allow="clipboard-read; clipboard-write; microphone"
        />
        <div className="agent-app-resize-handle" onMouseDown={onResizeStart} />
      </div>
    </div>
  )
}
