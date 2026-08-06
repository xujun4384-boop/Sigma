import React from 'react'
import { useTranslation } from '../i18n/I18nContext'
import './DocumentDiffViewer.css'

interface TextChange {
  index?: number
  line?: number
  old_line?: number | null
  new_line?: number | null
  text?: string
  old_text?: string
  new_text?: string
}

interface ChangeGroup {
  added: TextChange[]
  removed: TextChange[]
  modified: TextChange[]
}

interface DocumentDiffData {
  file_path: string
  file_type: string
  file_name: string
  paragraphs?: ChangeGroup
  lines?: ChangeGroup
}

interface DocumentDiffViewerProps {
  diffData: DocumentDiffData
  isModifying?: boolean
  onAcknowledge?: () => void
}

const DocumentDiffViewer: React.FC<DocumentDiffViewerProps> = ({ diffData, isModifying = false, onAcknowledge }) => {
  const { t } = useTranslation()
  const group = diffData.paragraphs || diffData.lines
  const unitLabel = diffData.file_type === 'markdown' ? t("diff.line") : t("diff.paragraph")
  const icon = diffData.file_type === 'markdown' ? '📝' : '📄'

  if (!group) {
    return (
      <div className="document-diff-viewer">
        <div className="diff-header">
          <div className="diff-title-row">
            <h3>{icon} {diffData.file_name}</h3>
            {onAcknowledge && <button className="diff-acknowledge-button" onClick={onAcknowledge}>{t("diff.acknowledge")}</button>}
          </div>
          <div className="diff-status no-changes">{t("diff.unsupported")}</div>
        </div>
      </div>
    )
  }

  const totalChanges = group.added.length + group.removed.length + group.modified.length

  if (totalChanges === 0) {
    return (
      <div className="document-diff-viewer">
        <div className="diff-header">
          <div className="diff-title-row">
            <h3>{icon} {diffData.file_name}</h3>
            {onAcknowledge && <button className="diff-acknowledge-button" onClick={onAcknowledge}>{t("diff.acknowledge")}</button>}
          </div>
          <div className="diff-status no-changes">{t("diff.no_changes")}</div>
        </div>
      </div>
    )
  }

  const getLocation = (change: TextChange, fallback: string) => {
    if (change.line !== undefined) return `${t("diff.line_n")} ${change.line} ${t("diff.line")}`
    if (change.index !== undefined) return `${t("diff.line_n")} ${change.index + 1} ${t("diff.paragraph")}`
    if (change.old_line || change.new_line) {
      const oldPart = change.old_line ? `${t("diff.old")} ${change.old_line}` : `${t("diff.old")} -`
      const newPart = change.new_line ? `${t("diff.new")} ${change.new_line}` : `${t("diff.new")} -`
      return `${oldPart} → ${newPart}`
    }
    return fallback
  }

  return (
    <div className="document-diff-viewer">
      <div className="diff-header">
        <div className="diff-title-row">
          <div className="diff-title">
            <h3>{icon} {diffData.file_name}</h3>
            {isModifying ? (
              <span className="modifying-indicator">{t("diff.editing")}</span>
            ) : (
              <span className="completed-indicator">{t("diff.done")}</span>
            )}
          </div>
          {onAcknowledge && <button className="diff-acknowledge-button" onClick={onAcknowledge}>{t("diff.acknowledge")}</button>}
        </div>
        <div className="diff-stats">
          <span className="stat-total">{t("diff.total_changes")} {totalChanges} {t("diff.added")}</span>
          {group.added.length > 0 && <span className="stat-added">+ {group.added.length} {t("diff.added")}</span>}
          {group.removed.length > 0 && <span className="stat-removed">- {group.removed.length} {t("diff.deleted")}</span>}
          {group.modified.length > 0 && <span className="stat-modified">~ {group.modified.length} {t("diff.modified")}</span>}
        </div>
      </div>

      <div className="diff-legend">
        <span className="legend-item added"><span className="legend-color"></span>{t("diff.add")}</span>
        <span className="legend-item removed"><span className="legend-color"></span>{t("diff.del")}</span>
        <span className="legend-item modified"><span className="legend-color"></span>{t("diff.mod")}</span>
      </div>

      <div className="document-diff-content">
        {group.added.map((change, index) => (
          <div key={`added-${index}`} className="document-change added">
            <div className="document-change-meta">+ {t("diff.add")} {unitLabel} · {getLocation(change, `${t("diff.add")} ${index + 1}`)}</div>
            <pre className="document-change-text added-text">{change.text}</pre>
          </div>
        ))}

        {group.removed.map((change, index) => (
          <div key={`removed-${index}`} className="document-change removed">
            <div className="document-change-meta">- {t("diff.del")} {unitLabel} · {getLocation(change, `${t("diff.del")} ${index + 1}`)}</div>
            <pre className="document-change-text removed-text">{change.text}</pre>
          </div>
        ))}

        {group.modified.map((change, index) => (
          <div key={`modified-${index}`} className="document-change modified">
            <div className="document-change-meta">~ {t("diff.mod")} {unitLabel} · {getLocation(change, `${t("diff.mod")} ${index + 1}`)}</div>
            <div className="document-change-pair">
              <pre className="document-change-text removed-text">{change.old_text}</pre>
              <pre className="document-change-text added-text">{change.new_text}</pre>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default DocumentDiffViewer
export type { DocumentDiffData, TextChange, ChangeGroup }
