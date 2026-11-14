import { BRUSHES, paintSample } from './brushes'
import { catmullRom, resample } from './path'
import type { LayerData, Point, SceneData, Stroke, StrokeAudit } from './types'
import { CANVAS_HEIGHT, CANVAS_WIDTH } from './types'

const DEFAULT_BACKGROUND = '#fbfaf6'
/** 单笔最短播放时长（秒），避免短笔一闪而过看不见 */
const MIN_STROKE_SECONDS = 0.05
/** 单笔最长播放时长（秒），避免个别超长笔画拖住整段节奏 */
const MAX_STROKE_SECONDS = 1.6
/** 整批播放的默认总时长（秒） */
const DEFAULT_PLAY_SECONDS = 12

interface LayerState {
  data: LayerData
  canvas: HTMLCanvasElement
  ctx: CanvasRenderingContext2D
  strokeIds: string[]
}

interface ActiveStroke {
  stroke: Stroke
  samples: Point[]
  drawn: number
  progress: number
  mode: 'anim' | 'live'
  /** 播放时整笔需要的秒数 */
  duration: number
  /** 播放起始时间戳，进度按真实时间推进，掉帧时不会拖慢整体节奏 */
  startTs: number
}

interface QueuedStroke {
  stroke: Stroke
  duration: number
}

export interface EngineOptions {
  width?: number
  height?: number
  background?: string
}

function createCanvas(width: number, height: number, dpr: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * dpr))
  canvas.height = Math.max(1, Math.round(height * dpr))
  return canvas
}

/** 原始控制点的路径长度，用于给每笔分配播放时长（不必先展开采样点） */
function strokeLength(stroke: Stroke): number {
  let total = 0
  for (let i = 1; i < stroke.points.length; i++) {
    total += Math.hypot(stroke.points[i][0] - stroke.points[i - 1][0], stroke.points[i][1] - stroke.points[i - 1][1])
  }
  return total
}

/**
 * 绘画引擎：持有图层位图、笔迹数据与播放状态。
 * 组件只负责 UI 与指针事件，所有绘制都收敛到这里。
 */
export class PaintEngine {
  readonly canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D
  private width: number
  private height: number
  private dpr: number
  private background: string

  private layers = new Map<string, LayerState>()
  private order: string[] = []
  private strokes: Stroke[] = []

  private active: ActiveStroke | null = null
  private queue: Stroke[] = []
  private raf = 0
  private lastTs = 0

  private scratch: HTMLCanvasElement
  private scratchCtx: CanvasRenderingContext2D
  private listeners = new Set<() => void>()

  constructor(canvas: HTMLCanvasElement, options: EngineOptions = {}) {
    this.canvas = canvas
    this.width = options.width ?? CANVAS_WIDTH
    this.height = options.height ?? CANVAS_HEIGHT
    this.background = options.background ?? DEFAULT_BACKGROUND
    this.dpr = Math.min(2, window.devicePixelRatio || 1)
    canvas.width = Math.round(this.width * this.dpr)
    canvas.height = Math.round(this.height * this.dpr)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('无法获取画布上下文')
    this.ctx = ctx

    this.scratch = createCanvas(this.width, this.height, this.dpr)
    this.scratchCtx = this.scratch.getContext('2d')!
    this.scratchCtx.lineCap = 'round'
    this.scratchCtx.lineJoin = 'round'

    this.createLayer({ id: 'color', name: '上色', visible: true, opacity: 1 })
    this.createLayer({ id: 'outline', name: '线稿', visible: true, opacity: 1 })
    this.createLayer({ id: 'detail', name: '细节', visible: true, opacity: 1 })
    this.render()
  }

  // ── 订阅 ──

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private emit(): void {
    this.listeners.forEach(fn => fn())
  }

  // ── 图层 ──

