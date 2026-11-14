/**
 * 角色资产的数据模型。
 *
 * 核心约定：角色是「参数 + 几何」的产物，不是一张位图。
 * 只有这样才能在动画里改表情、换姿态、切风格，并在不同镜头间保持同一个长相。
 */

/** 一条绘制指令。d 用 SVG 路径语法，Canvas 的 Path2D 和 SVG 都能直接吃。 */
export interface DrawOp {
  d: string
  fill?: string
  stroke?: string
  strokeWidth?: number
  opacity?: number
  /** 图层用途，供风格渲染 pass 区分处理（例如像素风只给轮廓描边） */
  role?: 'skin' | 'hair' | 'cloth' | 'apron' | 'ink' | 'detail'
  /**
   * 不参与统一描边。
   * 高光、阴影、发丝这类内部层次如果被加上轮廓线，会变成一层层贴纸，
   * 把形体切碎。
   */
  noOutline?: boolean
}

/** 体型比例。全部是相对总高的系数，换体型只改数字。 */
export interface Proportions {
  /** 头高占总高的比例。老年/儿童偏大，成年偏小 */
  headRatio: number
  /** 腿长占比 */
  legRatio: number
  /** 半肩宽 / 头宽 */
  shoulderRatio: number
  /** 半髋宽 / 头宽 */
  hipRatio: number
  /** 躯干圆润度 0~1，越大越胖 */
  belly: number
  /** 手臂长度 / 躯干长 */
  armRatio: number
}

export interface CharacterColors {
  skin: string
  skinShade: string
  hair: string
  hairShade: string
  cloth: string
  clothShade: string
  apron: string
  apronShade: string
  ink: string
}

export type HairStyle = 'bun' | 'short' | 'long' | 'baldTop'
export type Outfit = 'apron' | 'dress' | 'shirt'

export interface CharacterSpec {
  id: string
  name: string
  proportions: Proportions
  colors: CharacterColors
  hair: HairStyle
  outfit: Outfit
  glasses: boolean
  /** 皱纹强度 0~1，老年角色用来加面部细节 */
  wrinkle: number
}

export type View = 'front' | 'side' | 'back'
export type Pose = 'stand' | 'sit' | 'walk'
export type EyeMood = 'open' | 'closed' | 'happy' | 'worried' | 'surprised'
export type MouthMood = 'smile' | 'neutral' | 'open' | 'sad'

/** 一帧的姿态与表情参数。动画就是让这些值随时间变化。 */
export interface PoseParams {
  view: View
  pose: Pose
  eyes: EyeMood
  mouth: MouthMood
  /** 手臂张开角度（度），0 为自然下垂，正值向外张开，左右自动镜像 */
  armL: number
  armR: number
  /** 身体倾斜（度） */
  tilt: number
  /** 呼吸起伏（逻辑像素），正值向上 */
  bob: number
  /** 头部左右转动（度），侧脸与回头用 */
  headTurn: number
}

/**
 * 骨架输出：绘制指令 + 整体变换 + 实际包围盒。
 * tilt/bob 是作用于全身的变换，单独拿出来交给渲染器施加，
 * 这样不同渲染器（Canvas2D / SVG）都能用同一份数据。
 * bounds 用于取景：抬手、横躺这类姿态的横向范围远大于站姿，
 * 按固定身高缩放会把手臂裁掉。
 */
export interface CharacterDrawing {
  ops: DrawOp[]
  tilt: number
  bob: number
  bounds: { x0: number; y0: number; x1: number; y1: number }
}

export const DEFAULT_POSE: PoseParams = {
  view: 'front',
  pose: 'stand',
  eyes: 'open',
  mouth: 'smile',
  armL: 8,
  armR: 8,
  tilt: 0,
  bob: 0,
  headTurn: 0,
}

/** 风格名称。新增风格 = 在 render.ts 里加一条管线，不动角色几何。 */
export type StyleName = 'flat' | 'pixel'

export interface StyleOptions {
  style: StyleName
  /** 像素风的像素块大小（逻辑像素），越大越粗 */
  pixelSize: number
  /** 像素风的调色层级，越小颜色越少 */
  colorLevels: number
}
