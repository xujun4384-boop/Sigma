import { paintBus } from './bus'
import { buildDemoStrokes } from './demo'
import { PaintEngine } from './engine'
import { AppliedLedger, applyCommands } from './executor'
import { validateCommands } from './protocol'
import { CANVAS_HEIGHT, CANVAS_WIDTH } from './types'

document.body.style.margin = '0'
document.body.style.background = '#262626'

const canvas = document.createElement('canvas')
canvas.style.cssText = 'display:block;width:100%;height:auto;aspect-ratio:1600/1000;max-width:1400px;margin:24px auto;'
document.body.appendChild(canvas)

const engine = new PaintEngine(canvas, { width: CANVAS_WIDTH, height: CANVAS_HEIGHT })
const ledger = new AppliedLedger()

// 与 CanvasPanel 完全相同的消费链路：校验 → 去重 → 应用
paintBus.subscribe(patch => {
  const { commands, issues } = validateCommands(patch.commands)
  const fresh = commands.filter(cmd => ledger.shouldApply(cmd))
  if (fresh.length > 0) applyCommands(engine, fresh, 'play')
  if (issues.length > 0) {
    console.warn('[paint] 指令问题', issues)
    ;(window as any).paintLab.issues = issues
  }
})

;(window as any).paintLab = {
  engine,
  issues: [] as unknown[],
  /** 模拟后端 SSE 下发一批指令 */
  emit: (commands: unknown[], final = false) => paintBus.emit({ commands, final }),
  validate: validateCommands,
  applyNow: (commands: unknown[]) => {
    const { commands: valid, issues } = validateCommands(commands)
    return { applied: applyCommands(engine, valid, 'instant').applied, issues }
  },
  finish: () => engine.finishAll(),
  audit: () => engine.auditStrokes(),
  exportNow: () => engine.exportComplete('image/jpeg', 0.85),
  /** 模拟 CanvasPanel 的回传链路，用于端到端验证 */
  uploadSnapshot: async () => {
    const image = engine.exportComplete('image/jpeg', 0.85)
    const res = await fetch('http://127.0.0.1:8765/api/paint/snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image, strokes: engine.strokeCount, layers: engine.getLayers().map(l => l.id) }),
    })
    return { status: res.status, body: await res.json(), bytes: Math.round(image.length / 1024) }
  },
  demo: () => {
    engine.clear()
    ledger.reset()
    engine.play(buildDemoStrokes())
  },
  state: () => ({
    strokes: engine.getScene().strokes.length,
    layers: engine.getLayers().map(l => l.id),
    playing: engine.isPlaying,
  }),
}
