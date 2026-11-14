import { BRUSH_NAMES } from './brushes'
import { bezierPath, ellipsePath } from './path'
import type { BrushName, Point, Stroke } from './types'

/**
 * 绘图指令协议。
 *
 * 模型不直接写坐标密集的笔迹，而是给"少量控制点 + 图形描述"，
 * 由引擎展开成采样点。这样 token 可控，笔触也由笔刷质感决定。
 *
 * 所有指令都是可校验的纯数据，不执行任意代码。
 */

/** 路径描述：描述"一笔要走的形状"，由引擎展开成点列 */
export type PathSpec =
  | { type: 'curve'; points: Point[]; smooth?: number }
  | { type: 'polyline'; points: Point[] }
  /** 角度用度，0 度在三点钟方向，顺时针为正 */
  | { type: 'ellipse'; cx: number; cy: number; rx: number; ry: number; from?: number; to?: number; rotation?: number }
  | { type: 'rect'; x: number; y: number; width: number; height: number; radius?: number }
  /** 每四个点一段三次贝塞尔，点数必须是 1 + 3n */
  | { type: 'bezier'; points: Point[] }

export interface StrokeCommand {
  op: 'stroke'
  id: string
  layer: string
  brush: BrushName
  color?: string
  width?: number
  opacity?: number
  path: PathSpec
}

export interface LayerCommand {
  op: 'layer'
  id: string
  name?: string
  visible?: boolean
  opacity?: number
}

export interface RemoveCommand {
  op: 'remove'
  id: string
}

export interface ClearLayerCommand {
  op: 'clearLayer'
  layer: string
}

export interface ClearCommand {
  op: 'clear'
}

export type PaintCommand =
  | StrokeCommand
  | LayerCommand
  | RemoveCommand
  | ClearLayerCommand
  | ClearCommand

export const COMMAND_OPS = ['stroke', 'layer', 'remove', 'clearLayer', 'clear'] as const

export const DEFAULT_STROKE_COLOR = '#3a3733'
export const DEFAULT_STROKE_WIDTH = 3
export const DEFAULT_STROKE_OPACITY = 1

const MIN_WIDTH = 0.4
const MAX_WIDTH = 200

// ── 校验 ──

export interface CommandIssue {
  index: number
  id?: string
  field?: string
  message: string
}

function isPoint(value: unknown): value is Point {
  return Array.isArray(value) && value.length >= 2
    && typeof value[0] === 'number' && typeof value[1] === 'number'
    && Number.isFinite(value[0]) && Number.isFinite(value[1])
}

function checkPoints(points: unknown, field: string, minCount: number, label: string): string | null {
  if (!Array.isArray(points)) return `${field} 必须是坐标数组，例如 [[100,100],[200,150]]`
  if (points.length < minCount) return `${field} 至少需要 ${minCount} 个点，收到 ${points.length} 个`
  for (let i = 0; i < points.length; i++) {
    if (!isPoint(points[i])) return `${field}[${i}] 不是合法坐标，应为 [x, y] 两个数字`
  }
  return null
}

function checkNumber(value: unknown, field: string, min: number, max: number): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return `${field} 必须是数字`
  if (value < min || value > max) return `${field} 必须在 ${min} 到 ${max} 之间，收到 ${value}`
  return null
}

