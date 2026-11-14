import type { Point } from './types'

/** 两点距离 */
export function dist(a: Point, b: Point): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1])
}

/**
 * 确定性随机：同一个 (seed, i, salt) 永远得到同一个 0~1 的值。
 * 这个性质是"边画边显示"和"重绘已完成的笔迹"结果一致的前提——
 * 无论一笔是被分成多少帧画完的，第 i 个采样点的抖动都必须相同。
 */
export function hash01(seed: number, i: number, salt = 0): number {
  let h = Math.imul(seed ^ 0x9e3779b9, 374761393)
  h = Math.imul(h ^ (i + 0x85ebca6b), 668265263)
  h = Math.imul(h ^ (salt + 0xc2b2ae35), 2246822519)
  h ^= h >>> 15
  h = Math.imul(h, 2246822519)
  h ^= h >>> 13
  return (h >>> 0) / 4294967296
}

/** Catmull-Rom 插值：用少量控制点生成平滑曲线，per 为每段采样数 */
export function catmullRom(points: Point[], per: number, closed = false): Point[] {
  const n = points.length
  if (n < 2) return points.slice()
  if (n === 2) return [points[0], points[1]]
  const at = (i: number) => points[closed ? ((i % n) + n) % n : Math.max(0, Math.min(n - 1, i))]
  const out: Point[] = []
  const segments = closed ? n : n - 1
  for (let i = 0; i < segments; i++) {
    const p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2)
    for (let k = 0; k < per; k++) {
      const u = k / per, u2 = u * u, u3 = u2 * u
      out.push([
        0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * u + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * u2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * u3),
        0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * u + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * u2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * u3),
      ])
    }
  }
  out.push(points[closed ? 0 : n - 1])
  return out
}

/**
 * 按固定弧长间距重采样折线。
 * 笔刷的每个采样点都要落笔一次，间距越小越细腻、采样点越多。
 */
export function resample(points: Point[], spacing: number): Point[] {
  const n = points.length
  if (n < 2) return points.slice()
  const step = Math.max(0.35, spacing)
  const out: Point[] = [points[0]]
  let carry = 0
  for (let i = 1; i < n; i++) {
    const [x0, y0] = points[i - 1]
    const [x1, y1] = points[i]
    const d = Math.hypot(x1 - x0, y1 - y0)
    if (d <= 0) continue
    let t = step - carry
    while (t <= d) {
      out.push([x0 + (x1 - x0) * (t / d), y0 + (y1 - y0) * (t / d)])
      t += step
    }
    carry = d - (t - step)
  }
  const last = points[n - 1]
  const tail = out[out.length - 1]
  if (dist(last, tail) > step * 0.3) out.push(last)
  return out
}

/** 椭圆/圆弧路径 */
export function ellipsePath(
  cx: number, cy: number, rx: number, ry: number,
  from = 0, to = Math.PI * 2, n = 64, rotation = 0,
): Point[] {
  const out: Point[] = []
  for (let i = 0; i <= n; i++) {
    const a = from + (to - from) * (i / n) + rotation
    out.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry])
  }
  return out
}

/** 三次贝塞尔路径 */
export function bezierPath(p0: Point, p1: Point, p2: Point, p3: Point, n = 32): Point[] {
  const out: Point[] = []
  for (let i = 0; i <= n; i++) {
    const t = i / n, u = 1 - t
    const a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t
    out.push([
      a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
      a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
    ])
  }
  return out
}

/** 把折线整体按中心缩放/平移，方便复用同一套笔迹做构图微调 */
export function transformPath(points: Point[], scale: number, dx: number, dy: number, origin: Point): Point[] {
  return points.map(([x, y]) => [
    origin[0] + (x - origin[0]) * scale + dx,
    origin[1] + (y - origin[1]) * scale + dy,
  ] as Point)
}
