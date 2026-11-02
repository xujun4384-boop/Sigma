/** 思考档位：default = 跟随模型默认（不注入参数） */
export type ThinkingOptionId =
  | 'default' | 'off' | 'on' | 'auto'
  | 'low' | 'medium' | 'high' | 'xhigh' | 'max'

/** 兼容历史配置值，读取时统一归一成 ThinkingOptionId */
export type LegacyThinkingId = 'adaptive' | 'enabled' | 'disabled'

export interface SamplingSpec {
  default: number | null
  min: number | null
  max: number | null
}

/** 模型预设：由后端 /api/model-presets 下发，前端据此渲染表单 */
export interface ModelPreset {
  provider: string
  providerLabel: string
  model: string
  label: string
  family: string
  familyLabel: string
  protocol: 'anthropic' | 'openai'
  baseUrl: string
  context: number
  maxOutput: number | null
  recommendedMaxTokens: number
  vision: boolean
  toolCall: boolean
  thinkingOptions: ThinkingOptionId[]
  thinkingOptionsByProtocol: Record<'anthropic' | 'openai', ThinkingOptionId[]>
  /** 思考档位的补充说明（如关闭会路由到哪个模型） */
  thinkingNote: string
  sampling: {
    temperature: SamplingSpec | null
    topP: SamplingSpec | null
    topK: SamplingSpec | null
  }
}

export interface ProviderPreset {
  id: string
  label: string
  defaultProtocol: 'anthropic' | 'openai'
  baseUrls: Partial<Record<'anthropic' | 'openai', string>>
  /** 是否提供余额/用量查询接口 */
  supportsBalance: boolean
  models: ModelPreset[]
}

export interface FamilyPreset {
  id: string
  label: string
  options: string[]
  thinkingOptions: ThinkingOptionId[]
  temperature: boolean
  topP: boolean
  topK: boolean
}

export interface ModelRegistry {
  providers: ProviderPreset[]
  families: FamilyPreset[]
}

export interface LLMEntry {
  id: string
  name: string
  baseUrl: string
  apiKey: string
  model: string
  protocol: 'anthropic' | 'openai'
  provider?: string
  /** 命中的模型家族，用于未带注册表时的兜底展示 */
  family?: string
  /** 思考档位；历史值 adaptive/enabled/disabled 仍可读入，加载时自动归一 */
  thinking?: ThinkingOptionId | LegacyThinkingId
  /** 以下为用户覆盖值；留空表示使用模型预设默认 */
  contextSize?: number
  maxTokens?: number
  temperature?: number
  topP?: number
  topK?: number
  /** 是否支持图片输入（用户可覆盖预设） */
  vision?: boolean
}

export interface SkillKeysConfig {
  tavilyApiKey: string
  imageGenProvider?: 'ark' | 'minimax'
  imageGenApiKey?: string
  imageGenBaseUrl?: string
  imageGenModel?: string
  imageArkApiKey?: string
  imageArkBaseUrl?: string
  imageArkModel?: string
  imageMinimaxApiKey?: string
  imageMinimaxBaseUrl?: string
  imageMinimaxModel?: string
  /** 音乐生成 provider：腾讯云 TokenHub（默认）/ MiniMax 开放平台 */
  musicGenProvider?: 'tencent_tokenhub' | 'minimax'
  musicGenApiKey?: string
  musicGenBaseUrl?: string
  musicGenModel?: string
  /** 高德 Web端(JS API) Key 与安全密钥（视频里的真实地图/路线） */
  amapJsKey?: string
  amapSecurityCode?: string
  minimaxVideoApiKey: string
  /** 影视级视频生成服务商：minimax（Hailuo）/ ark（火山方舟 Seedance） */
  cinematicVideoProvider?: 'minimax' | 'ark'
  videoArkApiKey?: string
  videoArkBaseUrl?: string
  videoArkModel?: string
  doubaoVoiceApiKey: string
  /** 配音音色 ID（豆包 2.0），留空则用内置默认；可选项来自 /api/doubao-voices */
  doubaoVoiceSpeaker?: string
  webSearchProvider: 'kimi' | 'tavily' | 'custom'
  webSearchApiKey: string
  webSearchBaseUrl: string
  wechatAppId: string
  wechatAppSecret: string
  wechatRelayUrl: string
  wechatRelayKey: string
  fengniaoApiKey: string
  flyaiApiKey: string
  baiduMapAuthToken: string
  mail163Address: string
  mail163AuthCode: string
  mail163SmtpHost: string
  mail163SmtpPort: string
  mail163ImapHost: string
  mail163ImapPort: string
  wecomEmailAddress: string
  wecomEmailAuthCode: string
  wecomEmailSmtpHost: string
  wecomEmailSmtpPort: string
  wecomEmailImapHost: string
  wecomEmailImapPort: string
  gmailAddress: string
  gmailAuthCode: string
  gmailSmtpHost: string
  gmailSmtpPort: string
  gmailImapHost: string
  gmailImapPort: string
  volcAccessKey?: string
  volcSecretKey?: string
  /** 读图专用 LLM：config.llms 里的 id；留空 = 跟随主 LLM */
  visionLlmId?: string
}

export interface KimiConfig {
  baseUrl: string
  apiKey: string
  apiKey2: string
  model: string
  protocol: 'anthropic' | 'openai'
  activeApiKey: 'key1' | 'key2'
  llms: LLMEntry[]
  activeLLMId: string
  skillKeys: SkillKeysConfig
}

