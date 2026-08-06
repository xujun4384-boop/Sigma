import { useEffect, useState } from 'react'
import { Search, FolderTree, FileSearch } from 'lucide-react'
import { useTranslation } from '../i18n/I18nContext'
import './ScanningOverlay.css'

interface Props {
  visible: boolean
  phase: 'init' | 'scanning' | 'analyzing' | 'done'
}

const PHASE_CONFIG = {
  init: {
    titleKey: 'scan.first_use',
    subtitleKey: 'scan.preparing',
    icon: FolderTree,
  },
  scanning: {
    titleKey: 'scan.scanning',
    subtitleKey: 'scan.traversing',
    icon: Search,
  },
  analyzing: {
    titleKey: 'scan.analyzing',
    subtitleKey: 'scan.ai_analyzing',
    icon: FileSearch,
  },
  done: {
    titleKey: 'scan.complete',
    subtitleKey: '',
    icon: null,
  },
}

export default function ScanningOverlay({ visible, phase }: Props) {
  const { t } = useTranslation()
  const [dots, setDots] = useState('')

  useEffect(() => {
    if (!visible || phase === 'done') return
    const interval = setInterval(() => {
      setDots(prev => prev.length >= 3 ? '' : prev + '.')
    }, 400)
    return () => clearInterval(interval)
  }, [visible, phase])

  if (!visible) return null

  const config = PHASE_CONFIG[phase]
  const Icon = config.icon
  const isDone = phase === 'done'

  return (
    <div className={`scanning-overlay ${isDone ? 'fade-out' : ''}`}>
      <div className="scanning-container">
        {/* 扫描脉冲环 */}
        <div className="scanning-ring-area">
          <div className="scanning-ring outer" />
          <div className="scanning-ring middle" />
          <div className="scanning-ring inner" />
          <div className="scanning-center">
            {Icon && <Icon size={28} className="scanning-center-icon" />}
          </div>
        </div>

        {/* 扫描线 */}
        <div className="scanning-line-track">
          <div className={`scanning-line ${isDone ? 'done' : ''}`} />
        </div>

        {/* 文字 */}
        <div className="scanning-text">
          <span className="scanning-title">
            {t(config.titleKey)}
            {!isDone && <span className="scanning-dots">{dots}</span>}
          </span>
          {config.subtitleKey && (
            <span className="scanning-subtitle">{t(config.subtitleKey)}</span>
          )}
        </div>

        {/* 文件计数（扫描阶段模拟） */}
        {phase === 'scanning' && (
          <div className="scanning-files-anim">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="scanning-file-line"
                style={{
                  animationDelay: `${i * 0.3}s`,
                  width: `${40 + Math.random() * 40}%`,
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
