import type { CharacterSpec } from './types'

/**
 * 角色预设。
 * 只描述「长什么样」，不含任何镜头、场景、画风设定——
 * 风格由渲染管线决定，同一个角色可以出成平涂、像素、漫画。
 */

/** 和蔼的老太太：围裙、盘发、圆眼镜、皱纹 */
export const ELDER_WOMAN: CharacterSpec = {
  id: 'elder-woman',
  name: '和蔼的老太太',
  proportions: {
    headRatio: 0.26,
    legRatio: 0.28,
    shoulderRatio: 0.78,
    hipRatio: 0.92,
    belly: 0.72,
    armRatio: 1.0,
  },
  colors: {
    skin: '#f6d3b8',
    skinShade: '#dfb096',
    hair: '#d8d4cd',
    hairShade: '#a9a49c',
    cloth: '#8fa4bd',
    clothShade: '#6d8299',
    apron: '#f1e7d4',
    apronShade: '#d5c4a8',
    ink: '#4a4038',
  },
  hair: 'bun',
  outfit: 'apron',
  glasses: true,
  wrinkle: 1,
}

/** 成年女性：连衣裙、短发，用来验证体型参数切换 */
export const ADULT_WOMAN: CharacterSpec = {
  id: 'adult-woman',
  name: '成年女性',
  proportions: {
    headRatio: 0.2,
    legRatio: 0.42,
    shoulderRatio: 0.7,
    hipRatio: 0.82,
    belly: 0.2,
    armRatio: 1.05,
  },
  colors: {
    skin: '#f8d6bd',
    skinShade: '#e0ad92',
    hair: '#4a3a33',
    hairShade: '#2f2521',
    cloth: '#c96b6b',
    clothShade: '#a14f4f',
    apron: '#f3e6d2',
    apronShade: '#d3bfa4',
    ink: '#3d3230',
  },
  hair: 'long',
  outfit: 'dress',
  glasses: false,
  wrinkle: 0,
}

/** 小孩：大头、短腿，用来验证比例系数是否真的驱动几何 */
export const CHILD: CharacterSpec = {
  id: 'child',
  name: '小孩',
  proportions: {
    headRatio: 0.36,
    legRatio: 0.24,
    shoulderRatio: 0.66,
    hipRatio: 0.74,
    belly: 0.45,
    armRatio: 0.9,
  },
  colors: {
    skin: '#fbdcc4',
    skinShade: '#e5b79c',
    hair: '#3b2c26',
    hairShade: '#241a16',
    cloth: '#7fb069',
    clothShade: '#5c8a4a',
    apron: '#f7ecd8',
    apronShade: '#ddc9ab',
    ink: '#3a322c',
  },
  hair: 'short',
  outfit: 'shirt',
  glasses: false,
  wrinkle: 0,
}

export const CHARACTER_PRESETS: CharacterSpec[] = [ELDER_WOMAN, ADULT_WOMAN, CHILD]
