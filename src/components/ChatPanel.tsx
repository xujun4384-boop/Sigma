import { useState, useRef, useEffect, useCallback } from 'react'
import { ChevronDown, ChevronRight, Send, Wrench, CheckCircle2, XCircle, Menu, X, StopCircle, AlertCircle, Bot } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from '../i18n/I18nContext'
import type { KimiConfig, LLMEntry } from '../types/electron'
import { getBackendUrl } from '../utils/config'
import { loadAgents, type CustomAgent } from '../utils/agentStore'
import TodoListDisplay from './TodoListDisplay'
import ContextUsageIndicator, { type ContextUsageData } from './ContextUsageIndicator'
import ThinkingAnimation from './ThinkingAnimation'
import QuestionnaireDisplay, { type QuestionnaireData } from './QuestionnaireDisplay'
import './ChatPanel.css'

// ── 系统通知工具 ──

async function notifyIfUnfocused(title: string, body: string, soundPath?: string) {
  try {
    if (!window.electronAPI?.isWindowFocused) return
    const focused = await window.electronAPI.isWindowFocused()
    if (focused) return
    // 播放用户选择的提示音
    if (soundPath) {
      window.electronAPI.previewSound(soundPath).catch(() => {})
    }
    await window.electronAPI.showNotification(title, body)
  } catch { /* 静默失败 */ }
}

// ── 数据模型 ──

type AgentInternalBlock =
  | { type: 'agent_think'; content: string }
  | { type: 'agent_tool'; toolName: string; turn: number; result?: string; success?: boolean }

type Block =
  | { type: 'thinking'; content: string }
  | { type: 'response_text'; content: string }
  | { type: 'tool_call'; toolName: string; toolInput: Record<string, unknown>; result?: string; success?: boolean; displayName?: string; progressLog?: string[] }
  | { type: 'subagent_batch'; tasks: SubAgentTask[] }
  | { type: 'agent_execution'; agentName: string; status: 'running' | 'done'; turn: number; agentBlocks: AgentInternalBlock[] }

type SubAgentTask = {
  agent_id: string
  description: string
  status: 'running' | 'done' | 'error'
  turns: number
  content: string
  success: boolean
}

interface AssistantMessage {
  id: string
  role: 'assistant'
  blocks: Block[]
  content: string
  isStreaming: boolean
  todolist?: TodoListData | null
}

interface UserMessage {
  id: string
  role: 'user'
  content: string
  attachments?: { name: string; path: string }[]
}

type Message = UserMessage | AssistantMessage

export interface TodoItem {
  id: string
  content: string
  status: 'pending' | 'in_progress' | 'completed'
  priority: 'high' | 'medium' | 'low'
}

export interface TodoListData {
  todos: TodoItem[]
  total: number
  completed: number
  in_progress: number
}

export interface TerminalTab {
  id: string
  title: string
  content: string
  command: string
}

interface ChatPanelProps {
  config: KimiConfig
  systemSettings: { maxIterations: number; subAgentMaxTurns: number; backupEnabled?: boolean; notifySound?: string }
  onSelectLLM: (id: string) => void
  resetKey: number
  onFileDiffUpdate?: (data: { filePath: string; fileName: string; fileType: string; diffData: any }) => void
  onFileModificationStart?: (data: { filePath: string; fileName: string; fileType: string; isNew?: boolean }) => void
  onFileModificationComplete?: (data: { filePath: string }) => void
  onCanvasPatch?: (data: { canvasName: string; operation: 'add' | 'replace'; elements: any[]; batchIndex?: number; batchTotal?: number; isFinal?: boolean }) => void
  onOpenTerminal?: (tab: TerminalTab) => void
}

// ── 解析 todo_write 结果 ──

function parseTodoResult(content: string): TodoListData | null {
  try {
    // 尝试从工具结果中提取 todo 数据
    const lines = content.split('\n')
    const todos: TodoItem[] = []
    let total = 0
    let completed = 0
    let inProgress = 0

    for (const line of lines) {
      // 匹配格式: "  [x] [high] Do something" 或 "  [>] [medium] Doing"
      const match = line.match(/^\s*\[(.)\]\s*\[(\w+)\]\s*(.+)/)
      if (match) {
        const icon = match[1]
        const priority = match[2] as TodoItem['priority']
        const content = match[3].trim()
        const status = icon === 'x' ? 'completed' : icon === '>' ? 'in_progress' : 'pending'
        todos.push({
          id: `todo-${todos.length}`,
          content,
          status,
          priority,
        })
        total++
        if (status === 'completed') completed++
        if (status === 'in_progress') inProgress++
      } else {
        // 尝试匹配 "x/y 完成" 格式
        const progressMatch = line.match(/(\d+)\/(\d+)\s*完成/)
        if (progressMatch) {
          total = Math.max(total, parseInt(progressMatch[2]))
          completed = Math.max(completed, parseInt(progressMatch[1]))
        }
      }
    }

    if (todos.length === 0) return null
    return { todos, total: total || todos.length, completed, in_progress: inProgress }
  } catch {
    return null
  }
}

// ── 解析当前活跃的 LLM 配置 ──

function resolveActiveLLM(config: KimiConfig): { name: string; baseUrl: string; apiKey: string; model: string; protocol: 'anthropic' | 'openai'; provider?: LLMEntry['provider']; thinking?: LLMEntry['thinking']; contextSize?: number; maxTokens?: number; temperature?: number; topP?: number; label: string } {
  if (config.activeLLMId && config.llms.length > 0) {
    const active = config.llms.find(l => l.id === config.activeLLMId)
    if (active) {
      return {
        name: active.name,
        baseUrl: active.baseUrl,
        apiKey: active.apiKey,
        model: active.model,
        protocol: active.protocol,
        provider: active.provider,
        thinking: active.thinking,
        contextSize: active.contextSize,
        maxTokens: active.maxTokens,
        temperature: active.temperature,
        topP: active.topP,
        label: `${active.name} (${active.model})`,
      }
    }
  }

  const apiKey = config.activeApiKey === 'key1' ? config.apiKey : (config.apiKey2 || config.apiKey)
  return {
    name: config.model,
    baseUrl: config.baseUrl,
    apiKey,
    model: config.model,
    protocol: config.protocol,
    label: `Legacy - ${config.model}`,
  }
}

