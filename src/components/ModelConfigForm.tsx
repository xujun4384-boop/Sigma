import { useMemo, useState } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, Check, Eye, EyeOff, Loader2, Plus, RefreshCw } from 'lucide-react'
import { useTranslation } from '../i18n/I18nContext'
import { getBackendUrl } from '../utils/config'
import {
  findFamily,
  findModelPreset,
  findProvider,
  normalizeThinking,
  THINKING_LABEL_KEYS,
} from '../utils/modelPresets'
import type {
  LLMEntry,
  ModelRegistry,
  ThinkingOptionId,
} from '../types/electron'

interface ModelConfigFormProps {
  registry: ModelRegistry | null
  editing: LLMEntry | null
  onCancel: () => void
  onSubmit: (entry: LLMEntry) => void
}

function toNumber(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const num = Number(trimmed)
  return Number.isFinite(num) ? num : undefined
}

export default function ModelConfigForm({ registry, editing, onCancel, onSubmit }: ModelConfigFormProps) {
  const { t } = useTranslation()
  const initialPreset = findModelPreset(registry, editing?.provider, editing?.model)

  const [providerId, setProviderId] = useState(editing?.provider || initialPreset?.provider || '')
  const [modelMode, setModelMode] = useState<'preset' | 'custom'>(initialPreset ? 'preset' : 'custom')
  const [modelId, setModelId] = useState(initialPreset?.model || '')
  const [model, setModel] = useState(editing?.model || '')
  const [protocol, setProtocol] = useState<'anthropic' | 'openai'>(editing?.protocol || initialPreset?.protocol || 'anthropic')
  const [baseUrl, setBaseUrl] = useState(editing?.baseUrl || initialPreset?.baseUrl || '')
  const [apiKey, setApiKey] = useState(editing?.apiKey || '')
  const [name, setName] = useState(editing?.name || '')
  const [familyId, setFamilyId] = useState(editing?.family || initialPreset?.family || '')
  const [thinking, setThinking] = useState<ThinkingOptionId>(normalizeThinking(editing?.thinking as string | undefined))
  const [contextSize, setContextSize] = useState(editing?.contextSize ? String(editing.contextSize) : '')
  const [maxTokens, setMaxTokens] = useState(editing?.maxTokens ? String(editing.maxTokens) : '')
  const [temperature, setTemperature] = useState(editing?.temperature !== undefined ? String(editing.temperature) : '')
  const [topP, setTopP] = useState(editing?.topP !== undefined ? String(editing.topP) : '')
  const [topK, setTopK] = useState(editing?.topK !== undefined ? String(editing.topK) : '')
  const [vision, setVision] = useState<boolean>(editing?.vision ?? initialPreset?.vision ?? false)
  const [showAdvanced, setShowAdvanced] = useState(Boolean(editing))
  const [showKey, setShowKey] = useState(false)
  const [fetchingContext, setFetchingContext] = useState(false)
  const [contextHint, setContextHint] = useState('')

  const provider = findProvider(registry, providerId)
  const preset = useMemo(() => {
    if (modelMode !== 'preset' || !provider) return undefined
    return provider.models.find(m => m.model === modelId)
  }, [modelMode, provider, modelId])
  const family = findFamily(registry, preset?.family || familyId)
  const effectiveFamilyId = preset?.family || familyId

  const thinkingOptions: ThinkingOptionId[] = preset
    ? (preset.thinkingOptionsByProtocol?.[protocol] || preset.thinkingOptions)
    : (family?.thinkingOptions?.length ? family.thinkingOptions : ['default'])

  const sampling = preset
    ? preset.sampling
    : {
        temperature: family?.temperature ? { default: null, min: 0, max: 2 } : null,
        topP: family?.topP ? { default: null, min: 0, max: 1 } : null,
        topK: family?.topK ? { default: null, min: 0, max: 100 } : null,
      }

  const applyPreset = (nextPreset: NonNullable<typeof preset>) => {
    setProtocol(nextPreset.protocol)
    setBaseUrl(nextPreset.baseUrl || baseUrl)
    setFamilyId(nextPreset.family)
    setThinking('default')
    setVision(nextPreset.vision)
    if (!name.trim()) setName(nextPreset.label)
    // 切换模型时清掉上一模型的覆盖值，避免把 A 的窗口带到 B 上
    setContextSize('')
    setMaxTokens('')
    setTemperature('')
    setTopP('')
    setTopK('')
  }

  const handleProviderChange = (id: string) => {
    setProviderId(id)
    setModelMode('preset')
    setModelId('')
    setModel('')
    setFamilyId('')
    setThinking('default')
    setContextSize('')
    setMaxTokens('')
    setTemperature('')
    setTopP('')
    setTopK('')
    const nextProvider = findProvider(registry, id)
    if (nextProvider) {
      setProtocol(nextProvider.defaultProtocol)
      setBaseUrl(nextProvider.baseUrls[nextProvider.defaultProtocol] || '')
    }
  }

  const handleModelChange = (id: string) => {
    setModelId(id)
    const nextPreset = provider?.models.find(m => m.model === id)
    if (!nextPreset) return
    setModel(nextPreset.model)
    applyPreset(nextPreset)
  }

  const handleProtocolChange = (next: 'anthropic' | 'openai') => {
    setProtocol(next)
    // 只有当前地址为空或仍是服务商默认地址时才跟着协议切换，避免覆盖用户自定义中转地址
    const currentIsDefault = Object.values(provider?.baseUrls || {}).includes(baseUrl.trim())
    if (provider?.baseUrls[next] && (!baseUrl.trim() || currentIsDefault)) {
      setBaseUrl(provider.baseUrls[next] || '')
    }
    // 自定义模型没选族时，按协议落到对应的通用族
    if (modelMode === 'custom' && (!familyId || familyId.startsWith('generic-'))) {
      setFamilyId(next === 'openai' ? 'generic-openai' : 'generic-anthropic')
    }
    const nextOptions = preset
      ? (preset.thinkingOptionsByProtocol?.[next] || preset.thinkingOptions)
      : thinkingOptions
    if (!nextOptions.includes(thinking)) setThinking('default')
  }

  const handleFetchContext = async () => {
    if (!baseUrl || !apiKey || !model) return
    setFetchingContext(true)
    setContextHint('')
    try {
      const url = await getBackendUrl()
      const resp = await fetch(`${url}/api/model-info`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl, apiKey, model, protocol }),
      })
      const data = await resp.json()
      if (data.success && data.contextSize) {
        setContextSize(String(data.contextSize))
        setContextHint(t('api.context_fetched', String(data.contextSize)))
      } else {
        setContextHint(data.error || t('api.context_fetch_failed'))
      }
    } catch (err) {
      setContextHint(String(err))
    } finally {
      setFetchingContext(false)
    }
  }

  const handleSubmit = () => {
    const finalModel = (modelMode === 'preset' ? modelId : model).trim()
    if (!apiKey.trim() || !finalModel) return
    const entry: LLMEntry = {
      id: editing?.id || `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      name: name.trim() || preset?.label || finalModel,
      baseUrl: baseUrl.trim(),
      apiKey: apiKey.trim(),
      model: finalModel,
      protocol,
      provider: providerId || 'generic',
      ...(effectiveFamilyId ? { family: effectiveFamilyId } : {}),
      thinking,
      // 预设模型的能力由注册表决定；只有自定义模型才需要用户声明图片能力
      ...(modelMode === 'custom' ? { vision } : {}),
      ...(toNumber(contextSize) !== undefined ? { contextSize: toNumber(contextSize) } : {}),
      ...(toNumber(maxTokens) !== undefined ? { maxTokens: toNumber(maxTokens) } : {}),
      ...(toNumber(temperature) !== undefined ? { temperature: toNumber(temperature) } : {}),
      ...(toNumber(topP) !== undefined ? { topP: toNumber(topP) } : {}),
      ...(toNumber(topK) !== undefined ? { topK: toNumber(topK) } : {}),
    }
    onSubmit(entry)
  }

  const isEdit = Boolean(editing)
  const presetContext = preset?.context
  const presetMaxOutput = preset?.maxOutput
  const presetMaxTokens = preset?.recommendedMaxTokens

  return (
    <div className="tab-content">
      <div className="llm-add-form">
        <div className="llm-add-header">
          <button className="llm-back-btn" onClick={onCancel}>
            <ChevronLeft size={16} />
          </button>
          <h3>{isEdit ? t('api.edit_llm') : t('api.add_llm')}</h3>
        </div>

        {/* 1. 服务商 */}
        <div className="config-section">
          <h3>{t('api.step_provider')}</h3>
          <select
            className="config-select"
            value={providerId}
            onChange={e => handleProviderChange(e.target.value)}
          >
            <option value="">{t('api.select_provider')}</option>
            {(registry?.providers || []).map(p => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>

        {/* 2. 模型 */}
        <div className="config-section">
          <h3>{t('api.step_model')}</h3>
          <select
            className="config-select"
            value={modelMode === 'preset' ? modelId : '__custom__'}
            onChange={e => {
              if (e.target.value === '__custom__') {
                setModelMode('custom')
                setModelId('')
                setFamilyId(protocol === 'openai' ? 'generic-openai' : 'generic-anthropic')
                return
              }
              setModelMode('preset')
              handleModelChange(e.target.value)
            }}
          >
            <option value="">{t('api.select_model')}</option>
            {(provider?.models || []).map(m => (
              <option key={m.model} value={m.model}>{m.label}</option>
            ))}
            <option value="__custom__">{t('api.use_custom_model')}</option>
          </select>

          {modelMode === 'custom' && (
            <>
              <input
                className="config-input"
                style={{ marginTop: 8 }}
                value={model}
                onChange={e => setModel(e.target.value)}
                placeholder={t('api.model_placeholder')}
              />
              <select
                className="config-select"
                style={{ marginTop: 8 }}
                value={familyId}
                onChange={e => setFamilyId(e.target.value)}
              >
                {(registry?.families || []).map(f => (
                  <option key={f.id} value={f.id}>{f.label}</option>
                ))}
              </select>
              <span className="field-hint">{t('api.model_series_hint')}</span>
            </>
          )}

          {preset && (
            <div className="preset-meta">
              <span>{preset.familyLabel}</span>
              <span>{t('api.context_value', preset.context.toLocaleString())}</span>
              {preset.vision && <span>{t('api.cap_vision')}</span>}
              {preset.toolCall && <span>{t('api.cap_tools')}</span>}
            </div>
          )}
        </div>

        {/* 协议 / 地址 */}
        <div className="config-section">
          <h3>{t('api.protocol')}</h3>
          <div className="toggle-group">
            <button className={protocol === 'anthropic' ? 'active' : ''} onClick={() => handleProtocolChange('anthropic')}>Anthropic</button>
            <button className={protocol === 'openai' ? 'active' : ''} onClick={() => handleProtocolChange('openai')}>OpenAI</button>
          </div>
        </div>

        <div className="config-field">
          <label>{t('api.llm_name')}</label>
          <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder={t('api.llm_name_placeholder')} />
        </div>

        <div className="config-field">
          <label>{t('api.base_url')}</label>
          <input type="text" value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder={t('api.base_url_placeholder')} />
        </div>

        <div className="config-field">
          <label>{t('api.api_key')}</label>
          <div className="key-row">
            <input type={showKey ? 'text' : 'password'} value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-..." />
            <button onClick={() => setShowKey(v => !v)}>{showKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
          </div>
        </div>

        {/* 3. 高级配置 */}
        <div className="advanced-block">
          <button className="advanced-toggle" onClick={() => setShowAdvanced(v => !v)}>
            {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {t('api.advanced')}
          </button>
          <p className="field-hint">{t('api.advanced_hint')}</p>

          {showAdvanced && (
            <div className="advanced-body">
              <div className="config-field">
                <label>{t('api.thinking_mode')}</label>
                <select
                  className="config-select"
                  value={thinking}
                  onChange={e => setThinking(e.target.value as ThinkingOptionId)}
                >
                  {thinkingOptions.map(option => (
                    <option key={option} value={option}>{t(THINKING_LABEL_KEYS[option] || option)}</option>
                  ))}
                </select>
                <span className="field-hint">
                  {thinkingOptions.length > 1
                    ? t('api.thinking_capability_hint', String(thinkingOptions.length - 1))
                    : t('api.thinking_fixed_hint')}
                </span>
                {preset?.thinkingNote && (
                  <span className="field-hint">{preset.thinkingNote}</span>
                )}
              </div>

              <div className="config-field">
                <label>{t('api.context_window')}</label>
                <input
                  type="number"
                  value={contextSize}
                  onChange={e => setContextSize(e.target.value)}
                  placeholder={presetContext ? String(presetContext) : t('api.follow_default')}
                />
                <button className="link-btn" onClick={handleFetchContext} disabled={fetchingContext || !baseUrl || !apiKey || !model}>
                  {fetchingContext ? <Loader2 size={12} className="spin" /> : <RefreshCw size={12} />}
                  {t('api.fetch_context')}
                </button>
                {contextHint && <span className="field-hint">{contextHint}</span>}
              </div>

              <div className="config-field">
                <label>{t('api.max_output')}</label>
                <input
                  type="number"
                  value={maxTokens}
                  onChange={e => setMaxTokens(e.target.value)}
                  placeholder={presetMaxTokens ? String(presetMaxTokens) : t('api.follow_default')}
                />
                {presetMaxOutput && (
                  <span className="field-hint">{t('api.max_output_hint', String(presetMaxOutput))}</span>
                )}
              </div>

              {modelMode === 'custom' && (
                <div className="config-field">
                  <label>{t('api.support_vision')}</label>
                  <div className="toggle-group">
                    <button className={!vision ? 'active' : ''} onClick={() => setVision(false)}>{t('api.no')}</button>
                    <button className={vision ? 'active' : ''} onClick={() => setVision(true)}>{t('api.yes')}</button>
                  </div>
                </div>
              )}

              {(sampling.temperature || sampling.topP || sampling.topK) && (
                <div className="sampling-grid">
                  {sampling.temperature && (
                    <div className="config-field">
                      <label>Temperature</label>
                      <input
                        type="number"
                        step="0.05"
                        min={sampling.temperature.min ?? undefined}
                        max={sampling.temperature.max ?? undefined}
                        value={temperature}
                        onChange={e => setTemperature(e.target.value)}
                        placeholder={sampling.temperature.default !== null ? String(sampling.temperature.default) : t('api.follow_default')}
                      />
                    </div>
                  )}
                  {sampling.topP && (
                    <div className="config-field">
                      <label>Top P</label>
                      <input
                        type="number"
                        step="0.05"
                        min={sampling.topP.min ?? undefined}
                        max={sampling.topP.max ?? undefined}
                        value={topP}
                        onChange={e => setTopP(e.target.value)}
                        placeholder={sampling.topP.default !== null ? String(sampling.topP.default) : t('api.follow_default')}
                      />
                    </div>
                  )}
                  {sampling.topK && (
                    <div className="config-field">
                      <label>Top K</label>
                      <input
                        type="number"
                        step="1"
                        min={sampling.topK.min ?? undefined}
                        max={sampling.topK.max ?? undefined}
                        value={topK}
                        onChange={e => setTopK(e.target.value)}
                        placeholder={sampling.topK.default !== null ? String(sampling.topK.default) : t('api.follow_default')}
                      />
                    </div>
                  )}
                </div>
              )}
              <span className="field-hint">{t('api.sampling_hint')}</span>
            </div>
          )}
        </div>

        <div className="config-actions">
          <button
            className="add-llm-btn primary"
            onClick={handleSubmit}
            disabled={!apiKey.trim() || !(modelMode === 'preset' ? modelId : model).trim()}
          >
            {isEdit ? <Check size={14} /> : <Plus size={14} />}
            {isEdit ? t('api.save_changes') : t('api.add_key')}
          </button>
        </div>
      </div>
    </div>
  )
}
