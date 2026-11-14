import type { CharacterSpec, StyleOptions } from './types'

/**
 * 定妆预览总线。
 *
 * 角色由后端工具推上来的，不能做成画布组件的局部状态：
 * 用户可能停在别的页签，切回来时必须还能看到待确认的那一版。
 * 所以这里保留"当前预览"，订阅时先补发一次。
 */

export interface CharacterRole {
  /** 角色 key：hero / friend-a …，与镜头里的组件名、文件一一对应 */
  role: string
  spec: CharacterSpec
}

export interface CharacterPreview {
  /** 这一次预览的凭据，确认时原样回传给后端 */
  token: string
  spec: CharacterSpec
  /** 整组角色（主角 + 配角），一次确认；旧事件没有这个字段时按只有主角处理 */
  characters: CharacterRole[]
  title: string
  /** 模型给出的说明：为什么这样定，和上一版比改了什么 */
  note: string
  style: StyleOptions
}

type Listener = (preview: CharacterPreview | null) => void

class CharacterBus {
  private current: CharacterPreview | null = null
  private listeners = new Set<Listener>()

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn)
    fn(this.current)
    return () => {
      this.listeners.delete(fn)
    }
  }

  publish(preview: CharacterPreview): void {
    this.current = preview
    for (const fn of this.listeners) fn(preview)
  }

  clear(): void {
    this.current = null
    for (const fn of this.listeners) fn(null)
  }

  get active(): CharacterPreview | null {
    return this.current
  }
}

export const characterBus = new CharacterBus()

/**
 * 把后端推来的 character_preview 事件收敛成前端契约。
 * 缺字段返回 null 而不是丢一个半成品进去——画布上没有角色，
 * 至少不会画出一个没有身体的半个人。
 */
export function previewFromEvent(data: Record<string, unknown>): CharacterPreview | null {
  const spec = data.spec as CharacterSpec | undefined
  if (!spec || typeof spec !== 'object' || !spec.colors || !spec.proportions) return null
  const rawStyle = (data.style || {}) as Partial<StyleOptions>
  const rawCast: unknown[] = Array.isArray(data.characters) ? data.characters : []
  const characters: CharacterRole[] = []
  for (const item of rawCast) {
    const row = item as Record<string, unknown>
    const role = String(row.role || '')
    const s = row.spec as CharacterSpec | undefined
    if (role && s && s.colors && s.proportions) characters.push({role, spec: s})
  }
  return {
    token: String(data.token || ''),
    spec,
    characters: characters.length ? characters : [{role: 'hero', spec}],
    title: String(data.title || '角色定妆'),
    note: String(data.note || ''),
    style: {
      style: rawStyle.style === 'pixel' ? 'pixel' : 'flat',
      pixelSize: Number(rawStyle.pixelSize) || 4,
      colorLevels: Number(rawStyle.colorLevels) || 6,
    },
  }
}
