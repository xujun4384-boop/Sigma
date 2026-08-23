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

const DEFAULT_SYSTEM: SystemSettings = { maxIterations: 30, subAgentMaxTurns: 15, backupEnabled: true, notifySound: '', language: 'zh' }

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
  const [provider, setProvider] = useState<'generic' | 'deepseek' | 'kimi-code' | 'minimax'>('generic')
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
      ...(provider === 'minimax' ? { thinking: 'enabled' as const, contextSize: 1_000_000, maxTokens: 32768, temperature: 1.0, topP: 0.95 } : {}),
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
      ...(provider === 'minimax' ? { thinking: 'enabled' as const, contextSize: 1_000_000, maxTokens: 32768, temperature: 1.0, topP: 0.95 } : {}),
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
                      ) : entry.provider === 'minimax' && balances[entry.id]?.data ? (
                        <div className="usage-bars">
                          {(() => {
                            const list: any[] = Array.isArray(balances[entry.id].data?.model_remains) ? balances[entry.id].data.model_remains : []
                            const pick = (pred: (m: any) => boolean) => list.find(pred)
                            const row =
                              pick(m => typeof m?.model_name === 'string' && /minimax-m/i.test(m.model_name)) ||
                              pick(m => m?.model_name === 'general') ||
                              list[0] ||
                              null
                            if (!row) return null
                            const toDetail = (pct: any, ms: any) => {
                              const p = Number(pct)
                              const used = Number.isFinite(p) ? Math.max(0, Math.min(100, 100 - p)) : 0
                              const remain = Number(ms)
                              const resetTime = Number.isFinite(remain) ? new Date(Date.now() + remain).toISOString() : undefined
                              return { limit: 100, used, resetTime }
                            }
                            return (
                              <>
                                <UsageBlock title="5小时窗口" detail={toDetail(row.current_interval_remaining_percent, row.remains_time)} />
                                <UsageBlock title="本周用量" detail={toDetail(row.current_weekly_remaining_percent, row.weekly_remains_time)} />
                              </>
                            )
                          })()}
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
            <button className={provider === 'minimax' ? 'active' : ''} onClick={() => setProvider('minimax')}>{t("api.provider_minimax")}</button>
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

type SkillFieldType = 'text' | 'password' | 'toggle'

interface SkillFieldDef {
  key: keyof SkillKeysConfig
  type: SkillFieldType
  labelKey: string
  options?: { value: string; label: string }[]
  placeholder?: string | ((sk: SkillKeysConfig) => string)
  hintKey?: string
  visibleIf?: (sk: SkillKeysConfig) => boolean
}

interface SkillTestDef {
  labelKey: string
  endpoint: string
  buildBody: (sk: SkillKeysConfig) => Record<string, unknown>
}

interface SkillDef {
  id: string
  titleKey: string
  descKey: string
  requiredKeys: (keyof SkillKeysConfig)[]
  fields: SkillFieldDef[]
  test?: SkillTestDef
}

const SKILL_DEFS: SkillDef[] = [
  {
    id: 'web_search',
    titleKey: 'skill_keys.web_search',
    descKey: 'skill_keys.web_search_desc',
    requiredKeys: ['webSearchApiKey'],
    fields: [
      {
        key: 'webSearchProvider',
        type: 'toggle',
        labelKey: 'skill_keys.search_provider',
        options: [
          { value: 'kimi', label: 'Kimi' },
          { value: 'tavily', label: 'Tavily' },
          { value: 'custom', label: 'Custom' },
        ],
      },
      {
        key: 'webSearchApiKey',
        type: 'password',
        labelKey: 'skill_keys.web_search_api_key',
        placeholder: (sk) => (sk.webSearchProvider === 'kimi' ? 'sk-...' : sk.webSearchProvider === 'tavily' ? 'tvly-...' : 'Your API Key...'),
      },
      {
        key: 'webSearchBaseUrl',
        type: 'text',
        labelKey: 'skill_keys.web_search_base_url',
        placeholder: 'https://api.example.com/v1/search',
        visibleIf: (sk) => sk.webSearchProvider === 'custom',
      },
    ],
  },
  {
    id: 'image_search',
    titleKey: 'skill_keys.image_search',
    descKey: 'skill_keys.image_search_desc',
    requiredKeys: ['tavilyApiKey'],
    fields: [
      { key: 'tavilyApiKey', type: 'password', labelKey: 'skill_keys.tavily_api_key', placeholder: 'tvly-...', hintKey: 'skill_keys.tavily_register' },
    ],
  },
  {
    id: 'image_gen',
    titleKey: 'skill_keys.image_gen',
    descKey: 'skill_keys.image_gen_desc',
    requiredKeys: [],
    fields: [
      {
        key: 'imageGenProvider',
        type: 'toggle',
        labelKey: 'skill_keys.image_gen_provider',
        options: [
          { value: 'ark', label: '火山 ARK' },
          { value: 'minimax', label: 'MiniMax' },
        ],
      },
      {
        key: 'imageArkApiKey',
        type: 'password',
        labelKey: 'skill_keys.image_ark_api_key',
        placeholder: 'ARK API key',
        visibleIf: sk => (sk.imageGenProvider || 'ark') === 'ark',
      },
      {
        key: 'imageArkBaseUrl',
        type: 'text',
        labelKey: 'skill_keys.image_ark_base_url',
        placeholder: 'https://ark.cn-beijing.volces.com/api/v3',
        visibleIf: sk => (sk.imageGenProvider || 'ark') === 'ark',
      },
      {
        key: 'imageArkModel',
        type: 'text',
        labelKey: 'skill_keys.image_ark_model',
        placeholder: 'doubao-seedream-4-5-251128',
        visibleIf: sk => (sk.imageGenProvider || 'ark') === 'ark',
      },
      {
        key: 'imageMinimaxApiKey',
        type: 'password',
        labelKey: 'skill_keys.image_minimax_api_key',
        placeholder: 'MiniMax API key',
        visibleIf: sk => sk.imageGenProvider === 'minimax',
      },
      {
        key: 'imageMinimaxBaseUrl',
        type: 'text',
        labelKey: 'skill_keys.image_minimax_base_url',
        placeholder: 'https://api.minimaxi.com/v1',
        visibleIf: sk => sk.imageGenProvider === 'minimax',
      },
      {
        key: 'imageMinimaxModel',
        type: 'text',
        labelKey: 'skill_keys.image_minimax_model',
        placeholder: 'image-01',
        visibleIf: sk => sk.imageGenProvider === 'minimax',
      },
    ],
  },
  {
    id: 'music_generate',
    titleKey: 'skill_keys.music_generate',
    descKey: 'skill_keys.music_generate_desc',
    requiredKeys: ['musicGenApiKey'],
    fields: [
      { key: 'musicGenApiKey', type: 'password', labelKey: 'skill_keys.music_gen_api_key', placeholder: 'MiniMax Token Plan subscription key' },
      { key: 'musicGenBaseUrl', type: 'text', labelKey: 'skill_keys.music_gen_base_url', placeholder: 'https://api.minimaxi.com/v1', hintKey: 'skill_keys.music_gen_default' },
      { key: 'musicGenModel', type: 'text', labelKey: 'skill_keys.music_gen_model', placeholder: 'music-3.0', hintKey: 'skill_keys.music_gen_model_hint' },
    ],
    test: {
      labelKey: 'skill_keys.test_music',
      endpoint: '/api/test-music',
      buildBody: (sk) => ({
        apiKey: sk.musicGenApiKey,
        baseUrl: sk.musicGenBaseUrl,
        model: sk.musicGenModel,
      }),
    },
  },
  {
    id: 'vision_ocr',
    titleKey: 'skill_keys.vision_ocr',
    descKey: 'skill_keys.vision_desc',
    requiredKeys: ['visionApiKey'],
    fields: [
      { key: 'visionApiKey', type: 'password', labelKey: 'skill_keys.vision_api_key', placeholder: 'Vision API Key (e.g. Kimi)...' },
      { key: 'visionModel', type: 'text', labelKey: 'skill_keys.vision_model', placeholder: 'kimi-for-coding', hintKey: 'skill_keys.vision_model_hint' },
      { key: 'visionBaseUrl', type: 'text', labelKey: 'skill_keys.vision_base_url', placeholder: 'https://api.moonshot.cn/anthropic', hintKey: 'skill_keys.vision_url_hint' },
    ],
    test: {
      labelKey: 'skill_keys.test_vision',
      endpoint: '/api/test-vision',
      buildBody: (sk) => ({
        apiKey: sk.visionApiKey || '',
        model: sk.visionModel || 'kimi-for-coding',
        baseUrl: sk.visionBaseUrl || 'https://api.moonshot.cn/anthropic',
      }),
    },
  },
  {
    id: 'wechat',
    titleKey: 'skill_keys.wechat',
    descKey: 'skill_keys.wechat_desc',
    requiredKeys: ['wechatAppId', 'wechatAppSecret'],
    fields: [
      { key: 'wechatAppId', type: 'text', labelKey: 'skill_keys.wechat_appid', placeholder: 'wx...' },
      { key: 'wechatAppSecret', type: 'password', labelKey: 'skill_keys.wechat_appsecret', placeholder: 'Your AppSecret' },
    ],
  },
  {
    id: 'wechat_relay',
    titleKey: 'skill_keys.wechat_relay',
    descKey: 'skill_keys.wechat_relay_desc',
    requiredKeys: ['wechatRelayUrl', 'wechatRelayKey'],
    fields: [
      { key: 'wechatRelayUrl', type: 'text', labelKey: 'skill_keys.wechat_relay_url', placeholder: 'http://8.159.156.138:8888' },
      { key: 'wechatRelayKey', type: 'password', labelKey: 'skill_keys.wechat_relay_key', placeholder: 'Pre-shared key' },
    ],
  },
  {
    id: 'fengniao',
    titleKey: 'skill_keys.fengniao',
    descKey: 'skill_keys.fengniao_desc',
    requiredKeys: ['fengniaoApiKey'],
    fields: [
      { key: 'fengniaoApiKey', type: 'password', labelKey: 'skill_keys.fengniao_api_key', placeholder: 'FN_API_KEY' },
    ],
  },
  {
    id: 'flyai',
    titleKey: 'skill_keys.flyai',
    descKey: 'skill_keys.flyai_desc',
    requiredKeys: ['flyaiApiKey'],
    fields: [
      { key: 'flyaiApiKey', type: 'password', labelKey: 'skill_keys.flyai_api_key', placeholder: 'sk-...' },
    ],
  },
  {
    id: 'baidu_map',
    titleKey: 'skill_keys.baidu_map',
    descKey: 'skill_keys.baidu_map_desc',
    requiredKeys: ['baiduMapAuthToken'],
    fields: [
      { key: 'baiduMapAuthToken', type: 'password', labelKey: 'skill_keys.baidu_map_auth_token', placeholder: 'sk-ap-...' },
    ],
  },
  {
    id: 'voice_chat',
    titleKey: 'skill_keys.voice_chat',
    descKey: 'skill_keys.voice_chat_desc',
    requiredKeys: ['volcApiKey'],
    fields: [
      { key: 'volcApiKey', type: 'password', labelKey: 'skill_keys.volc_api_key', placeholder: '火山引擎 API Key' },
    ],
  },
  {
    id: 'voice_memory',
    titleKey: 'skill_keys.voice_memory',
    descKey: 'skill_keys.voice_memory_desc',
    requiredKeys: [],
    fields: [
      { key: 'embedBaseUrl', type: 'text', labelKey: 'skill_keys.embed_base_url', placeholder: 'https://ark.cn-beijing.volces.com/api/v3' },
      { key: 'embedApiKey', type: 'password', labelKey: 'skill_keys.embed_api_key', placeholder: '火山方舟 API Key' },
      { key: 'embedModel', type: 'text', labelKey: 'skill_keys.embed_model', placeholder: 'doubao-embedding-large-text-240915' },
      { key: 'voiceLlmBaseUrl', type: 'text', labelKey: 'skill_keys.voice_llm_base_url', placeholder: 'https://api.deepseek.com' },
      { key: 'voiceLlmApiKey', type: 'password', labelKey: 'skill_keys.voice_llm_api_key', placeholder: 'DeepSeek API Key' },
      { key: 'voiceLlmModel', type: 'text', labelKey: 'skill_keys.voice_llm_model', placeholder: 'deepseek-chat' },
    ],
  },
  {
    id: 'mail163',
    titleKey: 'skill_keys.mail163',
    descKey: 'skill_keys.mail163_desc',
    requiredKeys: ['mail163Address', 'mail163AuthCode'],
    fields: [
      { key: 'mail163Address', type: 'text', labelKey: 'skill_keys.mail163_address', placeholder: 'yourname@163.com' },
      { key: 'mail163AuthCode', type: 'password', labelKey: 'skill_keys.mail163_auth_code', placeholder: 'Client authorization code' },
      { key: 'mail163SmtpHost', type: 'text', labelKey: 'skill_keys.mail163_smtp_host', placeholder: 'smtp.163.com' },
      { key: 'mail163SmtpPort', type: 'text', labelKey: 'skill_keys.mail163_smtp_port', placeholder: '465' },
      { key: 'mail163ImapHost', type: 'text', labelKey: 'skill_keys.mail163_imap_host', placeholder: 'imap.163.com' },
      { key: 'mail163ImapPort', type: 'text', labelKey: 'skill_keys.mail163_imap_port', placeholder: '993' },
    ],
    test: {
      labelKey: 'skill_keys.test_mail163',
      endpoint: '/api/test-mail163',
      buildBody: (sk) => ({
        address: sk.mail163Address || '',
        authCode: sk.mail163AuthCode || '',
        smtpHost: sk.mail163SmtpHost || 'smtp.163.com',
        smtpPort: sk.mail163SmtpPort || '465',
        imapHost: sk.mail163ImapHost || 'imap.163.com',
        imapPort: sk.mail163ImapPort || '993',
      }),
    },
  },
]

function isSkillConfigured(sk: SkillKeysConfig | undefined, skill: SkillDef): boolean {
  if (!sk) return false
  return skill.requiredKeys.every(k => Boolean(sk[k]))
}

function normalizeImageGenConfig(config: KimiConfig): KimiConfig {
  const current = (config.skillKeys || {}) as SkillKeysConfig & Record<string, string>
  const provider = current.imageGenProvider || 'ark'
  const legacyKey = current.imageGenApiKey || ''
  const legacyBase = current.imageGenBaseUrl || ''
  const legacyModel = current.imageGenModel || ''
  return {
    ...config,
    skillKeys: {
      ...current,
      imageGenProvider: provider,
      imageArkApiKey: current.imageArkApiKey || (provider === 'ark' ? legacyKey : ''),
      imageArkBaseUrl: current.imageArkBaseUrl || (provider === 'ark' ? legacyBase : 'https://ark.cn-beijing.volces.com/api/v3'),
      imageArkModel: current.imageArkModel || (provider === 'ark' ? legacyModel : 'doubao-seedream-4-5-251128'),
      imageMinimaxApiKey: current.imageMinimaxApiKey || (provider === 'minimax' ? legacyKey : ''),
      imageMinimaxBaseUrl: current.imageMinimaxBaseUrl || (provider === 'minimax' ? legacyBase : 'https://api.minimaxi.com/v1'),
      imageMinimaxModel: current.imageMinimaxModel || (provider === 'minimax' ? legacyModel : 'image-01'),
    } as SkillKeysConfig,
  }
}

function SkillKeysTab({ config, onSave }: { config: KimiConfig; onSave: (c: KimiConfig) => void }) {
  const { t } = useTranslation()
  const [form, setForm] = useState<KimiConfig>(() => normalizeImageGenConfig(config))
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({})
  const [testing, setTesting] = useState<Record<string, boolean>>({})
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; error?: string; detail?: string }>>({})

  const sk = (form.skillKeys || {}) as SkillKeysConfig

  const setField = (key: keyof SkillKeysConfig, value: string) => {
    setForm(prev => {
      const skillKeys = { ...prev.skillKeys } as Record<string, string>
      skillKeys[key] = value
      return { ...prev, skillKeys: skillKeys as unknown as SkillKeysConfig }
    })
    setSaved(false)
  }

  const startEdit = (skill: SkillDef) => {
    setForm(normalizeImageGenConfig(config))
    setEditingId(skill.id)
    setSaved(false)
    setTestResults(prev => { const next = { ...prev }; delete next[skill.id]; return next })
  }

  const cancelEdit = () => setEditingId(null)

  const handleSave = () => {
    onSave(form)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
    setEditingId(null)

    // 同步语音/记忆配置到后端（供 voice_chat 读取）
    const skNow = form.skillKeys || ({} as SkillKeysConfig)
    getBackendUrl().then((baseUrl) => {
      fetch(`${baseUrl}/api/voice/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          volcApiKey: skNow.volcApiKey || '',
          embedBaseUrl: skNow.embedBaseUrl || '',
          embedApiKey: skNow.embedApiKey || '',
          embedModel: skNow.embedModel || '',
          voiceLlmBaseUrl: skNow.voiceLlmBaseUrl || '',
          voiceLlmApiKey: skNow.voiceLlmApiKey || '',
          voiceLlmModel: skNow.voiceLlmModel || '',
        }),
      }).catch(() => { /* 后端未启动时静默 */ })
    })
  }

  const handleTest = async (skill: SkillDef) => {
    if (!skill.test) return
    setTesting(prev => ({ ...prev, [skill.id]: true }))
    setTestResults(prev => { const next = { ...prev }; delete next[skill.id]; return next })
    try {
      const baseUrl = await getBackendUrl()
      const resp = await fetch(`${baseUrl}${skill.test.endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(skill.test.buildBody(sk)),
      })
      const data = await resp.json()
      setTestResults(prev => ({ ...prev, [skill.id]: data }))
    } catch (e: any) {
      setTestResults(prev => ({ ...prev, [skill.id]: { success: false, error: e.message || 'Network error' } }))
    } finally {
      setTesting(prev => ({ ...prev, [skill.id]: false }))
    }
  }

  const editingSkill = SKILL_DEFS.find(s => s.id === editingId)

  if (editingSkill) {
    return (
      <div className="tab-content">
        <div className="skill-key-edit-header">
          <button className="llm-back-btn" onClick={cancelEdit} title={t("skill_keys.back")}>
            <ChevronLeft size={16} />
          </button>
          <div className="skill-key-edit-title">
            <h3>{t(editingSkill.titleKey)}</h3>
            <p>{t(editingSkill.descKey)}</p>
          </div>
        </div>

        {editingSkill.fields.map(field => {
          if (field.visibleIf && !field.visibleIf(sk)) return null
          const value = sk[field.key] as string
          const placeholder = typeof field.placeholder === 'function' ? field.placeholder(sk) : field.placeholder

          return (
            <div className="config-field" key={field.key}>
              <label>{t(field.labelKey)}</label>

              {field.type === 'toggle' ? (
                <div className="toggle-group">
                  {(field.options || []).map(opt => (
                    <button
                      key={opt.value}
                      className={value === opt.value ? 'active' : ''}
                      onClick={() => setField(field.key, opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              ) : field.type === 'password' ? (
                <div className="key-row">
                  <input
                    type={visibleSecrets[field.key] ? 'text' : 'password'}
                    value={value}
                    onChange={e => setField(field.key, e.target.value)}
                    placeholder={placeholder}
                  />
                  <button onClick={() => setVisibleSecrets(prev => ({ ...prev, [field.key]: !prev[field.key] }))}>
                    {visibleSecrets[field.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              ) : (
                <input
                  type="text"
                  value={value}
                  onChange={e => setField(field.key, e.target.value)}
                  placeholder={placeholder}
                />
              )}

              {field.hintKey && <span className="field-hint">{t(field.hintKey)}</span>}
            </div>
          )
        })}

        {editingSkill.test && (
          <div className="config-field">
            <button className="test-btn" onClick={() => handleTest(editingSkill)} disabled={testing[editingSkill.id]}>
              {testing[editingSkill.id] ? t("api.testing") : t(editingSkill.test.labelKey)}
            </button>
            {testResults[editingSkill.id] && (
              <span className={`test-result ${testResults[editingSkill.id].success ? 'success' : 'fail'}`}>
                {testResults[editingSkill.id].success
                  ? (testResults[editingSkill.id].detail || 'OK')
                  : `Failed: ${testResults[editingSkill.id].error || 'Unknown error'}`}
              </span>
            )}
          </div>
        )}

        <div className="skill-key-edit-actions">
          <button className="save-btn" onClick={handleSave}>
            {saved ? t("settings.saved") : t("settings.save")}
          </button>
          <button className="skill-key-cancel" onClick={cancelEdit}>
            {t("api.cancel")}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="tab-content">
      <div className="skill-key-list">
        {SKILL_DEFS.map(skill => {
          const configured = isSkillConfigured(config.skillKeys, skill)
          return (
            <div key={skill.id} className="skill-key-card">
              <div className="skill-key-card-info">
                <div className="skill-key-card-header">
                  <span className="skill-key-card-name">{t(skill.titleKey)}</span>
                  <span className={`skill-key-badge ${configured ? 'configured' : ''}`}>
                    {configured ? t("skill_keys.configured") : t("skill_keys.not_configured")}
                  </span>
                </div>
                <p className="skill-key-card-desc">{t(skill.descKey)}</p>
              </div>
              <button className="skill-key-card-edit" onClick={() => startEdit(skill)} title={t("api.edit")}>
                <Pencil size={14} />
              </button>
            </div>
          )
        })}
      </div>
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
