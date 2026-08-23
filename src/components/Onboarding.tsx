import { useState, useCallback } from 'react'
import { Sparkles, Eye, EyeOff, Play, Loader2, CheckCircle2, XCircle, ArrowRight } from 'lucide-react'
import { useTranslation } from '../i18n/I18nContext'
import { getBackendUrl } from '../utils/config'
import type { LLMEntry } from '../types/electron'
import './Onboarding.css'

interface Props {
  onComplete: (entry: LLMEntry) => void
}

export default function Onboarding({ onComplete }: Props) {
  const { t } = useTranslation()
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [protocol, setProtocol] = useState<'anthropic' | 'openai'>('anthropic')
  const [showKey, setShowKey] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testPassed, setTestPassed] = useState(false)
  const [testError, setTestError] = useState('')
  const [loading, setLoading] = useState(false)

  const hasConfig = apiKey.trim().length > 0

  const resetTest = useCallback(() => {
    setTestPassed(false)
    setTestError('')
  }, [])

  const handleTest = async () => {
    if (!hasConfig) return
    setTesting(true)
    setTestPassed(false)
    setTestError('')
    try {
      const base = await getBackendUrl()
      const resp = await fetch(`${base}/api/test-llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl, apiKey, model, protocol }),
      })
      const data = await resp.json()
      if (data.success) {
        setTestPassed(true)
      } else {
        setTestError(data.error || 'Unknown error')
      }
    } catch (e: any) {
      setTestError(e.message || 'Network error')
    } finally {
      setTesting(false)
    }
  }

  const handleGetStarted = () => {
    if (!testPassed) return
    setLoading(true)
    const entry: LLMEntry = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      name: model,
      baseUrl,
      apiKey,
      model,
      protocol,
    }
    onComplete(entry)
  }

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-container">
        <div className="onboarding-hero">
          <div className="onboarding-logo">
            <Sparkles size={36} />
          </div>
          <h1>{t("onboarding.title")}</h1>
          <p className="onboarding-desc">
            {t("onboarding.subtitle")}
          </p>
        </div>

        <div className="onboarding-form">
          <div className="onboarding-field">
            <label>{t("onboarding.protocol")}</label>
            <div className="onboarding-toggle">
              <button
                className={protocol === 'anthropic' ? 'active' : ''}
                onClick={() => { setProtocol('anthropic'); resetTest() }}
              >Anthropic</button>
              <button
                className={protocol === 'openai' ? 'active' : ''}
                onClick={() => { setProtocol('openai'); resetTest() }}
              >OpenAI</button>
            </div>
          </div>

          <div className="onboarding-field">
            <label>{t("onboarding.base_url")}</label>
            <input
              type="text"
              value={baseUrl}
              onChange={e => { setBaseUrl(e.target.value); resetTest() }}
              placeholder="https://api.kimi.com/coding"
            />
          </div>

          <div className="onboarding-field">
            <label>{t("onboarding.model")}</label>
            <input
              type="text"
              value={model}
              onChange={e => { setModel(e.target.value); resetTest() }}
              placeholder="kimi-for-coding"
            />
          </div>

          <div className="onboarding-field">
            <label>{t("onboarding.api_key")}</label>
            <div className="onboarding-key-row">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={e => { setApiKey(e.target.value); resetTest() }}
                onKeyDown={e => { if (e.key === 'Enter' && hasConfig) handleTest() }}
                placeholder="sk-..."
                autoFocus
              />
              <button className="onboarding-key-toggle" onClick={() => setShowKey(v => !v)}>
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <span className="onboarding-hint">
              {t("onboarding.api_key_hint")}
            </span>
          </div>

          <div className="onboarding-actions">
            {/* Step 1: Test Connection */}
            <button
              className="onboarding-btn test"
              onClick={handleTest}
              disabled={!hasConfig || testing}
            >
              {testing ? (
                <Loader2 size={16} className="spin" />
              ) : testPassed ? (
                <CheckCircle2 size={16} />
              ) : (
                <Play size={16} />
              )}
              {testing ? t("onboarding.testing") : testPassed ? t("onboarding.verified") : t("onboarding.test_connection")}
            </button>

            {testError && (
              <span className="onboarding-test-result fail">{testError}</span>
            )}

            {/* Step 2: Get Started (only after test passes) */}
            {testPassed && (
              <button
                className="onboarding-btn primary"
                onClick={handleGetStarted}
                disabled={loading}
              >
                {loading ? t("onboarding.starting") : t("onboarding.get_started")}
                {!loading && <ArrowRight size={18} />}
              </button>
            )}
          </div>
        </div>

        <div className="onboarding-footer">
          <p>{t("onboarding.api_key_hint")}</p>
        </div>
      </div>
    </div>
  )
}