  private createLayer(data: LayerData): LayerState {
    const canvas = createCanvas(this.width, this.height, this.dpr)
    const state: LayerState = {
      data,
      canvas,
      ctx: canvas.getContext('2d')!,
      strokeIds: [],
    }
    state.ctx.lineCap = 'round'
    state.ctx.lineJoin = 'round'
    this.layers.set(data.id, state)
    this.order.push(data.id)
    return state
  }

  getLayers(): LayerData[] {
    return this.order.map(id => ({ ...this.layers.get(id)!.data }))
  }

  addLayer(name: string): string {
    const id = `layer-${Date.now().toString(36)}-${Math.floor(Math.random() * 1000)}`
    this.createLayer({ id, name, visible: true, opacity: 1 })
    this.render()
    this.emit()
    return id
  }

  /**
   * 按 id 取图层，不存在则创建。
   * 流式指令里笔画可能先于图层声明到达，所以这里必须宽容地自动建层。
   */
  ensureLayer(id: string, name?: string): LayerState {
    const existing = this.layers.get(id)
    if (existing) {
      if (name && existing.data.name !== name) {
        existing.data.name = name
        this.emit()
      }
      return existing
    }
    return this.createLayer({ id, name: name || id, visible: true, opacity: 1 })
  }

  hasLayer(id: string): boolean {
    return this.layers.has(id)
  }

  removeLayer(id: string): void {
    if (this.order.length <= 1) return
    const layer = this.layers.get(id)
    if (!layer) return
    const removed = new Set(layer.strokeIds)
    this.strokes = this.strokes.filter(s => !removed.has(s.id))
    this.layers.delete(id)
    this.order = this.order.filter(x => x !== id)
    this.render()
    this.emit()
  }

  setLayerVisible(id: string, visible: boolean): void {
    const layer = this.layers.get(id)
    if (!layer) return
    layer.data.visible = visible
    this.render()
    this.emit()
  }

  setLayerOpacity(id: string, opacity: number): void {
    const layer = this.layers.get(id)
    if (!layer) return
    layer.data.opacity = Math.max(0, Math.min(1, opacity))
    this.render()
    this.emit()
  }

  moveLayer(id: string, delta: number): void {
    const from = this.order.indexOf(id)
    if (from < 0) return
    const to = Math.max(0, Math.min(this.order.length - 1, from + delta))
    if (to === from) return
    this.order.splice(from, 1)
    this.order.splice(to, 0, id)
    this.render()
    this.emit()
  }

  // ── 笔迹 ──

  private buildSamples(stroke: Stroke): Point[] {
    const spec = BRUSHES[stroke.brush]
    const spacing = spec ? spec.spacing(stroke.width) : Math.max(0.8, stroke.width * 0.2)
    const smooth = stroke.smooth ?? 0
    const path = smooth > 0 && stroke.points.length > 2
      ? catmullRom(stroke.points, smooth, false)
      : stroke.points
    return resample(path, spacing)
  }

  private drawRange(active: ActiveStroke, from: number, to: number): void {
    const ctx = this.scratchCtx
    const samples = active.samples
    const total = samples.length
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    for (let i = Math.max(1, from); i < to; i++) {
      paintSample(ctx, active.stroke, samples[i - 1], samples[i], i, total)
    }
  }

  private startActive(stroke: Stroke, mode: 'anim' | 'live', durationOverride?: number, startTs?: number): void {
    this.endActive()
    this.scratchCtx.setTransform(1, 0, 0, 1, 0, 0)
    this.scratchCtx.clearRect(0, 0, this.scratch.width, this.scratch.height)

    const samples = this.buildSamples(stroke)

    this.active = {
      stroke,
      samples,
      drawn: 0,
      progress: mode === 'live' ? 1 : 0,
      mode,
      duration: durationOverride ?? MIN_STROKE_SECONDS,
      startTs: startTs ?? performance.now(),
    }
    this.startLoop()
  }

  private endActive(): void {
    const active = this.active
    if (!active) return
    this.active = null
    // 未画完的整笔补完，保证提交到图层的笔迹完整
    const target = active.samples.length
    if (active.drawn < target) {
      this.scratchCtx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
      for (let i = Math.max(1, active.drawn); i < target; i++) {
        paintSample(this.scratchCtx, active.stroke, active.samples[i - 1], active.samples[i], i, target)
      }
    }
    this.commit(active)
  }