/** 校验路径描述，返回错误说明（可直接反馈给模型去修） */
export function validatePath(path: unknown, field = 'path'): string | null {
  if (!path || typeof path !== 'object') return `${field} 必须是对象`
  const spec = path as PathSpec
  switch (spec.type) {
    case 'curve': {
      const err = checkPoints(spec.points, `${field}.points`, 2, '曲线')
      if (err) return err
      if (spec.smooth !== undefined) {
        const e = checkNumber(spec.smooth, `${field}.smooth`, 0, 30)
        if (e) return e
      }
      return null
    }
    case 'polyline':
      return checkPoints(spec.points, `${field}.points`, 2, '折线')
    case 'bezier': {
      const err = checkPoints(spec.points, `${field}.points`, 4, '贝塞尔')
      if (err) return err
      if ((spec.points.length - 1) % 3 !== 0) {
        return `${field}.points 数量必须是 1 + 3n（每三个点一段曲线），当前 ${spec.points.length} 个`
      }
      return null
    }
    case 'ellipse': {
      for (const [key, value] of [['cx', spec.cx], ['cy', spec.cy], ['rx', spec.rx], ['ry', spec.ry]] as const) {
        const e = checkNumber(value, `${field}.${key}`, -100000, 100000)
        if (e) return e
      }
      if (spec.from !== undefined) {
        const e = checkNumber(spec.from, `${field}.from`, -1440, 1440)
        if (e) return e
      }
      if (spec.to !== undefined) {
        const e = checkNumber(spec.to, `${field}.to`, -1440, 1440)
        if (e) return e
      }
      return null
    }
    case 'rect': {
      for (const [key, value] of [['x', spec.x], ['y', spec.y]] as const) {
        const e = checkNumber(value, `${field}.${key}`, -100000, 100000)
        if (e) return e
      }
      for (const [key, value] of [['width', spec.width], ['height', spec.height]] as const) {
        const e = checkNumber(value, `${field}.${key}`, 1, 100000)
        if (e) return e
      }
      if (spec.radius !== undefined) {
        const e = checkNumber(spec.radius, `${field}.radius`, 0, 10000)
        if (e) return e
      }
      return null
    }
    default:
      return `${field}.type 必须是 curve / polyline / bezier / ellipse / rect 之一，收到 ${String((spec as { type?: unknown }).type)}`
  }
}

/** 逐条校验指令，返回所有问题（不抛异常，方便一次性反馈给模型） */
export function validateCommands(input: unknown): { commands: PaintCommand[]; issues: CommandIssue[] } {
  const issues: CommandIssue[] = []
  if (!Array.isArray(input)) {
    return { commands: [], issues: [{ index: -1, message: 'commands 必须是数组' }] }
  }

  const commands: PaintCommand[] = []
  const seenIds = new Set<string>()

  input.forEach((raw, index) => {
    if (!raw || typeof raw !== 'object') {
      issues.push({ index, message: '指令必须是对象' })
      return
    }
    const cmd = raw as Record<string, unknown>
    const op = cmd.op

    if (op === 'stroke') {
      const id = typeof cmd.id === 'string' ? cmd.id.trim() : ''
      if (!id) {
        issues.push({ index, message: 'stroke 必须带 id，用于后续修正与撤销' })
        return
      }
      if (seenIds.has(id)) {
        issues.push({ index, id, message: `id "${id}" 在同一批指令中重复，每笔必须有唯一 id` })
        return
      }
      if (typeof cmd.layer !== 'string' || !cmd.layer.trim()) {
        issues.push({ index, id, field: 'layer', message: 'stroke 必须指定 layer（图层 id，不存在会自动创建）' })
        return
      }
      if (typeof cmd.brush !== 'string' || !(BRUSH_NAMES as string[]).includes(cmd.brush)) {
        issues.push({ index, id, field: 'brush', message: `brush 必须是 ${BRUSH_NAMES.join(' / ')} 之一，收到 ${String(cmd.brush)}` })
        return
      }
      if (cmd.color !== undefined && typeof cmd.color !== 'string') {
        issues.push({ index, id, field: 'color', message: 'color 必须是颜色字符串，如 "#3a3733"' })
        return
      }
      if (cmd.width !== undefined) {
        const e = checkNumber(cmd.width, 'width', MIN_WIDTH, MAX_WIDTH)
        if (e) { issues.push({ index, id, field: 'width', message: e }); return }
      }
      if (cmd.opacity !== undefined) {
        const e = checkNumber(cmd.opacity, 'opacity', 0, 1)
        if (e) { issues.push({ index, id, field: 'opacity', message: e }); return }
      }
      const pathError = validatePath(cmd.path, 'path')
      if (pathError) {
        issues.push({ index, id, field: 'path', message: pathError })
        return
      }
      seenIds.add(id)
      commands.push({
        op: 'stroke',
        id,
        layer: String(cmd.layer),
        brush: cmd.brush as BrushName,
        color: cmd.color as string | undefined,
        width: cmd.width as number | undefined,
        opacity: cmd.opacity as number | undefined,
        path: cmd.path as PathSpec,
      })
      return
    }

    if (op === 'layer') {
      const id = typeof cmd.id === 'string' ? cmd.id.trim() : ''
      if (!id) {
        issues.push({ index, message: 'layer 指令必须带 id' })
        return
      }
      if (cmd.opacity !== undefined) {
        const e = checkNumber(cmd.opacity, 'opacity', 0, 1)
        if (e) { issues.push({ index, id, field: 'opacity', message: e }); return }
      }
      commands.push({
        op: 'layer',
        id,
        name: typeof cmd.name === 'string' ? cmd.name : undefined,
        visible: typeof cmd.visible === 'boolean' ? cmd.visible : undefined,
        opacity: cmd.opacity as number | undefined,
      })
      return
    }

    if (op === 'remove') {
      if (typeof cmd.id !== 'string' || !cmd.id.trim()) {
        issues.push({ index, message: 'remove 必须带要删除的笔迹 id' })
        return
      }
      commands.push({ op: 'remove', id: cmd.id })
      return
    }

    if (op === 'clearLayer') {
      if (typeof cmd.layer !== 'string' || !cmd.layer.trim()) {
        issues.push({ index, message: 'clearLayer 必须指定 layer' })
        return
      }
      commands.push({ op: 'clearLayer', layer: cmd.layer })
      return
    }

    if (op === 'clear') {
      commands.push({ op: 'clear' })
      return
    }

    issues.push({
      index,
      message: `op 必须是 ${COMMAND_OPS.join(' / ')} 之一，收到 ${String(op)}`,
    })
  })

  return { commands, issues }
}

