import React from 'react'
import { useTranslation } from '../i18n/I18nContext'
import './ExcelDiffViewer.css'

interface ExcelCellChange {
  cell: string
  row: number
  col: number
  col_letter: string
  old_value?: string
  new_value?: string
  value?: string
}

interface ExcelSheetDiff {
  added: ExcelCellChange[]
  removed: ExcelCellChange[]
  modified: ExcelCellChange[]
}

interface ExcelDiffData {
  file_path: string
  file_type: string
  file_name: string
  sheets: {
    [sheetName: string]: ExcelSheetDiff
  }
}

interface ExcelDiffViewerProps {
  diffData: ExcelDiffData
  isModifying?: boolean
  onAcknowledge?: () => void
  queueIndex?: number
  queueTotal?: number
  onAcknowledgeAll?: () => void
}

const ExcelDiffViewer: React.FC<ExcelDiffViewerProps> = ({ diffData, isModifying = false, onAcknowledge, queueIndex = 1, queueTotal = 1, onAcknowledgeAll }) => {
  const { t } = useTranslation()
  const [activeSheet, setActiveSheet] = React.useState<string>('')

  // 初始化选中第一个有变化的 sheet
  React.useEffect(() => {
    if (diffData && diffData.sheets) {
      const sheetNames = Object.keys(diffData.sheets)
      if (sheetNames.length > 0 && (!activeSheet || !diffData.sheets[activeSheet])) {
        setActiveSheet(sheetNames[0])
      }
    }
  }, [diffData, activeSheet])

  if (!diffData || !diffData.sheets || Object.keys(diffData.sheets).length === 0) {
    return (
      <div className="excel-diff-viewer">
        <div className="diff-header">
          <div className="diff-title-row">
            <h3>📊 {diffData?.file_name || 'Excel 文件'}</h3>
            <div className="diff-actions">
              {queueTotal > 1 && (
                <span className="diff-queue-indicator">{queueIndex}/{queueTotal}</span>
              )}
              {onAcknowledge && <button className="diff-acknowledge-button" onClick={onAcknowledge}>{t("diff.acknowledge")}</button>}
              {queueTotal > 1 && onAcknowledgeAll && (
                <button className="diff-acknowledge-all-button" onClick={onAcknowledgeAll}>{t("diff.acknowledge_all")}</button>
              )}
            </div>
          </div>
          <div className="diff-status no-changes">
            ✓ {t("diff.no_changes")}
          </div>
        </div>
      </div>
    )
  }

  const sheetNames = Object.keys(diffData.sheets)
  const currentSheetDiff = diffData.sheets[activeSheet]

  // 统计变更数量
  const totalChanges = sheetNames.reduce((sum, sheetName) => {
    const sheet = diffData.sheets[sheetName]
    return sum + sheet.added.length + sheet.removed.length + sheet.modified.length
  }, 0)

  // 构建变更映射表
  const changesMap = new Map<string, ExcelCellChange & { type: 'added' | 'removed' | 'modified' }>()

  if (currentSheetDiff) {
    currentSheetDiff.added.forEach(cell => changesMap.set(cell.cell, { ...cell, type: 'added' }))
    currentSheetDiff.removed.forEach(cell => changesMap.set(cell.cell, { ...cell, type: 'removed' }))
    currentSheetDiff.modified.forEach(cell => changesMap.set(cell.cell, { ...cell, type: 'modified' }))
  }

  // 获取所有涉及到的行列范围
  const getRowColRange = () => {
    const allCells = [...changesMap.values()]
    if (allCells.length === 0) return { minRow: 1, maxRow: 10, minCol: 1, maxCol: 5 }

    const rows = allCells.map(c => c.row)
    const cols = allCells.map(c => c.col)

    return {
      minRow: Math.max(1, Math.min(...rows) - 1),
      maxRow: Math.min(100, Math.max(...rows) + 1),
      minCol: Math.max(1, Math.min(...cols) - 1),
      maxCol: Math.min(26, Math.max(...cols) + 1)
    }
  }

  const { minRow, maxRow, minCol, maxCol } = getRowColRange()

  const getColumnLetter = (colNum: number): string => {
    return String.fromCharCode(64 + colNum)
  }

  return (
    <div className="excel-diff-viewer">
      <div className="diff-header">
        <div className="diff-title-row">
          <div className="diff-title">
            <h3>📊 {diffData.file_name}</h3>
            {isModifying && (
              <span className="modifying-indicator">
                🔄 {t("diff.editing")}
              </span>
            )}
            {!isModifying && (
              <span className="completed-indicator">
                ✅ {t("diff.done")}
              </span>
            )}
          </div>
          <div className="diff-actions">
            {queueTotal > 1 && (
              <span className="diff-queue-indicator">{queueIndex}/{queueTotal}</span>
            )}
            {onAcknowledge && <button className="diff-acknowledge-button" onClick={onAcknowledge}>{t("diff.acknowledge")}</button>}
            {queueTotal > 1 && onAcknowledgeAll && (
              <button className="diff-acknowledge-all-button" onClick={onAcknowledgeAll}>{t("diff.acknowledge_all")}</button>
            )}
          </div>
        </div>
        <div className="diff-stats">
          <span className="stat-total">{t("diff.total_changes")} {totalChanges} {t("diff.added")}</span>
          {currentSheetDiff && (
            <>
              {currentSheetDiff.added.length > 0 && (
                <span className="stat-added">+ {currentSheetDiff.added.length} {t("diff.added")}</span>
              )}
              {currentSheetDiff.removed.length > 0 && (
                <span className="stat-removed">- {currentSheetDiff.removed.length} {t("diff.deleted")}</span>
              )}
              {currentSheetDiff.modified.length > 0 && (
                <span className="stat-modified">~ {currentSheetDiff.modified.length} {t("diff.modified")}</span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Sheet 标签 */}
      {sheetNames.length > 1 && (
        <div className="sheet-tabs">
          {sheetNames.map(sheetName => {
            const sheet = diffData.sheets[sheetName]
            const changeCount = sheet.added.length + sheet.removed.length + sheet.modified.length
            return (
              <button
                key={sheetName}
                className={`sheet-tab ${activeSheet === sheetName ? 'active' : ''}`}
                onClick={() => setActiveSheet(sheetName)}
              >
                {sheetName}
                <span className="change-badge">{changeCount}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* 变更图例 */}
      <div className="diff-legend">
        <span className="legend-item added">
          <span className="legend-color"></span>
          {t("diff.add")}
        </span>
        <span className="legend-item removed">
          <span className="legend-color"></span>
          {t("diff.del")}
        </span>
        <span className="legend-item modified">
          <span className="legend-color"></span>
          {t("diff.mod")}
        </span>
      </div>

      {/* Excel 表格 */}
      <div className="excel-table-container">
        <table className="excel-diff-table">
          <thead>
            <tr>
              <th className="row-header"></th>
              {Array.from({ length: maxCol - minCol + 1 }, (_, i) => minCol + i).map(colNum => (
                <th key={colNum} className="col-header">
                  {getColumnLetter(colNum)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: maxRow - minRow + 1 }, (_, i) => minRow + i).map(rowNum => (
              <tr key={rowNum}>
                <td className="row-header">{rowNum}</td>
                {Array.from({ length: maxCol - minCol + 1 }, (_, i) => minCol + i).map(colNum => {
                  const cellRef = `${getColumnLetter(colNum)}${rowNum}`
                  const change = changesMap.get(cellRef)

                  if (!change) {
                    return <td key={cellRef} className="cell unchanged"></td>
                  }

                  return (
                    <td key={cellRef} className={`cell ${change.type}`}>
                      {change.type === 'modified' && (
                        <div className="cell-diff">
                          <div className="old-value">{change.old_value}</div>
                          <div className="arrow">→</div>
                          <div className="new-value">{change.new_value}</div>
                        </div>
                      )}
                      {change.type === 'added' && (
                        <div className="cell-value added-value">
                          {change.value}
                        </div>
                      )}
                      {change.type === 'removed' && (
                        <div className="cell-value removed-value">
                          {change.value}
                        </div>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 变更详情列表 */}
      <div className="changes-detail">
        <h4>{t("diff.details")}</h4>
        <div className="changes-list">
          {currentSheetDiff.added.map((cell, idx) => (
            <div key={`added-${idx}`} className="change-item added">
              <span className="change-type">{t("diff.new_add")}</span>
              <span className="change-cell">{cell.cell}</span>
              <span className="change-value">{cell.value}</span>
            </div>
          ))}
          {currentSheetDiff.removed.map((cell, idx) => (
            <div key={`removed-${idx}`} className="change-item removed">
              <span className="change-type">{t("diff.new_delete")}</span>
              <span className="change-cell">{cell.cell}</span>
              <span className="change-value strikethrough">{cell.value}</span>
            </div>
          ))}
          {currentSheetDiff.modified.map((cell, idx) => (
            <div key={`modified-${idx}`} className="change-item modified">
              <span className="change-type">{t("diff.new_mod")}</span>
              <span className="change-cell">{cell.cell}</span>
              <span className="change-value">
                <span className="old">{cell.old_value}</span>
                <span className="arrow">→</span>
                <span className="new">{cell.new_value}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default ExcelDiffViewer
export type { ExcelDiffData, ExcelSheetDiff, ExcelCellChange }
