import React, { useMemo } from 'react'
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued'
import { useTranslation } from '../i18n/I18nContext'
import './CodeDiffViewer.css'

interface CodeDiffViewerProps {
  fileName: string
  fileType: string
  oldText: string
  newText: string
  addedCount: number
  removedCount: number
  modifiedCount: number
  isModifying?: boolean
  onAcknowledge?: () => void
  queueIndex?: number
  queueTotal?: number
  onAcknowledgeAll?: () => void
}

// 根据文件扩展名映射 highlight.js 语言
const LANG_MAP: Record<string, string> = {
  py: 'python', js: 'javascript', ts: 'typescript', tsx: 'typescript',
  jsx: 'javascript', html: 'xml', css: 'css', scss: 'scss', less: 'less',
  java: 'java', c: 'c', cpp: 'cpp', h: 'c', hpp: 'cpp',
  go: 'go', rs: 'rust', rb: 'ruby', php: 'php', swift: 'swift',
  json: 'json', yaml: 'yaml', yml: 'yaml', xml: 'xml', toml: 'ini',
  ini: 'ini', sql: 'sql', sh: 'bash', bat: 'dos', ps1: 'powershell',
  md: 'markdown', txt: 'plaintext', log: 'plaintext', csv: 'plaintext',
}

const CodeDiffViewer: React.FC<CodeDiffViewerProps> = ({
  fileName, fileType, oldText, newText,
  addedCount, removedCount, modifiedCount,
  isModifying = false, onAcknowledge,
  queueIndex = 1, queueTotal = 1, onAcknowledgeAll,
}) => {
  const { t } = useTranslation()

  const lang = useMemo(() => {
    const ext = fileName.split('.').pop()?.toLowerCase() || ''
    return LANG_MAP[ext] || 'plaintext'
  }, [fileName])

  const totalChanges = addedCount + removedCount + modifiedCount

  if (totalChanges === 0) {
    return (
      <div className="code-diff-viewer">
        <div className="diff-header">
          <div className="diff-title-row">
            <h3>📝 {fileName}</h3>
            <div className="diff-actions">
              {queueTotal > 1 && (
                <span className="diff-queue-indicator">
                  {queueIndex}/{queueTotal}
                </span>
              )}
              {onAcknowledge && (
                <button className="diff-acknowledge-button" onClick={onAcknowledge}>
                  {t('diff.acknowledge')}
                </button>
              )}
              {queueTotal > 1 && onAcknowledgeAll && (
                <button className="diff-acknowledge-all-button" onClick={onAcknowledgeAll}>
                  {t('diff.acknowledge_all')}
                </button>
              )}
            </div>
          </div>
          <div className="diff-status no-changes">✓ {t('diff.no_changes')}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="code-diff-viewer">
      <div className="diff-header">
        <div className="diff-title-row">
          <div className="diff-title">
            <h3>📝 {fileName}</h3>
            {isModifying ? (
              <span className="modifying-indicator">🔄 {t('diff.editing')}</span>
            ) : (
              <span className="completed-indicator">✅ {t('diff.done')}</span>
            )}
          </div>
          <div className="diff-actions">
            {queueTotal > 1 && (
              <span className="diff-queue-indicator">
                {queueIndex}/{queueTotal}
              </span>
            )}
            {onAcknowledge && (
              <button className="diff-acknowledge-button" onClick={onAcknowledge}>
                {t('diff.acknowledge')}
              </button>
            )}
            {queueTotal > 1 && onAcknowledgeAll && (
              <button className="diff-acknowledge-all-button" onClick={onAcknowledgeAll}>
                {t('diff.acknowledge_all')}
              </button>
            )}
          </div>
        </div>
        <div className="diff-stats">
          <span className="stat-total">{t('diff.total_changes')} {totalChanges}</span>
          {addedCount > 0 && <span className="stat-added">+ {addedCount}</span>}
          {removedCount > 0 && <span className="stat-removed">- {removedCount}</span>}
          {modifiedCount > 0 && <span className="stat-modified">~ {modifiedCount}</span>}
        </div>
      </div>
      <div className="code-diff-content">
        <ReactDiffViewer
          oldValue={oldText}
          newValue={newText}
          splitView={true}
          compareMethod={DiffMethod.WORDS}
          useDarkTheme={true}
          hideLineNumbers={false}
          showDiffOnly={false}
          extraLinesSurroundingDiff={5}
          styles={{
            variables: {
              dark: {
                diffViewerBackground: '#1e1e1e',
                diffViewerTitleBackground: '#252526',
                diffViewerColor: '#d4d4d4',
                addedBackground: '#1a3a1a',
                addedColor: '#b5e8b5',
                removedBackground: '#3a1a1a',
                removedColor: '#f8b8b8',
                wordAddedBackground: '#2d5a2d',
                wordRemovedBackground: '#5a2d2d',
                addedGutterBackground: '#1a3a1a',
                removedGutterBackground: '#3a1a1a',
                gutterBackground: '#1e1e1e',
                gutterBackgroundDark: '#1a1a1a',
                highlightBackground: '#2a2d2e',
                highlightGutterBackground: '#2a2d2e',
                codeFoldGutterBackground: '#252526',
                codeFoldBackground: '#252526',
                emptyLineBackground: '#1e1e1e',
                gutterColor: '#858585',
                addedGutterColor: '#b5e8b5',
                removedGutterColor: '#f8b8b8',
                codeFoldContentColor: '#858585',
                diffViewerTitleColor: '#cccccc',
                diffViewerBorderColor: '#3c3c3c',
              },
            },
            line: { fontSize: '13px' },
            gutter: { minWidth: '50px' },
          }}
        />
      </div>
    </div>
  )
}

export default CodeDiffViewer