export interface FolderTreeItem {
  name: string
  type: 'folder' | 'workspace-folder' | 'file' | 'docx' | 'xlsx' | 'pptx' | 'pdf' | 'markdown' |
        'python' | 'javascript' | 'typescript' | 'java' | 'cpp' | 'c' | 'csharp' |
        'go' | 'rust' | 'php' | 'ruby' | 'swift' | 'kotlin' | 'html' | 'css' |
        'json' | 'xml' | 'yaml' | 'shell' | 'powershell' | 'batch' | 'ini' | 'toml' | 'text' | 'image' | 'video' | 'audio'
  path: string
  children?: FolderTreeItem[]
}

export interface FileSystemChangeEvent {
  type: 'add' | 'addDir' | 'unlink' | 'unlinkDir' | 'change'
  path: string
  fullPath?: string
  name?: string
  fileType?: string
  isDirectory: boolean
  timestamp?: string
}

export interface SigmaConfig {
  backendPort: number
  frontendPort: number
}

export interface NativeThemeInfo {
  shouldUseDarkColors: boolean
}

export interface SystemSound {
  name: string
  path: string
}

export interface ElectronAPI {
  platform: string
  sendMessage: (message: string, config: KimiConfig) => Promise<{ success: boolean; error?: string }>
  checkBackend: () => Promise<{ success: boolean; data?: { status: string }; error?: string }>
  getBackendUrl: () => Promise<{ success: boolean; data?: string; error?: string }>
  getSigmaConfig: () => Promise<{ success: boolean; data?: SigmaConfig; error?: string }>
  saveSigmaConfig: (config: SigmaConfig) => Promise<{ success: boolean; error?: string }>
  getFolderTree: (folderPath?: string) => Promise<{ success: boolean; data?: FolderTreeItem[]; rootPath?: string; error?: string }>
  readFile: (filePath: string) => Promise<{ success: boolean; data?: string | ArrayBuffer; isVideo?: boolean; error?: string }>
  listCanvases: () => Promise<{ success: boolean; data?: string[]; error?: string }>
  loadCanvas: (name: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
  saveCanvas: (name: string, data: unknown) => Promise<{ success: boolean; error?: string }>
  getFileUrl: (filePath: string) => Promise<{ success: boolean; url?: string; error?: string }>
  getWorkingDirectory: () => Promise<{ success: boolean; data?: string; error?: string }>
  getWorkspaceDirectories: () => Promise<{ success: boolean; data?: string[]; error?: string }>
  selectFolder: () => Promise<{ success: boolean; data?: string; error?: string }>
  changeDirectory: (newDir: string) => Promise<{ success: boolean; data?: string; error?: string }>
  addDirectory: (newDir: string) => Promise<{ success: boolean; data?: string; error?: string }>
  removeDirectory: (dirPath: string) => Promise<{ success: boolean; error?: string }>
  onFileSystemChange: (callback: (event: FileSystemChangeEvent) => void) => () => void
  openFile: (filePath: string) => Promise<{ success: boolean; error?: string }>
  showItemInFolder: (filePath: string) => Promise<{ success: boolean; error?: string }>
  deleteFile: (filePath: string) => Promise<{ success: boolean; error?: string }>
  renameFile: (filePath: string, newName: string) => Promise<{ success: boolean; newPath?: string; error?: string }>
  createFile: (parentDir: string, name: string) => Promise<{ success: boolean; path?: string; error?: string }>
  createFolder: (parentDir: string, name: string) => Promise<{ success: boolean; path?: string; error?: string }>
  writeFile: (filePath: string, content: string) => Promise<{ success: boolean; error?: string }>
  pasteFile: (sourcePath: string, targetDir: string) => Promise<{ success: boolean; path?: string; error?: string }>
  moveFiles: (sourcePaths: string[], targetDir: string) => Promise<{ success: boolean; count?: number; conflicts?: string[]; error?: string }>
  copyPath: (filePath: string) => Promise<{ success: boolean; error?: string }>
  addToChat: (filePath: string) => Promise<{ success: boolean; error?: string }>
  convertPptxToImages: (filePath: string) => Promise<{ success: boolean; images?: string[]; count?: number; error?: string }>
  onDragStart: (filePath: string) => void
  copyFiles: (sourcePaths: string[], targetDir: string) => Promise<{ success: boolean; count?: number; conflicts?: string[]; error?: string }>
  getPathForFile: (file: File) => string
  onAddFileToChat: (callback: (fileInfo: { path: string; fullPath: string; name: string; type: string; isDirectory: boolean }) => void) => () => void
  onDirectoryChange: (callback: (data: { path: string }) => void) => () => void
  getNativeTheme: () => Promise<NativeThemeInfo>
  onNativeThemeUpdated: (callback: (info: NativeThemeInfo) => void) => () => void
  isWindowFocused: () => Promise<boolean>
  showNotification: (title: string, body: string) => Promise<boolean>
  getSystemSounds: () => Promise<SystemSound[]>
  previewSound: (soundPath: string) => Promise<boolean>
  enterComputerUseMode: (config: { baseUrl: string; apiKey: string; model: string; protocol: string; name?: string; provider?: string; thinking?: string; contextSize?: number; maxTokens?: number; temperature?: number; topP?: number }) => Promise<{ success: boolean; error?: string }>
  exitComputerUseMode: () => Promise<{ success: boolean; error?: string }>
  getComputerUseMode: () => Promise<{ success: boolean; active: boolean }>
  onComputerUseModeChange: (callback: (active: boolean) => void) => () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
