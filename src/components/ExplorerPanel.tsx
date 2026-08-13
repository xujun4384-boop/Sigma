import { useEffect, useState, useCallback, useRef } from 'react'
import { Folder, File, FileText, FileSpreadsheet, Presentation, Image, ChevronRight, ChevronDown, RefreshCw, Trash2, X, FolderOpen, FolderPlus, Edit3, Film, PanelRightClose } from 'lucide-react'
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

export default function ExplorerPanel({ width, onSelectFile, highlightPath, onToggleCollapse }: Props) {
  const [tree, setTree] = useState<FolderTreeItem[]>([])
  const [rootPath, setRootPath] = useState('')
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; item: any } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{ name: string; path: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [renameTarget, setRenameTarget] = useState<{ name: string; path: string } | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renaming, setRenaming] = useState(false)
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

  return (
    <div className="explorer-panel" style={{ width }}>
      <div className="explorer-header">
        <span className="explorer-title">{t("explorer.title")}</span>
        <div className="explorer-header-actions">
          <button className="explorer-collapse-btn" onClick={onToggleCollapse} title="折叠资源管理器">
            <PanelRightClose size={14} />
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
      <div className="explorer-tree" ref={treeContainerRef}>
        {tree.map((item, i) => (
          <TreeItem
            key={i} item={item} level={0}
            onSelect={onSelectFile}
            onContextMenu={handleContextMenu}
            expandedPaths={expandedPaths}
            onToggleExpand={(path) => setExpandedPaths(prev => {
              const next = new Set(prev)
              if (next.has(path)) next.delete(path); else next.add(path)
              return next
            })}
            highlightPath={highlightPath}
          />
        ))}
      </div>

      {contextMenu && (
        <ContextMenu
          visible={true}
          x={contextMenu.x}
          y={contextMenu.y}
          item={contextMenu.item}
          onClose={() => setContextMenu(null)}
          onAction={handleMenuAction}
        />
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

function TreeItem({ item, level, onSelect, onContextMenu, expandedPaths, onToggleExpand, highlightPath }: {
  item: FolderTreeItem; level: number;
  onSelect: (item: FolderTreeItem) => void;
  onContextMenu: (e: React.MouseEvent, item: FolderTreeItem) => void;
  expandedPaths: Set<string>;
  onToggleExpand: (path: string) => void;
  highlightPath?: string;
}) {
  const isWorkspace = item.type === 'workspace-folder'
  const isFolder = item.type === 'folder' || item.type === 'workspace-folder'
  const hasChildren = isFolder && item.children && item.children.length > 0
  const expanded = expandedPaths.has(item.path) || isWorkspace
  const isHighlighted = !!highlightPath && item.path === highlightPath

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
        className={`explorer-item ${isFolder ? 'folder' : ''} ${isWorkspace ? 'workspace-root' : ''} ${isHighlighted ? 'selected' : ''}`}
        style={{ paddingLeft: 12 + level * 14 }}
        onClick={handleClick}
        onContextMenu={(e) => onContextMenu(e, item)}
        data-highlighted={isHighlighted ? 'true' : undefined}
      >
        <span className="explorer-arrow">{icon}</span>
        <span className={`explorer-icon ${item.type}`}>{fileIcon}</span>
        <span className="explorer-name">{item.name}</span>
      </div>
      {isFolder && expanded && hasChildren && item.children!.map((child, i) => (
        <TreeItem key={i} item={child} level={level + 1} onSelect={onSelect} onContextMenu={onContextMenu} expandedPaths={expandedPaths} onToggleExpand={onToggleExpand} highlightPath={highlightPath} />
      ))}
    </div>
  )
}
