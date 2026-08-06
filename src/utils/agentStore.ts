/**
 * 自定义 Agent localStorage 存储
 * 提供 CRUD 操作和同步到后端的接口
 */
import type { LLMEntry } from '../types/electron'
import { getBackendUrl } from './config'

/** 可被 Agent 接管的能力类型 */
export type AgentCapability =
  | 'web_search'
  | 'search_document'
  | 'search_code'
  | 'search_image'
  | 'deep_research'
  | 'code_gen'
  | 'doc_processing'
  | 'spreadsheet_processing'
  | 'image_generation'
  | 'image_processing'
  | 'video_generation'
  | 'writing'
  | 'longread'
  | 'project_scan'
  | 'memory_management'
  | 'network_bridge'
  | 'enterprise_search'
  | 'travel_search'

/** 能力接管标签 */
export const CAPABILITY_LABELS: Record<AgentCapability, string> = {
  web_search: '网页搜索',
  search_document: '文档搜索',
  search_code: '代码搜索',
  search_image: '图片搜索',
  deep_research: '深度研究',
  code_gen: '代码编写',
  doc_processing: '文档处理',
  spreadsheet_processing: '表格处理',
  image_generation: '图片生成',
  image_processing: '图片处理',
  video_generation: '视频生成',
  writing: '写作润色',
  longread: '长文阅读',
  project_scan: '项目扫描',
  memory_management: '记忆管理',
  network_bridge: '网络桥接',
  enterprise_search: '企业查询',
  travel_search: '旅行搜索',
}

/** 工具 → 能力映射：根据选中的工具自动推导可接管的能力 */
const TOOL_TO_CAPABILITY: Record<string, AgentCapability> = {
  // 搜索类
  web_search: 'web_search',
  search_document: 'search_document',
  search_docx: 'search_document',
  search_code: 'search_code',
  search_image: 'search_image',
  deep_research: 'deep_research',
  // 代码类
  write: 'code_gen',
  edit: 'code_gen',
  sandbox_run: 'code_gen',
  bash: 'code_gen',
  // 文档处理
  read_docx: 'doc_processing',
  write_docx: 'doc_processing',
  edit_docx: 'doc_processing',
  read_pdf: 'doc_processing',
  read_pptx: 'doc_processing',
  convert_pptx: 'doc_processing',
  // 表格处理
  read_xlsx: 'spreadsheet_processing',
  write_xlsx: 'spreadsheet_processing',
  edit_xlsx: 'spreadsheet_processing',
  // 图片
  generate_image: 'image_generation',
  read_image: 'image_processing',
  // 视频
  video_scene: 'video_generation',
  video_tts: 'video_generation',
  video_compose: 'video_generation',
  // 写作与阅读
  writing_polish: 'writing',
  longread: 'longread',
  // 项目管理
  project_scan: 'project_scan',
  // 记忆
  memory_read: 'memory_management',
  memory_record: 'memory_management',
  memory_update: 'memory_management',
  // 网络
  network_bridge: 'network_bridge',
  // 项目管理
  todo_write: 'project_scan',
  // 企业查询
  fengniao_search: 'enterprise_search',
  fengniao_basic_info: 'enterprise_search',
  fengniao_shareholders: 'enterprise_search',
  fengniao_executives: 'enterprise_search',
  fengniao_investments: 'enterprise_search',
  fengniao_changes: 'enterprise_search',
  fengniao_executed: 'enterprise_search',
  fengniao_dishonest: 'enterprise_search',
  fengniao_limit_consumption: 'enterprise_search',
  fengniao_abnormal_operation: 'enterprise_search',
  fengniao_serious_illegal: 'enterprise_search',
  fengniao_admin_penalty: 'enterprise_search',
  // 旅行搜索
  flyai_keyword_search: 'travel_search',
  flyai_ai_search: 'travel_search',
  flyai_search_flight: 'travel_search',
  flyai_search_train: 'travel_search',
  flyai_search_hotel: 'travel_search',
  flyai_search_poi: 'travel_search',
  flyai_search_marriott_hotel: 'travel_search',
  flyai_search_marriott_package: 'travel_search',
  // 以下工具不映射能力（通用基础工具）: read, batch_read, get_current_time
}

