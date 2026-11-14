import type {
  CharacterDrawing, CharacterSpec, DrawOp, EyeMood, HairStyle, MouthMood, PoseParams, Proportions,
} from './types'

/**
 * 骨架：把「角色设定 + 姿态参数」展开成一串绘制指令。
 *
 * 坐标系：脚底中心为 (0,0)，向上为负 y，总高约 -totalHeight。
 * 所有尺寸都由比例系数推导，所以换体型只改系数，不改几何代码。
 */

const f = (value: number) => Math.round(value * 10) / 10

function ellipse(cx: number, cy: number, rx: number, ry: number): string {
  return `M ${f(cx - rx)} ${f(cy)} A ${f(rx)} ${f(ry)} 0 1 0 ${f(cx + rx)} ${f(cy)} A ${f(rx)} ${f(ry)} 0 1 0 ${f(cx - rx)} ${f(cy)} Z`
}

function poly(points: [number, number][]): string {
  return points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${f(x)} ${f(y)}`).join(' ') + ' Z'
}

function roundRect(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, w / 2, h / 2)
  return [
    `M ${f(x + rr)} ${f(y)}`,
    `L ${f(x + w - rr)} ${f(y)}`,
    `Q ${f(x + w)} ${f(y)} ${f(x + w)} ${f(y + rr)}`,
    `L ${f(x + w)} ${f(y + h - rr)}`,
    `Q ${f(x + w)} ${f(y + h)} ${f(x + w - rr)} ${f(y + h)}`,
    `L ${f(x + rr)} ${f(y + h)}`,
    `Q ${f(x)} ${f(y + h)} ${f(x)} ${f(y + h - rr)}`,
    `L ${f(x)} ${f(y + rr)}`,
    `Q ${f(x)} ${f(y)} ${f(x + rr)} ${f(y)}`,
    'Z',
  ].join(' ')
}

/** 两段手臂：肩 → 肘 → 手，角度 0 表示自然下垂 */
function armPoints(sx: number, sy: number, angleDeg: number, length: number): [number, number][] {
  const a = (angleDeg * Math.PI) / 180
  const ex = sx + Math.sin(a) * length * 0.52
  const ey = sy + Math.cos(a) * length * 0.52
  const a2 = a * 1.18
  const hx = ex + Math.sin(a2) * length * 0.48
  const hy = ey + Math.cos(a2) * length * 0.48
  return [[sx, sy], [ex, ey], [hx, hy]]
}

interface Metrics {
  totalHeight: number
  headH: number
  headW: number
  headCy: number
  neckY: number
  shoulderY: number
  shoulderHalf: number
  hipY: number
  hipHalf: number
  torsoH: number
  armLen: number
  legLen: number
  widthScale: number
}

function measure(spec: CharacterSpec, pose: PoseParams, totalHeight: number): Metrics {
  const p: Proportions = spec.proportions
  const headH = totalHeight * p.headRatio
  const headW = headH * 0.86
  const legLen = totalHeight * p.legRatio
  const torsoH = totalHeight - headH - legLen
  const neckY = -totalHeight + headH
  const sitDrop = pose.pose === 'sit' ? legLen * 0.42 : 0
  const widthScale = pose.view === 'side' ? 0.68 : 1

  return {
    totalHeight,
    headH,
    headW,
    headCy: -totalHeight + headH / 2,
    neckY,
    shoulderY: neckY + torsoH * 0.1,
    shoulderHalf: (headW / 2) * p.shoulderRatio * widthScale,
    hipY: -legLen + sitDrop,
    hipHalf: (headW / 2) * p.hipRatio * widthScale,
    torsoH: torsoH - sitDrop * 0.35,
    armLen: torsoH * p.armRatio,
    legLen: legLen - sitDrop,
    widthScale,
  }
}

/** 躯干轮廓：肩窄髋宽，belly 控制侧边外鼓程度 */
function bodyPath(m: Metrics, belly: number): string {
  const bulge = m.headW * 0.16 * belly
  const waistY = (m.shoulderY + m.hipY) / 2
  return [
    `M ${f(-m.shoulderHalf)} ${f(m.shoulderY)}`,
    `Q ${f(-m.shoulderHalf - bulge)} ${f(waistY)} ${f(-m.hipHalf)} ${f(m.hipY)}`,
    `Q 0 ${f(m.hipY + m.headW * 0.1)} ${f(m.hipHalf)} ${f(m.hipY)}`,
    `Q ${f(m.shoulderHalf + bulge)} ${f(waistY)} ${f(m.shoulderHalf)} ${f(m.shoulderY)}`,
    `Q 0 ${f(m.shoulderY - m.headW * 0.06)} ${f(-m.shoulderHalf)} ${f(m.shoulderY)}`,
    'Z',
  ].join(' ')
}

/** 画一只眼睛。正面与侧面共用，位置与大小由调用方给。 */
function eyeOps(
  ops: DrawOp[], spec: CharacterSpec, x: number, y: number, r: number,
  pose: PoseParams, aspect = 1,
): void {
  const { ink } = spec.colors
  const lw = r * 0.32
  const rx = r * aspect

  if (pose.eyes === 'closed') {
    ops.push({
      d: `M ${f(x - rx)} ${f(y)} Q ${f(x)} ${f(y + r * 0.7)} ${f(x + rx)} ${f(y)}`,
      stroke: ink, strokeWidth: lw, role: 'ink',
    })
    return
  }
  if (pose.eyes === 'happy') {
    ops.push({
      d: `M ${f(x - rx)} ${f(y + r * 0.35)} Q ${f(x)} ${f(y - r * 0.9)} ${f(x + rx)} ${f(y + r * 0.35)}`,
      stroke: ink, strokeWidth: lw, role: 'ink',
    })
    return
  }
  const ry = pose.eyes === 'surprised' ? r * 1.25 : r
  ops.push({ d: ellipse(x, y, rx, ry), fill: '#ffffff', role: 'skin' })
  ops.push({ d: ellipse(x, y + ry * 0.08, rx * 0.5, ry * 0.62), fill: ink, role: 'ink' })
  ops.push({
    d: ellipse(x - rx * 0.2, y - ry * 0.26, rx * 0.18, ry * 0.2),
    fill: '#ffffff', opacity: 0.9, role: 'detail',
  })
}

/**
 * 侧脸头型：额头 → 鼻梁 → 鼻尖 → 唇 → 下巴 → 下颌 → 后脑收成一个剪影。
 * 正面用圆就够了，侧面必须靠轮廓本身说明这是张侧脸。
 */
function profileHeadPath(hw: number, hh: number, cy: number): string {
  const p = (x: number, y: number) => `${f(x)} ${f(cy + y)}`
  return [
    `M ${p(-0.78 * hw, -0.62 * hh)}`,
    `Q ${p(-0.55 * hw, -1.0 * hh)} ${p(0.1 * hw, -0.98 * hh)}`,
    `Q ${p(0.66 * hw, -0.92 * hh)} ${p(0.8 * hw, -0.42 * hh)}`,
    `Q ${p(0.9 * hw, -0.1 * hh)} ${p(0.84 * hw, 0.02 * hh)}`,
    `L ${p(1.08 * hw, 0.16 * hh)}`,
    `L ${p(0.8 * hw, 0.22 * hh)}`,
    `Q ${p(0.88 * hw, 0.32 * hh)} ${p(0.78 * hw, 0.42 * hh)}`,
    `Q ${p(0.72 * hw, 0.52 * hh)} ${p(0.52 * hw, 0.66 * hh)}`,
    `Q ${p(0.3 * hw, 0.82 * hh)} ${p(0.0 * hw, 0.78 * hh)}`,
    `Q ${p(-0.6 * hw, 0.68 * hh)} ${p(-0.84 * hw, 0.16 * hh)}`,
    `Q ${p(-0.98 * hw, -0.25 * hh)} ${p(-0.78 * hw, -0.62 * hh)}`,
    'Z',
  ].join(' ')
}

/** 正面视角 */
function frontFaceOps(spec: CharacterSpec, m: Metrics, pose: PoseParams): DrawOp[] {
  const ops: DrawOp[] = []
  const { ink } = spec.colors
  const cy = m.headCy
  const headW = m.headW
  const turn = pose.headTurn
  const eyeY = cy + headW * 0.06
  const eyeR = headW * 0.088
  const eyeCenters = [-(headW * 0.2) + turn * 0.12, headW * 0.2 + turn * 0.12]

  for (const x of eyeCenters) eyeOps(ops, spec, x, eyeY, eyeR, pose)

  const browY = eyeY - eyeR * 1.75
  const browLift = pose.eyes === 'surprised' ? eyeR * 0.5 : 0
  for (const x of eyeCenters) {
    const tilt = pose.eyes === 'worried' ? eyeR * 0.35 : 0
    ops.push({
      d: `M ${f(x - eyeR * 1.1)} ${f(browY - browLift + tilt)} Q ${f(x)} ${f(browY - browLift - eyeR * 0.5)} ${f(x + eyeR * 1.1)} ${f(browY - browLift + tilt)}`,
      stroke: spec.colors.hairShade, strokeWidth: headW * 0.026, role: 'ink',
    })
  }

  const noseY = eyeY + headW * 0.19
  ops.push({
    d: `M ${f(turn * 0.3)} ${f(noseY - headW * 0.05)} L ${f(turn * 0.3 + headW * 0.03)} ${f(noseY)} L ${f(turn * 0.3 - headW * 0.02)} ${f(noseY)}`,
    stroke: spec.colors.skinShade, strokeWidth: headW * 0.022, role: 'detail',
  })

  const mouthY = noseY + headW * 0.15
  const mw = headW * 0.16
  ops.push(...mouthOps(spec, turn * 0.25, mouthY, mw, pose.mouth))

  for (const sx of [-1, 1]) {
    ops.push({
      d: ellipse(sx * headW * 0.3, eyeY + headW * 0.16, headW * 0.1, headW * 0.062),
      fill: '#e88a8a', opacity: 0.42, role: 'detail',
    })
  }

  ops.push(...wrinkleOps(spec, headW, eyeY, mouthY, pose, [-1, 1]))

  if (spec.glasses) {
    const gr = eyeR * 1.5
    for (const x of eyeCenters) {
      ops.push({ d: ellipse(x, eyeY, gr, gr * 0.86), stroke: '#5a5048', strokeWidth: headW * 0.02, role: 'ink' })
    }
    ops.push({
      d: `M ${f(eyeCenters[0] + gr)} ${f(eyeY)} L ${f(eyeCenters[1] - gr)} ${f(eyeY)}`,
      stroke: '#5a5048', strokeWidth: headW * 0.018, role: 'ink',
    })
  }

  return ops
}

/**
 * 侧面视角。头型本身已经收出鼻梁与下巴（profileHeadPath），
 * 这里只补五官：眼睛要压窄、位置靠前，嘴在唇线上，耳朵在后段。
 */
function profileFaceOps(spec: CharacterSpec, m: Metrics, pose: PoseParams): DrawOp[] {
  const ops: DrawOp[] = []
  const hw = m.headW / 2
  const hh = m.headH / 2
  const cy = m.headCy
  const headW = m.headW

  const eyeR = headW * 0.078
  const eyeX = hw * 0.3
  const eyeY = cy + headW * 0.02

  // 侧视的眼睛被压缩，横向只留六成多
  eyeOps(ops, spec, eyeX, eyeY, eyeR, pose, 0.66)

  const browLift = pose.eyes === 'surprised' ? eyeR * 0.5 : 0
  const browTilt = pose.eyes === 'worried' ? eyeR * 0.35 : 0
  ops.push({
    d: `M ${f(eyeX - eyeR * 0.9)} ${f(eyeY - eyeR * 1.8 - browLift + browTilt)} Q ${f(eyeX + eyeR * 0.1)} ${f(eyeY - eyeR * 2.3 - browLift)} ${f(eyeX + eyeR * 1.0)} ${f(eyeY - eyeR * 1.7 - browLift + browTilt)}`,
    stroke: spec.colors.hairShade, strokeWidth: headW * 0.026, role: 'ink',
  })

  // 鼻孔：一小段弧，暗示鼻底
  ops.push({
    d: `M ${f(hw * 0.9)} ${f(cy + hh * 0.3)} Q ${f(hw * 0.98)} ${f(cy + hh * 0.3)} ${f(hw * 1.0)} ${f(cy + hh * 0.24)}`,
    stroke: spec.colors.skinShade, strokeWidth: headW * 0.016, opacity: 0.7, role: 'detail',
  })

  // 嘴：位置在唇线上（鼻底与下巴之间），不能掉到下巴以下
  ops.push(...mouthOps(spec, hw * 0.72, cy + hh * 0.3, headW * 0.11, pose.mouth))

  // 腮红：单侧
  ops.push({
    d: ellipse(hw * 0.46, cy + hh * 0.28, headW * 0.085, headW * 0.05),
    fill: '#e88a8a', opacity: 0.42, role: 'detail',
  })

  ops.push(...wrinkleOps(spec, headW, eyeY, cy + hh * 0.3, pose, [1]))

  // 眼镜：单片 + 镜腿连到耳朵
  if (spec.glasses) {
    const gr = eyeR * 1.6
    ops.push({ d: ellipse(eyeX, eyeY, gr * 0.72, gr * 0.86), stroke: '#5a5048', strokeWidth: headW * 0.02, role: 'ink' })
    ops.push({
      d: `M ${f(eyeX - gr * 0.7)} ${f(eyeY)} L ${f(-hw * 0.3)} ${f(eyeY)}`,
      stroke: '#5a5048', strokeWidth: headW * 0.016, role: 'ink',
    })
  }

  return ops
}

/** 嘴型。x/y 为中心，w 为半宽。 */
function mouthOps(spec: CharacterSpec, x: number, y: number, w: number, mouth: MouthMood): DrawOp[] {
  const { ink } = spec.colors
  const lw = w * 0.16
  if (mouth === 'open') {
    return [{ d: ellipse(x, y, w * 0.42, w * 0.52), fill: '#8c4a52', role: 'detail' }]
  }
  if (mouth === 'sad') {
    return [{
      d: `M ${f(x - w)} ${f(y + w * 0.18)} Q ${f(x)} ${f(y - w * 0.28)} ${f(x + w)} ${f(y + w * 0.18)}`,
      stroke: ink, strokeWidth: lw, role: 'ink',
    }]
  }
  if (mouth === 'neutral') {
    return [{
      d: `M ${f(x - w * 0.7)} ${f(y)} L ${f(x + w * 0.7)} ${f(y)}`,
      stroke: ink, strokeWidth: lw, role: 'ink',
    }]
  }
  return [{
    d: `M ${f(x - w)} ${f(y - w * 0.1)} Q ${f(x)} ${f(y + w * 0.55)} ${f(x + w)} ${f(y - w * 0.1)}`,
    stroke: ink, strokeWidth: lw * 1.08, role: 'ink',
  }]
}

/** 皱纹：sides 决定画在哪几侧，正面两侧，侧面只画朝向观众的那侧 */
function wrinkleOps(
  spec: CharacterSpec, headW: number, eyeY: number, mouthY: number, _pose: PoseParams, sides: number[],
): DrawOp[] {
  if (spec.wrinkle <= 0) return []
  const ops: DrawOp[] = []
  const w = spec.wrinkle
  for (const sx of sides) {
    ops.push({
      d: `M ${f(sx * headW * 0.12)} ${f(eyeY - headW * 0.22)} Q ${f(sx * headW * 0.2)} ${f(eyeY - headW * 0.25)} ${f(sx * headW * 0.28)} ${f(eyeY - headW * 0.22)}`,
      stroke: spec.colors.skinShade, strokeWidth: headW * 0.016 * w, opacity: 0.55, role: 'detail',
    })
    ops.push({
      d: `M ${f(sx * headW * 0.17)} ${f(mouthY - headW * 0.03)} Q ${f(sx * headW * 0.22)} ${f(mouthY + headW * 0.04)} ${f(sx * headW * 0.16)} ${f(mouthY + headW * 0.09)}`,
      stroke: spec.colors.skinShade, strokeWidth: headW * 0.015 * w, opacity: 0.5, role: 'detail',
    })
  }
  return ops
}

function faceOps(spec: CharacterSpec, m: Metrics, pose: PoseParams): DrawOp[] {
  if (pose.view === 'back') return []
  if (pose.view === 'side') return profileFaceOps(spec, m, pose)
  return frontFaceOps(spec, m, pose)
}

/** 颜色向白色靠拢，用于受光面 */
function tint(hex: string, amount: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return hex
  const num = parseInt(m[1], 16)
  const mix = (c: number) => Math.round(c + (255 - c) * amount)
  const r = mix((num >> 16) & 255)
  const g = mix((num >> 8) & 255)
  const b = mix(num & 255)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}

/**
 * 头发内部层次的配色。深发压暗等于没画，必须提亮；浅发反过来要压暗。
 * 靠亮度判断而不是按角色写死，换任何发色都成立。
 */
function hairTones(hair: string, hairShade: string): { shadow: string; line: string } {
  const m = /^#([0-9a-fA-F]{6})$/.exec(hair)
  const num = m ? parseInt(m[1], 16) : 0x808080
  const lum = (0.299 * ((num >> 16) & 255) + 0.587 * ((num >> 8) & 255) + 0.114 * (num & 255)) / 255
  return lum < 0.42
    ? { shadow: tint(hair, 0.16), line: tint(hair, 0.55) }
    : { shadow: hairShade, line: tint(hairShade, 0.24) }
}

/**
 * 颊边垂下的发缕。drop 是发梢落点（以头宽为单位，下巴约在 0.58），
 * width 控制发缕宽度。内缘贴着脸颊，外缘不超过发帽，否则会鼓出一个包。
 */
function faceLockPath(side: number, hw: number, cy: number, drop: number, width: number): string {
  const p = (x: number, y: number) => `${f(side * hw * x)} ${f(cy + hw * y)}`
  const inner = 0.34
  const outer = inner + 0.22 * width
  return [
    `M ${p(inner, -0.34)}`,
    `L ${p(outer, -0.3)}`,
    `Q ${p(outer + 0.02 * width, 0)} ${p(outer, 0.26)}`,
    `Q ${p(outer - 0.02 * width, drop - 0.08)} ${p(outer - 0.1 * width, drop)}`,
    `L ${p(outer - 0.2 * width, drop - 0.04)}`,
    `Q ${p(inner + 0.04, 0.18)} ${p(inner, -0.34)}`,
    'Z',
  ].join(' ')
}

/**
 * 发型轮廓。不同发型不是换一套几何，而是同一套几何换系数：
 * 长发蓬出颅骨、垂过下巴；盘发贴着头骨向后梳，耳朵露在外面。
 */
interface HairShape {
  /** 发帽半宽，以头宽为单位（颅骨半宽为 0.5） */
  halfW: number
  /** 颅顶到发顶的厚度 */
  crownLift: number
  /** 发帽侧缘在鬓角处的高度，相对头部中心，向下为正 */
  templeY: number
  /** 颊边发缕的发梢位置，0 表示不长发缕 */
  lockDrop: number
  lockWidth: number
}

const HAIR_SHAPE: Record<HairStyle, HairShape> = {
  long: { halfW: 0.56, crownLift: 0.1, templeY: 0.12, lockDrop: 0.78, lockWidth: 1 },
  bun: { halfW: 0.54, crownLift: 0.07, templeY: 0.02, lockDrop: 0, lockWidth: 0 },
  short: { halfW: 0.56, crownLift: 0.09, templeY: 0.06, lockDrop: 0, lockWidth: 0 },
  baldTop: { halfW: 0.54, crownLift: 0.04, templeY: 0, lockDrop: 0, lockWidth: 0 },
}

/**
 * 头发分层：主体 → 受光 → 发丝 → 分缝 → 发髻细节。纯色块看起来像帽子，靠这几层才有体积。
 *
 * 返回前后两段：behind 画在身体和头之前（长发披在背后），front 画在头之上。
 * 用显式拆分而不是按下标切数组——层次一变下标就错位。
 */
function hairOps(spec: CharacterSpec, m: Metrics, pose: PoseParams): { behind: DrawOp[]; front: DrawOp[] } {
  const cy = m.headCy
  const hw = m.headW
  const capTop = cy - m.headH / 2

  if (pose.view === 'side') return sideHair(spec, m)
  if (pose.view === 'back') return backHair(spec, m)

  const { hair, hairShade } = spec.colors
  const lit = tint(hair, 0.26)
  const tone = hairTones(hair, hairShade)
  const shape = HAIR_SHAPE[spec.hair]
  // 颅顶再往上留一层发量，贴着头骨会像刷了层漆
  const crown = capTop - hw * shape.crownLift
  const capHalf = hw * shape.halfW
  // 发际线：约在颅顶到下颏的上三分之一处。画到眉下就成了戴头盔
  const hairline = cy - hw * 0.3
  const templeY = cy + hw * shape.templeY
  const ops: DrawOp[] = []
  let behindCount = 0

  // 长发后披：要宽过肩膀，否则只在身体两侧露出两条边，像贴了两片
  if (spec.hair === 'long') {
    ops.push({
      d: [
        `M ${f(-hw * 0.58)} ${f(cy - hw * 0.06)}`,
        `Q ${f(-hw * 0.9)} ${f(cy + hw * 0.55)} ${f(-hw * 0.78)} ${f(cy + hw * 1.12)}`,
        `Q ${f(-hw * 0.7)} ${f(cy + hw * 1.34)} ${f(-hw * 0.44)} ${f(cy + hw * 1.32)}`,
        `L ${f(hw * 0.44)} ${f(cy + hw * 1.32)}`,
        `Q ${f(hw * 0.7)} ${f(cy + hw * 1.34)} ${f(hw * 0.78)} ${f(cy + hw * 1.12)}`,
        `Q ${f(hw * 0.9)} ${f(cy + hw * 0.55)} ${f(hw * 0.58)} ${f(cy - hw * 0.06)}`,
        'Z',
      ].join(' '),
      fill: hairShade, role: 'hair',
    })
    // 垂发的走向线：长发不能是一整块布
    for (const sx of [-1, 1]) {
      for (const k of [0.3, 0.46, 0.62]) {
        ops.push({
          d: `M ${f(sx * hw * k)} ${f(cy + hw * 0.08)} Q ${f(sx * hw * (k + 0.1))} ${f(cy + hw * 0.7)} ${f(sx * hw * (k + 0.04))} ${f(cy + hw * 1.26)}`,
          stroke: tone.line, strokeWidth: hw * 0.016, opacity: 0.35, role: 'hair', noOutline: true,
        })
      }
    }
    behindCount = ops.length
  }

  // 颊边发缕：长发垂下来，盘发和短发全部梳上去
  if (shape.lockDrop > 0) {
    for (const sx of [-1, 1]) {
      ops.push({
        d: faceLockPath(sx, hw, cy, shape.lockDrop, shape.lockWidth),
        fill: hair, role: 'hair',
      })
    }
  }

  // 秃顶：只有两鬓，颅顶是空的，不能先画一颗完整的发帽
  if (spec.hair === 'baldTop') {
    for (const sx of [-1, 1]) {
      ops.push({
        d: `M ${f(sx * hw * 0.54)} ${f(cy - hw * 0.06)} Q ${f(sx * hw * 0.48)} ${f(cy - hw * 0.3)} ${f(sx * hw * 0.28)} ${f(cy - hw * 0.34)} L ${f(sx * hw * 0.28)} ${f(cy + hw * 0.12)} Q ${f(sx * hw * 0.44)} ${f(cy + hw * 0.16)} ${f(sx * hw * 0.54)} ${f(cy - hw * 0.06)} Z`,
        fill: hair, role: 'hair',
      })
      for (const k of [0.12, 0.38]) {
        ops.push({
          d: `M ${f(sx * hw * 0.48)} ${f(cy - hw * k)} Q ${f(sx * hw * 0.38)} ${f(cy - hw * (k + 0.06))} ${f(sx * hw * 0.31)} ${f(cy + hw * 0.02)}`,
          stroke: tone.line, strokeWidth: hw * 0.012, opacity: 0.35, role: 'hair', noOutline: true,
        })
      }
    }
    return { behind: ops.slice(0, behindCount), front: ops.slice(behindCount) }
  }

  // 主体
  ops.push({
    d: [
      `M ${f(-capHalf)} ${f(templeY)}`,
      `Q ${f(-capHalf)} ${f(crown)} 0 ${f(crown)}`,
      `Q ${f(capHalf)} ${f(crown)} ${f(capHalf)} ${f(templeY)}`,
      `Q ${f(hw * 0.44)} ${f(cy - hw * 0.22)} ${f(hw * 0.07)} ${f(hairline)}`,
      `L 0 ${f(hairline - hw * 0.03)}`,
      `L ${f(-hw * 0.07)} ${f(hairline)}`,
      `Q ${f(-hw * 0.44)} ${f(cy - hw * 0.22)} ${f(-capHalf)} ${f(templeY)}`,
      'Z',
    ].join(' '),
    fill: hair, role: 'hair',
  })

  // 顶部受光：一道月牙，模拟光从上方打下来
  ops.push({
    d: [
      `M ${f(-capHalf * 0.8)} ${f(crown + hw * 0.18)}`,
      `Q ${f(-capHalf * 0.52)} ${f(crown + hw * 0.01)} 0 ${f(crown + hw * 0.01)}`,
      `Q ${f(capHalf * 0.52)} ${f(crown + hw * 0.01)} ${f(capHalf * 0.8)} ${f(crown + hw * 0.18)}`,
      `Q ${f(capHalf * 0.4)} ${f(crown + hw * 0.12)} 0 ${f(crown + hw * 0.12)}`,
      `Q ${f(-capHalf * 0.4)} ${f(crown + hw * 0.12)} ${f(-capHalf * 0.8)} ${f(crown + hw * 0.18)}`,
      'Z',
    ].join(' '),
    fill: lit, opacity: 0.62, role: 'hair', noOutline: true,
  })

  // 发缘的一线亮边：画在发际线内侧，给刘海一点厚度。
  // 画在外侧就会变成一条压在额头上的发带。
  ops.push({
    d: [
      `M ${f(-capHalf + hw * 0.02)} ${f(templeY - hw * 0.02)}`,
      `Q ${f(-hw * 0.43)} ${f(cy - hw * 0.25)} ${f(-hw * 0.07)} ${f(hairline - hw * 0.04)}`,
      `L ${f(hw * 0.07)} ${f(hairline - hw * 0.04)}`,
      `Q ${f(hw * 0.43)} ${f(cy - hw * 0.25)} ${f(capHalf - hw * 0.02)} ${f(templeY - hw * 0.02)}`,
      `Q ${f(hw * 0.44)} ${f(cy - hw * 0.21)} ${f(hw * 0.07)} ${f(hairline)}`,
      `L ${f(-hw * 0.07)} ${f(hairline)}`,
      `Q ${f(-hw * 0.44)} ${f(cy - hw * 0.21)} ${f(-capHalf + hw * 0.02)} ${f(templeY - hw * 0.02)}`,
      'Z',
    ].join(' '),
    fill: tone.line, opacity: 0.22, role: 'hair', noOutline: true,
  })

  const strandEnd = hairline - hw * 0.02
  if (spec.hair === 'bun') {
    // 盘发是向后梳的：发丝从发际线收向颅顶，没有分缝
    for (const sx of [-1, 1]) {
      const arcs: [number, number, number, number][] = [
        [0.18, 0.24, 0.42, 0.16],
        [0.32, 0.38, 0.5, 0.24],
      ]
      for (const [x0, cx, x1, endK] of arcs) {
        ops.push({
          d: `M ${f(sx * hw * x0)} ${f(hairline + hw * (0.04 + x0 * 0.16))} Q ${f(sx * hw * cx)} ${f(crown + hw * 0.26)} ${f(sx * hw * x1)} ${f(crown + hw * endK)}`,
          stroke: tone.line, strokeWidth: hw * 0.016, opacity: 0.32, role: 'hair', noOutline: true,
        })
      }
    }
  } else {
    // 发束：从分缝向两侧披开。细线在 60px 的头宽下会整片消失，
    // 所以用楔形色块分组，再用两道发丝把边缘梳开。
    for (const sx of [-1, 1]) {
      ops.push({
        d: [
          `M ${f(sx * hw * 0.03)} ${f(crown + hw * 0.12)}`,
          `Q ${f(sx * hw * 0.34)} ${f(crown + hw * 0.24)} ${f(sx * hw * 0.47)} ${f(strandEnd)}`,
          `L ${f(sx * hw * 0.3)} ${f(strandEnd)}`,
          `Q ${f(sx * hw * 0.18)} ${f(crown + hw * 0.26)} ${f(sx * hw * 0.01)} ${f(crown + hw * 0.14)}`,
          'Z',
        ].join(' '),
        fill: tone.shadow, opacity: 0.16, role: 'hair', noOutline: true,
      })
      const strands: [number, number][] = [
        [0.08, 0.2],
        [0.18, 0.36],
      ]
      for (const [startY, spread] of strands) {
        ops.push({
          d: `M ${f(sx * hw * 0.05)} ${f(crown + hw * startY)} Q ${f(sx * hw * spread * 0.78)} ${f(crown + hw * (startY + 0.2))} ${f(sx * hw * (spread + 0.12))} ${f(strandEnd - hw * 0.02)}`,
          stroke: tone.line, strokeWidth: hw * 0.02, opacity: 0.26, role: 'hair', noOutline: true,
        })
      }
    }

    // 分缝
    ops.push({
      d: `M 0 ${f(crown + hw * 0.04)} L 0 ${f(strandEnd)}`,
      stroke: tone.line, strokeWidth: hw * 0.024, opacity: 0.45, role: 'hair', noOutline: true,
    })
  }

  if (spec.hair === 'bun') {
    const bx = 0
    // 发髻坐在颅顶的发帽上，不能悬空；压扁一点，正圆会像个丸子
    const by = crown - hw * 0.04
    const br = hw * 0.14
    ops.push({ d: ellipse(bx, by, br, br * 0.78), fill: hair, role: 'hair' })
    // 收拢的发根
    ops.push({
      d: ellipse(bx, by + br * 0.62, br * 0.72, br * 0.3), fill: hairShade, opacity: 0.4, role: 'hair', noOutline: true,
    })
    // 发髻根部暗面
    ops.push({
      d: ellipse(bx, by + br * 0.32, br * 0.84, br * 0.34), fill: hairShade, opacity: 0.3, role: 'hair', noOutline: true,
    })
    // 发髻受光
    ops.push({
      d: ellipse(bx - br * 0.24, by - br * 0.26, br * 0.46, br * 0.26), fill: lit, opacity: 0.45, role: 'hair', noOutline: true,
    })
    // 缠绕的发丝：两三道就够，画多了像编了个藤球
    for (const k of [-0.24, 0.26]) {
      ops.push({
        d: `M ${f(bx - br * 0.8)} ${f(by + br * k)} Q ${f(bx)} ${f(by + br * (k - 0.55))} ${f(bx + br * 0.8)} ${f(by + br * k)}`,
        stroke: tone.line, strokeWidth: hw * 0.014, opacity: 0.3, role: 'hair', noOutline: true,
      })
    }
  }

  return { behind: ops.slice(0, behindCount), front: ops.slice(behindCount) }
}

/** 侧视头发：只长在后脑，脸要完整露出 */
function sideHair(spec: CharacterSpec, m: Metrics): { behind: DrawOp[]; front: DrawOp[] } {
  const { hair, hairShade } = spec.colors
  const cy = m.headCy
  const hw = m.headW
  const hh = m.headH / 2
  const lit = tint(hair, 0.26)
  const tone = hairTones(hair, hairShade)
  const ops: DrawOp[] = []
  let behindCount = 0

  if (spec.hair === 'long') {
    // 垂发轮廓走 S 形：一条光滑弧线会像披了块布，两段起伏才有发束感
    const outer = [
      `M ${f(-hw * 0.1)} ${f(cy - hh * 0.3)}`,
      `Q ${f(-hw * 0.48)} ${f(cy - hh * 0.15)} ${f(-hw * 0.5)} ${f(cy + hh * 0.8)}`,
      `Q ${f(-hw * 0.52)} ${f(cy + hh * 1.18)} ${f(-hw * 0.38)} ${f(cy + hh * 1.34)}`,
      `Q ${f(-hw * 0.3)} ${f(cy + hh * 1.46)} ${f(-hw * 0.26)} ${f(cy + hh * 1.24)}`,
      `Q ${f(-hw * 0.22)} ${f(cy + hh * 1.44)} ${f(-hw * 0.04)} ${f(cy + hh * 1.4)}`,
    ]
    ops.push({ d: [...outer, 'Z'].join(' '), fill: hairShade, role: 'hair' })
    // 外缘受光：贴着轮廓的一道亮边，把披发从躯干上拉开
    ops.push({
      d: outer.join(' '),
      stroke: lit, strokeWidth: hw * 0.022, opacity: 0.32, role: 'hair', noOutline: true,
    })
    // 垂发的发丝
    for (const k of [0.1, 0.42, 0.74]) {
      ops.push({
        d: `M ${f(-hw * 0.22)} ${f(cy + hh * k)} Q ${f(-hw * 0.4)} ${f(cy + hh * (k + 0.35))} ${f(-hw * 0.34)} ${f(cy + hh * (k + 0.72))}`,
        stroke: tone.line, strokeWidth: hw * 0.022, opacity: 0.45, role: 'hair', noOutline: true,
      })
    }
    behindCount = ops.length
  }

  // 发帽：从前额发际线绕到后脑
  ops.push({
    d: [
      `M ${f(hw * 0.2)} ${f(cy - hh * 0.55)}`,
      `Q ${f(hw * 0.24)} ${f(cy - hh * 1.02)} ${f(hw * 0.02)} ${f(cy - hh * 1.02)}`,
      `Q ${f(-hw * 0.3)} ${f(cy - hh * 1.0)} ${f(-hw * 0.36)} ${f(cy - hh * 0.55)}`,
      `Q ${f(-hw * 0.46)} ${f(cy - hh * 0.05)} ${f(-hw * 0.38)} ${f(cy + hh * 0.62)}`,
      `L ${f(-hw * 0.24)} ${f(cy + hh * 0.52)}`,
      `Q ${f(-hw * 0.26)} ${f(cy - hh * 0.05)} ${f(-hw * 0.14)} ${f(cy - hh * 0.34)}`,
      `Q ${f(hw * 0.02)} ${f(cy - hh * 0.5)} ${f(hw * 0.2)} ${f(cy - hh * 0.55)}`,
      'Z',
    ].join(' '),
    fill: hair, role: 'hair',
  })

  // 颊边垂发：发帽的内缘本来就压到耳前、落到下颌，
  // 再单独加一缕只会多出一道平行的接缝，所以侧视不再画额前的发缕。

  // 头顶受光
  ops.push({
    d: [
      `M ${f(hw * 0.06)} ${f(cy - hh * 0.86)}`,
      `Q ${f(-hw * 0.16)} ${f(cy - hh * 0.98)} ${f(-hw * 0.3)} ${f(cy - hh * 0.6)}`,
      `Q ${f(-hw * 0.2)} ${f(cy - hh * 0.74)} ${f(hw * 0.04)} ${f(cy - hh * 0.78)}`,
      'Z',
    ].join(' '),
    fill: lit, opacity: 0.45, role: 'hair', noOutline: true,
  })

  // 后脑发丝：从头顶向后下方扫
  for (const k of [0.25, 0.55, 0.85]) {
    ops.push({
      d: `M ${f(hw * 0.04)} ${f(cy - hh * (1.0 - k * 0.35))} Q ${f(-hw * 0.34)} ${f(cy - hh * (0.55 - k * 0.2))} ${f(-hw * 0.34)} ${f(cy + hh * (k * 0.7))}`,
      stroke: tone.line, strokeWidth: hw * 0.016, opacity: 0.3, role: 'hair', noOutline: true,
    })
  }

  if (spec.hair === 'bun') {
    const bx = -hw * 0.34
    const by = cy - hh * 0.94
    const br = hw * 0.17
    // 收拢的发根：没有这层，发髻会浮在后脑上
    ops.push({
      d: ellipse(bx + br * 0.5, by + br * 0.62, br * 0.66, br * 0.4), fill: hairShade, opacity: 0.55, role: 'hair', noOutline: true,
    })
    ops.push({ d: ellipse(bx, by, br, br * 0.88), fill: hair, role: 'hair' })
    ops.push({
      d: ellipse(bx, by + br * 0.34, br * 0.85, br * 0.4), fill: hairShade, opacity: 0.35, role: 'hair', noOutline: true,
    })
    ops.push({
      d: ellipse(bx - br * 0.2, by - br * 0.3, br * 0.48, br * 0.3), fill: lit, opacity: 0.45, role: 'hair', noOutline: true,
    })
    // 盘发的缠绕线
    for (const k of [-0.32, 0.12, 0.5]) {
      ops.push({
        d: `M ${f(bx - br * 0.78)} ${f(by + br * k)} Q ${f(bx)} ${f(by + br * (k - 0.45))} ${f(bx + br * 0.78)} ${f(by + br * k)}`,
        stroke: hairShade, strokeWidth: hw * 0.012, opacity: 0.45, role: 'hair', noOutline: true,
      })
    }
  }

  if (spec.hair === 'baldTop') {
    // 老年：只有后脑一撮，前额完全空白
    ops.push({
      d: [
        `M ${f(-hw * 0.1)} ${f(cy - hh * 0.5)}`,
        `Q ${f(-hw * 0.38)} ${f(cy - hh * 0.55)} ${f(-hw * 0.4)} ${f(cy + hh * 0.1)}`,
        `L ${f(-hw * 0.24)} ${f(cy + hh * 0.12)}`,
        `Q ${f(-hw * 0.24)} ${f(cy - hh * 0.3)} ${f(-hw * 0.08)} ${f(cy - hh * 0.34)}`,
        'Z',
      ].join(' '),
      fill: hair, role: 'hair',
    })
    ops.push({
      d: `M ${f(-hw * 0.12)} ${f(cy - hh * 0.34)} Q ${f(-hw * 0.3)} ${f(cy - hh * 0.2)} ${f(-hw * 0.3)} ${f(cy + hh * 0.06)}`,
      stroke: hairShade, strokeWidth: hw * 0.011, opacity: 0.4, role: 'hair', noOutline: true,
    })
  }

  return { behind: ops.slice(0, behindCount), front: ops.slice(behindCount) }
}

/** 背面：整颗后脑被头发覆盖，只加一点走向线，不用画五官 */
function backHair(spec: CharacterSpec, m: Metrics): { behind: DrawOp[]; front: DrawOp[] } {
  const { hair, hairShade } = spec.colors
  const cy = m.headCy
  const hw = m.headW
  const hh = m.headH / 2
  const lit = tint(hair, 0.26)
  const tone = hairTones(hair, hairShade)
  const ops: DrawOp[] = [{ d: ellipse(0, cy, hw * 0.5, hh), fill: hair, role: 'hair' }]

  if (spec.hair === 'long') {
    ops.push({
      d: `M ${f(-hw * 0.48)} ${f(cy + hh * 0.3)} Q ${f(-hw * 0.56)} ${f(cy + hh * 1.1)} ${f(-hw * 0.34)} ${f(cy + hh * 1.35)} L ${f(hw * 0.34)} ${f(cy + hh * 1.35)} Q ${f(hw * 0.56)} ${f(cy + hh * 1.1)} ${f(hw * 0.48)} ${f(cy + hh * 0.3)} Z`,
      fill: hairShade, role: 'hair',
    })
  }

  ops.push({
    d: ellipse(-hw * 0.05, cy - hh * 0.45, hw * 0.3, hh * 0.3), fill: lit, opacity: 0.4, role: 'hair', noOutline: true,
  })

  // 后脑的发束走向：从顶心散向后颈，两侧各三道
  for (const sx of [-1, 1]) {
    for (const [startK, endK] of [[0.1, 0.22], [0.42, 0.34], [0.68, 0.44]]) {
      ops.push({
        d: `M ${f(sx * hw * 0.03)} ${f(cy - hh * 0.92)} Q ${f(sx * hw * (startK + 0.16))} ${f(cy - hh * 0.4)} ${f(sx * hw * endK)} ${f(cy + hh * 0.42)}`,
        stroke: tone.line, strokeWidth: hw * 0.02, opacity: 0.36, role: 'hair', noOutline: true,
      })
    }
  }

  if (spec.hair === 'bun') {
    ops.push({
      d: ellipse(0, cy - hh * 1.02, hw * 0.19, hw * 0.16), fill: hair, role: 'hair',
    })
  }
  return { behind: [], front: ops }
}

function outfitOps(spec: CharacterSpec, m: Metrics, pose: PoseParams): DrawOp[] {
  const ops: DrawOp[] = []
  const { apron, apronShade, cloth, clothShade } = spec.colors
  const top = m.shoulderY + m.headW * 0.08
  const bottom = m.hipY + m.headW * 0.12

  if (spec.outfit === 'apron') {
    // 围裙下摆
    ops.push({
      d: poly([
        [-m.shoulderHalf * 0.42, top],
        [m.shoulderHalf * 0.42, top],
        [m.hipHalf * 0.92, bottom],
        [-m.hipHalf * 0.92, bottom],
      ]),
      fill: apron, role: 'apron',
    })
    // 围裙阴影
    ops.push({
      d: poly([
        [m.shoulderHalf * 0.1, top],
        [m.shoulderHalf * 0.42, top],
        [m.hipHalf * 0.92, bottom],
        [m.hipHalf * 0.2, bottom],
      ]),
      fill: apronShade, opacity: 0.35, role: 'apron',
    })
    // 肩带
    for (const sx of [-1, 1]) {
      ops.push({
        d: `M ${f(sx * m.shoulderHalf * 0.34)} ${f(top)} L ${f(sx * m.shoulderHalf * 0.72)} ${f(m.shoulderY - m.headW * 0.02)}`,
        stroke: apronShade, strokeWidth: m.headW * 0.045, role: 'apron',
      })
    }
  } else if (spec.outfit === 'dress') {
    ops.push({
      d: poly([
        [-m.shoulderHalf * 1.02, m.shoulderY],
        [m.shoulderHalf * 1.02, m.shoulderY],
        [m.hipHalf * 1.5, bottom + m.headW * 0.2],
        [-m.hipHalf * 1.5, bottom + m.headW * 0.2],
      ]),
      fill: cloth, role: 'cloth',
    })
    ops.push({
      d: poly([
        [m.shoulderHalf * 0.2, m.shoulderY],
        [m.shoulderHalf * 1.02, m.shoulderY],
        [m.hipHalf * 1.5, bottom + m.headW * 0.2],
        [m.hipHalf * 0.3, bottom + m.headW * 0.2],
      ]),
      fill: clothShade, opacity: 0.45, role: 'cloth',
    })
  } else {
    // 衬衫领口
    ops.push({
      d: `M ${f(-m.shoulderHalf * 0.3)} ${f(m.shoulderY - m.headW * 0.02)} L 0 ${f(m.shoulderY + m.headW * 0.18)} L ${f(m.shoulderHalf * 0.3)} ${f(m.shoulderY - m.headW * 0.02)}`,
      fill: clothShade, role: 'cloth',
    })
  }
  return ops
}

/** 主入口：展开成绘制指令序列（顺序即叠放顺序） */
export function buildCharacter(spec: CharacterSpec, pose: PoseParams, totalHeight = 430): CharacterDrawing {
  const m = measure(spec, pose, totalHeight)
  const { skin, skinShade, cloth, clothShade, ink } = spec.colors
  const ops: DrawOp[] = []

  // 取景包围盒：从已知几何累加，避免再解析路径字符串
  const bounds = {
    x0: -m.headW * 0.62,
    y0: -totalHeight,
    x1: m.headW * 0.62,
    y1: 0,
  }
  const include = (x: number, y: number) => {
    if (x < bounds.x0) bounds.x0 = x
    if (x > bounds.x1) bounds.x1 = x
    if (y < bounds.y0) bounds.y0 = y
    if (y > bounds.y1) bounds.y1 = y
  }

  // 头发分前后两段：behind 披在身体与头之后，front 叠在头之上
  const hair = hairOps(spec, m, pose)
  ops.push(...hair.behind)

  // 腿
  const legW = m.headW * 0.19
  if (pose.pose === 'sit') {
    for (const sx of [-1, 1]) {
      ops.push({
        d: poly([
          [sx * legW * 0.5, m.hipY + m.headW * 0.05],
          [sx * legW * 1.6, m.hipY + m.headW * 0.05],
          [sx * legW * 1.75, -m.headW * 0.12],
          [sx * legW * 0.75, -m.headW * 0.12],
        ]),
        fill: clothShade, role: 'cloth',
      })
    }
  } else {
    for (const sx of [-1, 1]) {
      const lean = pose.pose === 'walk' ? sx * legW * 0.7 : sx * legW * 0.35
      ops.push({
        d: poly([
          [sx * legW * 0.28, m.hipY],
          [sx * legW * 1.15, m.hipY],
          [sx * legW * 1.05 + lean, 0],
          [sx * legW * 0.1 + lean, 0],
        ]),
        fill: clothShade, role: 'cloth',
      })
    }
  }
  // 鞋
  for (const sx of [-1, 1]) {
    const lean = pose.pose === 'walk' ? sx * legW * 0.7 : sx * legW * 0.35
    ops.push({
      d: roundRect(sx * legW * 0.1 + lean - legW * 0.55, -m.headW * 0.1, legW * 1.5, m.headW * 0.12, m.headW * 0.05),
      fill: '#3b3a38', role: 'cloth',
    })
  }

  // 躯干
  ops.push({ d: bodyPath(m, spec.proportions.belly), fill: cloth, role: 'cloth' })
  // 体侧阴影
  ops.push({
    d: bodyPath(m, spec.proportions.belly),
    fill: clothShade, opacity: 0.22, role: 'cloth',
  })

  // 手臂：用描边折线画，闭合多边形会变成细楔形
  const armWidth = m.headW * 0.15
  const arms: ('L' | 'R')[] = pose.view === 'side' ? ['R'] : ['L', 'R']
  for (const side of arms) {
    const dir = side === 'L' ? -1 : 1
    const sx = dir
    // 角度语义：0 为自然下垂，正值表示向外张开；左右靠 dir 镜像
    const angle = side === 'L' ? pose.armL : pose.armR
    const pts = armPoints(sx * m.shoulderHalf * 0.92, m.shoulderY + m.headW * 0.04, dir * angle, m.armLen)
    for (const [px, py] of pts) include(px, py)
    ops.push({
      d: pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${f(x)} ${f(y)}`).join(' '),
      stroke: cloth,
      strokeWidth: armWidth,
      role: 'cloth',
    })
    // 手
    const [hx, hy] = pts[pts.length - 1]
    include(hx + m.headW * 0.09, hy + m.headW * 0.13)
    ops.push({
      d: ellipse(hx, hy + m.headW * 0.04, m.headW * 0.078, m.headW * 0.085),
      fill: skin,
      role: 'skin',
    })
  }

  // 服装
  ops.push(...outfitOps(spec, m, pose))

  // 脖子
  ops.push({
    d: roundRect(-m.headW * 0.13, m.neckY - m.headW * 0.02, m.headW * 0.26, m.headW * 0.16, m.headW * 0.04),
    fill: skinShade, role: 'skin',
  })

  // 头。侧视用真正的侧面轮廓：额头、鼻梁、鼻尖、嘴唇、下巴、下颌一起收出剪影，
  // 而不是拿正面那个圆再贴一张脸。
  if (pose.view === 'side') {
    ops.push({ d: profileHeadPath(m.headW / 2, m.headH / 2, m.headCy), fill: skin, role: 'skin' })
  } else {
    ops.push({ d: ellipse(0, m.headCy, m.headW / 2, m.headH / 2), fill: skin, role: 'skin' })
  }
  // 耳朵：正面一对、侧面一只，都画在头发之前——长发才会把它盖住
  if (pose.view === 'front') {
    for (const sx of [-1, 1]) {
      ops.push({
        d: ellipse(sx * m.headW * 0.5, m.headCy + m.headW * 0.04, m.headW * 0.05, m.headW * 0.075),
        fill: skinShade, role: 'skin',
      })
    }
  } else if (pose.view === 'side') {
    ops.push({
      d: ellipse(-m.headW * 0.16, m.headCy + m.headW * 0.04, m.headW * 0.052, m.headW * 0.085),
      fill: skinShade, role: 'skin',
    })
  }
  // 脸部阴影（侧视靠轮廓表达体积，不再叠一块圆斑）
  if (pose.view !== 'side') {
    ops.push({
      d: ellipse(-m.headW * 0.18, m.headCy + m.headW * 0.05, m.headW * 0.36, m.headH * 0.34),
      fill: skinShade, opacity: 0.18, role: 'skin',
    })
  }

  // 头发（前）
  ops.push(...hair.front)

  // 五官
  ops.push(...faceOps(spec, m, pose))

  // 统一描边：只给形体轮廓加线。高光、阴影、发丝这类内部层次必须跳过，
  // 否则每一层都会被描一圈，画面碎成一堆贴纸。
  const painted = ops.map(op => {
    if (op.noOutline) return op
    return {
      ...op,
      stroke: op.stroke ?? (op.role === 'ink' ? undefined : ink),
      strokeWidth: op.strokeWidth ?? (op.role === 'ink' ? undefined : m.headW * 0.014),
    }
  })

  return { ops: painted, tilt: pose.tilt, bob: pose.bob, bounds }
}
