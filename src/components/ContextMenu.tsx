import { useEffect, useRef } from 'react'
import { ExternalLink, Eye, MessageSquare, Edit3, Trash2, FolderOpen, FilePlus, FolderPlus, Copy, ClipboardPaste, Link2 } from 'lucide-react'
import { useTranslation } from '../i18n/I18nContext'
import './ContextMenu.css'

interface Props {
  visible: boolean
  x: number
  y: number
  item: { name: string; path: string; type: string; fullPath: string } | null
  hasClipboard?: boolean
  onClose: () => void
  onAction?: (action: string, item: any) => void
}

export default function ContextMenu({ visible, x, y, item, hasClipboard, onClose, onAction }: Props) {
  const { t } = useTranslation()
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!visible) return
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') onClose() })
    return () => { document.removeEventListener('mousedown', close) }
  }, [visible, onClose])

  useEffect(() => {
    if (!visible || !menuRef.current) return
    const rect = menuRef.current.getBoundingClientRect()
    if (rect.right > window.innerWidth) menuRef.current.style.left = `${x - rect.width}px`
    if (rect.bottom > window.innerHeight) menuRef.current.style.top = `${y - rect.height}px`
  }, [visible, x, y])

  if (!visible || !item) return null

  const isFolder = item.type === 'folder'
  const api = window.electronAPI

  const handleAction = async (action: string) => {
    if (!api) { onClose(); return }
    try {
      switch (action) {
        case 'open': await api.openFile(item.path); break
        case 'preview': onAction?.('preview', item); break
        case 'showInFolder': await api.showItemInFolder(item.path); break
        case 'addToChat': await api.addToChat(item.path); onAction?.('addToChat', item); break
        case 'newFile': onAction?.('newFile', item); break
        case 'newFolder': onAction?.('newFolder', item); break
        case 'copy': onAction?.('copy', item); break
        case 'paste': onAction?.('paste', item); break
        case 'copyPath': await api.copyPath(item.path); break
        case 'rename': onAction?.('rename', item); break
        case 'delete': { await api.deleteFile(item.path); onAction?.('delete', item); break }
      }
    } catch {}
    onClose()
  }

  return (
    <div ref={menuRef} className="context-menu" style={{ position: 'fixed', left: x, top: y, zIndex: 10000 }}>
      <div className="context-menu-header">
        <span className="context-item-name">{item.name}</span>
        <span className="context-item-type">{isFolder ? t("context.folder") : t("context.file")}</span>
      </div>
      <button className="context-menu-item" onClick={() => handleAction('open')}>
        <ExternalLink size={14} /> {t("context.open")}
      </button>
      {!isFolder && (
        <button className="context-menu-item" onClick={() => handleAction('preview')}>
          <Eye size={14} /> {t("context.preview")}
        </button>
      )}
      <button className="context-menu-item" onClick={() => handleAction('showInFolder')}>
        <FolderOpen size={14} /> {t("context.show_in_folder")}
      </button>
      <div className="context-divider" />
      {isFolder && (
        <>
          <button className="context-menu-item" onClick={() => handleAction('newFile')}>
            <FilePlus size={14} /> {t("context.new_file")}
          </button>
          <button className="context-menu-item" onClick={() => handleAction('newFolder')}>
            <FolderPlus size={14} /> {t("context.new_folder")}
          </button>
        </>
      )}
      <button className="context-menu-item" onClick={() => handleAction('copy')}>
        <Copy size={14} /> {t("context.copy")}
      </button>
      <button
        className="context-menu-item"
        onClick={() => handleAction('paste')}
        disabled={!hasClipboard}
      >
        <ClipboardPaste size={14} /> {t("context.paste")}
      </button>
      <button className="context-menu-item" onClick={() => handleAction('copyPath')}>
        <Link2 size={14} /> {t("context.copy_path")}
      </button>
      <div className="context-divider" />
      <button className="context-menu-item" onClick={() => handleAction('addToChat')}>
        <MessageSquare size={14} /> {t("context.add_to_chat")}
      </button>
      <div className="context-divider" />
      <button className="context-menu-item" onClick={() => handleAction('rename')}>
        <Edit3 size={14} /> {t("context.rename")}
      </button>
      <button className="context-menu-item danger" onClick={() => handleAction('delete')}>
        <Trash2 size={14} /> {t("context.delete")}
      </button>
    </div>
  )
}
