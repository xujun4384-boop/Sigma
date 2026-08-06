import { useState, useEffect, type ReactNode } from 'react'
import { X, Settings2, Wrench, Key, Eye, EyeOff, Plus, Trash2, Play, CheckCircle2, XCircle, Loader2, Moon, Sun, Monitor, Palette, Bot, ChevronLeft, Pencil, Check, Wallet, GripVertical } from 'lucide-react'
import type { KimiConfig, LLMEntry, SigmaConfig, SkillKeysConfig } from '../types/electron'
import type { ThemeMode } from '../App'
import { getBackendUrl, getSigmaConfig, saveSigmaConfig } from '../utils/config'
import './Sidebar.css'
import { useTranslation } from '../i18n/I18nContext'
import CustomAgentPanel from './CustomAgentPanel'

type Tab = 'api' | 'skill_keys' | 'system' | 'appearance' | 'agents'

interface SystemSettings {
  maxIterations: number
  subAgentMaxTurns: number
  backupEnabled: boolean
  notifySound: string
  language: string
}

interface SidebarProps {
  config: KimiConfig
  system: SystemSettings
  themeMode: ThemeMode
  language: string
  onSaveConfig: (config: KimiConfig) => void
  onAddLLM: (entry: LLMEntry) => void
  onUpdateLLM: (entry: LLMEntry) => void
  onRemoveLLM: (id: string) => void
  onSelectLLM: (id: string) => void
  onSaveSystem: (settings: SystemSettings) => void
  onThemeChange: (mode: ThemeMode) => void
  onLanguageChange: (lang: string) => void
}

const DEFAULT_SYSTEM: SystemSettings = { maxIterations: 30, subAgentMaxTurns: 15, backupEnabled: true, notifySound: '', language: 'en' }

export function loadSystemSettings(): SystemSettings {
  try {
    const saved = localStorage.getItem('sigma_system_settings')
    if (saved) return { ...DEFAULT_SYSTEM, ...JSON.parse(saved) }
  } catch {}
  return DEFAULT_SYSTEM
}

/** 解析当前活跃的 LLM 配置（给 Agent 面板的 AI 生成功能使用） */
export function resolveActiveLLMForAgent(config: KimiConfig): { baseUrl: string; apiKey: string; model: string; protocol: 'anthropic' | 'openai' } | null {
  if (config.activeLLMId && config.llms.length > 0) {
    const active = config.llms.find(l => l.id === config.activeLLMId)
    if (active) {
      return {
        baseUrl: active.baseUrl,
        apiKey: active.apiKey,
        model: active.model,
        protocol: active.protocol,
      }
    }
  }
  // fallback: legacy config
  if (config.baseUrl && config.apiKey && config.model) {
    return {
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      model: config.model,
      protocol: config.protocol,
    }
  }
  return null
}

export default function Sidebar({ config, system, themeMode, language, onSaveConfig, onAddLLM, onUpdateLLM, onRemoveLLM, onSelectLLM, onSaveSystem, onThemeChange, onLanguageChange }: SidebarProps) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<Tab>('api')
  const { t } = useTranslation()

  useEffect(() => {
    const handler = () => setOpen(v => !v)
    window.addEventListener('sigma-toggle-sidebar', handler)
    return () => window.removeEventListener('sigma-toggle-sidebar', handler)
  }, [])

  return (
    <>
      {/* Backdrop */}
      {open && <div className="sidebar-backdrop" onClick={() => setOpen(false)} />}

      {/* Panel */}
      <div className={`sidebar-panel ${open ? 'open' : ''}`}>
        <div className="sidebar-header">
          <h2>{t("settings.title")}</h2>
          <button className="sidebar-close" onClick={() => setOpen(false)}>
            <X size={18} />
          </button>
        </div>

        {/* Tabs */}
        <div className="sidebar-tabs">
          <button className={`sidebar-tab ${tab === 'api' ? 'active' : ''}`} onClick={() => setTab('api')}>
            <Wrench size={14} /> {t("settings.api")}
          </button>
          <button className={`sidebar-tab ${tab === 'skill_keys' ? 'active' : ''}`} onClick={() => setTab('skill_keys')}>
            <Key size={14} /> {t("settings.skill_keys")}
          </button>
          <button className={`sidebar-tab ${tab === 'system' ? 'active' : ''}`} onClick={() => setTab('system')}>
            <Settings2 size={14} /> {t("settings.system")}
          </button>
          <button className={`sidebar-tab ${tab === 'appearance' ? 'active' : ''}`} onClick={() => setTab('appearance')}>
            <Palette size={14} /> {t("settings.appearance")}
          </button>
          <button className={`sidebar-tab ${tab === 'agents' ? 'active' : ''}`} onClick={() => setTab('agents')}>
            <Bot size={14} /> {t("settings.agents")}
          </button>
        </div>

        {/* Tab Content */}
        <div className="sidebar-body">
          <div style={{ display: tab === 'api' ? 'block' : 'none' }}>
            <ApiTab config={config} onSave={onSaveConfig} onAddLLM={onAddLLM} onUpdateLLM={onUpdateLLM} onRemoveLLM={onRemoveLLM} onSelectLLM={onSelectLLM} />
          </div>
          <div style={{ display: tab === 'skill_keys' ? 'block' : 'none' }}>
            <SkillKeysTab config={config} onSave={onSaveConfig} />
          </div>
          <div style={{ display: tab === 'system' ? 'block' : 'none' }}>
            <SystemTab settings={system} onSave={onSaveSystem} />
          </div>
          <div style={{ display: tab === 'appearance' ? 'block' : 'none' }}>
            <AppearanceTab themeMode={themeMode} language={language} onThemeChange={onThemeChange} onLanguageChange={onLanguageChange} />
          </div>
          <div style={{ display: tab === 'agents' ? 'block' : 'none' }}>
            <CustomAgentPanel
              llmConfigs={config.llms}
              activeLLM={resolveActiveLLMForAgent(config)}
              activeLLMId={config.activeLLMId}
            />
          </div>
        </div>
      </div>
    </>
  )
}

