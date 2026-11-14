import { buildCharacter } from './rig'
import { CHARACTER_PRESETS, ADULT_WOMAN, CHILD, ELDER_WOMAN } from './presets'
import { renderCharacter } from './render'
import type { CharacterSpec, PoseParams, StyleOptions } from './types'
import { DEFAULT_POSE } from './types'

document.body.style.cssText = 'margin:0;background:#22252a;color:#d8d8d8;font:13px/1.5 system-ui,sans-serif'

const CELL_W = 210
const CELL_H = 290

interface Cell {
  label: string
  spec: CharacterSpec
  pose: Partial<PoseParams>
  style: StyleOptions
  /** 单独指定画布尺寸，用来模拟不同景别下的头部大小 */
  w?: number
  h?: number
}

const moodCases: { label: string; pose: Partial<PoseParams> }[] = [
  { label: '微笑 / 睁眼', pose: { mouth: 'smile', eyes: 'open' } },
  { label: '开心 / 眯眼', pose: { mouth: 'smile', eyes: 'happy' } },
  { label: '闭嘴 / 平静', pose: { mouth: 'neutral', eyes: 'open' } },
  { label: '张嘴 / 惊讶', pose: { mouth: 'open', eyes: 'surprised' } },
  { label: '担忧', pose: { mouth: 'sad', eyes: 'worried' } },
  { label: '闭眼 / 微笑', pose: { mouth: 'smile', eyes: 'closed' } },
]

const flat: StyleOptions = { style: 'flat', pixelSize: 4, colorLevels: 8 }
const pixel: StyleOptions = { style: 'pixel', pixelSize: 4, colorLevels: 6 }

const sections: { title: string; cells: Cell[] }[] = [
  {
    title: '表情参数（平涂）— 六格应当是不同的神态',
    cells: moodCases.map(c => ({ label: c.label, spec: ELDER_WOMAN, pose: c.pose, style: flat })),
  },
  {
    title: '同一组表情（像素风，像素块 4px / 6 级色）',
    cells: moodCases.map(c => ({ label: c.label, spec: ELDER_WOMAN, pose: c.pose, style: pixel })),
  },
  {
    title: '体型参数 — 头身比、腿长、体宽都应由系数驱动',
    cells: CHARACTER_PRESETS.map(spec => ({
      label: `${spec.name}｜头 ${spec.proportions.headRatio}`,
      spec,
      pose: {},
      style: flat,
    })),
  },
  {
    title: '侧脸专项 — 眼睛在前段、鼻子凸出脸缘、耳朵在后段',
    cells: [
      { label: '侧脸 / 微笑', pose: { view: 'side' }, spec: ELDER_WOMAN, style: flat },
      { label: '侧脸 / 张嘴', pose: { view: 'side', mouth: 'open', eyes: 'surprised' }, spec: ELDER_WOMAN, style: flat },
      { label: '侧脸 / 闭眼', pose: { view: 'side', eyes: 'closed' }, spec: ELDER_WOMAN, style: flat },
      { label: '侧脸 / 成年', pose: { view: 'side' }, spec: ADULT_WOMAN, style: flat },
      { label: '侧脸 / 小孩', pose: { view: 'side' }, spec: CHILD, style: flat },
      { label: '侧脸 / 像素', pose: { view: 'side' }, spec: ELDER_WOMAN, style: pixel },
    ],
  },
  {
    title: '视角与姿态',
    cells: [
      { label: '正面', pose: { view: 'front' }, spec: ELDER_WOMAN, style: flat },
      { label: '侧脸', pose: { view: 'side', headTurn: 8 }, spec: ELDER_WOMAN, style: flat },
      { label: '背面', pose: { view: 'back' }, spec: ELDER_WOMAN, style: flat },
      { label: '坐姿', pose: { pose: 'sit', armL: 26, armR: 26 }, spec: ELDER_WOMAN, style: flat },
      { label: '抬手', pose: { armL: 72, armR: 14 }, spec: ELDER_WOMAN, style: flat },
      { label: '倾斜', pose: { tilt: 10 }, spec: ELDER_WOMAN, style: flat },
    ].map(c => ({ ...c, pose: c.pose, spec: c.spec, style: c.style })),
  },
  {
    title: '头发专项 — 正面颊边发缕、侧脸垂发、背面发束',
    cells: [
      { label: '成年女性 / 正面', spec: ADULT_WOMAN, pose: {}, style: flat, w: 300, h: 430 },
      { label: '成年女性 / 侧脸', spec: ADULT_WOMAN, pose: { view: 'side' }, style: flat, w: 300, h: 430 },
      { label: '成年女性 / 背面', spec: ADULT_WOMAN, pose: { view: 'back' }, style: flat, w: 300, h: 430 },
      { label: '老太太 / 正面', spec: ELDER_WOMAN, pose: {}, style: flat, w: 300, h: 430 },
      { label: '老太太 / 侧脸', spec: ELDER_WOMAN, pose: { view: 'side' }, style: flat, w: 300, h: 430 },
    ],
  },
  {
    title: '远景与中景（画布高 260 / 420）— 缩到这个尺寸还认得出吗',
    cells: [260, 420].map(h => ({
      label: `画布高 ${h}px`,
      spec: ADULT_WOMAN,
      pose: {},
      style: flat,
      w: Math.round(h * 0.72),
      h,
    })),
  },
  {
    title: '近景（画布高 640）— 发缕、发丝、发髻的细节',
    cells: [
      { label: '成年女性 / 正面', spec: ADULT_WOMAN, pose: {}, style: flat, w: 460, h: 640 },
      { label: '成年女性 / 侧脸', spec: ADULT_WOMAN, pose: { view: 'side' }, style: flat, w: 460, h: 640 },
      { label: '老太太 / 正面', spec: ELDER_WOMAN, pose: {}, style: flat, w: 460, h: 640 },
      { label: '老太太 / 侧脸', spec: ELDER_WOMAN, pose: { view: 'side' }, style: flat, w: 460, h: 640 },
    ],
  },
  {
    title: '像素块大小对比（同一角色）',
    cells: [2, 4, 6, 8].map(size => ({
      label: `像素块 ${size}px`,
      spec: ELDER_WOMAN,
      pose: {},
      style: { style: 'pixel', pixelSize: size, colorLevels: 6 } as StyleOptions,
    })),
  },
]

const app = document.getElementById('app')!
;(window as any).charLab = { sections, render: () => paint() }

function paint() {
  app.innerHTML = ''
  for (const section of sections) {
    const title = document.createElement('div')
    title.textContent = section.title
    title.style.cssText = 'padding:16px 20px 8px;font-size:13px;color:#8fa4bd;letter-spacing:.5px'
    app.appendChild(title)

    const row = document.createElement('div')
    row.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;padding:0 20px 8px'

    for (const cell of section.cells) {
      const wrap = document.createElement('div')
      wrap.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:4px'

      const canvas = document.createElement('canvas')
      canvas.style.cssText = 'background:#f4efe6;border-radius:6px'
      wrap.appendChild(canvas)

      const label = document.createElement('div')
      label.textContent = cell.label
      label.style.cssText = 'font-size:11px;color:#9aa2ad'
      wrap.appendChild(label)

      row.appendChild(wrap)

      const pose: PoseParams = { ...DEFAULT_POSE, ...cell.pose }
      const drawing = buildCharacter(cell.spec, pose, 430)
      renderCharacter(canvas, drawing, { width: cell.w ?? CELL_W, height: cell.h ?? CELL_H }, cell.style)
    }
    app.appendChild(row)
  }
}

paint()
