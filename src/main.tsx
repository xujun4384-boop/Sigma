import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// 全局捕获外部链接点击：在 Electron 中阻止页面内跳转，改由系统默认浏览器打开
if (window.electronAPI?.platform && typeof document !== 'undefined') {
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    const anchor = target.closest('a') as HTMLAnchorElement | null
    if (!anchor) return
    const href = anchor.getAttribute('href')
    if (!href) return
    if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:')) {
      e.preventDefault()
      window.open(href, '_blank')
    }
  })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
