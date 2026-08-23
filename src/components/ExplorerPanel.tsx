import { useEffect, useState, useCallback, useRef } from 'react'
import { Folder, File, FileText, FileSpreadsheet, Presentation, Image, ChevronRight, ChevronDown, RefreshCw, Trash2, X, FolderOpen, FolderPlus, Edit3, Film, PanelRightClose, FilePlus, FolderDot } from 'lucide-react'
import ContextMenu from './ContextMenu'
import type { FolderTreeItem } from '../types/electron'
import { useTranslation } from '../i18n/I18nContext'
import './ExplorerPanel.css'

interface Props {
  width: number
  onSelectFile: (item: FolderTreeItem) => void
  highlightPath?: string
  onToggleCollapse?: () => void
}

const FILE_ICONS: Record<string, React.ReactNode> = {
  docx: <FileText size={14} color="#4a90d9" />,
  xlsx: <FileSpreadsheet size={14} color="#4caf50" />,
  pptx: <Presentation size={14} color="#ff6d3a" />,
  pdf: <FileText size={14} color="#e74c3c" />,
  image: <Image size={14} />,
  video: <Film size={14} color="#9b59b6" />,
  file: <File size={14} />,
}

// 新建文件时的扩展名选择清单（按类别分组）
// key 为选项展示文本，ext 为实际扩展名（不含点）。扩展名为空表示「无扩展名」。
const FILE_EXT_GROUPS: Array<{ label: string; options: Array<{ label: string; ext: string }> }> = [
  {
    label: '文档与文本',
    options: [
      { label: '.txt', ext: 'txt' },
      { label: '.md', ext: 'md' },
      { label: '.docx', ext: 'docx' },
      { label: '.pdf', ext: 'pdf' },
      { label: '.rtf', ext: 'rtf' },
      { label: '.tex', ext: 'tex' },
    ],
  },
  {
    label: '表格数据',
    options: [
      { label: '.xlsx', ext: 'xlsx' },
      { label: '.csv', ext: 'csv' },
      { label: '.tsv', ext: 'tsv' },
    ],
  },
  {
    label: '演示文稿',
    options: [
      { label: '.pptx', ext: 'pptx' },
      { label: '.key', ext: 'key' },
      { label: '.odp', ext: 'odp' },
    ],
  },
  {
    label: '开发代码',
    options: [
      { label: '.py', ext: 'py' },
      { label: '.js', ext: 'js' },
      { label: '.ts', ext: 'ts' },
      { label: '.tsx', ext: 'tsx' },
      { label: '.jsx', ext: 'jsx' },
      { label: '.java', ext: 'java' },
      { label: '.c', ext: 'c' },
      { label: '.cpp', ext: 'cpp' },
      { label: '.h', ext: 'h' },
      { label: '.hpp', ext: 'hpp' },
      { label: '.cs', ext: 'cs' },
      { label: '.go', ext: 'go' },
      { label: '.rs', ext: 'rs' },
      { label: '.rb', ext: 'rb' },
      { label: '.php', ext: 'php' },
      { label: '.swift', ext: 'swift' },
      { label: '.kt', ext: 'kt' },
      { label: '.sh', ext: 'sh' },
      { label: '.ps1', ext: 'ps1' },
      { label: '.bat', ext: 'bat' },
    ],
  },
  {
    label: '网页前端',
    options: [
      { label: '.html', ext: 'html' },
      { label: '.htm', ext: 'htm' },
      { label: '.css', ext: 'css' },
      { label: '.scss', ext: 'scss' },
      { label: '.less', ext: 'less' },
      { label: '.vue', ext: 'vue' },
      { label: '.svelte', ext: 'svelte' },
    ],
  },
  {
    label: '数据与配置',
    options: [
      { label: '.json', ext: 'json' },
      { label: '.xml', ext: 'xml' },
      { label: '.yaml', ext: 'yaml' },
      { label: '.yml', ext: 'yml' },
      { label: '.toml', ext: 'toml' },
      { label: '.ini', ext: 'ini' },
      { label: '.env', ext: 'env' },
      { label: '.sql', ext: 'sql' },
    ],
  },
  {
    label: '图片与媒体',
    options: [
      { label: '.png', ext: 'png' },
      { label: '.jpg', ext: 'jpg' },
      { label: '.jpeg', ext: 'jpeg' },
      { label: '.gif', ext: 'gif' },
      { label: '.svg', ext: 'svg' },
      { label: '.webp', ext: 'webp' },
      { label: '.bmp', ext: 'bmp' },
      { label: '.ico', ext: 'ico' },
      { label: '.mp4', ext: 'mp4' },
      { label: '.mov', ext: 'mov' },
      { label: '.mp3', ext: 'mp3' },
      { label: '.wav', ext: 'wav' },
      { label: '.flac', ext: 'flac' },
    ],
  },
  {
    label: '其他类型',
    options: [
      { label: '.log', ext: 'log' },
      { label: '.zip', ext: 'zip' },
      { label: '.tar', ext: 'tar' },
      { label: '.gz', ext: 'gz' },
    ],
  },
]

