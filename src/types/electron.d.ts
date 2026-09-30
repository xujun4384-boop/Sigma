export interface LLMEntry {
  id: string
  name: string
  baseUrl: string
  apiKey: string
  model: string
  protocol: 'anthropic' | 'openai'
  provider?: 'generic' | 'deepseek' | 'kimi-code' | 'minimax' | 'ark'
  /** 思考模式：自适应 / 强制开启 / 关闭 */
  thinking?: 'adaptive' | 'enabled' | 'disabled'
  contextSize?: number
  maxTokens?: number
  temperature?: number
  topP?: number
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
  musicGenApiKey: string
  musicGenBaseUrl: string
  musicGenModel: string
  minimaxVideoApiKey: string
  doubaoVoiceApiKey: string
  opendesignLlmId?: string
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
        'json' | 'xml' | 'yaml' | 'shell' | 'powershell' | 'batch' | 'ini' | 'toml' | 'text' | 'image' | 'video'
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
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
