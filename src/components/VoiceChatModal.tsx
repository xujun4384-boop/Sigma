import { useEffect, useRef, useState, useCallback } from 'react'
import { X, Mic, PhoneOff, Wrench, CheckCircle2, XCircle, ChevronDown, ChevronRight } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { VoiceChatClient, type VoiceStatus } from '../utils/voiceChat'
import { getBackendUrl } from '../utils/config'
import './VoiceChatModal.css'

interface VoiceChatModalProps {
  apiKey: string
  speaker?: string
  onClose: () => void
}

// ── 主 Sigma 任务过程块（复用主界面的渲染思路） ──

type TaskBlock =
  | { type: 'thinking'; content: string }
  | { type: 'response_text'; content: string }
  | { type: 'tool_call'; toolName: string; toolInput: Record<string, unknown>; result?: string; success?: boolean }

interface VoiceTask {
  id: string
  prompt: string
  blocks: TaskBlock[]
  done: boolean
}

interface OrbitNode {
  angle: number
  radius: number
  orbit: number
  size: number
  phase: number
  speed: number
  kind: 'node' | 'tick' | 'satellite'
}

interface RadarSegment {
  angle: number
  length: number
  width: number
  speed: number
}

const ORBIT_NODE_COUNT = 120
const SATELLITE_COUNT = 34
const TICK_COUNT = 72
const RADAR_COUNT = 6

const STATUS_COLOR: Record<VoiceStatus, string> = {
  idle: '#ff9f43',
  connecting: '#ff7f11',
  listening: '#4aa8ff',
  speaking: '#ff6a00',
}

const STATUS_COMPACT: Record<VoiceStatus, number> = {
  idle: 0.72,
  connecting: 0.58,
  listening: 0.34,
  speaking: 0.16,
}

const STATUS_LABEL: Record<VoiceStatus, string> = {
  idle: '点击开始通话',
  connecting: '连接中…',
  listening: '正在聆听',
  speaking: '正在回复',
}

function initOrbitNodes(): OrbitNode[] {
  const nodes: OrbitNode[] = []
  for (let i = 0; i < ORBIT_NODE_COUNT; i++) {
    nodes.push({
      angle: (i / ORBIT_NODE_COUNT) * Math.PI * 2,
      radius: 72 + Math.random() * 58,
      orbit: 0.65 + Math.random() * 0.35,
      size: 0.8 + Math.random() * 1.6,
      phase: Math.random() * Math.PI * 2,
      speed: (Math.random() < 0.5 ? -1 : 1) * (0.001 + Math.random() * 0.002),
      kind: 'node',
    })
  }

  for (let i = 0; i < TICK_COUNT; i++) {
    nodes.push({
      angle: (i / TICK_COUNT) * Math.PI * 2,
      radius: 124 + Math.random() * 22,
      orbit: 1,
      size: 0,
      phase: Math.random() * Math.PI * 2,
      speed: 0.0004 + Math.random() * 0.0008,
      kind: 'tick',
    })
  }

  for (let i = 0; i < SATELLITE_COUNT; i++) {
    nodes.push({
      angle: Math.random() * Math.PI * 2,
      radius: 148 + Math.random() * 60,
      orbit: 0.72 + Math.random() * 0.42,
      size: 1.2 + Math.random() * 2.4,
      phase: Math.random() * Math.PI * 2,
      speed: (Math.random() < 0.5 ? -1 : 1) * (0.0018 + Math.random() * 0.0028),
      kind: 'satellite',
    })
  }

  return nodes
}

function initRadarSegments(): RadarSegment[] {
  return Array.from({ length: RADAR_COUNT }, (_, i) => ({
    angle: (i / RADAR_COUNT) * Math.PI * 2,
    length: 48 + Math.random() * 78,
    width: 1 + Math.random() * 2,
    speed: (Math.random() < 0.5 ? -1 : 1) * (0.003 + Math.random() * 0.004),
  }))
}

function drawSegment(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  radius: number,
  angle: number,
  length: number,
  thickness: number,
  color: string,
  alpha: number,
) {
  const startX = cx + Math.cos(angle) * radius
  const startY = cy + Math.sin(angle) * radius
  const endX = cx + Math.cos(angle) * (radius + length)
  const endY = cy + Math.sin(angle) * (radius + length)
  const perpX = -Math.sin(angle) * thickness
  const perpY = Math.cos(angle) * thickness

  ctx.globalAlpha = alpha
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.moveTo(startX + perpX, startY + perpY)
  ctx.lineTo(endX + perpX, endY + perpY)
  ctx.lineTo(endX - perpX, endY - perpY)
  ctx.lineTo(startX - perpX, startY - perpY)
  ctx.closePath()
  ctx.fill()
}