  private commit(active: ActiveStroke): void {
    const layer = this.ensureLayer(active.stroke.layer)
    layer.ctx.setTransform(1, 0, 0, 1, 0, 0)
    layer.ctx.drawImage(this.scratch, 0, 0)
    layer.strokeIds.push(active.stroke.id)
    this.strokes.push(active.stroke)
    this.render()
    this.emit()
  }

  /** 批量修改后统一刷新一次（渲染 + 通知订阅者） */
  refresh(): void {
    this.render()
    this.emit()
  }

  /**
   * 播放一串笔迹（逐笔生长）。
   * totalSeconds 控制整批总时长：按每笔路径长度分配时间，笔数再多也不会拖成几分钟。
   */
  play(strokes: Stroke[], totalSeconds = DEFAULT_PLAY_SECONDS): void {
    if (strokes.length === 0) return
    const lengths = strokes.map(strokeLength)
    const totalLength = lengths.reduce((a, b) => a + b, 0)
    const perPixel = totalLength > 0 ? totalSeconds / totalLength : 0

    this.queue = strokes.map((s, i) => ({
      stroke: { ...s, points: s.points.map(p => [...p] as Point) },
      duration: Math.min(MAX_STROKE_SECONDS, Math.max(MIN_STROKE_SECONDS, lengths[i] * perPixel)),
    }))
    this.startLoop()
  }

  /**
   * 流式追加笔迹：模型还在输出时就边到边画。
   * 队列积压越多单笔越快，避免"模型早已说完、画面还在慢慢追"。
   */
  enqueue(strokes: Stroke[], secondsPerStroke = 0.18): void {
    if (strokes.length === 0) return
    for (const stroke of strokes) {
      const copy = { ...stroke, points: stroke.points.map(p => [...p] as Point) }
      this.queue.push({ stroke: copy, duration: this.paceDuration(secondsPerStroke) })
    }
    this.startLoop()
  }

  private paceDuration(base: number): number {
    const backlog = this.queue.length
    const factor = Math.min(1, Math.max(0.3, 8 / (backlog + 8)))
    return Math.max(MIN_STROKE_SECONDS, Math.min(MAX_STROKE_SECONDS, base * factor))
  }

  /** 立即提交一笔（不播动画）。同 id 会覆盖旧笔，用于修正式指令 */
  applyStrokeNow(stroke: Stroke): void {
    this.removeStrokeById(stroke.id, false)
    const layer = this.ensureLayer(stroke.layer)
    const samples = this.buildSamples(stroke)
    layer.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    for (let i = 1; i < samples.length; i++) {
      paintSample(layer.ctx, stroke, samples[i - 1], samples[i], i, samples.length)
    }
    layer.strokeIds.push(stroke.id)
    this.strokes.push(stroke)
  }

  /** 按 id 删除一笔。notify=false 时不触发重绘，供批量操作内部调用 */
  removeStrokeById(id: string, notify = true): boolean {
    // 还没画到的笔也要从队列里摘掉，否则删完又会被补画出来
    this.queue = this.queue.filter(q => q.stroke.id !== id)
    if (this.active?.stroke.id === id) this.active = null

    const index = this.strokes.findIndex(s => s.id === id)
    if (index < 0) return false
    const [stroke] = this.strokes.splice(index, 1)
    const layer = this.layers.get(stroke.layer)
    if (layer) {
      layer.strokeIds = layer.strokeIds.filter(x => x !== id)
      this.redrawLayer(layer)
    }
    if (notify) {
      this.render()
      this.emit()
    }
    return true
  }

