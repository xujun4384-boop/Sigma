const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,

  // Chat
  sendMessage: (message, config) => ipcRenderer.invoke('send-message', message, config),
  checkBackend: () => ipcRenderer.invoke('check-backend'),
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),

  // Config
  getSigmaConfig: () => ipcRenderer.invoke('get-sigma-config'),
  saveSigmaConfig: (config) => ipcRenderer.invoke('save-sigma-config', config),

  // File Tree
  getFolderTree: (folderPath) => ipcRenderer.invoke('get-folder-tree', folderPath),
  readFile: (filePath) => ipcRenderer.invoke('read-file', filePath),
  listCanvases: () => ipcRenderer.invoke('canvas-list'),
  loadCanvas: (name) => ipcRenderer.invoke('canvas-load', name),
  saveCanvas: (name, data) => ipcRenderer.invoke('canvas-save', name, data),
  getFileUrl: (filePath) => ipcRenderer.invoke('get-file-url', filePath),
  getWorkingDirectory: () => ipcRenderer.invoke('get-working-directory'),
  getWorkspaceDirectories: () => ipcRenderer.invoke('get-workspace-directories'),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  changeDirectory: (newDir) => ipcRenderer.invoke('change-directory', newDir),
  addDirectory: (newDir) => ipcRenderer.invoke('add-directory', newDir),
  removeDirectory: (dirPath) => ipcRenderer.invoke('remove-directory', dirPath),

  // File System Events
  onFileSystemChange: (callback) => {
    const listener = (event, data) => callback(data)
    ipcRenderer.on('file-system-change', listener)
    return () => ipcRenderer.removeListener('file-system-change', listener)
  },

  // File Operations
  openFile: (filePath) => ipcRenderer.invoke('file-open', filePath),
  showItemInFolder: (filePath) => ipcRenderer.invoke('file-show-in-folder', filePath),
  deleteFile: (filePath) => ipcRenderer.invoke('file-delete', filePath),
  renameFile: (filePath, newName) => ipcRenderer.invoke('file-rename', filePath, newName),
  createFile: (parentDir, name) => ipcRenderer.invoke('file-create', parentDir, name),
  createFolder: (parentDir, name) => ipcRenderer.invoke('folder-create', parentDir, name),
  writeFile: (filePath, content) => ipcRenderer.invoke('file-write', filePath, content),
  pasteFile: (sourcePath, targetDir) => ipcRenderer.invoke('file-paste', sourcePath, targetDir),
  moveFiles: (sourcePaths, targetDir) => ipcRenderer.invoke('file-move', sourcePaths, targetDir),
  copyPath: (filePath) => ipcRenderer.invoke('copy-path', filePath),
  addToChat: (filePath) => ipcRenderer.invoke('file-add-to-chat', filePath),
  convertPptxToImages: (filePath) => ipcRenderer.invoke('convert-pptx', filePath),

  onAddFileToChat: (callback) => {
    const listener = (event, fileInfo) => callback(fileInfo)
    ipcRenderer.on('add-file-to-chat', listener)
    return () => ipcRenderer.removeListener('add-file-to-chat', listener)
  },

  // Directory Change
  onDirectoryChange: (callback) => {
    const listener = (event, data) => callback(data)
    ipcRenderer.on('directory-changed', listener)
    return () => ipcRenderer.removeListener('directory-changed', listener)
  },

  // Theme
  getNativeTheme: () => ipcRenderer.invoke('get-native-theme'),
  onNativeThemeUpdated: (callback) => {
    ipcRenderer.invoke('on-native-theme-updated')
    const listener = (event, data) => callback(data)
    ipcRenderer.on('native-theme-updated', listener)
    return () => ipcRenderer.removeListener('native-theme-updated', listener)
  },

  // Notification
  isWindowFocused: () => ipcRenderer.invoke('is-window-focused'),
  showNotification: (title, body) => ipcRenderer.invoke('show-notification', title, body),
  getSystemSounds: () => ipcRenderer.invoke('get-system-sounds'),
  previewSound: (soundPath) => ipcRenderer.invoke('preview-sound', soundPath),
})
