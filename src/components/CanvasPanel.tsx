import { useCallback, useEffect, useRef, useState } from 'react'
import { BRUSHES, BRUSH_NAMES } from '../paint/brushes'
import { paintBus } from '../paint/bus'
import { buildDemoStrokes } from '../paint/demo'
import { PaintEngine } from '../paint/engine'
import { AppliedLedger, applyCommands } from '../paint/executor'
import { validateCommands, type CommandIssue } from '../paint/protocol'
import type { BrushName, LayerData, Point } from '../paint/types'
import { CANVAS_HEIGHT, CANVAS_WIDTH } from '../paint/types'
import type { CharacterPreview } from '../characters/bus'
import { characterBus } from '../characters/bus'
import { getBackendUrl } from '../utils/config'
import CharacterSheetPanel from './CharacterSheetPanel'
import './CanvasPanel.css'

const PALETTE = ['#3a3733', '#eda866', '#c9762f', '#e39a9a', '#6a9ec4', '#7fa96b', '#8d8175', '#ffffff']

type Phase = 'idle' | 'painting' | 'done'

function sameLayers(a: LayerData[], b: LayerData[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    const x = a[i], y = b[i]
    if (x.id !== y.id || x.name !== y.name || x.visible !== y.visible || x.opacity !== y.opacity) return false
  }
  return true
}