function drawRing(ctx: CanvasRenderingContext2D, cx: number, cy: number, radius: number, color: string, alpha: number) {
  ctx.globalAlpha = alpha
  ctx.strokeStyle = color
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.stroke()
}

/** 语音实时通话弹窗：粒子动画随「倾听/说话」状态变化颜色与紧凑度 */
export default function VoiceChatModal({ apiKey, speaker, onClose }: VoiceChatModalProps) {
  const [status, setStatus] = useState<VoiceStatus>('idle')
  const [error, setError] = useState('')
  const [tasks, setTasks] = useState<VoiceTask[]>([])
  const clientRef = useRef<VoiceChatClient | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const nodesRef = useRef<OrbitNode[]>([])
  const radarRef = useRef<RadarSegment[]>([])
  const rafRef = useRef<number>(0)
  const statusRef = useRef<VoiceStatus>('idle')

  statusRef.current = status

  // 初始化画布与粒子
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      nodesRef.current = initOrbitNodes()
      radarRef.current = initRadarSegments()
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])

  // 动画循环
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const loop = () => {
      const dpr = window.devicePixelRatio || 1
      const w = canvas.width / dpr
      const h = canvas.height / dpr
      const cx = w / 2
      const cy = h / 2
      const st = statusRef.current
      const client = clientRef.current

      const micLevel = client?.getMicLevel() ?? 0
      const outLevel = client?.getOutputLevel() ?? 0
      const level = Math.max(micLevel, outLevel)

      const compact = STATUS_COMPACT[st]
      const color = STATUS_COLOR[st]
      const now = performance.now()
      const baseRadius = Math.min(w, h) * 0.24
      const ringRadius = baseRadius * (0.92 + compact * 0.14)
      const energy = level * (st === 'speaking' ? 1.2 : 0.85)

      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.save()
      ctx.scale(dpr, dpr)

      // 背景光晕：只在中心附近出现，保持界面干净
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.min(w, h) * 0.42)
      glow.addColorStop(0, `${color}2f`)
      glow.addColorStop(0.35, `${color}14`)
      glow.addColorStop(1, `${color}00`)
      ctx.fillStyle = glow
      ctx.fillRect(0, 0, w, h)

      // 外圈结构环，形成 HUD 圆形扫描面板
      drawRing(ctx, cx, cy, ringRadius * 1.18, color, 0.12)
      drawRing(ctx, cx, cy, ringRadius * 1.34, color, 0.08)
      drawRing(ctx, cx, cy, ringRadius * 1.52, color, 0.05)

      // 中心定位环与内圈刻度
      drawRing(ctx, cx, cy, ringRadius * 0.5, color, 0.4)
      drawRing(ctx, cx, cy, ringRadius * 0.72, color, 0.2)
      drawRing(ctx, cx, cy, ringRadius * 0.88, color, 0.14)

      // 动态扫掠叶片
      for (const seg of radarRef.current) {
        seg.angle += seg.speed * (st === 'speaking' ? 1.8 : 1)
        const segmentLength = seg.length * (0.9 + energy * 0.5)
        const segmentAlpha = 0.12 + Math.min(0.34, energy * 0.18)
        drawSegment(ctx, cx, cy, ringRadius * 0.58, seg.angle, segmentLength, seg.width, color, segmentAlpha)
      }

      // 中层几何节点与外层刻度
      for (const node of nodesRef.current) {
        node.angle += node.speed * (st === 'speaking' ? 1.45 : 0.8)
        const wave = Math.sin(now * 0.0016 * node.orbit + node.phase)
        const radius = ringRadius * 0.68 + (node.radius - 96) * 0.52 + wave * (1.5 + energy * 8)
        const x = cx + Math.cos(node.angle) * radius
        const y = cy + Math.sin(node.angle) * radius * 0.98

        if (node.kind === 'tick') {
          drawSegment(ctx, cx, cy, ringRadius * 0.96, node.angle, 6 + wave * 2, 0.9, color, 0.14 + energy * 0.12)
          continue
        }

        if (node.kind === 'satellite') {
          const satelliteRadius = ringRadius * 1.12 + Math.sin(now * 0.001 + node.phase) * 4
          const sx = cx + Math.cos(node.angle) * satelliteRadius
          const sy = cy + Math.sin(node.angle) * satelliteRadius * 0.95
          ctx.globalAlpha = 0.3 + energy * 0.22
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(sx, sy, node.size, 0, Math.PI * 2)
          ctx.fill()
          drawSegment(ctx, cx, cy, satelliteRadius, node.angle + 0.12, 8 + energy * 5, 0.8, color, 0.08)
          continue
        }

        ctx.globalAlpha = 0.18 + Math.min(0.62, energy * 0.28)
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.arc(x, y, node.size, 0, Math.PI * 2)
        ctx.fill()
      }

      // 中心标识：用 SIGMA 字样替代六边形，保持品牌识别
      const labelScale = 1 + energy * 0.05
      ctx.globalAlpha = 1
      ctx.fillStyle = color
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.font = `700 ${Math.max(22, ringRadius * 0.18)}px Segoe UI, Inter, Arial, sans-serif`
      ctx.letterSpacing = '0.18em'
      ctx.save()
      ctx.translate(cx, cy)
      ctx.scale(labelScale, labelScale)
      ctx.fillText('SIGMA', 0, 0)
      ctx.restore()

      // 内层聚焦脉冲
      ctx.globalAlpha = 0.2 + energy * 0.18
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(cx, cy, ringRadius * 0.16 * (1 + energy * 0.2), 0, Math.PI * 2)
      ctx.fill()

      // 从中心向外扩散的短射线，像声纹扫描而不是实心圆
      for (let i = 0; i < 18; i++) {
        const a = (Math.PI * 2 * i) / 18 + now * 0.0006
        const len = ringRadius * (0.2 + energy * 0.12) + (i % 3) * 4
        drawSegment(ctx, cx, cy, ringRadius * 0.3, a, len, 0.7, color, 0.12 + energy * 0.18)
      }

      // 中心细线框，保持 AI 仪器的秩序感
      ctx.globalAlpha = 0.55
      ctx.strokeStyle = color
      ctx.lineWidth = 0.8
      ctx.beginPath()
      ctx.arc(cx, cy, ringRadius * 0.24, 0, Math.PI * 2)
      ctx.stroke()

      ctx.restore()

      rafRef.current = requestAnimationFrame(loop)
    }

    rafRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  // ESC 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        clientRef.current?.stop()
        onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // 卸载时清理
  useEffect(() => {
    return () => {
      clientRef.current?.stop()
    }
  }, [])

  const start = useCallback(async () => {
    if (!apiKey) {
      setError('未配置火山语音 API Key，请在设置 → Skill Keys 中填写')
      return
    }
    setError('')
    const client = new VoiceChatClient({
      onStatusChange: (s) => setStatus(s),
      onError: (msg) => setError(msg),
      onReady: () => setStatus('listening'),
      onTaskEvent: (taskId, event) => handleTaskEvent(taskId, event),
    })
    clientRef.current = client
    try {
      const baseUrl = await getBackendUrl()
      const wsUrl = baseUrl.replace(/^http/, 'ws') + '/ws/voice'
      await client.start(wsUrl, { apiKey, speaker })
    } catch {
      // start 内部已设置错误
    }
  }, [apiKey, speaker])

  // 处理主 Sigma 任务过程事件，累积成 VoiceTask.blocks
  const handleTaskEvent = useCallback((taskId: string, event: Record<string, unknown>) => {
    setTasks(prev => {
      const tasks = [...prev]
      let idx = tasks.findIndex(t => t.id === taskId)
      if (idx < 0) {
        tasks.push({ id: taskId, prompt: '', blocks: [], done: false })
        idx = tasks.length - 1
      }
      const task = { ...tasks[idx], blocks: [...tasks[idx].blocks] }
      const type = event.type as string

      if (type === 'text') {
        const ct = (event.contentType as string) || 'text'
        const text = (event.content as string) || ''
        if (!text) return prev
        const last = task.blocks[task.blocks.length - 1]
        if (ct === 'thinking') {
          if (last && last.type === 'thinking') {
            task.blocks[task.blocks.length - 1] = { ...last, content: last.content + text }
          } else {
            task.blocks.push({ type: 'thinking', content: text })
          }
        } else {
          if (last && last.type === 'response_text') {
            task.blocks[task.blocks.length - 1] = { ...last, content: last.content + text }
          } else {
            task.blocks.push({ type: 'response_text', content: text })
          }
        }
      } else if (type === 'tool_start') {
        task.blocks.push({
          type: 'tool_call',
          toolName: (event.tool_name as string) || '',
          toolInput: (event.tool_input as Record<string, unknown>) || {},
        })
      } else if (type === 'tool_result') {
        const toolName = (event.tool_name as string) || ''
        for (let i = task.blocks.length - 1; i >= 0; i--) {
          const b = task.blocks[i]
          if (b.type === 'tool_call' && b.toolName === toolName && b.result === undefined) {
            task.blocks[i] = { ...b, result: (event.content as string) || '', success: !!event.success }
            break
          }
        }
      } else if (type === 'chat_complete') {
        task.done = true
      } else if (type === 'error') {
        task.done = true
        task.blocks.push({ type: 'response_text', content: `出错：${event.message || ''}` })
      }

      tasks[idx] = task
      return tasks
    })
  }, [])

  const stop = useCallback(async () => {
    await clientRef.current?.stop()
    clientRef.current = null
    setStatus('idle')
  }, [])

  const handleClose = useCallback(() => {
    clientRef.current?.stop()
    onClose()
  }, [onClose])

  const isActive = status === 'connecting' || status === 'listening' || status === 'speaking'

  return (
    <div className="voice-backdrop" onClick={handleClose}>
      <div className="voice-modal" onClick={(e) => e.stopPropagation()}>
        <div className="voice-header">
          <span className="voice-title">语音通话</span>
          <button className="voice-close" onClick={handleClose} title="关闭">
            <X size={18} />
          </button>
        </div>

        <div className="voice-body">
          {/* 左侧：粒子动画 + 状态 + 操作 */}
          <div className="voice-left">
            <canvas ref={canvasRef} className="voice-canvas" />
            <div className="voice-status">{error || STATUS_LABEL[status]}</div>
            <div className="voice-actions">
              {!isActive ? (
                <button className="voice-btn voice-btn-start" onClick={start}>
                  <Mic size={22} />
                  <span>开始通话</span>
                </button>
              ) : (
                <button className="voice-btn voice-btn-stop" onClick={stop}>
                  <PhoneOff size={22} />
                  <span>结束通话</span>
                </button>
              )}
            </div>
          </div>

          {/* 右侧：主 Sigma 任务过程 */}
          <div className="voice-right">
            <div className="voice-right-title">主 Sigma 任务过程</div>
            <div className="voice-tasks">
              {tasks.length === 0 && (
                <div className="voice-tasks-empty">语音发起任务后，这里会显示主 Sigma 的思考与工具调用过程</div>
              )}
              {tasks.map(task => (
                <TaskProcessView key={task.id} task={task} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── 单个任务过程渲染：复用主界面 block 的简洁版 ──

function TaskProcessView({ task }: { task: VoiceTask }) {
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [task.blocks])

  return (
    <div className="voice-task">
      <div className="voice-task-header">
        <span className={`voice-task-dot ${task.done ? 'done' : 'running'}`} />
        <span className="voice-task-id">{task.id}</span>
        {!task.done && <span className="voice-task-running">进行中</span>}
        {task.done && <span className="voice-task-done">已完成</span>}
      </div>
      <div ref={bodyRef} className="voice-task-body">
        {task.blocks.map((block, i) =>
          block.type === 'thinking' ? (
            <div key={i} className="vt-block vt-thinking">{block.content}</div>
          ) : block.type === 'response_text' ? (
            <div key={i} className="vt-block vt-response">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
            </div>
          ) : (
            <TaskToolBlock key={i} block={block} />
          )
        )}
      </div>
    </div>
  )
}

function TaskToolBlock({ block }: { block: Extract<TaskBlock, { type: 'tool_call' }> }) {
  const [collapsed, setCollapsed] = useState(false)
  const hasResult = block.result !== undefined
  const firstLine = hasResult ? (block.result || '').split('\n')[0].slice(0, 50) : ''

  return (
    <div className={`vt-block vt-tool ${hasResult ? (block.success ? 'success' : 'failed') : 'running'}`}>
      <div className="vt-tool-header" onClick={() => hasResult && setCollapsed(v => !v)}>
        <span className="vt-tool-icon">
          {!hasResult ? <span className="vt-spinner" /> : block.success ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
        </span>
        <Wrench size={11} />
        <span className="vt-tool-name">{block.toolName}</span>
        <span className="vt-tool-preview">{firstLine}</span>
        {hasResult && <span className="vt-tool-toggle">{collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}</span>}
      </div>
      {!collapsed && hasResult && (
        <pre className="vt-tool-result">{block.result}</pre>
      )}
    </div>
  )
}