/** 根据选中的工具列表，推导出可接管的能力列表（去重） */
export function deriveCapabilities(tools: string[]): AgentCapability[] {
  const caps = new Set<AgentCapability>()
  for (const tool of tools) {
    const cap = TOOL_TO_CAPABILITY[tool]
    if (cap) caps.add(cap)
  }
  return Array.from(caps)
}

export interface CustomAgent {
  id: string
  name: string
  description: string
  systemPrompt: string
  tools: string[]
  model: string
  llmConfigId: string  // 引用 config.llms 中的 LLM 配置 ID
  capabilities: AgentCapability[]
  createdAt: number
}

const STORAGE_KEY = 'sigma_custom_agents'

export function loadAgents(): CustomAgent[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as CustomAgent[]
  } catch { /* ignore */ }
  return []
}

export function saveAgents(agents: CustomAgent[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(agents))
}

export function createAgent(
  name: string,
  description: string,
  systemPrompt: string,
  tools: string[],
  model: string,
  llmConfigId: string = '',
  capabilities: AgentCapability[] = [],
): CustomAgent {
  return {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    name: name.trim(),
    description: description.trim(),
    systemPrompt: systemPrompt.trim(),
    tools,
    model,
    llmConfigId,
    capabilities,
    createdAt: Date.now(),
  }
}

/**
 * Skill 信息（从后端动态获取）
 */
export interface SkillInfo {
  name: string
  label: string
  tool_count: number
  tool_names: string[]
}

/**
 * 从后端动态获取所有可用的 Skill 列表。
 * 带重试机制（3 次，间隔 1s/2s/4s），失败时返回空数组。
 */
export async function fetchAvailableSkills(): Promise<SkillInfo[]> {
  const maxRetries = 3
  let lastErr: unknown = null

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      if (attempt > 0) {
        await new Promise(r => setTimeout(r, Math.pow(2, attempt - 1) * 1000))
      }
      const baseUrl = await getBackendUrl()
      const resp = await fetch(`${baseUrl}/api/available-skills`)
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`)
      }
      const data = await resp.json()
      if (data.skills && Array.isArray(data.skills)) {
        return data.skills
      }
      throw new Error('Invalid response format')
    } catch (err) {
      lastErr = err
      console.error(`[AgentStore] Failed to fetch available skills (attempt ${attempt + 1}/${maxRetries}):`, err)
    }
  }
  console.error('[AgentStore] All retries exhausted, returning empty skills list')
  return []
}

/**
 * 将选中的 skill 名称列表展开为工具名列表。
 */
export function expandSkillsToTools(skillNames: string[], skills: SkillInfo[]): string[] {
  const tools = new Set<string>()
  for (const sn of skillNames) {
    const skill = skills.find(s => s.name === sn)
    if (skill) {
      for (const tn of skill.tool_names) {
        tools.add(tn)
      }
    }
  }
  return Array.from(tools)
}

/**
 * 同步 Agent 配置到后端
 * llmConfigs: 完整的 LLM 配置列表，用于解析 Agent 的 LLM 配置信息
 */
export async function syncAgentsToBackend(
  agents: CustomAgent[],
  llmConfigs: LLMEntry[] = [],
): Promise<boolean> {
  try {
    const baseUrl = await getBackendUrl()
    const resp = await fetch(`${baseUrl}/api/custom-agents/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agents: agents.map(a => {
          const llm = llmConfigs.find(l => l.id === a.llmConfigId)
          return {
            name: a.name,
            description: a.description,
            system_prompt: a.systemPrompt,
            tools: a.tools,
            model: llm?.model || a.model,
            capabilities: a.capabilities,
            llm_config: llm ? {
              base_url: llm.baseUrl,
              api_key: llm.apiKey,
              model: llm.model,
              protocol: llm.protocol,
            } : null,
          }
        }),
      }),
    })
    const data = await resp.json()
    return data.success === true
  } catch (err) {
    console.error('[CustomAgent] Sync failed:', err)
    return false
  }
}