export default function ExplorerPanel({ width, onSelectFile, highlightPath, onToggleCollapse }: Props) {
  const [tree, setTree] = useState<FolderTreeItem[]>([])
  const [rootPath, setRootPath] = useState('')
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; item: any } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{ name: string; path: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [renameTarget, setRenameTarget] = useState<{ name: string; path: string } | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [createTarget, setCreateTarget] = useState<{ kind: 'file' | 'folder'; parentDir: string } | null>(null)
  const [createValue, setCreateValue] = useState('')
  const [selectedGroupIndex, setSelectedGroupIndex] = useState(0)
  const [selectedExt, setSelectedExt] = useState('')
  const [creating, setCreating] = useState(false)
  const [clipboard, setClipboard] = useState<{ path: string; name: string } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [draggingPath, setDraggingPath] = useState<string | null>(null)
  const [dropTargetPath, setDropTargetPath] = useState<string | null>(null)
  const { t } = useTranslation()

  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const treeContainerRef = useRef<HTMLDivElement>(null)

  const loadTree = useCallback(async () => {
    try {
      if (!window.electronAPI?.getFolderTree) return
      const result = await window.electronAPI.getFolderTree()
      if (result.success) {
        setTree(result.data || [])
        setRootPath(result.rootPath || '')
      }
    } catch {}
  }, [])

  useEffect(() => {
    loadTree()
    // electron 原生文件变化事件 (chokidar watcher)
    if (window.electronAPI?.onFileSystemChange) {
      const cleanup = window.electronAPI.onFileSystemChange((event) => {
        if (['add', 'addDir', 'unlink', 'unlinkDir', 'rename', 'delete'].includes(event.type)) {
          loadTree()
        }
      })
      return cleanup
    }
  }, [loadTree])

  const handleContextMenu = (e: React.MouseEvent, item: FolderTreeItem) => {
    e.preventDefault()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      item: { ...item, fullPath: item.path },
    })
  }

  const handleMenuAction = (action: string, item: any) => {
    setContextMenu(null)
    if (action === 'delete') {
      setDeleteTarget({ name: item.name, path: item.path })
    }
    if (action === 'rename') {
      setRenameTarget({ name: item.name, path: item.path })
      setRenameValue(item.name)
    }
    if (action === 'newFile' || action === 'newFolder') {
      const isDir = item.type === 'folder' || item.type === 'workspace-folder'
      const kind = action === 'newFile' ? 'file' : 'folder'
      setCreateTarget({ kind, parentDir: isDir ? item.path : getParentPath(item.path) })
      setCreateValue('')
      setSelectedGroupIndex(0)
      setSelectedExt(kind === 'file' ? 'txt' : '')
    }
    if (action === 'copy') {
      setClipboard({ path: item.path, name: item.name })
    }
    if (action === 'paste') {
      handlePaste(item)
    }
  }

  // 从路径推导父目录（兼容 Windows/Unix 分隔符）
  const getParentPath = (p: string) => {
    const idx = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'))
    return idx > 0 ? p.slice(0, idx) : p
  }

  const handlePaste = async (targetItem: any) => {
    if (!clipboard || !window.electronAPI?.pasteFile) return
    const isDir = targetItem.type === 'folder' || targetItem.type === 'workspace-folder'
    const targetDir = isDir ? targetItem.path : getParentPath(targetItem.path)
    try {
      const result = await window.electronAPI.pasteFile(clipboard.path, targetDir)
      if (result.success) {
        if (isDir) setExpandedPaths(prev => new Set(prev).add(targetDir))
        loadTree()
      } else if (result.error) {
        setNotice(result.error)
      }
    } catch {}
  }

  const handleCreate = async () => {
    if (!createTarget || !createValue.trim()) return
    setCreating(true)
    try {
      const api = window.electronAPI
      let name = createValue.trim()
      if (createTarget.kind === 'file') {
        // 文件名去掉可能已有的扩展名，再用下拉选中的扩展名（如果有）
        const baseName = name.replace(/\.[^./\\]+$/, '')
        const trimmedBase = baseName.replace(/[.\s]+$/, '')
        name = selectedExt ? `${trimmedBase}.${selectedExt}` : trimmedBase
        if (!name || name === '.' + selectedExt) name = selectedExt ? `untitled.${selectedExt}` : 'untitled'
      }
      const result = createTarget.kind === 'file'
        ? await api?.createFile(createTarget.parentDir, name)
        : await api?.createFolder(createTarget.parentDir, name)
      if (result?.success) {
        setExpandedPaths(prev => new Set(prev).add(createTarget.parentDir))
        setCreateTarget(null)
        loadTree()
      } else if (result?.error) {
        setNotice(result.error === 'already_exists' ? t('explorer.error_exists') : result.error)
      }
    } catch {}
    setCreating(false)
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      if (window.electronAPI?.deleteFile) {
        await window.electronAPI.deleteFile(deleteTarget.path)
      }
    } catch {}
    setDeleting(false)
    setDeleteTarget(null)
    loadTree()
  }

  const handleOpenFolder = async () => {
    if (!window.electronAPI?.selectFolder || !window.electronAPI?.changeDirectory) return
    const result = await window.electronAPI.selectFolder()
    if (!result.success || !result.data) return
    await window.electronAPI.changeDirectory(result.data)
    loadTree()
  }

  const handleAddFolder = async () => {
    if (!window.electronAPI?.selectFolder || !window.electronAPI?.addDirectory) return
    const result = await window.electronAPI.selectFolder()
    if (!result.success || !result.data) return
    await window.electronAPI.addDirectory(result.data)
    loadTree()
  }

  const handleRename = async () => {
    if (!renameTarget || !renameValue.trim()) return
    setRenaming(true)
    try {
      if (window.electronAPI?.renameFile) {
        await window.electronAPI.renameFile(renameTarget.path, renameValue.trim())
      }
    } catch {}
    setRenaming(false)
    setRenameTarget(null)
    loadTree()
  }

  // 递归查找文件中所有祖先文件夹路径
  const findAncestorPaths = useCallback((targetPath: string, items: FolderTreeItem[], ancestors: string[]): string[] | null => {
    for (const item of items) {
      if (item.type === 'file' || item.type === 'docx' || item.type === 'xlsx' || item.type === 'pptx' || item.type === 'pdf' || item.type === 'image') {
        if (item.path === targetPath) return ancestors
      }
      if ((item.type === 'folder' || item.type === 'workspace-folder') && item.children) {
        const result = findAncestorPaths(targetPath, item.children, [...ancestors, item.path])
        if (result) return result
      }
    }
    return null
  }, [])

  // highlightPath 变化时自动展开所有祖先文件夹
  useEffect(() => {
    if (!highlightPath || tree.length === 0) return
    const ancestors = findAncestorPaths(highlightPath, tree, [])
    if (ancestors && ancestors.length > 0) {
      setExpandedPaths(prev => {
        const next = new Set(prev)
        for (const p of ancestors) next.add(p)
        return next
      })
    }
  }, [highlightPath, tree, findAncestorPaths])

  // 展开完成后滚动高亮文件到可见区域
  useEffect(() => {
    if (!highlightPath) return
    // 等 DOM 渲染完（展开动画后）
    const timer = setTimeout(() => {
      const el = treeContainerRef.current?.querySelector('[data-highlighted="true"]')
      if (el) {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    }, 100)
    return () => clearTimeout(timer)
  }, [highlightPath, expandedPaths])

  const handleDrop = async (sourcePath: string, targetPath: string) => {
    setDropTargetPath(null)
    setDraggingPath(null)
    if (!sourcePath || sourcePath === targetPath || !window.electronAPI?.moveFiles) return
    const result = await window.electronAPI.moveFiles([sourcePath], targetPath)
    if (!result.success) {
      const message = result.error === 'already_exists'
        ? t('explorer.move_exists')
        : result.error === 'invalid_target'
          ? t('explorer.move_invalid_target')
          : t('explorer.move_failed')
      setNotice(message)
      return
    }
    loadTree()
  }

  const handleDragEnd = () => {
    setDraggingPath(null)
    setDropTargetPath(null)
  }

  const getTreeItemProps = (item: FolderTreeItem) => ({
    item,
    onSelect: onSelectFile,
    onContextMenu: handleContextMenu,
    expandedPaths,
    onToggleExpand: (path: string) => setExpandedPaths(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path); else next.add(path)
      return next
    }),
    highlightPath,
    draggingPath,
    dropTargetPath,
    onDragStart: (path: string) => setDraggingPath(path),
    onDragEnd: handleDragEnd,
    onDragOver: (path: string) => setDropTargetPath(path),
    onDragLeave: (path: string) => setDropTargetPath(prev => prev === path ? null : prev),
    onDrop: handleDrop,
  })

  return (
    <div className="explorer-panel" style={{ width }}>
      <div className="explorer-header">
        <span className="explorer-title">{t("explorer.title")}</span>
        <div className="explorer-header-actions">
          <button className="explorer-collapse-btn" onClick={onToggleCollapse} title="折叠资源管理器">
            <PanelRightClose size={14} />
          </button>
          <button className="explorer-refresh" onClick={() => { if (rootPath) { setCreateTarget({ kind: 'file', parentDir: rootPath }); setCreateValue(''); setSelectedGroupIndex(0); setSelectedExt('txt') } }} title={t("explorer.new_file")}>
            <FilePlus size={14} />
          </button>
          <button className="explorer-refresh" onClick={() => { if (rootPath) { setCreateTarget({ kind: 'folder', parentDir: rootPath }); setCreateValue(''); setSelectedGroupIndex(0); setSelectedExt('') } }} title={t("explorer.new_folder")}>
            <FolderDot size={14} />
          </button>
          <button className="explorer-refresh" onClick={handleOpenFolder} title={t("explorer.open_folder")}>
            <FolderOpen size={14} />
          </button>
          <button className="explorer-refresh" onClick={handleAddFolder} title={t("explorer.add_folder")}>
            <FolderPlus size={14} />
          </button>
          <button className="explorer-refresh" onClick={loadTree} title={t("explorer.refresh")}>
            <RefreshCw size={14} />
          </button>
        </div>
      </div>
      <div
        className="explorer-tree"
        ref={treeContainerRef}
        onDragOver={e => {
          if (e.dataTransfer.types.includes('application/x-sigma-path')) {
            e.preventDefault()
            e.dataTransfer.dropEffect = 'move'
          }
        }}
      >
        {tree.map((item, i) => (
          <TreeItem
            key={i}
            level={0}
            {...getTreeItemProps(item)}
          />
        ))}
      </div>

      {contextMenu && (
        <ContextMenu
          visible={true}
          x={contextMenu.x}
          y={contextMenu.y}
          item={contextMenu.item}
          hasClipboard={!!clipboard}
          onClose={() => setContextMenu(null)}
          onAction={handleMenuAction}
        />
      )}

      {/* 轻量提示条（复制路径成功、错误信息等） */}
      {notice && (
        <div className="explorer-notice" onAnimationEnd={() => setNotice(null)}>
          {notice}
        </div>
      )}

      {/* Create File/Folder Modal */}
      {createTarget && (
        <div className="explorer-modal-backdrop" onClick={() => setCreateTarget(null)}>
          <div className="explorer-modal" onClick={e => e.stopPropagation()}>
            <div className="explorer-modal-icon explorer-modal-icon-accent">
              {createTarget.kind === 'file' ? <FilePlus size={24} /> : <FolderDot size={24} />}
            </div>
            <div className="explorer-modal-text">
              <p className="explorer-modal-title">
                {createTarget.kind === 'file' ? t("explorer.new_file") : t("explorer.new_folder")}
              </p>
              <p className="explorer-modal-name">{createTarget.parentDir}</p>
            </div>
            <div className="explorer-create-form">
              <label className="explorer-form-field explorer-form-field-full">
                <span className="explorer-form-label">{t("explorer.file_name_label")}</span>
                <input
                  className="rename-input explorer-file-name-input"
                  value={createValue}
                  placeholder={createTarget.kind === 'file' ? t("explorer.new_file_placeholder") : t("explorer.new_folder_placeholder")}
                  onChange={e => {
                    const v = e.target.value
                    setCreateValue(v)
                    if (createTarget.kind === 'file') {
                      const m = v.match(/\.([^./\\]+)$/)
                      const ext = m ? m[1].toLowerCase() : ''
                      setSelectedExt(ext)
                      const groupIndex = FILE_EXT_GROUPS.findIndex(group => group.options.some(option => option.ext === ext))
                      if (groupIndex >= 0) setSelectedGroupIndex(groupIndex)
                    }
                  }}
                  onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setCreateTarget(null) }}
                  autoFocus
                />
              </label>
              {createTarget.kind === 'file' && (
                <div className="explorer-type-picker">
                  <label className="explorer-form-field">
                    <span className="explorer-form-label">{t("explorer.file_category_label")}</span>
                    <select
                      className="explorer-form-select"
                      value={selectedGroupIndex}
                      onChange={e => {
                        const nextIndex = Number(e.target.value)
                        const nextGroup = FILE_EXT_GROUPS[nextIndex]
                        setSelectedGroupIndex(nextIndex)
                        setSelectedExt(nextGroup.options[0]?.ext || '')
                      }}
                    >
                      {FILE_EXT_GROUPS.map((group, index) => (
                        <option key={group.label} value={index}>{group.label}</option>
                      ))}
                    </select>
                  </label>
                  <label className="explorer-form-field">
                    <span className="explorer-form-label">{t("explorer.file_format_label")}</span>
                    <select
                      className="explorer-form-select"
                      value={selectedExt}
                      onChange={e => setSelectedExt(e.target.value)}
                      title={t("explorer.ext_select_title")}
                    >
                      <option value="">{t("explorer.ext_none")}</option>
                      {FILE_EXT_GROUPS[selectedGroupIndex]?.options.map(option => (
                        <option key={option.ext} value={option.ext}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </div>
            <div className="explorer-modal-actions">
              <button className="modal-btn modal-btn-cancel" onClick={() => setCreateTarget(null)} disabled={creating}>
                {t("explorer.cancel")}
              </button>
              <button className="modal-btn modal-btn-delete" onClick={handleCreate} disabled={creating || !createValue.trim()}>
                {creating ? t("explorer.creating") : t("explorer.create")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="explorer-modal-backdrop" onClick={() => setDeleteTarget(null)}>
          <div className="explorer-modal" onClick={e => e.stopPropagation()}>
            <div className="explorer-modal-icon">
              <Trash2 size={24} />
            </div>
            <div className="explorer-modal-text">
              <p className="explorer-modal-title">{t("explorer.confirm_delete")}</p>
              <p className="explorer-modal-name">"{deleteTarget.name}"</p>
              <p className="explorer-modal-warning">{t("explorer.delete_warning")}</p>
            </div>
            <div className="explorer-modal-actions">
              <button className="modal-btn modal-btn-cancel" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                {t("explorer.cancel")}
              </button>
              <button className="modal-btn modal-btn-delete" onClick={handleConfirmDelete} disabled={deleting}>
                {deleting ? t("explorer.deleting") : t("explorer.delete")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Modal */}
      {renameTarget && (
        <div className="explorer-modal-backdrop" onClick={() => setRenameTarget(null)}>
          <div className="explorer-modal" onClick={e => e.stopPropagation()}>
            <div className="explorer-modal-icon">
              <Edit3 size={24} />
            </div>
            <div className="explorer-modal-text">
              <p className="explorer-modal-title">{t("explorer.rename")}</p>
            </div>
            <input
              className="rename-input"
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleRename(); if (e.key === 'Escape') setRenameTarget(null) }}
              autoFocus
            />
            <div className="explorer-modal-actions">
              <button className="modal-btn modal-btn-cancel" onClick={() => setRenameTarget(null)} disabled={renaming}>
                {t("explorer.cancel")}
              </button>
              <button className="modal-btn modal-btn-delete" onClick={handleRename} disabled={renaming || !renameValue.trim()}>
                {renaming ? t("explorer.renaming") : t("explorer.rename")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function TreeItem({ item, level, onSelect, onContextMenu, expandedPaths, onToggleExpand, highlightPath, draggingPath, dropTargetPath, onDragStart, onDragEnd, onDragOver, onDragLeave, onDrop }: {
  item: FolderTreeItem; level: number;
  onSelect: (item: FolderTreeItem) => void;
  onContextMenu: (e: React.MouseEvent, item: FolderTreeItem) => void;
  expandedPaths: Set<string>;
  onToggleExpand: (path: string) => void;
  highlightPath?: string;
  draggingPath: string | null;
  dropTargetPath: string | null;
  onDragStart: (path: string) => void;
  onDragEnd: () => void;
  onDragOver: (path: string) => void;
  onDragLeave: (path: string) => void;
  onDrop: (sourcePath: string, targetPath: string) => void;
}) {
  const isWorkspace = item.type === 'workspace-folder'
  const isFolder = item.type === 'folder' || item.type === 'workspace-folder'
  const hasChildren = isFolder && item.children && item.children.length > 0
  const expanded = expandedPaths.has(item.path) || isWorkspace
  const isHighlighted = !!highlightPath && item.path === highlightPath
  const isDragging = draggingPath === item.path
  const isDropTarget = isFolder && dropTargetPath === item.path && draggingPath !== item.path

  const icon = isFolder
    ? (expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />)
    : null

  const fileIcon = isFolder
    ? (isWorkspace ? <FolderOpen size={14} /> : <Folder size={14} />)
    : (FILE_ICONS[item.type] || <File size={14} />)

  const handleClick = () => {
    if (isFolder) {
      onToggleExpand(item.path)
    } else {
      onSelect(item)
    }
  }

  return (
    <div>
      <div
        className={`explorer-item ${isFolder ? 'folder' : ''} ${isWorkspace ? 'workspace-root' : ''} ${isHighlighted ? 'selected' : ''} ${isDragging ? 'dragging' : ''} ${isDropTarget ? 'drop-target' : ''}`}
        style={{ paddingLeft: 12 + level * 14 }}
        draggable={!isWorkspace}
        onDragStart={e => {
          e.dataTransfer.effectAllowed = 'copyMove'
          e.dataTransfer.setData('application/x-sigma-path', item.path)
          e.dataTransfer.setData('application/x-sigma-paths', JSON.stringify([{ path: item.path, name: item.name }]))
          e.dataTransfer.setData('text/plain', item.path)
          onDragStart(item.path)
        }}
        onDragEnd={onDragEnd}
        onDragEnter={e => {
          if (!isFolder || draggingPath === item.path) return
          e.preventDefault()
          onDragOver(item.path)
        }}
        onDragOver={e => {
          if (!isFolder || draggingPath === item.path) return
          e.preventDefault()
          e.stopPropagation()
          e.dataTransfer.dropEffect = 'move'
          onDragOver(item.path)
        }}
        onDragLeave={e => {
          if (isFolder && !e.currentTarget.contains(e.relatedTarget as Node)) onDragLeave(item.path)
        }}
        onDrop={e => {
          if (!isFolder) return
          e.preventDefault()
          e.stopPropagation()
          const sourcePath = e.dataTransfer.getData('application/x-sigma-path') || e.dataTransfer.getData('text/plain')
          onDrop(sourcePath, item.path)
        }}
        onClick={handleClick}
        onContextMenu={(e) => onContextMenu(e, item)}
        data-highlighted={isHighlighted ? 'true' : undefined}
      >
        <span className="explorer-arrow">{icon}</span>
        <span className={`explorer-icon ${item.type}`}>{fileIcon}</span>
        <span className="explorer-name">{item.name}</span>
      </div>
      {isFolder && expanded && hasChildren && item.children!.map((child, i) => (
        <TreeItem
          key={i}
          level={level + 1}
          item={child}
          onSelect={onSelect}
          onContextMenu={onContextMenu}
          expandedPaths={expandedPaths}
          onToggleExpand={onToggleExpand}
          highlightPath={highlightPath}
          draggingPath={draggingPath}
          dropTargetPath={dropTargetPath}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
        />
      ))}
    </div>
  )
}