  /** 清空指定图层的所有笔迹，保留图层本身 */
  clearLayerStrokes(id: string): void {
    const layer = this.layers.get(id)
    if (!layer) return
    const ids = new Set(layer.strokeIds)
    this.strokes = this.strokes.filter(s => !ids.has(s.id))
    this.queue = this.queue.filter(q => q.stroke.layer !== id)
    if (this.active?.stroke.layer === id) this.active = null
    layer.strokeIds = []
    layer.ctx.setTransform(1, 0, 0, 1, 0, 0)
    layer.ctx.clearRect(0, 0, layer.canvas.width, layer.canvas.height)
    this.render()
    this.emit()
  }

  get isPlaying(): boolean {
    return this.queue.length > 0 || this.active !== null
  }

  /** 从头重播当前所有笔迹，保留图层结构 */
  replayAll(totalSeconds = DEFAULT_PLAY_SECONDS): void {
    if (this.strokes.length === 0) return
    const saved = this.strokes.map(s => ({ ...s, points: s.points.map(p => [...p] as Point) }))
    for (const layer of this.layers.values()) {
      layer.strokeIds = []
      layer.ctx.setTransform(1, 0, 0, 1, 0, 0)
      layer.ctx.clearRect(0, 0, layer.canvas.width, layer.canvas.height)
    }
    this.strokes = []
    this.play(saved, totalSeconds)
  }

  get strokeCount(): number {
    return this.strokes.length
  }

  get pendingCount(): number {
    return this.queue.length
  }

  /** 立即完成剩余所有笔迹 */
  finishAll(): void {
    while (this.queue.length > 0) {
      const next = this.queue.shift()!
      this.startActive(next.stroke, 'anim', next.duration)
      this.endActive()
    }
    if (this.active) this.endActive()
    this.render()
    this.emit()
  }

  // ── 手绘 ──

  beginLive(stroke: Omit<Stroke, 'points'> & { points?: Point[] }): void {
    const full: Stroke = { ...stroke, points: stroke.points?.slice() ?? [] }
    this.startActive(full, 'live')
  }

  extendLive(point: Point): void {
    const active = this.active
    if (!active || active.mode !== 'live') return
    const stroke = active.stroke
    const last = stroke.points[stroke.points.length - 1]
    if (last && Math.hypot(point[0] - last[0], point[1] - last[1]) < 0.8) return

    stroke.points.push(point)
    const spec = BRUSHES[stroke.brush]
    const spacing = spec ? spec.spacing(stroke.width) : 1
    const tail = last ? resample([last, point], spacing) : [point]
    // 首点与已有点重复，去掉
    if (last) tail.shift()
    active.samples.push(...tail)
    this.startLoop()
  }

  endLive(): void {
    const active = this.active
    if (!active || active.mode !== 'live') return
    if (active.samples.length < 2) {
      this.active = null
      this.scratchCtx.setTransform(1, 0, 0, 1, 0, 0)
      this.scratchCtx.clearRect(0, 0, this.scratch.width, this.scratch.height)
      this.render()
      return
    }
    this.endActive()
  }

  // ── 撤销与清空 ──

  get canUndo(): boolean {
    return this.strokes.length > 0
  }

  undo(): void {
    const last = this.strokes.pop()
    if (!last) return
    const layer = this.layers.get(last.layer)
    if (!layer) return
    layer.strokeIds = layer.strokeIds.filter(id => id !== last.id)
    this.redrawLayer(layer)
    this.render()
    this.emit()
  }

  clear(): void {
    this.strokes = []
    this.queue = []
    this.active = null
    for (const layer of this.layers.values()) {
      layer.strokeIds = []
      layer.ctx.setTransform(1, 0, 0, 1, 0, 0)
      layer.ctx.clearRect(0, 0, layer.canvas.width, layer.canvas.height)
    }
    this.render()
    this.emit()
  }

  private redrawLayer(layer: LayerState): void {
    layer.ctx.setTransform(1, 0, 0, 1, 0, 0)
    layer.ctx.clearRect(0, 0, layer.canvas.width, layer.canvas.height)
    layer.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    const byId = new Map(this.strokes.map(s => [s.id, s]))
    for (const id of layer.strokeIds) {
      const stroke = byId.get(id)
      if (!stroke) continue
      const samples = this.buildSamples(stroke)
      for (let i = 1; i < samples.length; i++) {
        paintSample(layer.ctx, stroke, samples[i - 1], samples[i], i, samples.length)
      }
    }
  }

