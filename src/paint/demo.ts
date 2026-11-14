import { bezierPath, ellipsePath } from './path'
import type { Point, Stroke } from './types'

/**
 * 示例画作：一只坐着的橘猫。
 * 这里只产出笔迹数据，不碰渲染细节——引擎怎么画是引擎的事。
 * 分层顺序遵循真实绘画习惯：轮廓 → 上色 → 细节。
 */

const INK = '#3a3733'
const FUR = '#efa96b'
const FUR_DARK = '#b9661f'
const PINK = '#e7a3a3'
const NOSE = '#cf7280'
const SHADOW = '#8d8175'
const EYE = '#2f2c28'

let seq = 0
function stroke(partial: Omit<Stroke, 'id' | 'seed'>): Stroke {
  seq += 1
  return { ...partial, id: `demo-${seq}`, seed: seq * 97 + 13 }
}

/**
 * 躯干轮廓：顶部是圆润的肩，中段向下张开，底部收成一条宽带（坐姿压在地面上）。
 * 顶部圆顶藏在头部后面，只露出两侧肩线，避免出现"头身分家"的尖角。
 */
function bodyPath(cx: number, yTop: number, yBottom: number, neckW: number, maxW: number): Point[] {
  const height = yBottom - yTop
  const steps = 44
  const crownT = 0.1
  const flareT = 0.6
  const halfWidth = (t: number): number => {
    if (t <= crownT) {
      const k = t / crownT
      return neckW * Math.sqrt(Math.max(0, 1 - (1 - k) ** 2))
    }
    if (t <= flareT) {
      const k = (t - crownT) / (flareT - crownT)
      return neckW + (maxW - neckW) * (k * k * (3 - 2 * k))
    }
    const k = (t - flareT) / (1 - flareT)
    return maxW * Math.sqrt(Math.max(0, 1 - k * k * 0.94))
  }
  const left: Point[] = []
  const right: Point[] = []
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const y = yTop + height * t
    const w = halfWidth(t)
    left.push([cx - w, y])
    right.push([cx + w, y])
  }
  return [...right, ...left.reverse()]
}

/** 确定性伪随机，用于打散填充行，保证同一笔每次重绘一致 */
function noise(i: number, salt: number): number {
  const v = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return v - Math.floor(v)
}

/** 扫描线填充：把任意多边形用一排排横向水彩笔刷铺满，整体向内收一点避免压出轮廓 */
function fillPolygonRows(
  poly: Point[], color: string, layer: string, rows: number,
  brush: Stroke['brush'] = 'watercolor', insetRatio = 0.035,
): Stroke[] {
  const ys = poly.map(p => p[1])
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanY = maxY - minY
  const step = spanY / rows
  const out: Stroke[] = []

  const crossings = (y: number): number[] => {
    const xs: number[] = []
    for (let i = 0; i < poly.length; i++) {
      const [x1, y1] = poly[i]
      const [x2, y2] = poly[(i + 1) % poly.length]
      if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) {
        xs.push(x1 + ((y - y1) / (y2 - y1)) * (x2 - x1))
      }
    }
    return xs.sort((a, b) => a - b)
  }

  for (let i = 0; i < rows; i++) {
    // 行位置与端点加抖动，避免整片填充出现规则的横向条纹
    const baseY = minY + spanY * 0.03 + (spanY * 0.94) * ((i + 0.5) / rows)
    const y = baseY + (noise(i, 1) - 0.5) * step * 0.5
    const xs = crossings(y)
    if (xs.length < 2) continue
    const x0 = xs[0]
    const x1 = xs[xs.length - 1]
    const span = x1 - x0
    if (span < 3) continue
    // 窄行按绝对像素收边，宽行按比例收边；水彩点有固定扩散半径，只按比例缩挡不住溢出
    const inset = Math.min(span * 0.4, Math.max(span * insetRatio, 9))
    const left = x0 + inset
    const right = x1 - inset
    if (right - left < 2) continue
    const wobble = (noise(i, 5) - 0.5) * step * 0.7
    out.push(stroke({
      layer,
      brush,
      color,
      width: step * 2.4,
      opacity: 0.92,
      smooth: 6,
      points: [
        [left, y + (noise(i, 9) - 0.5) * step * 0.5],
        [(left + right) / 2, y + wobble],
        [right, y + (noise(i, 13) - 0.5) * step * 0.5],
      ],
    }))
  }
  return out
}

