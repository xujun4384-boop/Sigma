// 绘画画布的核心数据模型。
// 一条 stroke 就是"一笔"：它有目标图层、笔刷、颜色、若干控制点，
// 引擎负责把控制点展开成采样点并逐笔绘制出来。

export type Point = [number, number]

/** 笔刷名称。新增笔刷只需在 brushes.ts 的 BRUSHES 注册表里加一条，不改引擎。 */
export type BrushName = 'pencil' | 'charcoal' | 'marker' | 'watercolor' | 'ink'

export interface StrokeStyle {
  brush: BrushName
  color: string
  /** 笔宽，单位为画布逻辑像素 */
  width: number
  /** 不透明度 0~1 */
  opacity: number
}

export interface Stroke extends StrokeStyle {
  id: string
  layer: string
  points: Point[]
  /**
   * 平滑强度：0 表示按折线直连（手绘笔迹用），
   * 大于 0 时用 Catmull-Rom 插值，数值为每段采样数。
   */
  smooth?: number
  /** 抖动种子，保证同一笔每次重绘结果完全一致 */
  seed?: number
}

export interface LayerData {
  id: string
  name: string
  visible: boolean
  /** 图层整体不透明度 0~1 */
  opacity: number
}

export interface SceneData {
  version: 2
  /** 画布逻辑尺寸，所有坐标都在这个坐标系内 */
  width: number
  height: number
  layers: LayerData[]
  strokes: Stroke[]
}

/**
 * 一笔的几何事实，用于后端做精确审计。
 * 由引擎按真实采样点算出，不是目测，因此可以当作可信数据使用。
 */
export interface StrokeAudit {
  id: string
  layer: string
  brush: BrushName
  color: string
  /** [左, 上, 右, 下] */
  bbox: [number, number, number, number]
  /** 路径总长（逻辑像素） */
  length: number
  /** 首尾是否闭合 */
  closed: boolean
}

export const CANVAS_WIDTH = 1600
export const CANVAS_HEIGHT = 1000