  // ── 场景序列化 ──

  getScene(): SceneData {
    return {
      version: 2,
      width: this.width,
      height: this.height,
      layers: this.getLayers(),
      strokes: this.strokes.map(s => ({ ...s, points: s.points.map(p => [...p] as Point) })),
    }
  }

  loadScene(scene: SceneData): void {
    this.clear()
    this.layers.clear()
    this.order = []
    this.strokes = []
    const layers = scene.layers?.length ? scene.layers : [{ id: 'outline', name: '线稿', visible: true, opacity: 1 }]
    for (const data of layers) this.createLayer({ ...data })

    const byId = new Map(this.order.map(id => [id, this.layers.get(id)!]))
    for (const stroke of scene.strokes ?? []) {
      const layer = byId.get(stroke.layer) ?? this.layers.get(this.order[0])
      if (!layer) continue
      const normalized: Stroke = { ...stroke, layer: layer.data.id }
      const samples = this.buildSamples(normalized)
      layer.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
      for (let i = 1; i < samples.length; i++) {
        paintSample(layer.ctx, normalized, samples[i - 1], samples[i], i, samples.length)
      }
      layer.strokeIds.push(normalized.id)
      this.strokes.push(normalized)
    }
    this.render()
    this.emit()
  }

  // ── 渲染循环 ──

  private startLoop(): void {
    if (this.raf) return
    this.lastTs = performance.now()
    this.raf = requestAnimationFrame(this.loop)
  }

  private loop = (ts: number): void => {
    this.lastTs = ts

    // 一帧内把已经超时的笔迹依次画完再渲染。
    // 否则低帧率环境下每帧只能完成一笔，整段动画会被拖成几十秒。
    let cursor = ts
    let guard = 0
    while (guard++ < 200) {
      if (!this.active && this.queue.length > 0) {
        const next = this.queue.shift()!
        this.startActive(next.stroke, 'anim', next.duration, cursor)
      }

      const active = this.active
      if (!active) break

      if (active.mode === 'anim') {
        // 进度按本帧真实时间算；startTs 由 cursor 连续排布，
        // 两者配合才能在一帧内把积压的笔画依次消化掉。
        active.progress = Math.min(1, (ts - active.startTs) / (active.duration * 1000))
      }
      const target = active.mode === 'live'
        ? active.samples.length
        : Math.max(1, Math.ceil(active.samples.length * active.progress))
      if (target > active.drawn) {
        this.drawRange(active, active.drawn, target)
        active.drawn = target
      }

      if (active.mode === 'anim' && active.progress >= 1) {
        cursor = active.startTs + active.duration * 1000
        this.endActive()
        continue
      }
      break
    }

    this.render()

    if (this.active || this.queue.length > 0) {
      this.raf = requestAnimationFrame(this.loop)
    } else {
      this.raf = 0
      this.emit()
    }
  }

  render(): void {
    const ctx = this.ctx
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.globalAlpha = 1
    ctx.globalCompositeOperation = 'source-over'
    ctx.fillStyle = this.background
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height)

    for (const id of this.order) {
      const layer = this.layers.get(id)
      if (!layer || !layer.data.visible || layer.data.opacity <= 0) continue
      ctx.globalAlpha = layer.data.opacity
      ctx.drawImage(layer.canvas, 0, 0)
    }

