import React from 'react'

interface Props {
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] React render error:', error.message)
    console.error('[ErrorBoundary] Component stack:', info.componentStack)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          padding: '24px',
          color: 'var(--text-primary)',
          background: 'var(--bg-primary)',
          gap: '16px',
        }}>
          <div style={{ fontSize: '48px' }}>&#9888;</div>
          <h3 style={{ margin: 0 }}>界面渲染出错</h3>
          <p style={{ color: 'var(--text-secondary)', margin: 0, textAlign: 'center', maxWidth: '400px' }}>
            {this.state.error?.message || '发生未知错误'}
          </p>
          <button
            onClick={this.handleRetry}
            style={{
              padding: '8px 20px',
              border: 'none',
              borderRadius: '6px',
              background: 'var(--accent)',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
