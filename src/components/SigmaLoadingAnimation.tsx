import { useEffect, useState } from 'react'
import './SigmaLoadingAnimation.css'

const LETTERS = ['S', 'I', 'G', 'M', 'A']

export default function SigmaLoadingAnimation() {
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveIndex((i) => (i + 1) % LETTERS.length)
    }, 350)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="sigma-loading" aria-label="SIGMA waiting">
      <div className="sigma-loading-bg" aria-hidden="true" />
      <div className="sigma-loading-grid" aria-hidden="true" />
      <div className="sigma-loading-scanline" aria-hidden="true" />
      <div className="sigma-loading-content">
        <div className="sigma-loading-title">
          {LETTERS.map((ch, i) => (
            <span
              key={i}
              className={`sigma-letter ${i === activeIndex ? 'active' : ''}`}
              style={{ '--i': i } as React.CSSProperties}
            >
              {ch}
            </span>
          ))}
        </div>
        <div className="sigma-loading-subtitle">
          <span className="sigma-dot" />
          <span className="sigma-dot" />
          <span className="sigma-dot" />
          <span className="sigma-status">AWAITING INPUT</span>
        </div>
      </div>
    </div>
  )
}
