import { useState } from 'react'
import { Eye, EyeOff, Save, X } from 'lucide-react'
import { useTranslation } from '../i18n/I18nContext'
import type { KimiConfig } from '../types/electron'
import './ConfigPanel.css'

interface ConfigPanelProps {
  config: KimiConfig
  onSave: (config: KimiConfig) => void
  onClose: () => void
}

export default function ConfigPanel({ config, onSave, onClose }: ConfigPanelProps) {
  const { t } = useTranslation()
  const [form, setForm] = useState<KimiConfig>({ ...config })
  const [showKey1, setShowKey1] = useState(false)
  const [showKey2, setShowKey2] = useState(false)
  const [saved, setSaved] = useState(false)

  const update = (patch: Partial<KimiConfig>) => {
    setForm(prev => ({ ...prev, ...patch }))
    setSaved(false)
  }

  const handleSave = () => {
    onSave(form)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const activeKey = form.activeApiKey === 'key1' ? form.apiKey : (form.apiKey2 || form.apiKey)

  return (
    <div className="config-panel">
      <div className="config-header">
        <div>
          <span className="config-eyebrow">{t("config.title")}</span>
          <h2>{t("config.subtitle")}</h2>
          <p>{t("config.desc")}</p>
        </div>
        <button className="config-close" onClick={onClose}>
          <X size={18} />
        </button>
      </div>

      <div className="config-body">
        {/* Protocol Selection */}
        <div className="config-section">
          <h3>{t("onboarding.protocol")}</h3>
          <div className="config-toggle-group">
            <button
              className={form.protocol === 'anthropic' ? 'active' : ''}
              onClick={() => update({ protocol: 'anthropic' })}
            >
              Anthropic
            </button>
            <button
              className={form.protocol === 'openai' ? 'active' : ''}
              onClick={() => update({ protocol: 'openai' })}
            >
              OpenAI
            </button>
          </div>
        </div>

        {/* Base URL */}
        <div className="config-field">
          <label>{t("onboarding.base_url")}</label>
          <input
            type="text"
            value={form.baseUrl}
            onChange={e => update({ baseUrl: e.target.value })}
            placeholder="https://api.kimi.com/coding"
          />
          <span className="field-hint">{t("config.base_url_hint")}</span>
        </div>

        {/* Model */}
        <div className="config-field">
          <label>{t("onboarding.model")}</label>
          <input
            type="text"
            value={form.model}
            onChange={e => update({ model: e.target.value })}
            placeholder="kimi-for-coding"
          />
        </div>

        {/* API Key 1 */}
        <div className="config-field">
          <label>{t("config.api_key1")}</label>
          <div className="config-key-row">
            <input
              type={showKey1 ? 'text' : 'password'}
              value={form.apiKey}
              onChange={e => update({ apiKey: e.target.value })}
              placeholder="sk-kimi-..."
            />
            <button onClick={() => setShowKey1(v => !v)}>
              {showKey1 ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>

        {/* API Key 2 */}
        <div className="config-field">
          <label>{t("config.api_key2")}</label>
          <div className="config-key-row">
            <input
              type={showKey2 ? 'text' : 'password'}
              value={form.apiKey2}
              onChange={e => update({ apiKey2: e.target.value })}
              placeholder="sk-kimi-... (optional)"
            />
            <button onClick={() => setShowKey2(v => !v)}>
              {showKey2 ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>

        {/* Active Key */}
        <div className="config-section">
          <h3>{t("config.active_key")}</h3>
          <div className="config-toggle-group">
            <button
              className={form.activeApiKey === 'key1' ? 'active' : ''}
              onClick={() => update({ activeApiKey: 'key1' })}
            >
              Key 1
            </button>
            <button
              className={form.activeApiKey === 'key2' ? 'active' : ''}
              onClick={() => update({ activeApiKey: 'key2' })}
            >
              Key 2
            </button>
          </div>
          <span className="field-hint">{t("config.active_key_hint")}</span>
        </div>

        {/* Key Preview */}
        <div className="config-key-preview">
          <div className="preview-label">{t("config.active_key_preview")}</div>
          <code>{activeKey ? `${activeKey.slice(0, 12)}...${activeKey.slice(-4)}` : t("api.not_set")}</code>
        </div>

        {/* Save & Status */}
        <div className="config-actions">
          <button className="save-btn" onClick={handleSave}>
            <Save size={14} />
            {saved ? t("settings.saved") : t("config.save_config")}
          </button>
        </div>

        {saved && <div className="config-success">{t("config.save_success")}</div>}
      </div>
    </div>
  )
}