// ── 路径展开 ──

/** 圆角矩形的四分之一圆采样数 */
const CORNER_SEGMENTS = 8

function roundedRectPath(x: number, y: number, width: number, height: number, radius: number): Point[] {
  const r = Math.max(0, Math.min(radius, Math.min(width, height) / 2))
  if (r <= 0) {
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height], [x, y]]
  }
  const points: Point[] = []
  const corners: [number, number, number][] = [
    [x + width - r, y + r, -Math.PI / 2],
    [x + width - r, y + height - r, 0],
    [x + r, y + height - r, Math.PI / 2],
    [x + r, y + r, Math.PI],
  ]
  for (const [cx, cy, startAngle] of corners) {
    for (let i = 0; i <= CORNER_SEGMENTS; i++) {
      const a = startAngle + (Math.PI / 2) * (i / CORNER_SEGMENTS)
      points.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r])
    }
  }
  points.push(points[0])
  return points
}

/** 把路径描述展开成点列。新增图形类型只需在这里加一个分支。 */
export function expandPath(spec: PathSpec): { points: Point[]; smooth: number } {
  switch (spec.type) {
    case 'curve':
      return { points: spec.points.map(p => [p[0], p[1]] as Point), smooth: spec.smooth ?? 8 }
    case 'polyline':
      return { points: spec.points.map(p => [p[0], p[1]] as Point), smooth: 0 }
    case 'bezier': {
      const points: Point[] = []
      for (let i = 0; i + 3 < spec.points.length; i += 3) {
        const segment = bezierPath(spec.points[i], spec.points[i + 1], spec.points[i + 2], spec.points[i + 3], 18)
        // 相邻段的连接点重复，去掉一个
        points.push(...(points.length ? segment.slice(1) : segment))
      }
      return { points, smooth: 0 }
    }
    case 'ellipse': {
      const from = ((spec.from ?? 0) * Math.PI) / 180
      const to = ((spec.to ?? 360) * Math.PI) / 180
      const rotation = ((spec.rotation ?? 0) * Math.PI) / 180
      const span = Math.abs(to - from)
      const segments = Math.max(16, Math.round((span / (Math.PI * 2)) * 60))
      return { points: ellipsePath(spec.cx, spec.cy, spec.rx, spec.ry, from, to, segments, rotation), smooth: 0 }
    }
    case 'rect':
      return { points: roundedRectPath(spec.x, spec.y, spec.width, spec.height, spec.radius ?? 0), smooth: 4 }
  }
}

/** 把一条 stroke 指令转成引擎可渲染的笔迹 */
export function commandToStroke(cmd: StrokeCommand): Stroke {
  const { points, smooth } = expandPath(cmd.path)
  return {
    id: cmd.id,
    layer: cmd.layer,
    brush: cmd.brush,
    color: cmd.color ?? DEFAULT_STROKE_COLOR,
    width: cmd.width ?? DEFAULT_STROKE_WIDTH,
    opacity: cmd.opacity ?? DEFAULT_STROKE_OPACITY,
    points,
    smooth,
    seed: hashSeed(cmd.id),
  }
}

/** 用 id 派生种子：同一条指令无论何时重放，笔触纹理完全一致 */
function hashSeed(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) % 1000000
}
