import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Edit3, Save, X, ChevronDown, ChevronRight, Bot, Sparkles, Wand2, Loader2, RefreshCw, AlertCircle } from 'lucide-react'
import { useTranslation } from '../i18n/I18nContext'
import type { LLMEntry } from '../types/electron'
import type { CustomAgent, AgentCapability, SkillInfo } from '../utils/agentStore'
import {
  loadAgents, saveAgents, createAgent,
  fetchAvailableSkills, expandSkillsToTools, syncAgentsToBackend, CAPABILITY_LABELS, deriveCapabilities,
} from '../utils/agentStore'
import { getBackendUrl } from '../utils/config'
import './CustomAgentPanel.css'

interface Props {
  llmConfigs: LLMEntry[]
  activeLLM: { baseUrl: string; apiKey: string; model: string; protocol: 'anthropic' | 'openai' } | null
  activeLLMId?: string
}

export default function CustomAgentPanel({ llmConfigs, activeLLM, activeLLMId }: Props) {
  const { t } = useTranslation()
  const [agents, setAgents] = useState<CustomAgent[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const firstLlm = llmConfigs[0]
  const defaultLLMId = llmConfigs.find(l => l.id === activeLLMId)?.id || firstLlm?.id || ''
  const defaultForm = {
    name: '',
    description: '',
    systemPrompt: '',
    tools: [] as string[],
    selectedSkills: [] as string[],
    llmConfigId: '',
    capabilities: [] as AgentCapability[],
  }
  const [form, setForm] = useState(defaultForm)

  // AI 生成/润色加载状态: { field: 'description' | 'systemPrompt', mode: 'generate' | 'polish' } | null
  const [aiLoading, setAiLoading] = useState<{ field: string; mode: string } | null>(null)

  // 从后端动态获取可用 Skill 列表
  const [availableSkills, setAvailableSkills] = useState<SkillInfo[]>([])
  const [skillsLoading, setSkillsLoading] = useState(true)
  const [skillsError, setSkillsError] = useState(false)

  const loadSkills = useCallback(async () => {
    setSkillsLoading(true)
    setSkillsError(false)
    try {
      const skills = await fetchAvailableSkills()
      setAvailableSkills(skills)
      setSkillsError(skills.length === 0)
    } catch {
      setSkillsError(true)
    } finally {
      setSkillsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSkills()
  }, [loadSkills])

  useEffect(() => {
    setAgents(loadAgents())
  }, [])

  useEffect(() => {
    if (llmConfigs.length === 0) return
    const targetId = llmConfigs.find(l => l.id === activeLLMId)?.id || firstLlm?.id
    if (targetId && !form.llmConfigId) {
      setForm(prev => ({ ...prev, llmConfigId: targetId }))
    }
  }, [llmConfigs, activeLLMId, form.llmConfigId, firstLlm?.id])

  const resetForm = () => {
    const targetId = llmConfigs.find(l => l.id === activeLLMId)?.id || firstLlm?.id || ''
    setForm({ ...defaultForm, llmConfigId: targetId })
  }

  const persistAndSync = (updated: CustomAgent[]) => {
    setAgents(updated)
    saveAgents(updated)
    syncAgentsToBackend(updated, llmConfigs)
  }

  // ── AI 生成/润色 ──

  const callAIGenerate = async (field: 'description' | 'systemPrompt', mode: 'generate' | 'polish'): Promise<string> => {
    if (!activeLLM) throw new Error('No active LLM configured')

    const baseUrl = await getBackendUrl()

    let systemPrompt = ''
    let userPrompt = ''

    if (field === 'description') {
      if (mode === 'generate') {
        userPrompt = [
          `Agent Name: ${form.name || '(not set yet)'}`,
          `System Prompt: ${form.systemPrompt || '(not set yet)'}`,
          '',
          'Based on the agent name and system prompt above, write a concise one-line description (max 80 characters) in the same language as the system prompt. Output only the description, no extra text.',
        ].join('\n')
      } else {
        userPrompt = [
          `Current description: "${form.description || '(empty)'}"`,
          `Agent Name: ${form.name || '(not set yet)'}`,
          `System Prompt: ${form.systemPrompt || '(not set yet)'}`,
          '',
          'Polish and improve this agent description. Make it concise, clear, and professional (max 80 characters). Output only the polished description, no extra text.',
        ].join('\n')
      }
    } else {
      // systemPrompt
      if (mode === 'generate') {
        systemPrompt = 'You are a prompt engineer. Write professional system prompts for AI agents.'
        userPrompt = [
          `Agent Name: ${form.name || '(not set yet)'}`,
          `Description: ${form.description || '(not set yet)'}`,
          `Selected Tools: ${form.tools.length > 0 ? form.tools.join(', ') : '(none)'}`,
          '',
          'Write a detailed system prompt for this agent. Include: role definition, behavior rules, tool usage guidelines, and output format requirements. Write in the same language as the agent name. Output only the system prompt, no extra text.',
        ].join('\n')
      } else {
        systemPrompt = 'You are a prompt engineer. Polish system prompts to make them more effective.'
        userPrompt = [
          `Current system prompt:`,
          '"""',
          form.systemPrompt,
          '"""',
          '',
          'Polish and improve this system prompt. Make it more structured and effective while preserving the core intent and language. Output only the polished system prompt, no extra text.',
        ].join('\n')
      }
    }

    const resp = await fetch(`${baseUrl}/api/agent-ai-generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        baseUrl: activeLLM.baseUrl,
        apiKey: activeLLM.apiKey,
        model: activeLLM.model,
        protocol: activeLLM.protocol,
        systemPrompt,
        userPrompt,
      }),
    })

    const data = await resp.json()
    if (!data.success) throw new Error(data.error || 'AI generation failed')
    return data.text as string
  }

  const handleAIGenerate = async (field: 'description' | 'systemPrompt', mode: 'generate' | 'polish') => {
    setAiLoading({ field, mode })
    try {
      const result = await callAIGenerate(field, mode)
      setForm(prev => ({ ...prev, [field === 'description' ? 'description' : 'systemPrompt']: result }))
    } catch (err: any) {
      console.error('[AI Generate] Error:', err)
      alert(`AI ${mode === 'generate' ? '生成' : '润色'}失败: ${err.message}`)
    } finally {
      setAiLoading(null)
    }
  }

  // ── CRUD ──

  const handleCreate = () => {
    if (!form.name.trim() || !form.systemPrompt.trim()) return
    const selectedLlm = llmConfigs.find(l => l.id === form.llmConfigId) || firstLlm
    const agent = createAgent(
      form.name, form.description,
      form.systemPrompt, form.tools, selectedLlm?.model || '',
      form.llmConfigId, form.capabilities,
    )
    const updated = [...agents, agent]
    persistAndSync(updated)
    setEditingId(null)
    resetForm()
  }

  const handleDelete = (id: string) => {
    const updated = agents.filter(a => a.id !== id)
    persistAndSync(updated)
    if (editingId === id) setEditingId(null)
    if (expandedId === id) setExpandedId(null)
  }

  const handleUpdate = (id: string) => {
    const agent = agents.find(a => a.id === id)
    if (!agent) return
    const selectedLlm = llmConfigs.find(l => l.id === form.llmConfigId)
    const updated = agents.map(a => a.id === id
      ? { ...agent, ...form, model: selectedLlm?.model || agent.model }
      : a)
    persistAndSync(updated)
    setEditingId(null)
  }

  const startEdit = (agent: CustomAgent) => {
    setEditingId(agent.id)
    // 从已存储的工具列表反向推导已选中的 skills
    const agentTools = agent.tools || []
    const derivedSkills = availableSkills
      .filter(s => s.tool_names.length > 0 && s.tool_names.every(tn => agentTools.includes(tn)))
      .map(s => s.name)
    setForm({
      name: agent.name,
      description: agent.description,
      systemPrompt: agent.systemPrompt,
      tools: [...agentTools],
      selectedSkills: derivedSkills,
      llmConfigId: agent.llmConfigId || defaultLLMId,
      capabilities: [...(agent.capabilities || [])],
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
    resetForm()
  }

  const toggleSkill = (skillName: string) => {
    setForm(prev => {
      const isSelected = prev.selectedSkills.includes(skillName)
      const newSkills = isSelected
        ? prev.selectedSkills.filter(s => s !== skillName)
        : [...prev.selectedSkills, skillName]
      return {
        ...prev,
        selectedSkills: newSkills,
        tools: expandSkillsToTools(newSkills, availableSkills),
      }
    })
  }

  const toggleCapability = (cap: AgentCapability) => {
    setForm(prev => ({
      ...prev,
      capabilities: prev.capabilities.includes(cap)
        ? prev.capabilities.filter(c => c !== cap)
        : [...prev.capabilities, cap],
    }))
  }

  const isCreating = editingId === '__new__'
  const isAiAvailable = !!activeLLM
  // 根据当前选中的工具动态推导可接管的能力
  const availableCapabilities = deriveCapabilities(form.tools)

  // 工具变化时自动清理已失效的能力勾选
  useEffect(() => {
    setForm(prev => ({
      ...prev,
      capabilities: prev.capabilities.filter(c => availableCapabilities.includes(c)),
    }))
  }, [form.tools.join(',')])

  return (
    <div className="custom-agent-panel">
      <h3 className="agent-section-title">
        <Bot size={16} /> {t("agent.title")} ({agents.length})
      </h3>

      {/* Agent 列表 */}
      {agents.length > 0 && (
        <div className="agent-list">
          {agents.map(agent => (
            <div key={agent.id} className={`agent-card ${expandedId === agent.id ? 'expanded' : ''}`}>
              <div className="agent-card-header" onClick={() => setExpandedId(expandedId === agent.id ? null : agent.id)}>
                <span className="agent-card-toggle">
                  {expandedId === agent.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </span>
                <div className="agent-card-info">
                  <span className="agent-card-name">{agent.name}</span>
                  <span className="agent-card-model">{agent.model}</span>
                </div>
                <div className="agent-card-actions">
                  <button
                    className="agent-card-edit"
                    onClick={e => { e.stopPropagation(); startEdit(agent) }}
                    title={t("agent.edit")}
                  >
                    <Edit3 size={14} />
                  </button>
                  <button
                    className="agent-card-delete"
                    onClick={e => { e.stopPropagation(); handleDelete(agent.id) }}
                    title={t("agent.delete")}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              {expandedId === agent.id && (
                <div className="agent-card-detail">
                  <div className="agent-detail-row">
                    <span className="agent-detail-label">{t("agent.description")}</span>
                    <span className="agent-detail-value">{agent.description || t("agent.none")}</span>
                  </div>
                  <div className="agent-detail-row">
                    <span className="agent-detail-label">{t("agent.skills")}</span>
                    <span className="agent-detail-value">
                      {(() => {
                        const agentTools = agent.tools || []
                        const matched = availableSkills
                          .filter(s => s.tool_names.length > 0 && s.tool_names.every(tn => agentTools.includes(tn)))
                          .map(s => s.label)
                        return matched.length > 0 ? matched.join(', ') : (agent.tools.length > 0 ? agent.tools.join(', ') : t("agent.none"))
                      })()}
                    </span>
                  </div>
                  {(agent.capabilities?.length ?? 0) > 0 && (
                    <div className="agent-detail-row">
                      <span className="agent-detail-label">{t("agent.capabilities")}</span>
                      <span className="agent-detail-value agent-capability-tags">
                        {agent.capabilities.map(c => (
                          <span key={c} className="agent-capability-tag">{CAPABILITY_LABELS[c] || c}</span>
                        ))}
                      </span>
                    </div>
                  )}
                  <div className="agent-detail-row">
                    <span className="agent-detail-label">{t("agent.system_prompt")}</span>
                    <pre className="agent-detail-prompt">{agent.systemPrompt}</pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 创建/编辑表单 */}
      {(isCreating || editingId) ? (
        <div className="agent-form">
          {/* 名称 */}
          <div className="agent-form-field">
            <label>{t("agent.name")} *</label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
              placeholder={t("agent.name_placeholder")}
            />
          </div>

          {/* 描述 + AI 按钮 */}
          <div className="agent-form-field">
            <label>{t("agent.description")}</label>
            <div className="agent-field-row">
              <input
                type="text"
                value={form.description}
                onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder={t("agent.description_placeholder")}
              />
              {isAiAvailable && (
                <div className="agent-ai-btns">
                  <button
                    className="agent-ai-btn"
                    onClick={() => handleAIGenerate('description', 'generate')}
                    disabled={!!aiLoading || !form.name.trim()}
                    title={t("agent.ai_generate_desc")}
                  >
                    {aiLoading?.field === 'description' && aiLoading?.mode === 'generate'
                      ? <Loader2 size={12} className="spinning" />
                      : <Sparkles size={12} />}
                    <span>{t("agent.ai_generate")}</span>
                  </button>
                  <button
                    className="agent-ai-btn"
                    onClick={() => handleAIGenerate('description', 'polish')}
                    disabled={!!aiLoading || !form.description.trim()}
                    title={t("agent.ai_polish_desc")}
                  >
                    {aiLoading?.field === 'description' && aiLoading?.mode === 'polish'
                      ? <Loader2 size={12} className="spinning" />
                      : <Wand2 size={12} />}
                    <span>{t("agent.ai_polish")}</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* 模型 */}
          <div className="agent-form-field">
            <label>{t("agent.model")}</label>
            <select
              value={form.llmConfigId}
              onChange={e => setForm(prev => ({ ...prev, llmConfigId: e.target.value }))}
            >
              {llmConfigs.map(llm => (
                <option key={llm.id} value={llm.id}>
                  {llm.name} ({llm.model})
                </option>
              ))}
            </select>
          </div>

          {/* 提示词 + AI 按钮 */}
          <div className="agent-form-field">
            <label>{t("agent.system_prompt")} *</label>
            <div className="agent-field-row">
              <textarea
                value={form.systemPrompt}
                onChange={e => setForm(prev => ({ ...prev, systemPrompt: e.target.value }))}
                placeholder={t("agent.system_prompt_placeholder")}
                rows={5}
              />
              {isAiAvailable && (
                <div className="agent-ai-btns agent-ai-btns-col">
                  <button
                    className="agent-ai-btn"
                    onClick={() => handleAIGenerate('systemPrompt', 'generate')}
                    disabled={!!aiLoading || !form.name.trim()}
                    title={t("agent.ai_generate_prompt")}
                  >
                    {aiLoading?.field === 'systemPrompt' && aiLoading?.mode === 'generate'
                      ? <Loader2 size={12} className="spinning" />
                      : <Sparkles size={12} />}
                    <span>{t("agent.ai_generate")}</span>
                  </button>
                  <button
                    className="agent-ai-btn"
                    onClick={() => handleAIGenerate('systemPrompt', 'polish')}
                    disabled={!!aiLoading || !form.systemPrompt.trim()}
                    title={t("agent.ai_polish_prompt")}
                  >
                    {aiLoading?.field === 'systemPrompt' && aiLoading?.mode === 'polish'
                      ? <Loader2 size={12} className="spinning" />
                      : <Wand2 size={12} />}
                    <span>{t("agent.ai_polish")}</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Skills 选择 */}
          <div className="agent-form-field">
            <label>{t("agent.skills")} ({form.selectedSkills.length} {t("agent.skills_selected")})</label>
            <div className="agent-tools-grid">
              {skillsLoading ? (
                <span className="agent-tools-loading"><Loader2 size={14} className="spinning" /> {t("agent.loading_skills")}</span>
              ) : skillsError ? (
                <button className="agent-tools-retry" onClick={loadSkills}>
                  <RefreshCw size={14} /> {t("agent.loading_skills")}
                </button>
              ) : (
                availableSkills.map(skill => (
                  <label key={skill.name} className={`agent-tool-checkbox ${form.selectedSkills.includes(skill.name) ? 'checked' : ''}`}>
                    <input
                      type="checkbox"
                      checked={form.selectedSkills.includes(skill.name)}
                      onChange={() => toggleSkill(skill.name)}
                    />
                    {skill.label}
                    <span className="agent-skill-tool-count">({skill.tool_count})</span>
                  </label>
                ))
              )}
            </div>
          </div>

          {/* 能力接管声明（根据已选工具自动推导） */}
          {availableCapabilities.length > 0 && (
            <div className="agent-form-field">
              <label>{t("agent.capabilities")} <span className="agent-field-hint">{t("agent.capabilities_hint")}</span></label>
              <div className="agent-capabilities-grid">
                {availableCapabilities.map(cap => (
                  <label
                    key={cap}
                    className={`agent-capability-checkbox ${form.capabilities.includes(cap) ? 'checked' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={form.capabilities.includes(cap)}
                      onChange={() => toggleCapability(cap)}
                    />
                    {CAPABILITY_LABELS[cap] || cap}
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* 操作按钮 */}
          <div className="agent-form-actions">
            <button
              className="agent-form-save"
              onClick={isCreating ? handleCreate : () => handleUpdate(editingId!)}
              disabled={!form.name.trim() || !form.systemPrompt.trim()}
            >
              {isCreating ? <><Plus size={14} /> {t("agent.create")}</> : <><Save size={14} /> {t("agent.save")}</>}
            </button>
            <button className="agent-form-cancel" onClick={cancelEdit}>
              <X size={14} /> {t("agent.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <button
          className="agent-add-btn"
          onClick={() => {
            setEditingId('__new__')
            resetForm()
          }}
        >
          <Plus size={16} /> {t("agent.create")}
        </button>
      )}
    </div>
  )
}