// ── API Config Tab ──

function ApiTab({ config, onSave, onAddLLM, onUpdateLLM, onRemoveLLM, onSelectLLM }: {
  config: KimiConfig
  onSave: (c: KimiConfig) => void
  onAddLLM: (e: LLMEntry) => void
  onUpdateLLM: (e: LLMEntry) => void
  onRemoveLLM: (id: string) => void
  onSelectLLM: (id: string) => void
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState<KimiConfig>({ ...config })
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)
  const [llmName, setLlmName] = useState('')
  const [provider, setProvider] = useState<'generic' | 'deepseek' | 'kimi-code'>('generic')
  const [testingIds, setTestingIds] = useState<Record<string, 'testing' | 'success' | 'error'>>({})
  const [balances, setBalances] = useState<Record<string, { loading: boolean; data?: any; error?: string }>>({})
  const [view, setView] = useState<'list' | 'add' | 'edit'>('list')
  const [editingLLM, setEditingLLM] = useState<LLMEntry | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<LLMEntry | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)

  // 进入列表时自动查询一次支持余额查询的 LLM
  useEffect(() => {
    if (view !== 'list') return
    const balanceEntries = config.llms.filter(l => l.provider && l.provider !== 'generic')
    balanceEntries.forEach(entry => {
      if (!balances[entry.id]) {
        handleFetchBalance(entry)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, config.llms])

  const update = (patch: Partial<KimiConfig>) => {
    setForm(prev => ({ ...prev, ...patch }))
    setSaved(false)
  }

  const resetForm = () => {
    setForm({ ...config })
    setLlmName('')
    setProvider('generic')
    setEditingLLM(null)
    setShowKey(false)
  }

  const openAdd = () => { resetForm(); setView('add') }
  const openEdit = (entry: LLMEntry, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingLLM(entry)
    setLlmName(entry.name)
    setProvider(entry.provider || 'generic')
    setForm(prev => ({ ...prev, baseUrl: entry.baseUrl, apiKey: entry.apiKey, model: entry.model, protocol: entry.protocol }))
    setView('edit')
  }
  const backToList = () => { setView('list'); setEditingLLM(null) }

  const handleAddLLM = () => {
    if (!form.apiKey || !form.model) return
    const entry: LLMEntry = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      name: llmName.trim() ? llmName.trim() : `${form.protocol === 'anthropic' ? 'Anthropic' : 'OpenAI'} - ${form.model}`,
      baseUrl: form.baseUrl,
      apiKey: form.apiKey,
      model: form.model,
      protocol: form.protocol,
      provider,
    }
    onAddLLM(entry)
    backToList()
  }

  const handleUpdateLLM = () => {
    if (!editingLLM || !form.apiKey || !form.model) return
    const entry: LLMEntry = {
      ...editingLLM,
      name: llmName.trim() ? llmName.trim() : `${form.protocol === 'anthropic' ? 'Anthropic' : 'OpenAI'} - ${form.model}`,
      baseUrl: form.baseUrl,
      apiKey: form.apiKey,
      model: form.model,
      protocol: form.protocol,
      provider,
    }
    onUpdateLLM(entry)
    backToList()
  }

  const formatResetIn = (resetTime?: string) => {
    if (!resetTime) return ''
    const diff = new Date(resetTime).getTime() - Date.now()
    if (diff <= 0) return '即将重置'
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    const parts: string[] = []
    if (days > 0) parts.push(`${days}d`)
    if (hours > 0) parts.push(`${hours}h`)
    if (minutes > 0) parts.push(`${minutes}min`)
    return parts.join(' ') + '后重置'
  }

  const UsageBlock = ({ title, detail }: { title: string; detail?: any }) => {
    if (!detail) return null
    const limit = Number(detail.limit ?? 0)
    const used = Number(detail.used ?? 0)
    const usedPercent = limit > 0 ? Math.min(100, Math.max(0, (used / limit) * 100)) : 0
    let colorClass = 'good'
    if (usedPercent >= 80) colorClass = 'critical'
    else if (usedPercent >= 50) colorClass = 'warning'
    return (
      <div className="usage-block">
        <div className="usage-block-header">
          <span className="usage-block-title">{title}</span>
          <span className={`usage-block-percent ${colorClass}`}>{Math.round(usedPercent)}%</span>
          <span className="usage-block-reset">{formatResetIn(detail.resetTime)}</span>
        </div>
        <div className="usage-bar-track">
          <div className={`usage-bar-fill ${colorClass}`} style={{ width: `${usedPercent}%` }} />
        </div>
      </div>
    )
  }

  const handleFetchBalance = async (entry: LLMEntry, e?: React.MouseEvent) => {
    e?.stopPropagation()
    if (!entry.provider || entry.provider === 'generic') return
    setBalances(prev => ({ ...prev, [entry.id]: { loading: true } }))
    try {
      const baseUrl = await getBackendUrl()
      const resp = await fetch(`${baseUrl}/api/llm-balance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: entry.provider, apiKey: entry.apiKey, baseUrl: entry.baseUrl }),
      })
      const data = await resp.json()
      if (data.success) {
        setBalances(prev => ({ ...prev, [entry.id]: { loading: false, data: data.balance } }))
      } else {
        setBalances(prev => ({ ...prev, [entry.id]: { loading: false, error: data.error || 'Failed' } }))
      }
    } catch (err: any) {
      setBalances(prev => ({ ...prev, [entry.id]: { loading: false, error: err.message || 'Network error' } }))
    }
  }

  const formatBalance = (entry: LLMEntry, balance: any): ReactNode => {
    if (!balance) return ''
    if (entry.provider === 'deepseek' && Array.isArray(balance.balance_infos)) {
      const infos = balance.balance_infos.filter((info: any) => info.currency !== 'USD')
      return infos.map((info: any, idx: number) => {
        const amount = Number(info.total_balance ?? 0)
        const isLowCNY = info.currency === 'CNY' && amount < 20
        return (
          <span key={idx}>
            <span className={isLowCNY ? 'balance-low' : ''}>{info.currency || ''} {info.total_balance || ''}</span>
            {idx < infos.length - 1 ? ' / ' : ''}
          </span>
        )
      })
    }
    if (entry.provider === 'kimi-code') {
      const weekly = balance.usage
      const short = Array.isArray(balance.limits) ? balance.limits[0]?.detail : null
      const parts: string[] = []
      if (weekly && weekly.remaining != null) {
        parts.push(`W ${weekly.remaining}/${weekly.limit}`)
      }
      if (short && short.remaining != null) {
        parts.push(`5h ${short.remaining}/${short.limit}`)
      }
      return parts.join(' · ') || ''
    }
    return ''
  }

  const handleTestLLM = async (entry: LLMEntry, e: React.MouseEvent) => {
    e.stopPropagation()
    setTestingIds(prev => ({ ...prev, [entry.id]: 'testing' }))
    try {
      const baseUrl = await getBackendUrl()
      const resp = await fetch(`${baseUrl}/api/test-llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseUrl: entry.baseUrl,
          apiKey: entry.apiKey,
          model: entry.model,
          protocol: entry.protocol,
        }),
      })
      const data = await resp.json()
      setTestingIds(prev => ({ ...prev, [entry.id]: data.success ? 'success' : 'error' }))
      // 3 秒后清除状态
      setTimeout(() => {
        setTestingIds(prev => {
          const next = { ...prev }
          delete next[entry.id]
          return next
        })
      }, 3000)
    } catch {
      setTestingIds(prev => ({ ...prev, [entry.id]: 'error' }))
    }
  }

  const handleDragStart = (e: React.DragEvent, id: string) => {
    e.dataTransfer.setData('text/plain', id)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleDragOver = (e: React.DragEvent, id: string) => {
    e.preventDefault()
    if (dragOverId !== id) setDragOverId(id)
  }

  const handleDrop = (e: React.DragEvent, targetId: string) => {
    e.preventDefault()
    e.stopPropagation()
    const sourceId = e.dataTransfer.getData('text/plain')
    setDragOverId(null)
    if (!sourceId || sourceId === targetId) return
    const sourceIndex = config.llms.findIndex(l => l.id === sourceId)
    const targetIndex = config.llms.findIndex(l => l.id === targetId)
    if (sourceIndex === -1 || targetIndex === -1) return
    const newLLMs = [...config.llms]
    const [moved] = newLLMs.splice(sourceIndex, 1)
    newLLMs.splice(targetIndex, 0, moved)
    onSave({ ...config, llms: newLLMs })
  }

  const handleDragEnd = () => {
    setDragOverId(null)
  }

  // 默认显示已保存 LLM 列表
  if (view === 'list') {
    return (
      <div className="tab-content">
        <div className="llm-list-section">
          <div className="llm-list-header">
            <h3>{t("api.saved_llms")} ({config.llms.length})</h3>
            <button className="add-llm-btn" onClick={openAdd}>
              <Plus size={14} /> {t("api.add_llm")}
            </button>
          </div>
          {config.llms.length === 0 ? (
            <div className="llm-empty">
              <Bot size={32} />
              <p>{t("api.no_llms")}</p>
              <p className="llm-empty-hint">{t("api.no_llms_hint")}</p>
            </div>
          ) : (
            <div className="llm-list">
              {config.llms.map(entry => (
                <div
                  key={entry.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, entry.id)}
                  onDragOver={(e) => handleDragOver(e, entry.id)}
                  onDrop={(e) => handleDrop(e, entry.id)}
                  onDragEnd={handleDragEnd}
                  className={`llm-card ${config.activeLLMId === entry.id ? 'active' : ''} ${dragOverId === entry.id ? 'drag-over' : ''}`}
                  onClick={() => onSelectLLM(entry.id)}
                >
                  <div className="llm-card-header">
                    <span className="llm-drag-handle" title={t("api.drag_sort")}>
                      <GripVertical size={14} />
                    </span>
                    <span className="llm-card-name">{entry.name}</span>
                    {config.activeLLMId === entry.id && <span className="llm-card-badge">{t("api.active")}</span>}
                  </div>
                  <div className="llm-card-detail">
                    {entry.protocol === 'anthropic' ? 'Anthropic' : 'OpenAI'} &middot; {entry.model}
                  </div>
                  <div className="llm-card-detail llm-card-url">{entry.baseUrl}</div>
                  {entry.provider && entry.provider !== 'generic' && (
                    <div
                      className={`llm-card-balance ${balances[entry.id]?.loading ? 'loading' : ''}`}
                      onClick={(e) => handleFetchBalance(entry, e)}
                      title={t("api.refresh_balance")}
                    >
                      {balances[entry.id]?.loading ? (
                        <Loader2 size={12} className="spin" />
                      ) : balances[entry.id]?.error ? (
                        <>
                          <Wallet size={12} />
                          <span className="balance-error">{balances[entry.id].error}</span>
                        </>
                      ) : entry.provider === 'kimi-code' && balances[entry.id]?.data ? (
                        <div className="usage-bars">
                          <UsageBlock title="本周用量" detail={balances[entry.id].data?.usage} />
                          <UsageBlock title="频限明细" detail={balances[entry.id].data?.limits?.[0]?.detail} />
                        </div>
                      ) : balances[entry.id]?.data ? (
                        <>
                          <Wallet size={12} />
                          <span>{formatBalance(entry, balances[entry.id].data)}</span>
                        </>
                      ) : (
                        <>
                          <Wallet size={12} />
                          <span>{t("api.check_balance")}</span>
                        </>
                      )}
                    </div>
                  )}
                  <div className="llm-card-actions">
                    <button
                      className={`llm-card-test ${testingIds[entry.id] || ''}`}
                      onClick={(e) => handleTestLLM(entry, e)}
                      title={t("api.test_connection")}
                      disabled={testingIds[entry.id] === 'testing'}
                    >
                      {testingIds[entry.id] === 'testing' ? <Loader2 size={14} className="spin" /> :
                       testingIds[entry.id] === 'success' ? <CheckCircle2 size={14} /> :
                       testingIds[entry.id] === 'error' ? <XCircle size={14} /> :
                       <Play size={14} />}
                    </button>
                    <button
                      className="llm-card-edit"
                      onClick={(e) => openEdit(entry, e)}
                      title={t("api.edit")}
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      className="llm-card-delete"
                      onClick={e => { e.stopPropagation(); setDeleteTarget(entry) }}
                      title={t("api.remove")}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 删除确认弹窗 */}
        {deleteTarget && (
          <div className="confirm-overlay" onClick={() => setDeleteTarget(null)}>
            <div className="confirm-modal" onClick={e => e.stopPropagation()}>
              <div className="confirm-icon">
                <Trash2 size={24} />
              </div>
              <p className="confirm-title">{t("api.remove_confirm_title")}</p>
              <p className="confirm-message">{t("api.remove_confirm", deleteTarget.name)}</p>
              <div className="confirm-actions">
                <button className="confirm-cancel" onClick={() => setDeleteTarget(null)}>
                  {t("api.cancel")}
                </button>
                <button className="confirm-delete" onClick={() => { onRemoveLLM(deleteTarget.id); setDeleteTarget(null) }}>
                  {t("api.confirm_delete")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // 添加 / 编辑 LLM 表单
  const isEdit = view === 'edit'
  return (
    <div className="tab-content">
      <div className="llm-add-form">
        <div className="llm-add-header">
          <button className="llm-back-btn" onClick={backToList}>
            <ChevronLeft size={16} />
          </button>
          <h3>{isEdit ? t("api.edit_llm") : t("api.add_llm")}</h3>
        </div>

        <div className="config-section">
          <h3>{t("api.protocol")}</h3>
          <div className="toggle-group">
            <button className={form.protocol === 'anthropic' ? 'active' : ''} onClick={() => update({ protocol: 'anthropic' })}>Anthropic</button>
            <button className={form.protocol === 'openai' ? 'active' : ''} onClick={() => update({ protocol: 'openai' })}>OpenAI</button>
          </div>
        </div>

        <div className="config-section">
          <h3>{t("api.provider")}</h3>
          <div className="toggle-group">
            <button className={provider === 'generic' ? 'active' : ''} onClick={() => setProvider('generic')}>{t("api.provider_generic")}</button>
            <button className={provider === 'deepseek' ? 'active' : ''} onClick={() => setProvider('deepseek')}>{t("api.provider_deepseek")}</button>
            <button className={provider === 'kimi-code' ? 'active' : ''} onClick={() => setProvider('kimi-code')}>{t("api.provider_kimi_code")}</button>
          </div>
        </div>

        <div className="config-field">
          <label>{t("api.llm_name")}</label>
          <input type="text" value={llmName} onChange={e => setLlmName(e.target.value)} placeholder={t("api.llm_name_placeholder")} />
        </div>

        <div className="config-field">
          <label>{t("api.base_url")}</label>
          <input type="text" value={form.baseUrl} onChange={e => update({ baseUrl: e.target.value })} placeholder={t("api.base_url_placeholder")} />
        </div>

        <div className="config-field">
          <label>{t("api.model")}</label>
          <input type="text" value={form.model} onChange={e => update({ model: e.target.value })} placeholder={t("api.model_placeholder")} />
        </div>

        <div className="config-field">
          <label>{t("api.api_key")}</label>
          <div className="key-row">
            <input type={showKey ? 'text' : 'password'} value={form.apiKey} onChange={e => update({ apiKey: e.target.value })} placeholder="sk-..." />
            <button onClick={() => setShowKey(v => !v)}>{showKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
          </div>
        </div>

        <div className="key-preview">
          <code>{form.apiKey ? `${form.apiKey.slice(0, 12)}...${form.apiKey.slice(-4)}` : t("api.not_set")}</code>
        </div>

        <div className="config-actions">
          <button className="add-llm-btn primary" onClick={isEdit ? handleUpdateLLM : handleAddLLM} disabled={!form.apiKey || !form.model}>
            {isEdit ? <Check size={14} /> : <Plus size={14} />}
            {isEdit ? t("api.save_changes") : t("api.add_key")}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Skill Keys Tab ──

function SkillKeysTab({ config, onSave }: { config: KimiConfig; onSave: (c: KimiConfig) => void }) {
  const { t } = useTranslation()
  const [form, setForm] = useState<KimiConfig>({ ...config })
  const [saved, setSaved] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; error?: string } | null>(null)
  const [showWsKey, setShowWsKey] = useState(false)
  const [showTavilyKey, setShowTavilyKey] = useState(false)
  const [showImgKey, setShowImgKey] = useState(false)
  const [showVisionKey, setShowVisionKey] = useState(false)
  const [showWechatKey, setShowWechatKey] = useState(false)
  const [showRelayKey, setShowRelayKey] = useState(false)
  const [showFengniaoKey, setShowFengniaoKey] = useState(false)
  const [showFlyaiKey, setShowFlyaiKey] = useState(false)

  const updateSkillKeys = (patch: Partial<SkillKeysConfig>) => {
    setForm(prev => ({ ...prev, skillKeys: { ...prev.skillKeys, ...patch } }))
    setSaved(false)
  }

  const handleSave = () => {
    onSave(form)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleTestVision = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const sk = form.skillKeys || {}
      const baseUrl = await getBackendUrl()
      const resp = await fetch(`${baseUrl}/api/test-vision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          apiKey: sk.visionApiKey || '',
          model: sk.visionModel || 'kimi-for-coding',
          baseUrl: sk.visionBaseUrl || 'https://api.moonshot.cn/anthropic',
        }),
      })
      const data = await resp.json()
      setTestResult(data)
    } catch (e: any) {
      setTestResult({ success: false, error: e.message || 'Network error' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="tab-content">
      {/* ── Web Search ── */}
      <div className="config-section">
        <h3>{t("skill_keys.web_search")}</h3>
        <p className="section-desc">{t("skill_keys.web_search_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.search_provider")}</label>
        <div className="toggle-group">
          <button
            className={(form.skillKeys?.webSearchProvider || 'kimi') === 'kimi' ? 'active' : ''}
            onClick={() => updateSkillKeys({ webSearchProvider: 'kimi' })}
          >Kimi</button>
          <button
            className={(form.skillKeys?.webSearchProvider || 'kimi') === 'tavily' ? 'active' : ''}
            onClick={() => updateSkillKeys({ webSearchProvider: 'tavily' })}
          >Tavily</button>
          <button
            className={(form.skillKeys?.webSearchProvider || 'kimi') === 'custom' ? 'active' : ''}
            onClick={() => updateSkillKeys({ webSearchProvider: 'custom' })}
          >Custom</button>
        </div>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.web_search_api_key")}</label>
        <div className="key-row">
          <input
            type={showWsKey ? 'text' : 'password'}
            value={form.skillKeys?.webSearchApiKey || ''}
            onChange={e => updateSkillKeys({ webSearchApiKey: e.target.value })}
            placeholder={
              (form.skillKeys?.webSearchProvider || 'kimi') === 'kimi' ? 'sk-...' :
              (form.skillKeys?.webSearchProvider || 'kimi') === 'tavily' ? 'tvly-...' :
              'Your API Key...'
            }
          />
          <button onClick={() => setShowWsKey(v => !v)}>{showWsKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
        <span className="field-hint">
          Kimi: <a href="https://platform.kimi.com" target="_blank" rel="noopener">platform.kimi.com</a>
          {' | '}Tavily: <a href="https://tavily.com" target="_blank" rel="noopener">tavily.com</a>
        </span>
      </div>

      {(form.skillKeys?.webSearchProvider || 'kimi') === 'custom' && (
        <div className="config-field">
          <label>{t("skill_keys.web_search_base_url")}</label>
          <input
            type="text"
            value={form.skillKeys?.webSearchBaseUrl || ''}
            onChange={e => updateSkillKeys({ webSearchBaseUrl: e.target.value })}
            placeholder="https://api.example.com/v1/search"
          />
        </div>
      )}

      {/* ── Image Search ── */}
      <div className="config-section" style={{ marginTop: 20 }}>
        <h3>{t("skill_keys.image_search")}</h3>
        <p className="section-desc">{t("skill_keys.image_search_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.tavily_api_key")}</label>
        <div className="key-row">
          <input
            type={showTavilyKey ? 'text' : 'password'}
            value={form.skillKeys?.tavilyApiKey || ''}
            onChange={e => updateSkillKeys({ tavilyApiKey: e.target.value })}
            placeholder="tvly-..."
          />
          <button onClick={() => setShowTavilyKey(v => !v)}>{showTavilyKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
        <span className="field-hint">
          {t("skill_keys.tavily_register")}
        </span>
      </div>

      {/* ── Image Generation ── */}
      <div className="config-section" style={{ marginTop: 20 }}>
        <h3>{t("skill_keys.image_gen")}</h3>
        <p className="section-desc">{t("skill_keys.image_gen_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.image_gen_api_key")}</label>
        <div className="key-row">
          <input
            type={showImgKey ? 'text' : 'password'}
            value={form.skillKeys?.imageGenApiKey || ''}
            onChange={e => updateSkillKeys({ imageGenApiKey: e.target.value })}
            placeholder={t("skill_keys.image_gen_api_key_placeholder")}
          />
          <button onClick={() => setShowImgKey(v => !v)}>{showImgKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.image_gen_base_url")}</label>
        <input
          type="text"
          value={form.skillKeys?.imageGenBaseUrl || ''}
          onChange={e => updateSkillKeys({ imageGenBaseUrl: e.target.value })}
          placeholder="https://ark.cn-beijing.volces.com/api/v3"
        />
        <span className="field-hint">{t("skill_keys.image_gen_default")}</span>
      </div>

      {/* ── Vision (PDF OCR) ── */}
      <div className="config-section" style={{ marginTop: 20 }}>
        <h3>{t("skill_keys.vision_ocr")}</h3>
        <p className="section-desc">
          {t("skill_keys.vision_desc")}
        </p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.vision_api_key")}</label>
        <div className="key-row">
          <input
            type={showVisionKey ? 'text' : 'password'}
            value={form.skillKeys?.visionApiKey || ''}
            onChange={e => updateSkillKeys({ visionApiKey: e.target.value })}
            placeholder="支持视觉的 API Key（如 Kimi）..."
          />
          <button onClick={() => setShowVisionKey(v => !v)}>{showVisionKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.vision_model")}</label>
        <input
          type="text"
          value={form.skillKeys?.visionModel || ''}
          onChange={e => updateSkillKeys({ visionModel: e.target.value })}
          placeholder="kimi-for-coding"
        />
        <span className="field-hint">{t("skill_keys.vision_model_hint")}</span>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.vision_base_url")}</label>
        <input
          type="text"
          value={form.skillKeys?.visionBaseUrl || ''}
          onChange={e => updateSkillKeys({ visionBaseUrl: e.target.value })}
          placeholder="https://api.moonshot.cn/anthropic"
        />
        <span className="field-hint">{t("skill_keys.vision_url_hint")}</span>
      </div>

      <div className="config-field">
        <button className="test-btn" onClick={handleTestVision} disabled={testing}>
          {testing ? t("api.testing") : t("skill_keys.test_vision")}
        </button>
        {testResult && (
          <span className={`test-result ${testResult.success ? 'success' : 'fail'}`}>
            {testResult.success ? 'OK' : `Failed: ${testResult.error}`}
          </span>
        )}
      </div>

      <div className="config-section">
        <h3>{t("skill_keys.wechat")}</h3>
        <p className="section-desc">{t("skill_keys.wechat_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.wechat_appid")}</label>
        <input
          type="text"
          value={form.skillKeys?.wechatAppId || ''}
          onChange={e => updateSkillKeys({ wechatAppId: e.target.value })}
          placeholder={t("skill_keys.wechat_appid_placeholder")}
        />
      </div>

      <div className="config-field">
        <label>{t("skill_keys.wechat_appsecret")}</label>
        <div className="key-row">
          <input
            type={showWechatKey ? 'text' : 'password'}
            value={form.skillKeys?.wechatAppSecret || ''}
            onChange={e => updateSkillKeys({ wechatAppSecret: e.target.value })}
            placeholder={t("skill_keys.wechat_appsecret_placeholder")}
          />
          <button onClick={() => setShowWechatKey(v => !v)}>{showWechatKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
      </div>

      <div className="config-section">
        <h3>{t("skill_keys.wechat_relay")}</h3>
        <p className="section-desc">{t("skill_keys.wechat_relay_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.wechat_relay_url")}</label>
        <input
          type="text"
          value={form.skillKeys?.wechatRelayUrl || ''}
          onChange={e => updateSkillKeys({ wechatRelayUrl: e.target.value })}
          placeholder={t("skill_keys.wechat_relay_url_placeholder")}
        />
      </div>

      <div className="config-field">
        <label>{t("skill_keys.wechat_relay_key")}</label>
        <div className="key-row">
          <input
            type={showRelayKey ? 'text' : 'password'}
            value={form.skillKeys?.wechatRelayKey || ''}
            onChange={e => updateSkillKeys({ wechatRelayKey: e.target.value })}
            placeholder={t("skill_keys.wechat_relay_key_placeholder")}
          />
          <button onClick={() => setShowRelayKey(v => !v)}>{showRelayKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
      </div>

      <div className="config-section">
        <h3>{t("skill_keys.fengniao")}</h3>
        <p className="section-desc">{t("skill_keys.fengniao_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.fengniao_api_key")}</label>
        <div className="key-row">
          <input
            type={showFengniaoKey ? 'text' : 'password'}
            value={form.skillKeys?.fengniaoApiKey || ''}
            onChange={e => updateSkillKeys({ fengniaoApiKey: e.target.value })}
            placeholder="FN_API_KEY"
          />
          <button onClick={() => setShowFengniaoKey(v => !v)}>{showFengniaoKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
      </div>

      <div className="config-section">
        <h3>{t("skill_keys.flyai")}</h3>
        <p className="section-desc">{t("skill_keys.flyai_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("skill_keys.flyai_api_key")}</label>
        <div className="key-row">
          <input
            type={showFlyaiKey ? 'text' : 'password'}
            value={form.skillKeys?.flyaiApiKey || ''}
            onChange={e => updateSkillKeys({ flyaiApiKey: e.target.value })}
            placeholder="sk-..."
          />
          <button onClick={() => setShowFlyaiKey(v => !v)}>{showFlyaiKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
      </div>

      <button className="save-btn" onClick={handleSave}>
        {saved ? t("settings.saved") : t("settings.save")}
      </button>
    </div>
  )
}

// ── Appearance Tab ──

function AppearanceTab({ themeMode, language, onThemeChange, onLanguageChange }: { themeMode: ThemeMode; language: string; onThemeChange: (mode: ThemeMode) => void; onLanguageChange: (lang: string) => void }) {
  const { t } = useTranslation()
  return (
    <div className="tab-content">
      <div className="config-section">
        <h3>{t("appearance.theme")}</h3>
        <p className="section-desc">{t("appearance.theme_desc")}</p>
      </div>

      <div className="theme-toggle-group">
        <button
          className={`theme-btn ${themeMode === 'dark' ? 'active' : ''}`}
          onClick={() => onThemeChange('dark')}
          title={t("appearance.dark")}
        >
          <Moon size={24} />
          <span>{t("appearance.dark")}</span>
        </button>
        <button
          className={`theme-btn ${themeMode === 'light' ? 'active' : ''}`}
          onClick={() => onThemeChange('light')}
          title={t("appearance.light")}
        >
          <Sun size={24} />
          <span>{t("appearance.light")}</span>
        </button>
        <button
          className={`theme-btn ${themeMode === 'auto' ? 'active' : ''}`}
          onClick={() => onThemeChange('auto')}
          title={t("appearance.auto")}
        >
          <Monitor size={24} />
          <span>{t("appearance.auto")}</span>
        </button>
      </div>

      <div className="config-section" style={{ marginTop: '16px' }}>
        <h3>{t("appearance.language")}</h3>
        <p className="section-desc">{t("appearance.language_desc")}</p>
      </div>

      <div className="theme-toggle-group">
        <button
          className={`theme-btn ${language === 'en' ? 'active' : ''}`}
          onClick={() => onLanguageChange('en')}
        >
          <span>{t("appearance.en")}</span>
        </button>
        <button
          className={`theme-btn ${language === 'zh' ? 'active' : ''}`}
          onClick={() => onLanguageChange('zh')}
        >
          <span>{t("appearance.zh")}</span>
        </button>
      </div>
    </div>
  )
}

// ── System Settings Tab ──

function SystemTab({ settings, onSave }: { settings: SystemSettings; onSave: (s: SystemSettings) => void }) {
  const { t } = useTranslation()
  const [form, setForm] = useState<SystemSettings>({ ...settings })
  const [saved, setSaved] = useState(false)
  const [sigmaConfig, setSigmaConfig] = useState<SigmaConfig>({ backendPort: 8765, frontendPort: 5173 })
  const [configLoaded, setConfigLoaded] = useState(false)
  const [sounds, setSounds] = useState<{ name: string; path: string }[]>([])
  const [previewing, setPreviewing] = useState(false)

  useEffect(() => {
    getSigmaConfig().then(cfg => {
      setSigmaConfig(cfg)
      setConfigLoaded(true)
    })
  }, [])

  useEffect(() => {
    if (window.electronAPI?.getSystemSounds) {
      window.electronAPI.getSystemSounds().then(s => setSounds(s))
    }
  }, [])

  const update = (patch: Partial<SystemSettings>) => {
    setForm(prev => ({ ...prev, ...patch }))
    setSaved(false)
  }

  const updatePort = (patch: Partial<SigmaConfig>) => {
    setSigmaConfig(prev => ({ ...prev, ...patch }))
    setSaved(false)
  }

  const handleSave = async () => {
    onSave(form)
    await saveSigmaConfig(sigmaConfig)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="tab-content">
      <div className="config-section">
        <h3>{t("system.tool_loop")}</h3>
        <p className="section-desc">{t("system.tool_loop_desc")}</p>
      </div>

      <div className="config-field">
        <label>{t("system.max_iterations")}</label>
        <input
          type="number"
          min={1}
          max={30}
          value={form.maxIterations}
          onChange={e => update({ maxIterations: parseInt(e.target.value) || 10 })}
        />
        <span className="field-hint">
          {t("system.max_iterations_hint")}
        </span>
      </div>

      <div className="config-field">
        <label>{t("system.sub_agent_turns")}</label>
        <input
          type="number"
          min={1}
          max={30}
          value={form.subAgentMaxTurns}
          onChange={e => update({ subAgentMaxTurns: parseInt(e.target.value) || 8 })}
        />
        <span className="field-hint">
          {t("system.sub_agent_turns_hint")}
        </span>
      </div>

      <div className="config-section" style={{ marginTop: 20 }}>
        <h3>{t("system.doc_editing")}</h3>
      </div>

      <div className="config-field config-field-toggle">
        <div className="toggle-label-row">
          <label>{t("system.auto_backup")}</label>
          <button
            className={`toggle-switch ${form.backupEnabled ? 'on' : 'off'}`}
            onClick={() => update({ backupEnabled: !form.backupEnabled })}
          >
            <span className="toggle-knob" />
          </button>
        </div>
        <span className="field-hint">
          {t("system.auto_backup_hint")}
        </span>
      </div>

      <div className="config-section" style={{ marginTop: 20 }}>
        <h3>{t("system.notification")}</h3>
        <p className="section-desc">
          {t("system.notification_hint")}
        </p>
      </div>

      {sounds.length > 0 && (
        <div className="config-field">
          <label>{t("system.alert_sound")}</label>
          <div className="key-row">
            <select
              className="sound-select"
              value={form.notifySound || ''}
              onChange={e => update({ notifySound: e.target.value })}
            >
              <option value="">{t("system.none")}</option>
              {sounds.map(s => (
                <option key={s.path} value={s.path}>{s.name}</option>
              ))}
            </select>
            <button
              className="test-btn"
              onClick={async () => {
                if (!form.notifySound || previewing) return
                setPreviewing(true)
                try {
                  await window.electronAPI?.previewSound(form.notifySound)
                } catch {}
                setPreviewing(false)
              }}
              disabled={!form.notifySound || previewing}
              title="Preview sound"
            >
              {previewing ? '...' : t("system.play")}
            </button>
          </div>
          <span className="field-hint">
            Select a system sound to play when notifications appear. Click Play to preview.
          </span>
        </div>
      )}

      <div className="config-section" style={{ marginTop: 20 }}>
        <h3>{t("system.ports")}</h3>
        <p className="section-desc">{t("system.ports_hint")}</p>
      </div>

      <div className="config-field">
        <label>{t("system.backend_port")}</label>
        <input
          type="number"
          min={1024}
          max={65535}
          value={sigmaConfig.backendPort}
          onChange={e => updatePort({ backendPort: parseInt(e.target.value) || 8765 })}
          disabled={!configLoaded}
        />
        <span className="field-hint">{t("system.backend_port_hint")}</span>
      </div>

      <div className="config-field">
        <label>{t("system.frontend_port")}</label>
        <input
          type="number"
          min={1024}
          max={65535}
          value={sigmaConfig.frontendPort}
          onChange={e => updatePort({ frontendPort: parseInt(e.target.value) || 5173 })}
          disabled={!configLoaded}
        />
        <span className="field-hint">{t("system.frontend_port_hint")}</span>
      </div>

      <button className="save-btn" onClick={handleSave}>
        {saved ? t("settings.saved") : t("settings.save")}
      </button>
    </div>
  )
}