// ── ChatPanel ──

export default function ChatPanel({ config, systemSettings, onSelectLLM, resetKey, onFileDiffUpdate, onFileModificationStart, onFileModificationComplete, onCanvasPatch, onOpenTerminal }: ChatPanelProps) {
  const { t, lang } = useTranslation()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<{ name: string; path: string }[]>([])
  const [isDropActive, setIsDropActive] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [backendConnected, setBackendConnected] = useState(false)
  const [contextUsage, setContextUsage] = useState<ContextUsageData | null>(null)
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireData | null>(null)
  const questionnaireRef = useRef<string | null>(null)  // 去重：相同 request_id 不重复渲染
  const [toolTimeout, setToolTimeout] = useState<{
    request_id: string; tool_name: string; options: {value:string;label:string;description:string}[];
  } | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<CustomAgent | null>(null)
  const [agentSuggestions, setAgentSuggestions] = useState<CustomAgent[]>([])
  const [showAgentSuggestions, setShowAgentSuggestions] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const isFirstMount = useRef(true)

  useEffect(() => {
    const check = async () => {
      try {
        const baseUrl = await getBackendUrl()
        const res = await fetch(`${baseUrl}/api/health`)
        setBackendConnected(res.ok)
      } catch { setBackendConnected(false) }
    }
    check()
    const interval = setInterval(check, 5000)
    return () => clearInterval(interval)
  }, [])

  // 切换工作目录时清空所有聊天状态（等同于重启）
  useEffect(() => {
    if (isFirstMount.current) {
      isFirstMount.current = false
      return
    }
    setMessages([])
    setInput('')
    setAttachedFiles([])
    setIsLoading(false)
    setContextUsage(null)
  }, [resetKey])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 问卷出现时也滚动到可见区域
  useEffect(() => {
    if (questionnaire) {
      // 延迟一帧确保 DOM 已渲染
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      })
    }
  }, [questionnaire])

  // 监听 Electron 的 "添加到聊天" 事件
  useEffect(() => {
    if (!window.electronAPI?.onAddFileToChat) return
    const cleanup = window.electronAPI.onAddFileToChat((fileInfo) => {
      setAttachedFiles(prev => {
        if (prev.some(f => f.path === fileInfo.path)) return prev
        return [...prev, { name: fileInfo.name, path: fileInfo.path }]
      })
    })
    return cleanup
  }, [])

  // 监听文件系统变更（外部编辑实时 diff）
  useEffect(() => {
    let abortController: AbortController | null = null
    let running = true

    const connect = async () => {
      let workingDir = ''
      if (window.electronAPI?.getWorkingDirectory) {
        const dirResult = await window.electronAPI.getWorkingDirectory()
        if (dirResult.success) workingDir = dirResult.data || ''
      }
      if (!workingDir) return

      const baseUrl = await getBackendUrl()
      abortController = new AbortController()

      try {
        const resp = await fetch(
          `${baseUrl}/api/watch-files?dir=${encodeURIComponent(workingDir)}`,
          { signal: abortController.signal },
        )
        if (!resp.ok || !resp.body) return

        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (running) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const data = JSON.parse(line.slice(6))
              const type = data.type as string
              if (type === 'file_modification_start') {
                onFileModificationStart?.({
                  filePath: data.file_path as string,
                  fileName: data.file_name as string,
                  fileType: data.file_type as string,
                  isNew: (data.is_new as boolean) || false,
                })
              } else if (type === 'file_diff_update') {
                onFileDiffUpdate?.({
                  filePath: data.file_path as string,
                  fileName: data.file_name as string,
                  fileType: data.file_type as string,
                  diffData: data.diff_data,
                })
              } else if (type === 'file_modification_complete') {
                onFileModificationComplete?.({ filePath: data.file_path as string })
              } else if (type === 'canvas_patch') {
                onCanvasPatch?.({
                  canvasName: (data.canvas_name || 'default') as string,
                  operation: (data.operation || 'add') as 'add' | 'replace',
                  elements: (data.elements || []) as any[],
                  batchIndex: data.batch_index as number | undefined,
                  batchTotal: data.batch_total as number | undefined,
                  isFinal: data.is_final as boolean | undefined,
                })
              }
            } catch { /* skip */ }
          }
        }
      } catch {
        // 连接断开，忽略
      }
    }

    connect()
    return () => {
      running = false
      abortController?.abort()
    }
  }, [resetKey, onFileDiffUpdate, onFileModificationStart, onFileModificationComplete])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || isLoading) return

    // 构建显示用的消息内容
    const displayText = selectedAgent ? `@${selectedAgent.name} ${text}` : text
    const userMsg: UserMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: displayText,
      attachments: attachedFiles.length > 0 ? attachedFiles.map(f => ({ name: f.name, path: f.path })) : undefined,
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setContextUsage(null)
    setQuestionnaire(null)
    questionnaireRef.current = null
    setToolTimeout(null)

    // 保存当前 Agent 引用（后面的 setSelectedAgent(null) 会清除）
    const currentAgent = selectedAgent
    setSelectedAgent(null)

    // 拼接附件路径
    const filePaths = attachedFiles.map(f => f.path).join('\n')
    const fullMessage = filePaths
      ? `I have attached the following files. Please read them first:\n\n${filePaths}\n\n---\n${text}`
      : text
    setAttachedFiles([])
    setIsLoading(true)

    const assistantId = (Date.now() + 1).toString()
    const assistantMsg: AssistantMessage = {
      id: assistantId, role: 'assistant', blocks: [], content: '', isStreaming: true,
    }
    setMessages(prev => [...prev, assistantMsg])

    try {
      abortRef.current = new AbortController()

      let workingDir = ''
      if (window.electronAPI?.getWorkingDirectory) {
        const dirResult = await window.electronAPI.getWorkingDirectory()
        if (dirResult.success) workingDir = dirResult.data || ''
      }

      const baseUrl = await getBackendUrl()
      const requestBody: Record<string, unknown> = {
        message: fullMessage,
        maxIterations: systemSettings.maxIterations || 10,
        subAgentMaxTurns: systemSettings.subAgentMaxTurns || 8,
        backupEnabled: systemSettings.backupEnabled ?? true,
        working_dir: workingDir,
        language: lang,
        config: { ...resolveActiveLLM(config), skillKeys: config.skillKeys, llms: config.llms, customAgents: loadAgents().map(a => {
          const llm = config.llms.find(entry => entry.id === a.llmConfigId)
          return { name: a.name, description: a.description, systemPrompt: a.systemPrompt, tools: a.tools, model: llm?.model || a.model, capabilities: a.capabilities, llmConfigId: a.llmConfigId || '' }
        }) },
      }

      // @ 触发模式：附带 Agent 配置（含 LLM 端点信息）
      if (currentAgent) {
        const agentLlm = config.llms.find(l => l.id === currentAgent.llmConfigId)
        const mainLlm = resolveActiveLLM(config)
        // Agent 有自定义 LLM 配置：用自己的端点和模型
        // Agent 无自定义配置：回退到主 LLM 的端点和模型
        const hasOwnLlm = !!(agentLlm?.baseUrl && agentLlm?.apiKey)
        requestBody.custom_agent = {
          name: currentAgent.name,
          description: currentAgent.description,
          system_prompt: currentAgent.systemPrompt,
          tools: currentAgent.tools,
          model: hasOwnLlm ? agentLlm!.model : mainLlm.model,
          base_url: hasOwnLlm ? agentLlm!.baseUrl : mainLlm.baseUrl,
          api_key: hasOwnLlm ? agentLlm!.apiKey : mainLlm.apiKey,
          protocol: hasOwnLlm ? agentLlm!.protocol : mainLlm.protocol,
        }
      }

      const response = await fetch(`${baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
        signal: abortRef.current.signal,
      })

      if (!response.ok) {
        const err = await response.text()
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: `Error: ${err}`, isStreaming: false } as AssistantMessage : m
        ))
        return
      }

      const reader = response.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'questionnaire') {
              const rid = data.request_id as string
              if (questionnaireRef.current === rid) continue  // 去重：已显示的不重复设置
              questionnaireRef.current = rid
              setQuestionnaire({
                request_id: data.request_id as string,
                title: data.title as string,
                questions: data.questions as QuestionnaireData['questions'],
              })
              // 通知：窗口未聚焦时弹出系统通知
              notifyIfUnfocused('Sigma', `${t("chat.need_answer")}: ${data.title}`, systemSettings.notifySound)
              continue
            }
            if (data.type === 'tool_timeout') {
              setToolTimeout({
                request_id: data.request_id as string,
                tool_name: data.tool_name as string,
                options: data.options as {value:string;label:string;description:string}[],
              })
              notifyIfUnfocused('Sigma', `${t("chat.tool_timeout")}: ${data.tool_name}`, systemSettings.notifySound)
              continue
            }
            if (data.type === 'chat_complete') {
              handleSSEEvent(data, assistantId, setMessages, setContextUsage, onFileDiffUpdate, onFileModificationStart, onFileModificationComplete, onCanvasPatch)
              // 通知：任务完成
              notifyIfUnfocused('Sigma', t("chat.task_complete"), systemSettings.notifySound)
              continue
            }
            handleSSEEvent(data, assistantId, setMessages, setContextUsage, onFileDiffUpdate, onFileModificationStart, onFileModificationComplete, onCanvasPatch)
          } catch { /* skip malformed */ }
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, isStreaming: false } as AssistantMessage : m
        ))
      } else {
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, content: `Connection error: ${err.message}`, isStreaming: false } as AssistantMessage : m
        ))
      }
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading, config])

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setInput(value)

    // 动态调整高度，最多3行
    const textarea = e.target
    textarea.style.height = 'auto'
    const lineHeight = parseFloat(getComputedStyle(textarea).lineHeight)
    const maxHeight = lineHeight * 3
    textarea.style.height = Math.min(textarea.scrollHeight, maxHeight) + 'px'

    // @ mention 检测
    const cursorPos = e.target.selectionStart || 0
    const textBeforeCursor = value.slice(0, cursorPos)
    const atMatch = textBeforeCursor.match(/@(\S*)$/)

    if (atMatch) {
      const query = atMatch[1].toLowerCase()
      const agents = loadAgents()
      const filtered = agents.filter(a =>
        a.name.toLowerCase().includes(query) ||
        a.description.toLowerCase().includes(query)
      )
      setAgentSuggestions(filtered)
      setShowAgentSuggestions(filtered.length > 0)
    } else {
      setShowAgentSuggestions(false)
      setAgentSuggestions([])
    }
  }, [])

  const selectAgent = useCallback((agent: CustomAgent) => {
    // 替换 @xxx 为 agent 名称（视觉上保留）
    const cursorPos = inputRef.current?.selectionStart || input.length
    const textBeforeCursor = input.slice(0, cursorPos)
    const textAfterCursor = input.slice(cursorPos)
    const atIndex = textBeforeCursor.lastIndexOf('@')
    if (atIndex >= 0) {
      const newText = textBeforeCursor.slice(0, atIndex) + textAfterCursor
      setInput(newText)
    }
    setSelectedAgent(agent)
    setShowAgentSuggestions(false)
    setAgentSuggestions([])
    inputRef.current?.focus()
  }, [input])

  const clearAgent = useCallback(() => {
    setSelectedAgent(null)
    inputRef.current?.focus()
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleQuestionnaireSubmit = useCallback(async (requestId: string, answers: Record<string, string | string[]>) => {
    setQuestionnaire(null)
    questionnaireRef.current = null
    // 转换为 {id, value} 格式
    const answersList = Object.entries(answers).map(([id, value]) => ({ id, value }))
    try {
      const baseUrl = await getBackendUrl()
      await fetch(`${baseUrl}/api/user-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, answers: answersList }),
      })
    } catch (err) {
      console.error('[Questionnaire] Submit failed:', err)
    }
  }, [])

  const handleToolTimeoutChoice = useCallback(async (choice: string) => {
    if (!toolTimeout) return
    const requestId = toolTimeout.request_id
    setToolTimeout(null)
    try {
      const baseUrl = await getBackendUrl()
      await fetch(`${baseUrl}/api/tool-timeout-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, choice }),
      })
    } catch (err) {
      console.error('[ToolTimeout] Submit failed:', err)
    }
  }, [toolTimeout])

  const handleChatDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDropActive(false)

    const rawFiles = e.dataTransfer.getData('application/x-sigma-paths')
    const rawPath = e.dataTransfer.getData('application/x-sigma-path')
    let files: { name: string; path: string }[] = []
    try {
      files = rawFiles ? JSON.parse(rawFiles) : []
    } catch {
      files = []
    }
    if (files.length === 0 && rawPath) {
      files = [{ path: rawPath, name: rawPath.split(/[\\/]/).pop() || rawPath }]
    }
    if (files.length > 0) {
      setAttachedFiles(prev => {
        const existing = new Set(prev.map(file => file.path))
        return [...prev, ...files.filter(file => file.path && !existing.has(file.path))]
      })
    }
  }, [])

  const handleChatDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer.types.includes('application/x-sigma-path') && !e.dataTransfer.types.includes('application/x-sigma-paths')) return
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'copy'
    setIsDropActive(true)
  }, [])

  const handleChatDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) setIsDropActive(false)
  }, [])

  return (
    <div
      className={`chat-panel ${isDropActive ? 'drop-active' : ''}`}
      onDragOver={handleChatDragOver}
      onDragLeave={handleChatDragLeave}
      onDrop={handleChatDrop}
    >
      <div className="chat-header">
        <button className="chat-menu-btn" onClick={() => {
          const event = new CustomEvent('sigma-toggle-sidebar')
          window.dispatchEvent(event)
        }}>
          <Menu size={18} />
        </button>
        <h2>{t("chat.assistant")}</h2>
        <div className="chat-header-actions">
          <span className="backend-status">
            <span className={`dot ${backendConnected ? 'connected' : 'disconnected'}`} />
            {backendConnected ? t("chat.connected") : t("chat.disconnected")}
          </span>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <h3>{t("chat.assistant")}</h3>
            <p>{t("chat.start_hint")}</p>
          </div>
        )}
        {messages.map(msg =>
          msg.role === 'user' ? (
            <div key={msg.id} className="user-message">
              <div className="message user">
                <div className="role-label">{t("chat.you")}</div>
                <div className="message-text">{msg.content}</div>
              </div>
              {msg.attachments && msg.attachments.length > 0 && (
                <div className="user-message-attachments">
                  {msg.attachments.map(file => (
                    <div key={file.path} className="file-chip user-file-chip" title={file.path}>
                      <span className="file-chip-name">{file.name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <SigmaMessage key={msg.id} msg={msg as AssistantMessage} toolTimeout={toolTimeout} onToolTimeoutChoice={handleToolTimeoutChoice} questionnaire={questionnaire} onQuestionnaireSubmit={handleQuestionnaireSubmit} onOpenTerminal={onOpenTerminal} />
          )
        )}
        <div ref={messagesEndRef} />
        {contextUsage && (
          <div className="context-usage-bar">
            <ContextUsageIndicator usage={contextUsage} />
          </div>
        )}
      </div>

      <div
        className={`chat-input-area ${isDropActive ? 'drop-active' : ''}`}
        onDragOver={handleChatDragOver}
        onDragLeave={handleChatDragLeave}
        onDrop={handleChatDrop}
      >
        {isLoading ? (
          <div className="chat-input-working">
            <ThinkingAnimation isStreaming={true} />
            <button className="stop-btn" onClick={() => { abortRef.current?.abort(); setQuestionnaire(null); questionnaireRef.current = null }}>
              <StopCircle size={18} />
            </button>
          </div>
        ) : (
          <>
            <div className="chat-input-toolbar">
              <select
                className="model-selector"
                value={config.activeLLMId || '__legacy__'}
                onChange={e => onSelectLLM(e.target.value === '__legacy__' ? '' : e.target.value)}
                title={t("chat.select_llm")}
              >
                <option value="__legacy__">Legacy Config</option>
                {config.llms.map(llm => (
                  <option key={llm.id} value={llm.id}>{llm.name} ({llm.model})</option>
                ))}
              </select>
              <span className="chat-input-meta">Protocol: {resolveActiveLLM(config).protocol}</span>
            </div>
            {attachedFiles.length > 0 && (
              <div className="attached-files">
                {attachedFiles.map(file => (
                  <div key={file.path} className="file-chip" title={file.path}>
                    <span className="file-chip-name">{file.name}</span>
                    <button
                      className="file-chip-remove"
                      onClick={() => setAttachedFiles(prev => prev.filter(f => f.path !== file.path))}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {selectedAgent && (
              <div className="attached-files">
                <div className="file-chip agent-chip" title={selectedAgent.description}>
                  <Bot size={12} />
                  <span className="file-chip-name">@{selectedAgent.name}</span>
                  <button
                    className="file-chip-remove"
                    onClick={clearAgent}
                    title="Remove agent"
                  >
                    <X size={12} />
                  </button>
                </div>
              </div>
            )}
            <div className="chat-input-row">
              <div className="chat-input-box">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={selectedAgent
                    ? `Message @${selectedAgent.name}...`
                    : t("chat.type_message")}
                  disabled={isLoading}
                />
                {/* Agent 建议下拉 */}
                {showAgentSuggestions && agentSuggestions.length > 0 && (
                  <div className="agent-suggestions">
                    {agentSuggestions.map(agent => (
                      <div
                        key={agent.id}
                        className="agent-suggestion-item"
                        onClick={() => selectAgent(agent)}
                      >
                        <Bot size={14} />
                        <div className="agent-suggestion-info">
                          <span className="agent-suggestion-name">{agent.name}</span>
                          <span className="agent-suggestion-desc">{agent.description}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={handleSend} disabled={!input.trim()}>
                <Send size={18} />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── 自定义 Agent 执行头部 ──

function AgentExecutionHeader({ agentName, status, turn, agentBlocks }: { agentName: string; status: 'running' | 'done'; turn: number; agentBlocks: AgentInternalBlock[] }) {
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    if (status === 'running') setCollapsed(false)
  }, [status])

  return (
    <div className={`agent-execution-header ${status}`}>
      <div className="agent-execution-bar" onClick={() => setCollapsed(v => !v)}>
        <Bot size={14} />
        <span className="agent-execution-name">@{agentName}</span>
        {status === 'running' && (
          <>
            <span className="agent-execution-spinner" />
            <span className="agent-execution-status">Round {turn}</span>
          </>
        )}
        {status === 'done' && (
          <>
            <CheckCircle2 size={12} />
            <span className="agent-execution-status done">{turn} rounds</span>
          </>
        )}
        <span className="agent-execution-toggle">{collapsed ? '▸' : '▾'}</span>
      </div>
      {!collapsed && agentBlocks.length > 0 && (
        <div className="agent-execution-body">
          {agentBlocks.map((ab, i) =>
            ab.type === 'agent_think' ? (
              <div key={i} className="agent-nested-block agent-nested-think">
                <span className="agent-nested-label">Thinking</span>
                <div className="agent-nested-content">{ab.content.slice(0, 200)}{ab.content.length > 200 ? '...' : ''}</div>
              </div>
            ) : (
              <div key={i} className={`agent-nested-block agent-nested-tool ${ab.result !== undefined ? (ab.success ? 'success' : 'failed') : 'running'}`}>
                <div className="agent-nested-tool-header">
                  {ab.result === undefined ? (
                    <span className="agent-nested-spinner" />
                  ) : ab.success ? (
                    <CheckCircle2 size={12} />
                  ) : (
                    <XCircle size={12} />
                  )}
                  <Wrench size={10} />
                  <span className="agent-nested-tool-name">{ab.toolName}</span>
                  {ab.result !== undefined && (
                    <span className="agent-nested-tool-preview">
                      {ab.result.slice(0, 40)}
                    </span>
                  )}
                </div>
              </div>
            )
          )}
        </div>
      )}
    </div>
  )
}

// ── SubAgent 并行任务显示 ──

function SubAgentDisplay({ tasks }: { tasks: SubAgentTask[] }) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(false)
  const running = tasks.filter(t => t.status === 'running').length
  const done = tasks.filter(t => t.status === 'done').length
  const failed = tasks.filter(t => t.status === 'error').length

  const statusIcons: Record<string, string> = { running: '🔄', done: '✅', error: '❌' }

  return (
    <div className="subagent-batch">
      <div className="subagent-header" onClick={() => setCollapsed(v => !v)}>
        <span className="subagent-icon">🤖</span>
        <span className="subagent-title">{t("chat.sub_agents")}</span>
        <span className="subagent-stats">
          {done}/{tasks.length} {t("chat.done")} {running > 0 && `· ${running} ${t("chat.running")}`} {failed > 0 && `· ${failed} ${t("chat.failed")}`}
        </span>
        <span className="subagent-toggle">{collapsed ? '▶' : '▼'}</span>
      </div>
      {!collapsed && (
        <div className="subagent-tasks">
          {tasks.map(task => (
            <div key={task.agent_id} className={`subagent-task ${task.status}`}>
              <div className="subagent-task-header">
                <span className="subagent-task-icon">{statusIcons[task.status] || '⏳'}</span>
                <span className="subagent-task-id">{task.description || task.agent_id}</span>
                {task.turns > 0 && <span className="subagent-task-turns">{t("chat.turn")} {task.turns}</span>}
              </div>
              {task.status === 'running' && (
                <div className="subagent-task-progress">
                  <div className="subagent-spinner" />
                  <span>{t("chat.working")}</span>
                </div>
              )}
              {task.status !== 'running' && task.content && (
                <div className="subagent-task-content">{task.content}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── SSE 事件处理 ──

function handleSSEEvent(
  data: Record<string, unknown>,
  assistantId: string,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  setContextUsage: React.Dispatch<React.SetStateAction<ContextUsageData | null>>,
  onFileDiffUpdate?: (data: { filePath: string; fileName: string; fileType: string; diffData: any }) => void,
  onFileModificationStart?: (data: { filePath: string; fileName: string; fileType: string; isNew?: boolean }) => void,
  onFileModificationComplete?: (data: { filePath: string }) => void,
  onCanvasPatch?: (data: { canvasName: string; operation: 'add' | 'replace'; elements: any[]; batchIndex?: number; batchTotal?: number; isFinal?: boolean }) => void,
) {
  const type = data.type as string

  if (type === 'text' && data.content) {
    const ct = (data.contentType as string) || 'text'
    const text = data.content as string
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      if (ct === 'thinking') {
        const blocks = [...am.blocks]
        const last = blocks[blocks.length - 1]
        if (last && last.type === 'thinking') {
          blocks[blocks.length - 1] = { ...last, content: last.content + text }
        } else {
          blocks.push({ type: 'thinking', content: text })
        }
        return { ...am, blocks }
      }
      // 非 thinking 文本也存入 blocks（response_text），不再直接填 content
      const blocks = [...am.blocks]
      const last = blocks[blocks.length - 1]
      if (last && last.type === 'response_text') {
        blocks[blocks.length - 1] = { ...last, content: last.content + text }
      } else {
        blocks.push({ type: 'response_text', content: text })
      }
      return { ...am, blocks }
    }))
    return
  }

  if (type === 'tool_start') {
    const toolName = data.tool_name as string
    const toolInput = data.tool_input as Record<string, unknown>
    const displayName = (data.display_name as string) || undefined
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      return { ...am, blocks: [...am.blocks, { type: 'tool_call', toolName, toolInput, displayName }] }
    }))
    return
  }

  if (type === 'tool_progress') {
    const toolName = data.tool_name as string
    const content = (data.content as string) || ''
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = [...am.blocks]
      // 找到最后一个匹配的未完成 tool_call
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i]
        if (b.type === 'tool_call' && b.toolName === toolName && b.result === undefined) {
          const log = [...(b.progressLog || []), content]
          blocks[i] = { ...b, progressLog: log }
          break
        }
      }
      return { ...am, blocks }
    }))
    return
  }

  if (type === 'tool_result') {
    const toolName = data.tool_name as string
    const success = !!data.success
    const resultContent = (data.content as string) || ''
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = [...am.blocks]
      // 找到最后一个匹配的未完成 tool_call
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i]
        if (b.type === 'tool_call' && b.toolName === toolName && b.result === undefined) {
          blocks[i] = { ...b, result: resultContent, success }
          break
        }
      }
      // 检测 todo_write 结果
      let todolist = am.todolist
      if (toolName === 'todo_write') {
        todolist = parseTodoResult(resultContent)
      }
      return { ...am, blocks, todolist }
    }))
    return
  }

  if (type === 'chat_complete') {
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      // 只取最后一段连续的 response_text（工具调用之后的最终回复）
      const blocks = am.blocks
      let finalContent = ''
      for (let i = blocks.length - 1; i >= 0; i--) {
        if (blocks[i].type === 'response_text') {
          finalContent = blocks[i].content + finalContent
        } else {
          break
        }
      }
      return { ...am, content: finalContent, isStreaming: false } as AssistantMessage
    }))
    return
  }

  if (type === 'error') {
    setMessages(prev => prev.map(m =>
      m.id === assistantId
        ? { ...m, content: `Error: ${data.message}`, isStreaming: false } as AssistantMessage
        : m
    ))
    return
  }

  if (type === 'context_usage') {
    setContextUsage({
      current_tokens: data.current_tokens as number,
      max_tokens: data.max_tokens as number,
      usage_percent: data.usage_percent as number,
      usage_ratio: data.usage_ratio as number,
    })
    return
  }

  // ── 自定义 Agent 事件 ──
  if (type === 'agent_start') {
    const agentName = data.agent_name as string
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = [...am.blocks]
      blocks.push({ type: 'agent_execution', agentName, status: 'running' as const, turn: 0, agentBlocks: [] })
      return { ...am, blocks }
    }))
    return
  }

  if (type === 'agent_turn') {
    const agentName = data.agent_name as string
    const turn = data.turn as number
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = am.blocks.map(b => {
        if (b.type !== 'agent_execution' || b.agentName !== agentName) return b
        return { ...b, turn }
      })
      return { ...am, blocks }
    }))
    return
  }

  // ── Agent 内部思考文本 ──
  if (type === 'agent_think') {
    const agentName = data.agent_name as string
    const content = (data.content as string) || ''
    const turn = data.turn as number
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = am.blocks.map(b => {
        if (b.type !== 'agent_execution' || b.agentName !== agentName) return b
        const ab = [...b.agentBlocks]
        ab.push({ type: 'agent_think', content })
        return { ...b, agentBlocks: ab, turn }
      })
      return { ...am, blocks }
    }))
    return
  }

  // ── Agent 内部工具调用 ──
  if (type === 'agent_tool_call') {
    const agentName = data.agent_name as string
    const toolName = (data.tool_name as string) || ''
    const turn = data.turn as number
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = am.blocks.map(b => {
        if (b.type !== 'agent_execution' || b.agentName !== agentName) return b
        const ab = [...b.agentBlocks]
        ab.push({ type: 'agent_tool', toolName, turn, result: undefined, success: undefined })
        return { ...b, agentBlocks: ab, turn }
      })
      return { ...am, blocks }
    }))
    return
  }

  // ── Agent 内部工具结果 ──
  if (type === 'agent_tool_result') {
    const agentName = data.agent_name as string
    const toolName = (data.tool_name as string) || ''
    const result = (data.result as string) || ''
    const success = !!data.success
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = am.blocks.map(b => {
        if (b.type !== 'agent_execution' || b.agentName !== agentName) return b
        const ab = b.agentBlocks.map(t => {
          if (t.type === 'agent_tool' && t.toolName === toolName && t.result === undefined) {
            return { ...t, result, success }
          }
          return t
        })
        return { ...b, agentBlocks: ab }
      })
      return { ...am, blocks }
    }))
    return
  }

  if (type === 'agent_complete') {
    const agentName = data.agent_name as string
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = am.blocks.map(b => {
        if (b.type !== 'agent_execution' || b.agentName !== agentName) return b
        return { ...b, status: 'done' as const }
      })
      return { ...am, blocks }
    }))
    return
  }

  // ── SubAgent 事件 ──
  if (type === 'subagent_start') {
    const agentId = data.agent_id as string
    const desc = (data.description as string) || agentId
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = [...am.blocks]
      const existing = blocks.find(b => b.type === 'subagent_batch')
      if (existing && existing.type === 'subagent_batch') {
        const tasks = [...existing.tasks]
        if (!tasks.find(t => t.agent_id === agentId)) {
          tasks.push({ agent_id: agentId, description: desc, status: 'running', turns: 0, content: '', success: false })
        }
        blocks[blocks.indexOf(existing)] = { ...existing, tasks }
      } else {
        blocks.push({ type: 'subagent_batch', tasks: [{ agent_id: agentId, description: desc, status: 'running', turns: 0, content: '', success: false }] })
      }
      return { ...am, blocks }
    }))
    return
  }

  if (type === 'subagent_progress') {
    const agentId = data.agent_id as string
    const turn = data.turn as number
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = am.blocks.map(b => {
        if (b.type !== 'subagent_batch') return b
        return { ...b, tasks: b.tasks.map(t => t.agent_id === agentId ? { ...t, turns: turn } : t) }
      })
      return { ...am, blocks }
    }))
    return
  }

  if (type === 'subagent_result') {
    const agentId = data.agent_id as string
    const success = !!data.success
    const content = (data.content as string) || ''
    const turn = data.turns as number
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      const blocks = am.blocks.map(b => {
        if (b.type !== 'subagent_batch') return b
        return { ...b, tasks: b.tasks.map(t => t.agent_id === agentId ? { ...t, status: success ? 'done' : 'error' as const, turns: turn, content, success } : t) }
      })
      return { ...am, blocks }
    }))
    return
  }

  if (type === 'todolist') {
    setMessages(prev => prev.map(m => {
      if (m.id !== assistantId || m.role !== 'assistant') return m
      const am = m as AssistantMessage
      return {
        ...am,
        todolist: {
          todos: (data.todos as TodoItem[]) || [],
          total: (data.progress as any)?.total || 0,
          completed: (data.progress as any)?.completed || 0,
          in_progress: (data.progress as any)?.in_progress || 0,
        },
      }
    }))
    return
  }

  if (type === 'compact') {
    // 压缩事件：前端暂时不做特殊处理，后续可加 toast 提示
    console.log('[Compact]', data.summary)
    return
  }

  // ── 文件 Diff 事件 ──
  if (type === 'file_modification_start') {
    onFileModificationStart?.({
      filePath: data.file_path as string,
      fileName: data.file_name as string,
      fileType: data.file_type as string,
      isNew: (data.is_new as boolean) || false,
    })
    return
  }

  if (type === 'file_diff_update') {
    onFileDiffUpdate?.({
      filePath: (data.file_path || data.diff_data?.file_path) as string,
      fileName: (data.diff_data?.file_name || data.file_name) as string,
      fileType: (data.diff_data?.file_type || data.file_type) as string,
      diffData: data.diff_data,
    })
    return
  }

  if (type === 'file_modification_complete') {
    onFileModificationComplete?.({ filePath: data.file_path as string })
    return
  }

  if (type === 'canvas_patch') {
    onCanvasPatch?.({
      canvasName: (data.canvas_name || 'default') as string,
      operation: (data.operation || 'add') as 'add' | 'replace',
      elements: (data.elements || []) as any[],
      batchIndex: data.batch_index as number | undefined,
      batchTotal: data.batch_total as number | undefined,
      isFinal: data.is_final as boolean | undefined,
    })
    return
  }
}

// ── SigmaMessage ──

function SigmaMessage({ msg, toolTimeout, onToolTimeoutChoice, questionnaire, onQuestionnaireSubmit, onOpenTerminal }: { msg: AssistantMessage; toolTimeout: { request_id: string; tool_name: string; options: {value:string;label:string;description:string}[] } | null; onToolTimeoutChoice: (choice: string) => void; questionnaire: QuestionnaireData | null; onQuestionnaireSubmit: (requestId: string, answers: Record<string, string | string[]>) => void; onOpenTerminal?: (tab: TerminalTab) => void }) {
  const { t } = useTranslation()
  const [thinkingCollapsed, setThinkingCollapsed] = useState(false)
  const thinkingBodyRef = useRef<HTMLDivElement>(null)
  const hasBlocks = msg.blocks.length > 0
  const hasContent = msg.content.length > 0
  const streamingDone = !msg.isStreaming
  const hasRunningTools = msg.blocks.some(b =>
    (b.type === 'tool_call' && b.result === undefined) ||
    (b.type === 'agent_execution' && b.status === 'running') ||
    (b.type === 'agent_execution' && b.agentBlocks.some(ab => ab.type === 'agent_tool' && ab.result === undefined))
  )
  const hasAgentExecution = msg.blocks.some(b => b.type === 'agent_execution')

  // 有未完成的工具调用时展开；全部完成后自动折叠
  useEffect(() => {
    if (hasRunningTools) {
      setThinkingCollapsed(false)
    } else if (streamingDone) {
      setThinkingCollapsed(true)
    }
  }, [streamingDone, hasRunningTools])

  // thinking-body 自动滚底
  useEffect(() => {
    if (thinkingBodyRef.current) {
      thinkingBodyRef.current.scrollTop = thinkingBodyRef.current.scrollHeight
    }
  }, [msg.blocks])

  return (
    <div className="sigma-message-group">
      {/* ── 思考容器：推理文本 + 工具调用 穿插显示，任务完成后自动折叠 ── */}
      {hasBlocks && (
        <div className={`message thinking-bubble ${thinkingCollapsed ? 'collapsed' : ''} ${hasAgentExecution ? 'has-agent' : ''}`}>
          <div className="thinking-header" onClick={() => setThinkingCollapsed(v => !v)}>
            <span className="role-label">
              {t("chat.thinking")}
              {!streamingDone && hasRunningTools && <span className="thinking-spinner" />}
            </span>
            <span className="thinking-toggle">
              {thinkingCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            </span>
          </div>
          {!thinkingCollapsed && (
            <div ref={thinkingBodyRef} className="thinking-body">
              {msg.blocks.map((block, i) =>
                block.type === 'thinking' ? (
                  <ThinkingText key={i} text={block.content} />
                ) : block.type === 'response_text' ? (
                  <ResponseText
                    key={i}
                    text={block.content}
                    isStreaming={msg.isStreaming && i === msg.blocks.length - 1 && msg.blocks.filter(b => b.type === 'response_text').pop() === block}
                    showCursor={msg.isStreaming && i === msg.blocks.length - 1}
                  />
                ) : block.type === 'subagent_batch' ? (
                  <SubAgentDisplay key={i} tasks={block.tasks} />
                ) : block.type === 'agent_execution' ? (
                  <AgentExecutionHeader key={i} agentName={block.agentName} status={block.status} turn={block.turn} agentBlocks={block.agentBlocks} />
                ) : (
                  <ToolCallBlock key={i} block={block} onOpenTerminal={onOpenTerminal} />
                )
              )}
              {toolTimeout && msg.isStreaming && (
                <div className="tool-timeout-inline">
                  <div className="tool-timeout-inline-header">
                    <AlertCircle size={14} />
                    <strong>{t('chat.tool_timeout')} {toolTimeout.tool_name}</strong>
                  </div>
                  <p className="tool-timeout-inline-msg">
                    {t("chat.tool_timeout_msg")}
                  </p>
                  <div className="tool-timeout-inline-options">
                    {toolTimeout.options.map(opt => (
                      <button
                        key={opt.value}
                        className="tool-timeout-inline-option"
                        onClick={() => onToolTimeoutChoice(opt.value)}
                      >
                        <strong>{opt.label}</strong>
                        <span>{opt.description}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {/* ask_user 问卷嵌入思考容器内部 */}
              {questionnaire && msg.isStreaming && msg.blocks.some(b => b.type === 'tool_call' && b.toolName === 'ask_user' && b.result === undefined) && (
                <QuestionnaireDisplay data={questionnaire} onSubmit={onQuestionnaireSubmit} />
              )}
            </div>
          )}
        </div>
      )}

      {/* TodoList */}
      {msg.todolist && (
        <TodoListDisplay todolist={msg.todolist} />
      )}

      {/* Sigma Reply Bubble - only when there's final text content */}
      {hasContent && (
        <div className="message sigma-bubble">
          <div className="role-label">{t("chat.sigma")}</div>
          <div className="message-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {msg.content}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 流式文本（逐字显示 + 光标）──

function StreamingText({ text }: { text: string }) {
  return (
    <span className="streaming-text">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {text}
      </ReactMarkdown>
    </span>
  )
}

function ResponseText({ text, isStreaming, showCursor }: { text: string; isStreaming: boolean; showCursor: boolean }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight
    }
  }, [text])

  return (
    <div ref={ref} className="response-text">
      {isStreaming ? (
        <StreamingText text={text} />
      ) : (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {text}
        </ReactMarkdown>
      )}
      {showCursor && <span className="response-text-cursor" />}
    </div>
  )
}

// ── 思考文本块（固定高度 + 自动滚底） ──

function ThinkingText({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight
    }
  }, [text])

  return (
    <div ref={ref} className="thinking-text">{text}</div>
  )
}

// ── 单个工具调用块 ──

function ToolCallBlock({ block, onOpenTerminal }: { block: Extract<Block, { type: 'tool_call' }>; onOpenTerminal?: (tab: TerminalTab) => void }) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(true)
  const hasResult = block.result !== undefined

  useEffect(() => {
    if (hasResult) setCollapsed(true)
  }, [hasResult])

  const resultFirstLine = hasResult ? (block.result || '').split('\n')[0].slice(0, 60) : ''
  const isBash = block.toolName === 'bash' || block.toolName === 'sandbox_run'

  const handleOpenTerminal = () => {
    if (!hasResult || !onOpenTerminal) return
    const cmd = typeof block.toolInput?.command === 'string'
      ? block.toolInput.command
      : typeof block.toolInput?.code === 'string'
        ? block.toolInput.code
        : ''
    onOpenTerminal({
      id: `term-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      title: cmd.slice(0, 40) || block.toolName,
      content: block.result || '',
      command: cmd,
    })
  }

  return (
    <div className={`tool-call-block ${hasResult ? (block.success ? 'success' : 'failed') : 'running'}`}>
      <div className="tool-call-header" onClick={() => hasResult && setCollapsed(v => !v)}>
        <span className="tool-call-icon">
          {!hasResult ? (
            <span className="tool-spinner" />
          ) : block.success ? (
            <CheckCircle2 size={14} />
          ) : (
            <XCircle size={14} />
          )}
        </span>
        <span className="tool-call-name">
          <Wrench size={12} /> {block.displayName ? `@${block.displayName}` : block.toolName}
        </span>
        <span className="tool-call-input-preview">{resultFirstLine}</span>
        {hasResult && (
          <span className="thinking-toggle">
            {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          </span>
        )}
        {isBash && hasResult && onOpenTerminal && (
          <span
            className="tool-call-terminal-btn"
            onClick={(e) => { e.stopPropagation(); handleOpenTerminal() }}
            title={t("chat.open_terminal")}
          >
            <ChevronRight size={12} />
          </span>
        )}
      </div>
      {/* 运行中：显示实时进度日志 */}
      {!hasResult && block.progressLog && block.progressLog.length > 0 && (
        <div className="tool-call-progress-log">
          {block.progressLog.slice(-5).map((line, i) => (
            <div key={i} className="tool-progress-line">{line}</div>
          ))}
        </div>
      )}
      {!collapsed && hasResult && (
        <div className="tool-call-body">
          <div className="tool-call-section">
            <div className="tool-call-label">{t("chat.result")}</div>
            <pre className="tool-call-result">{block.result}</pre>
          </div>
        </div>
      )}
    </div>
  )
}