export default function CanvasPanel() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const engineRef = useRef<PaintEngine | null>(null)
  const ledgerRef = useRef(new AppliedLedger())

  const [layers, setLayers] = useState<LayerData[]>([])
  const [activeLayer, setActiveLayer] = useState('outline')
  const [brush, setBrush] = useState<BrushName>('pencil')
  const [color, setColor] = useState('#3a3733')
  const [lineWidth, setLineWidth] = useState(3.2)
  const [canUndo, setCanUndo] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [strokeCount, setStrokeCount] = useState(0)
  const [phase, setPhase] = useState<Phase>('idle')
  const [issues, setIssues] = useState<CommandIssue[]>([])
  // 定妆预览：盖在绘画画布之上，画布本身保持挂载，关掉预览不会丢笔迹
  const [character, setCharacter] = useState<CharacterPreview | null>(characterBus.active)
  const drawingRef = useRef(false)
  // 已应用（不等于已画完）的笔迹数：快照去重用它，而不是用渲染进度，
  // 否则窗口切到后台、动画被节流时笔数不涨，会误判成没内容而不回传。
  const appliedStrokesRef = useRef(0)
  const uploadedStrokesRef = useRef(0)
  const snapshotTimerRef = useRef<number | null>(null)

  /**
   * 把当前完整画面回传给后端，供 canvas_review 审查。
   * 用 exportComplete 而不是截图，保证拿到的是成品而不是动画中间态。
   *
   * force 用于一轮绘制的收尾：流式阶段可能已经回传过同笔数的画面，
   * 但后端只认"最后一条指令之后"的回传，所以收尾必须无条件重传一次。
   */
  const uploadSnapshot = useCallback(async (force = false) => {
    const engine = engineRef.current
    if (!engine) return
    if (appliedStrokesRef.current === 0) return
    if (!force && appliedStrokesRef.current === uploadedStrokesRef.current) return
    uploadedStrokesRef.current = appliedStrokesRef.current
    try {
      const image = engine.exportComplete('image/jpeg', 0.85)
      const base = await getBackendUrl()
      await fetch(`${base}/api/paint/snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image,
          strokes: appliedStrokesRef.current,
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          layers: engine.getLayers().map(layer => layer.id),
          // 笔迹几何事实：后端用它做精确审计，避免视觉模型凭观感误报
          stroke_audit: engine.auditStrokes(),
        }),
      })
    } catch {
      // 回传失败不影响绘制本身；下一次落笔后会再试
      uploadedStrokesRef.current = 0
    }
  }, [])

  // 收到指令后延迟回传一张完整画面。
  // 不等动画播完：exportComplete 会把还没落盘的笔迹补齐，任何时候导出的都是成品，
  // 因此回传时机只取决于指令何时到齐，不受逐笔动画长短影响。
  const scheduleSnapshot = useCallback((force = false) => {
    if (snapshotTimerRef.current) window.clearTimeout(snapshotTimerRef.current)
    snapshotTimerRef.current = window.setTimeout(() => {
      snapshotTimerRef.current = null
      void uploadSnapshot(force)
    }, 400)
  }, [uploadSnapshot])

  useEffect(() => characterBus.subscribe(setCharacter), [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const engine = new PaintEngine(canvas, { width: CANVAS_WIDTH, height: CANVAS_HEIGHT })
    engineRef.current = engine

    const sync = () => {
      const next = engine.getLayers()
      setLayers(prev => (sameLayers(prev, next) ? prev : next))
      setCanUndo(engine.canUndo)
      setPlaying(engine.isPlaying)
      setStrokeCount(engine.strokeCount)
    }
    const unsubscribe = engine.subscribe(sync)

    // 指令流：边到边校验、去重、上屏
    const unsubscribeBus = paintBus.subscribe(patch => {
      const { commands, issues: found } = validateCommands(patch.commands)
      // 整张清空后笔迹计数归零，否则新画面会被当成"已经回传过"而跳过
      if (commands.some(cmd => cmd.op === 'clear')) {
        appliedStrokesRef.current = 0
        uploadedStrokesRef.current = 0
      }
      const fresh = commands.filter(cmd => ledgerRef.current.shouldApply(cmd))
      if (fresh.length > 0) {
        const outcome = applyCommands(engine, fresh, 'play')
        appliedStrokesRef.current += outcome.painted
        setPhase('painting')
        scheduleSnapshot()
      }
      if (found.length > 0) {
        setIssues(prev => [...prev, ...found].slice(-12))
      }
      if (patch.final) {
        setPhase('done')
        // 收尾必须无条件重传：后端以"最后一条指令之后"的回传为准
        scheduleSnapshot(true)
      }
    })

    sync()
    const initialLayers = engine.getLayers()
    setActiveLayer(initialLayers[initialLayers.length - 1]?.id ?? 'outline')

    return () => {
      unsubscribe()
      unsubscribeBus()
      if (snapshotTimerRef.current) window.clearTimeout(snapshotTimerRef.current)
      engine.destroy()
      engineRef.current = null
    }
  }, [scheduleSnapshot])

  const toCanvasPoint = useCallback((event: React.PointerEvent<HTMLCanvasElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect()
    return [
      ((event.clientX - rect.left) / rect.width) * CANVAS_WIDTH,
      ((event.clientY - rect.top) / rect.height) * CANVAS_HEIGHT,
    ]
  }, [])

  // 笔迹画完、队列清空后收尾状态
  useEffect(() => {
    if (phase === 'painting' && !playing && strokeCount > 0) setPhase('done')
  }, [phase, playing, strokeCount])

  const handlePointerDown = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    const engine = engineRef.current
    if (!engine || event.button !== 0) return
    if (engine.isPlaying) engine.finishAll()
    event.currentTarget.setPointerCapture(event.pointerId)
    drawingRef.current = true
    engine.beginLive({
      id: `live-${Date.now().toString(36)}-${Math.floor(Math.random() * 1000)}`,
      layer: activeLayer,
      brush,
      color,
      width: lineWidth,
      opacity: 1,
      smooth: 0,
      seed: Math.floor(Math.random() * 1e6),
      points: [toCanvasPoint(event)],
    })
  }, [activeLayer, brush, color, lineWidth, toCanvasPoint])

  const handlePointerMove = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return
    engineRef.current?.extendLive(toCanvasPoint(event))
  }, [toCanvasPoint])

  const handlePointerUp = useCallback(() => {
    if (!drawingRef.current) return
    drawingRef.current = false
    engineRef.current?.endLive()
  }, [])

  const handleDemo = useCallback(() => {
    const engine = engineRef.current
    if (!engine) return
    paintBus.reset()
    ledgerRef.current.reset()
    uploadedStrokesRef.current = 0
    engine.clear()
    setIssues([])
    setPhase('painting')
    engine.play(buildDemoStrokes())
  }, [])

  const handleReplay = useCallback(() => {
    const engine = engineRef.current
    if (!engine) return
    engine.replayAll()
  }, [])

  const handleClear = useCallback(() => {
    const engine = engineRef.current
    if (!engine) return
    paintBus.reset()
    ledgerRef.current.reset()
    uploadedStrokesRef.current = 0
    engine.clear()
    setIssues([])
    setPhase('idle')
    // 画布已空，后端快照也要丢弃，否则下一步会审查到已经不存在的画面
    void (async () => {
      try {
        const base = await getBackendUrl()
        await fetch(`${base}/api/paint/clear`, { method: 'POST' })
      } catch { /* 后端未就绪时忽略 */ }
    })()
  }, [])

  const handleExport = useCallback(() => {
    const engine = engineRef.current
    if (!engine) return
    const link = document.createElement('a')
    link.href = engine.toDataURL('image/png')
    link.download = `paint-${new Date().toISOString().replace(/[:.]/g, '-')}.png`
    link.click()
  }, [])

  const orderedLayers = [...layers].reverse()

  const statusText = phase === 'painting'
    ? `绘制中 · ${strokeCount} 笔`
    : phase === 'done'
      ? `已完成 · ${strokeCount} 笔`
      : '等待指令'

  return (
    <div className="canvas-panel">
      <div className="canvas-panel-toolbar">
        <span className={`canvas-status ${phase}`}>{statusText}</span>

        <div className="paint-group">
          {BRUSH_NAMES.map(name => (
            <button
              key={name}
              className={`paint-brush-btn ${brush === name ? 'active' : ''}`}
              onClick={() => setBrush(name)}
              title={BRUSHES[name].label}
            >
              {BRUSHES[name].label}
            </button>
          ))}
        </div>

        <div className="paint-group paint-colors">
          {PALETTE.map(hex => (
            <button
              key={hex}
              className={`paint-swatch ${color.toLowerCase() === hex ? 'active' : ''}`}
              style={{ background: hex }}
              onClick={() => setColor(hex)}
              aria-label={`颜色 ${hex}`}
            />
          ))}
          <input
            type="color"
            className="paint-color-input"
            value={color}
            onChange={e => setColor(e.target.value)}
            aria-label="自定义颜色"
          />
        </div>

        <div className="paint-group paint-width-group">
          <span className="paint-label">笔宽</span>
          <input
            type="range"
            min={0.8}
            max={40}
            step={0.2}
            value={lineWidth}
            onChange={e => setLineWidth(Number(e.target.value))}
            className="paint-width-range"
          />
          <span className="paint-width-value">{lineWidth.toFixed(1)}</span>
        </div>

        <div className="paint-group paint-actions">
          <button onClick={() => engineRef.current?.undo()} disabled={!canUndo}>撤销</button>
          <button onClick={handleClear} disabled={strokeCount === 0}>清空</button>
          <button onClick={handleReplay} disabled={strokeCount === 0}>重播</button>
          <button onClick={() => engineRef.current?.finishAll()} disabled={!playing}>跳过动画</button>
          <button onClick={handleDemo}>示例</button>
          <button onClick={handleExport} disabled={strokeCount === 0}>导出 PNG</button>
        </div>
      </div>

      {issues.length > 0 && (
        <div className="canvas-issues">
          {issues.map((issue, i) => (
            <div key={`${issue.index}-${i}`}>
              指令 #{issue.index + 1}
              {issue.id ? ` (${issue.id})` : ''}：{issue.message}
            </div>
          ))}
        </div>
      )}

      <div className="canvas-panel-body">
        <div className="paint-stage">
          <canvas
            ref={canvasRef}
            className="paint-canvas"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
          />
        </div>

        <div className="paint-layers">
          <div className="paint-layers-header">
            <span>图层</span>
            <button onClick={() => engineRef.current?.addLayer(`图层 ${layers.length}`)}>新建</button>
          </div>
          <div className="paint-layers-list">
            {orderedLayers.map(layer => (
              <div
                key={layer.id}
                className={`paint-layer-item ${activeLayer === layer.id ? 'active' : ''}`}
                onClick={() => setActiveLayer(layer.id)}
              >
                <button
                  className={`paint-layer-eye ${layer.visible ? 'on' : ''}`}
                  onClick={e => { e.stopPropagation(); engineRef.current?.setLayerVisible(layer.id, !layer.visible) }}
                  title={layer.visible ? '隐藏' : '显示'}
                >
                  {layer.visible ? '◉' : '○'}
                </button>
                <span className="paint-layer-name">{layer.name}</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={layer.opacity}
                  onClick={e => e.stopPropagation()}
                  onChange={e => engineRef.current?.setLayerOpacity(layer.id, Number(e.target.value))}
                  className="paint-layer-opacity"
                  title="不透明度"
                />
              </div>
            ))}
          </div>
          <div className="paint-layers-footer">
            <button onClick={() => engineRef.current?.moveLayer(activeLayer, 1)}>上移</button>
            <button onClick={() => engineRef.current?.moveLayer(activeLayer, -1)}>下移</button>
            <button
              className="danger"
              onClick={() => engineRef.current?.removeLayer(activeLayer)}
              disabled={layers.length <= 1}
            >
              删除
            </button>
          </div>
        </div>
      </div>

      {character && (
        <div className="char-sheet-overlay">
          <CharacterSheetPanel preview={character} />
        </div>
      )}
    </div>
  )
}