function fillEllipseRows(
  cx: number, cy: number, rx: number, ry: number, color: string, layer: string, rows: number,
  insetRatio = 0.035,
): Stroke[] {
  const poly: Point[] = ellipsePath(cx, cy, rx, ry, 0, Math.PI * 2, 48)
  return fillPolygonRows(poly, color, layer, rows, 'watercolor', insetRatio)
}

/** 给轮廓加轻微手抖，避免看起来像矢量图 */
function shake(points: Point[], amount: number, seed: number): Point[] {
  return points.map(([x, y], i) => {
    const a = Math.sin(seed * 12.9898 + i * 78.233) * 43758.5453
    const b = Math.sin(seed * 41.1234 + i * 17.377) * 24634.6345
    return [x + (a - Math.floor(a) - 0.5) * amount, y + (b - Math.floor(b) - 0.5) * amount] as Point
  })
}

/** 一条短弧：三个点走平滑，用于斑纹这种"一笔带过"的线条 */
function arc(a: Point, b: Point, c: Point, seed: number, wobble = 1.4): Point[] {
  return shake([a, b, c], wobble, seed)
}

const HEAD = { cx: 770, cy: 362, rx: 152, ry: 138 }
const BODY = { cx: 770, yTop: 418, yBottom: 848, neckW: 86, maxW: 196 }