    const active = this.active
    if (active) {
      const layer = this.layers.get(active.stroke.layer)
      if (layer?.data.visible && layer.data.opacity > 0) {
        ctx.globalAlpha = layer.data.opacity
        ctx.drawImage(this.scratch, 0, 0)
      }
    }
    ctx.globalAlpha = 1
  }

  /** 当前合成图，用于导出或回传给模型看图 */
  toDataURL(type = 'image/png'): string {
    this.render()
    return this.canvas.toDataURL(type)
  }

  /**
   * 导出"完整画面"，与当前播放进度无关。
   *
   * 播放过程中有两类笔迹还没落到图层位图上：正在生长的那一笔，以及队列里排队等待的。
   * 直接截屏会只截到一部分，模型据此评审会得出错误结论。
   * 所以这里把待绘制笔迹按图层补齐后重新合成，得到最终成品。
   * 输出为逻辑尺寸（不乘 DPR），避免回传图片过大。
   */
  exportComplete(type = 'image/jpeg', quality = 0.85): string {
    // 待绘制笔迹按图层分组：active 是正在画的那一笔，queue 是还没轮到的
    const pending = new Map<string, Stroke[]>()
    const collect = (stroke: Stroke) => {
      const list = pending.get(stroke.layer)
      if (list) list.push(stroke)
      else pending.set(stroke.layer, [stroke])
    }
    if (this.active) collect(this.active.stroke)
    for (const item of this.queue) collect(item.stroke)

    const overlays = new Map<string, HTMLCanvasElement>()
    for (const [layerId, strokes] of pending) {
      const canvas = createCanvas(this.width, this.height, this.dpr)
      const ctx = canvas.getContext('2d')!
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
      for (const stroke of strokes) {
        const samples = this.buildSamples(stroke)
        for (let i = 1; i < samples.length; i++) {
          paintSample(ctx, stroke, samples[i - 1], samples[i], i, samples.length)
        }
      }
      overlays.set(layerId, canvas)
    }

    const out = createCanvas(this.width, this.height, 1)
    const ctx = out.getContext('2d')
    if (!ctx) return this.toDataURL(type)

    ctx.fillStyle = this.background
    ctx.fillRect(0, 0, out.width, out.height)

    for (const id of this.order) {
      const layer = this.layers.get(id)
      if (!layer || !layer.data.visible || layer.data.opacity <= 0) continue
      ctx.globalAlpha = layer.data.opacity
      ctx.drawImage(layer.canvas, 0, 0, out.width, out.height)
      const overlay = overlays.get(id)
      if (overlay) ctx.drawImage(overlay, 0, 0, out.width, out.height)
      ctx.globalAlpha = 1
    }

    return out.toDataURL(type, quality)
  }

  /**
   * 输出全部笔迹的几何事实（含尚未落盘的），供后端做精确审计。
   * 坐标与长度都按真实采样点算，后端据此可以给出可核对的结论，
   * 而不是让视觉模型凭观感猜。
   */
  auditStrokes(): StrokeAudit[] {
    const all: Stroke[] = [...this.strokes]
    if (this.active) all.push(this.active.stroke)
    for (const item of this.queue) all.push(item.stroke)

    const seen = new Set<string>()
    const result: StrokeAudit[] = []
    for (const stroke of all) {
      if (seen.has(stroke.id)) continue
      seen.add(stroke.id)

      const samples = this.buildSamples(stroke)
      if (samples.length === 0) continue
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, length = 0
      for (let i = 0; i < samples.length; i++) {
        const [x, y] = samples[i]
        if (x < x0) x0 = x
        if (y < y0) y0 = y
        if (x > x1) x1 = x
        if (y > y1) y1 = y
        if (i > 0) {
          length += Math.hypot(x - samples[i - 1][0], y - samples[i - 1][1])
        }
      }
      const first = samples[0]
      const last = samples[samples.length - 1]
      const closed = samples.length > 2 && Math.hypot(last[0] - first[0], last[1] - first[1]) < 3
      result.push({
        id: stroke.id,
        layer: stroke.layer,
        brush: stroke.brush,
        color: stroke.color,
        bbox: [x0, y0, x1, y1],
        length,
        closed,
      })
    }
    return result
  }

  destroy(): void {
    if (this.raf) cancelAnimationFrame(this.raf)
    this.raf = 0
    this.listeners.clear()
  }
}
