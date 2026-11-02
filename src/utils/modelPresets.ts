/**
 * 模型预设的前端工具：拉取注册表、按模型匹配、把历史配置归一成新结构。
 * 能力数据的唯一来源是后端 model_presets.py，这里不重复维护任何模型参数。
 */
import type {
  FamilyPreset,
  LLMEntry,
  ModelPreset,
  ModelRegistry,
  ThinkingOptionId,
} from '../types/electron'
import { getBackendUrl } from './config'

let registryPromise: Promise<ModelRegistry | null> | null = null

export function fetchModelRegistry(force = false): Promise<ModelRegistry | null> {
  if (!force && registryPromise) return registryPromise
  registryPromise = (async () => {
    try {
      const baseUrl = await getBackendUrl()
      const resp = await fetch(`${baseUrl}/api/model-presets`)
      if (!resp.ok) return null
      const data = await resp.json()
      if (!data || !Array.isArray(data.providers)) return null
      return data as ModelRegistry
    } catch {
      return null
    }
  })()
  return registryPromise
}

/** 思考档位的 i18n key；注册表只给 id，文案在前端统一维护 */
export const THINKING_LABEL_KEYS: Record<ThinkingOptionId, string> = {
  default: 'api.thinking_option_default',
  off: 'api.thinking_option_off',
  on: 'api.thinking_option_on',
  auto: 'api.thinking_option_auto',
  low: 'api.thinking_option_low',
  medium: 'api.thinking_option_medium',
  high: 'api.thinking_option_high',
  xhigh: 'api.thinking_option_xhigh',
  max: 'api.thinking_option_max',
}

const LEGACY_THINKING: Record<string, ThinkingOptionId> = {
  adaptive: 'default',
  enabled: 'on',
  disabled: 'off',
}

export function normalizeThinking(value?: string | null): ThinkingOptionId {
  if (!value) return 'default'
  const normalized = LEGACY_THINKING[value] || value
  return normalized as ThinkingOptionId
}

/** 先按 provider + model 精确命中，再退化为按 model 全局命中（与后端规则一致）。 */
export function findModelPreset(
  registry: ModelRegistry | null,
  provider: string | undefined,
  model: string | undefined
): ModelPreset | undefined {
  if (!registry || !model) return undefined
  const targetModel = model.trim().toLowerCase()
  if (!targetModel) return undefined
  const targetProvider = (provider || '').trim().toLowerCase()

  for (const p of registry.providers) {
    if (p.id !== targetProvider) continue
    const hit = p.models.find(m => m.model.toLowerCase() === targetModel)
    if (hit) return hit
  }
  for (const p of registry.providers) {
    const hit = p.models.find(m => m.model.toLowerCase() === targetModel)
    if (hit) return hit
  }
  let best: ModelPreset | undefined
  for (const p of registry.providers) {
    for (const m of p.models) {
      const key = m.model.toLowerCase()
      if (targetModel.startsWith(key) && (!best || key.length > best.model.length)) {
        best = m
      }
    }
  }
  return best
}

export function findProvider(registry: ModelRegistry | null, providerId: string | undefined) {
  if (!registry || !providerId) return undefined
  return registry.providers.find(p => p.id === providerId)
}

export function findFamily(registry: ModelRegistry | null, familyId: string | undefined) {
  if (!registry || !familyId) return undefined
  return registry.families.find(f => f.id === familyId)
}

/** 该模型可用的思考档位；未命中预设时按协议给通用档位。 */
export function thinkingOptionsFor(
  registry: ModelRegistry | null,
  entry: Pick<LLMEntry, 'provider' | 'model' | 'protocol' | 'family'>
): ThinkingOptionId[] {
  const preset = findModelPreset(registry, entry.provider, entry.model)
  if (preset) return preset.thinkingOptions
  const genericId = entry.protocol === 'openai' ? 'generic-openai' : 'generic-anthropic'
  const family = findFamily(registry, entry.family) || findFamily(registry, genericId)
  if (family) return family.thinkingOptions
  return ['default']
}

/**
 * 把历史配置迁移到新结构：
 * - 思考档位归一，超出模型能力的档位回落到 default
 * - 补齐 family（不写入 contextSize 等覆盖值，留空才能跟随预设）
 */
export function migrateLLMEntry(entry: LLMEntry, registry: ModelRegistry | null): { entry: LLMEntry; changed: boolean } {
  const preset = findModelPreset(registry, entry.provider, entry.model)
  const thinking = normalizeThinking(entry.thinking as string | undefined)
  const allowed = preset
    ? preset.thinkingOptions
    : thinkingOptionsFor(registry, entry)
  const nextThinking: ThinkingOptionId = allowed.includes(thinking) ? thinking : 'default'

  const next: LLMEntry = { ...entry, thinking: nextThinking }
  if (preset && next.family !== preset.family) next.family = preset.family
  if (preset && !entry.provider) next.provider = preset.provider

  let changed = next.thinking !== entry.thinking || next.family !== entry.family || next.provider !== entry.provider

  // 200000 是旧版本拿不到上下文时的全局兜底值，不是用户的选择；
  // 命中预设时清掉，让配置回到“跟随预设窗口”。
  const LEGACY_DEFAULT_CONTEXT = 200_000
  if (preset && entry.contextSize === LEGACY_DEFAULT_CONTEXT && preset.context !== LEGACY_DEFAULT_CONTEXT) {
    delete next.contextSize
    changed = true
  }

  return { entry: next, changed }
}

export function migrateConfig(
  entries: LLMEntry[],
  registry: ModelRegistry | null
): { entries: LLMEntry[]; changed: boolean } {
  let changed = false
  const next = entries.map(item => {
    const result = migrateLLMEntry(item, registry)
    if (result.changed) changed = true
    return result.entry
  })
  return { entries: next, changed }
}

/** 能力徽章用的简短描述 */
export function describeEntry(
  entry: LLMEntry,
  registry: ModelRegistry | null
): { familyLabel: string; thinking: ThinkingOptionId; context: number | null; vision: boolean } {
  const preset = findModelPreset(registry, entry.provider, entry.model)
  const family: FamilyPreset | undefined = findFamily(registry, preset?.family || entry.family)
  return {
    familyLabel: preset?.familyLabel || family?.label || '',
    thinking: normalizeThinking(entry.thinking as string | undefined),
    context: entry.contextSize || preset?.context || null,
    vision: entry.vision !== undefined ? entry.vision : Boolean(preset?.vision),
  }
}