export function buildDemoStrokes(): Stroke[] {
  seq = 0
  const out: Stroke[] = []

  // ══ 轮廓层：铅笔线稿 ══
  // 耳朵
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 3.2, opacity: 1, smooth: 12,
    points: shake([[654, 272], [588, 150], [726, 240]], 2.2, 5),
  }))
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 3.2, opacity: 1, smooth: 12,
    points: shake([[886, 272], [952, 150], [814, 240]], 2.2, 7),
  }))
  // 头
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 3.4, opacity: 1, smooth: 12,
    points: shake(ellipsePath(HEAD.cx, HEAD.cy, HEAD.rx, HEAD.ry, Math.PI * 0.09, Math.PI * 2.06, 26), 2.6, 3),
  }))
  // 躯干：圆肩 + 下宽，顶部藏在头后
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 3.6, opacity: 1, smooth: 10,
    points: shake(bodyPath(BODY.cx, BODY.yTop, BODY.yBottom, BODY.neckW, BODY.maxW), 2.4, 11),
  }))
  // 前腿分界：两条微微内收的竖线，把躯干读成"坐着"
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 2.8, opacity: 1, smooth: 12,
    points: shake([[734, 664], [724, 748], [728, 820]], 1.5, 31),
  }))
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 2.8, opacity: 1, smooth: 12,
    points: shake([[806, 664], [816, 748], [812, 820]], 1.5, 33),
  }))
  // 两只前爪
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 2.6, opacity: 1, smooth: 10,
    points: shake(ellipsePath(730, 826, 44, 24, Math.PI * 0.02, Math.PI * 1.0, 16), 1.5, 35),
  }))
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 2.6, opacity: 1, smooth: 10,
    points: shake(ellipsePath(810, 826, 44, 24, Math.PI * 0.02, Math.PI * 1.0, 16), 1.5, 37),
  }))
  // 尾巴：从身体右侧向后再向上卷
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 4, opacity: 1, smooth: 10,
    points: bezierPath([942, 742], [1128, 828], [1218, 664], [1098, 566], 22),
  }))
  out.push(stroke({
    layer: 'outline', brush: 'pencil', color: INK, width: 4, opacity: 1, smooth: 10,
    points: bezierPath([950, 782], [1116, 862], [1200, 700], [1096, 606], 22),
  }))

  // ══ 上色层：水彩 ══
  out.push(...fillEllipseRows(HEAD.cx, HEAD.cy, HEAD.rx, HEAD.ry, FUR, 'color', 26, 0.06))
  out.push(...fillPolygonRows(bodyPath(BODY.cx, BODY.yTop, BODY.yBottom, BODY.neckW, BODY.maxW), FUR, 'color', 30, 'watercolor', 0.07))
  out.push(...fillPolygonRows([[660, 268], [596, 162], [716, 240]], PINK, 'color', 8, 'watercolor', 0.12))
  out.push(...fillPolygonRows([[880, 268], [944, 162], [824, 240]], PINK, 'color', 8, 'watercolor', 0.12))
  out.push(...fillPolygonRows([[757, 404], [783, 404], [770, 424]], NOSE, 'color', 4, 'watercolor', 0.16))

  // ══ 细节层：眼睛、鼻线、嘴、胡须、斑纹 ══
  for (const cx of [700, 840]) {
    out.push(stroke({
      layer: 'detail', brush: 'ink', color: INK, width: 3, opacity: 1, smooth: 10,
      points: ellipsePath(cx, 352, 33, 39, 0, Math.PI * 2, 28),
    }))
    out.push(stroke({
      layer: 'detail', brush: 'ink', color: EYE, width: 12, opacity: 1, smooth: 10,
      points: ellipsePath(cx, 354, 10.5, 26, 0, Math.PI * 2, 20),
    }))
    out.push(stroke({
      layer: 'detail', brush: 'ink', color: '#ffffff', width: 6, opacity: 1, smooth: 8,
      points: ellipsePath(cx - 5, 342, 5.5, 6.5, 0, Math.PI * 2, 14),
    }))
  }

  // 鼻中线
  out.push(stroke({
    layer: 'detail', brush: 'ink', color: INK, width: 2.2, opacity: 1, smooth: 8,
    points: [[770, 424], [770, 440]],
  }))
  // 嘴：从鼻下分两撇
  out.push(stroke({
    layer: 'detail', brush: 'ink', color: INK, width: 2.4, opacity: 1, smooth: 10,
    points: [[770, 440], [750, 456], [730, 448]],
  }))
  out.push(stroke({
    layer: 'detail', brush: 'ink', color: INK, width: 2.4, opacity: 1, smooth: 10,
    points: [[770, 440], [790, 456], [810, 448]],
  }))

  // 胡须
  const whiskers: [Point, Point][] = [
    [[722, 414], [614, 392]],
    [[720, 430], [606, 428]],
    [[722, 446], [616, 466]],
    [[818, 414], [926, 392]],
    [[820, 430], [934, 428]],
    [[818, 446], [924, 466]],
  ]
  for (const [a, b] of whiskers) {
    out.push(stroke({
      layer: 'detail', brush: 'ink', color: '#6a6259', width: 1.6, opacity: 0.8, smooth: 8,
      points: [a, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 5], b],
    }))
  }

  // 斑纹：马克笔，额头走对称八字、脸颊在眼侧、身体顺着侧边向下弯
  const stripes: { pts: Point[]; w: number }[] = [
    { pts: arc([700, 268], [738, 250], [776, 262], 41), w: 11 },
    { pts: arc([840, 268], [802, 250], [764, 262], 43), w: 11 },
    { pts: arc([688, 310], [730, 290], [772, 302], 45), w: 11 },
    { pts: arc([852, 310], [810, 290], [768, 302], 47), w: 11 },
    { pts: arc([644, 390], [672, 380], [698, 386], 49), w: 9 },
    { pts: arc([640, 426], [668, 420], [694, 426], 51), w: 9 },
    { pts: arc([896, 390], [868, 380], [842, 386], 53), w: 9 },
    { pts: arc([900, 426], [872, 420], [846, 426], 55), w: 9 },
    { pts: arc([612, 682], [652, 664], [694, 674], 57), w: 12 },
    { pts: arc([604, 736], [648, 716], [692, 726], 59), w: 12 },
    { pts: arc([928, 682], [888, 664], [846, 674], 61), w: 12 },
    { pts: arc([936, 736], [892, 716], [848, 726], 63), w: 12 },
  ]
  for (const { pts, w } of stripes) {
    out.push(stroke({
      layer: 'detail', brush: 'marker', color: FUR_DARK, width: w, opacity: 0.38, smooth: 8,
      points: pts,
    }))
  }

  // 地面阴影：炭笔排线，紧贴身体底部
  for (let i = 0; i < 8; i++) {
    const y = 858 + i * 8
    const half = 208 - Math.abs(i - 3.5) * 21
    out.push(stroke({
      layer: 'color', brush: 'charcoal', color: SHADOW, width: 12, opacity: 0.42, smooth: 0,
      points: [[770 - half, y], [770 + half, y]],
    }))
  }

  return out
}
