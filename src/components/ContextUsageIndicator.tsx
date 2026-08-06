import { useTranslation } from '../i18n/I18nContext'
import './ContextUsageIndicator.css'

export interface ContextUsageData {
  current_tokens: number
  max_tokens: number
  usage_percent: number
  usage_ratio: number
}

interface Props {
  usage: ContextUsageData | null
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return `${n}`
}

function getColor(percent: number): string {
  if (percent >= 85) return '#ef4444'  // red
  if (percent >= 60) return '#f59e0b'  // amber
  return '#22c55e'                      // green
}

export default function ContextUsageIndicator({ usage }: Props) {
  const { t } = useTranslation()
  if (!usage) {
    return (
      <div className="context-usage">
        <div className="circular-progress" style={{ '--color': '#6b7280' } as React.CSSProperties}>
          <svg viewBox="0 0 36 36">
            <circle className="bg" cx="18" cy="18" r="15" />
            <circle className="fg" cx="18" cy="18" r="15" strokeDasharray="0 100" />
          </svg>
          <span className="percent-text">--</span>
        </div>
        <span className="context-label">{t("context_usage.context")}</span>
      </div>
    )
  }

  const { usage_percent, current_tokens, max_tokens } = usage
  const color = getColor(usage_percent)
  const circumference = 2 * Math.PI * 15 // r=15
  const dashOffset = circumference * (1 - usage_percent / 100)

  return (
    <div className="context-usage" title={`${formatTokens(current_tokens)} / ${formatTokens(max_tokens)} tokens`}>
      <div className="circular-progress" style={{ '--color': color } as React.CSSProperties}>
        <svg viewBox="0 0 36 36">
          <circle className="bg" cx="18" cy="18" r="15" />
          <circle
            className="fg"
            cx="18" cy="18" r="15"
            strokeDasharray={`${circumference}`}
            strokeDashoffset={`${dashOffset}`}
          />
        </svg>
        <span className="percent-text">{usage_percent}%</span>
      </div>
      <span className="context-label">{formatTokens(current_tokens)}/{formatTokens(max_tokens)}</span>
    </div>
  )
}
