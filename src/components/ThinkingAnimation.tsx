import { useState, useEffect } from 'react'
import { useTranslation } from '../i18n/I18nContext'
import './ThinkingAnimation.css'

interface Props {
  isStreaming?: boolean
}

const STATES = [
  'Sigma is thinking...',
  'Reading files...',
  'Searching...',
  'Analyzing content...',
  'Generating output...',
  'Compiling results...',
]

export default function ThinkingAnimation({ isStreaming = true }: Props) {
  const { t } = useTranslation()
  const labels = [
    t("thinking.default"),
    t("thinking.reading"),
    t("thinking.searching"),
    t("thinking.analyzing"),
    t("thinking.generating"),
    t("thinking.compiling"),
  ]
  const [index, setIndex] = useState(0)
  const [transitioning, setTransitioning] = useState(false)

  useEffect(() => {
    if (!isStreaming) return
    const timer = setInterval(() => {
      setTransitioning(true)
      setTimeout(() => {
        setIndex(prev => (prev + 1) % labels.length)
        setTransitioning(false)
      }, 300)
    }, 2500)
    return () => clearInterval(timer)
  }, [isStreaming, labels.length])

  if (!isStreaming) return null

  return (
    <div className="thinking-animation">
      <div className="thinking-cursor">*</div>
      <div className={`thinking-state ${transitioning ? 'out' : 'in'}`}>
        {labels[index]}
      </div>
    </div>
  )
}
