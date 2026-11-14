import type { CharacterDrawing, DrawOp, StyleOptions } from './types'

/**
 * 角色渲染器。
 *
 * 几何只有一份（buildCharacter 产出的绘制指令），这里按风格决定「怎么落笔」：
 * - flat  平涂矢量
 * - pixel 先按低分辨率绘制，再做调色板量化与最近邻放大
 *
 * 新增风格只需在这里加一条管线，角色几何与参数完全不用改。
 */

export interface Viewport {
  width: number
  height: number
  /** 四周留白比例 */
  margin?: number
}

function paintOps(ctx: CanvasRenderingContext2D, ops: DrawOp[]): void {
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  for (const op of ops) {
    const path = new Path2D(op.d)
    if (op.fill) {
      ctx.globalAlpha = op.opacity ?? 1
      ctx.fillStyle = op.fill
      ctx.fill(path)
    }
    if (op.stroke) {
      ctx.globalAlpha = op.opacity ?? 1
      ctx.strokeStyle = op.stroke
      ctx.lineWidth = op.strokeWidth ?? 1
      ctx.stroke(path)
    }
  }
  ctx.globalAlpha = 1
}

/** 按包围盒把角色摆进视口：水平居中、底部贴边，并施加整体倾斜与起伏 */
function placeCharacter(
  ctx: CanvasRenderingContext2D,
  view: Viewport,
  drawing: CharacterDrawing,
): number {
  const margin = view.margin ?? 0.1
  const { x0, y0, x1, y1 } = drawing.bounds
  const boxW = Math.max(1, x1 - x0)
  const boxH = Math.max(1, y1 - y0)
  const usableW = view.width * (1 - margin * 2)
  const usableH = view.height * (1 - margin * 2)
  // 取宽高两个方向的较小缩放，保证抬手、倾斜等姿态也不会被裁掉
  const scale = Math.min(usableW / boxW, usableH / boxH)

  ctx.translate(view.width / 2, view.height - view.height * margin)
  // 倾斜绕脚底旋转，起伏沿身体向上——两者都作用于全身，不是单个部件
  if (drawing.tilt) ctx.rotate((drawing.tilt * Math.PI) / 180)
  if (drawing.bob) ctx.translate(0, -drawing.bob)
  ctx.scale(scale, scale)
  // 把包围盒中心对到视口中心
  ctx.translate(-(x0 + x1) / 2, -y1)
  return scale
}

function quantize(imageData: ImageData, levels: number): void {
  const data = imageData.data
  const step = 255 / Math.max(1, levels - 1)
  for (let i = 0; i < data.length; i += 4) {
    // 半透明抗锯齿像素直接抹掉，否则放大后边缘会发灰、不够「像素」
    if (data[i + 3] < 128) {
      data[i + 3] = 0
      continue
    }
    data[i + 3] = 255
    data[i] = Math.round(data[i] / step) * step
    data[i + 1] = Math.round(data[i + 1] / step) * step
    data[i + 2] = Math.round(data[i + 2] / step) * step
  }
}

/**
 * 把角色画到目标画布上。
 * 目标画布按 CSS 尺寸呈现，内部按 devicePixelRatio 放大以保证清晰。
 */
export function renderCharacter(
  canvas: HTMLCanvasElement,
  drawing: CharacterDrawing,
  view: Viewport,
  style: StyleOptions,
): void {
  const dpr = Math.min(2, window.devicePixelRatio || 1)
  const targetW = Math.max(1, Math.round(view.width * dpr))
  const targetH = Math.max(1, Math.round(view.height * dpr))
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW
    canvas.height = targetH
  }
  canvas.style.width = `${view.width}px`
  canvas.style.height = `${view.height}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  if (style.style === 'pixel') {
    // 低分辨率绘制：像素块大小换算成画布像素
    const block = Math.max(1, style.pixelSize * dpr)
    const smallW = Math.max(8, Math.round(targetW / block))
    const smallH = Math.max(8, Math.round(targetH / block))
    const small = document.createElement('canvas')
    small.width = smallW
    small.height = smallH
    const sctx = small.getContext('2d')
    if (!sctx) return

    sctx.save()
    placeCharacter(sctx, { ...view, width: smallW, height: smallH }, drawing)
    paintOps(sctx, drawing.ops)
    sctx.restore()

    const img = sctx.getImageData(0, 0, smallW, smallH)
    quantize(img, style.colorLevels)
    sctx.putImageData(img, 0, 0)

    ctx.imageSmoothingEnabled = false
    ctx.drawImage(small, 0, 0, smallW, smallH, 0, 0, targetW, targetH)
    ctx.imageSmoothingEnabled = true
    return
  }

  ctx.save()
  placeCharacter(ctx, { ...view, width: targetW, height: targetH }, drawing)
  paintOps(ctx, drawing.ops)
  ctx.restore()
}

/** 视口尺寸变化时按容器等比换算 */
export function fitViewport(width: number, height: number): Viewport {
  return { width, height, margin: 0.1 }
}
