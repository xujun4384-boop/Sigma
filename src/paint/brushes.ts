import { hash01 } from './path'
import type { BrushName, Point, Stroke } from './types'

/**
 * 笔刷描述。笔刷只描述"怎么落笔"，不关心图层、播放、撤销。
 * 新增一种笔刷 = 往 BRUSHES 里加一条配置，引擎代码不需要任何改动。
 */
export interface BrushSpec {
  label: string
  /** 渲染方式：stamp 按采样点堆叠颗粒，line 按采样段描边 */
  mode: 'stamp' | 'line'
  /** 相邻采样点间距 */
  spacing: (width: number) => number
  /** stamp 单点半径 */
  radius?: (width: number) => number
  /** stamp 落点随机偏移量 */
  scatter?: (width: number) => number
  /** stamp 每个采样点重复落笔次数 */
  passes?: number
  /** stamp 单点不透明度区间 */
  alpha?: [number, number]
  /** line 线宽 */
  lineWidth?: (width: number) => number
  /** line 单段不透明度 */
  lineAlpha?: number
  /** 两端收笔变细 */
  taper?: boolean
  /**
   * 柔边程度 0~1。大于 0 时用径向渐变笔尖替代实心圆，
   * 避免宽笔画出"串珠"状的硬边圆点。水彩这类湿画法必须开。
   */
  soft?: number
}

export const BRUSHES: Record<BrushName, BrushSpec> = {
  pencil: {
    label: '铅笔',
    mode: 'stamp',
    spacing: (w) => Math.max(0.6, w * 0.11),
    radius: (w) => w * 0.26,
    scatter: (w) => w * 0.2,
    passes: 3,
    alpha: [0.16, 0.52],
    taper: true,
  },
  charcoal: {
    label: '炭笔',
    mode: 'stamp',
    spacing: (w) => Math.max(1.6, w * 0.34),
    radius: (w) => w * 0.44,
    scatter: (w) => w * 0.55,
    passes: 3,
    alpha: [0.07, 0.3],
    taper: true,
  },
  marker: {
    label: '马克笔',
    mode: 'line',
    spacing: (w) => Math.max(0.8, w * 0.12),
    lineWidth: (w) => w,
    lineAlpha: 0.82,
    taper: false,
  },
  watercolor: {
    label: '水彩',
    mode: 'stamp',
    spacing: (w) => Math.max(1.4, w * 0.14),
    radius: (w) => w * 0.62,
    scatter: (w) => w * 0.16,
    passes: 3,
    alpha: [0.08, 0.22],
    taper: true,
    soft: 0.6,
  },
  ink: {
    label: '墨水笔',
    mode: 'line',
    spacing: (w) => Math.max(0.5, w * 0.1),
    lineWidth: (w) => w * 0.85,
    lineAlpha: 0.95,
    taper: true,
  },
}

export const BRUSH_NAMES = Object.keys(BRUSHES) as BrushName[]

/** 两端收笔：起收处逐渐变细，避免每条线都像铁棍 */
function taperFactor(index: number, total: number): number {
  if (total <= 2) return 1
  const p = index / (total - 1)
  return 0.45 + 0.55 * Math.min(1, Math.min(p, 1 - p) * 5)
}

const SOFT_STAMP_SIZE = 64
const SOFT_STAMP_LIMIT = 160
const softStampCache = new Map<string, HTMLCanvasElement>()

/** 把 #rgb / #rrggbb 转成带透明度的 rgba */
function withAlpha(color: string, alpha: number): string {
  const hex = color.trim()
  if (/^#[0-9a-f]{6}$/i.test(hex)) {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return `rgba(${r},${g},${b},${alpha})`
  }
  if (/^#[0-9a-f]{3}$/i.test(hex)) {
    const r = parseInt(hex[1] + hex[1], 16)
    const g = parseInt(hex[2] + hex[2], 16)
    const b = parseInt(hex[3] + hex[3], 16)
    return `rgba(${r},${g},${b},${alpha})`
  }
  return hex
}

/**
 * 柔边笔尖：预渲染成一张径向渐变贴图后复用。
 * 每个采样点都新建渐变会很慢，缓存后按 (颜色, 柔度) 命中即可。
 */
function getSoftStamp(color: string, softness: number): HTMLCanvasElement {
  const key = `${color}|${softness.toFixed(2)}`
  const cached = softStampCache.get(key)
  if (cached) return cached

  const size = SOFT_STAMP_SIZE
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const radius = size / 2
  const gradient = ctx.createRadialGradient(radius, radius, 0, radius, radius, radius)
  const core = Math.max(0.04, 1 - softness) * 0.7
  gradient.addColorStop(0, withAlpha(color, 1))
  gradient.addColorStop(core, withAlpha(color, 0.82))
  gradient.addColorStop(Math.min(0.97, core + (1 - core) * 0.5), withAlpha(color, 0.3))
  gradient.addColorStop(1, withAlpha(color, 0))
  ctx.fillStyle = gradient
  ctx.beginPath()
  ctx.arc(radius, radius, radius, 0, Math.PI * 2)
  ctx.fill()

  if (softStampCache.size > SOFT_STAMP_LIMIT) softStampCache.clear()
  softStampCache.set(key, canvas)
  return canvas
}

/**
 * 绘制一个采样点。prev 为上一个采样点，用于 line 模式连线。
 * index / total 提供整笔内的位置，供收笔变细使用。
 */
export function paintSample(
  ctx: CanvasRenderingContext2D,
  stroke: Stroke,
  prev: Point | null,
  cur: Point,
  index: number,
  total: number,
): void {
  const spec = BRUSHES[stroke.brush]
  if (!spec) return
  const seed = stroke.seed ?? 1
  const width = stroke.width
  const taper = spec.taper ? taperFactor(index, total) : 1

  if (spec.mode === 'line') {
    const lw = (spec.lineWidth?.(width) ?? width) * taper
    if (prev) {
      ctx.lineWidth = Math.max(0.4, lw)
      ctx.globalAlpha = (spec.lineAlpha ?? 0.9) * stroke.opacity
      ctx.strokeStyle = stroke.color
      ctx.beginPath()
      ctx.moveTo(prev[0], prev[1])
      ctx.lineTo(cur[0], cur[1])
      ctx.stroke()
    }
    return
  }

  const radius = spec.radius?.(width) ?? width * 0.4
  const scatter = spec.scatter?.(width) ?? 0
  const passes = spec.passes ?? 1
  const alphaRange = spec.alpha ?? [0.4, 0.8]
  const stamp = spec.soft ? getSoftStamp(stroke.color, spec.soft) : null

  for (let pass = 0; pass < passes; pass++) {
    const salt = pass * 13
    const angle = hash01(seed, index, salt + 1) * Math.PI * 2
    const offset = (hash01(seed, index, salt + 2) - 0.5) * 2 * scatter
    const x = cur[0] + Math.cos(angle) * offset
    const y = cur[1] + Math.sin(angle) * offset
    const r = radius * (0.55 + hash01(seed, index, salt + 3) * 0.9) * taper
    const a = alphaRange[0] + (alphaRange[1] - alphaRange[0]) * hash01(seed, index, salt + 4)
    ctx.globalAlpha = a * stroke.opacity

    if (stamp) {
      const size = Math.max(0.5, r) * 2
      ctx.drawImage(stamp, x - size / 2, y - size / 2, size, size)
    } else {
      ctx.fillStyle = stroke.color
      ctx.beginPath()
      ctx.arc(x, y, Math.max(0.25, r), 0, Math.PI * 2)
      ctx.fill()
    }
  }
}
