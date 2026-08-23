import { useState, useEffect } from 'react'
import { useTranslation } from '../i18n/I18nContext'
import { ChevronLeft, ChevronRight, Check } from 'lucide-react'
import './QuestionnaireDisplay.css'

export interface QuestionnaireQuestion {
  id: string
  text: string
  type: 'single_choice' | 'multi_choice' | 'open'
  options?: string[]
  required?: boolean
}

export interface QuestionnaireData {
  request_id: string
  title: string
  questions: QuestionnaireQuestion[]
}

interface Props {
  data: QuestionnaireData
  onSubmit: (requestId: string, answers: Record<string, string | string[]>) => void
}

export default function QuestionnaireDisplay({ data, onSubmit }: Props) {
  const { t } = useTranslation()
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({})
  const [submitted, setSubmitted] = useState(false)

  const questions = Array.isArray(data.questions) ? data.questions : []
  const currentQuestion = questions[currentIndex]
  const options = Array.isArray(currentQuestion?.options) ? currentQuestion.options.filter((option): option is string => typeof option === 'string') : []
  const isLast = currentIndex === questions.length - 1

  // 检查当前题目是否已填写
  const isCurrentAnswered = (() => {
    if (!currentQuestion) return false
    const a = answers[currentQuestion.id]
    if (currentQuestion.type === 'open') return typeof a === 'string' && a.trim().length > 0
    if (currentQuestion.type === 'multi_choice') return Array.isArray(a) && a.length > 0
    return typeof a === 'string' && a.length > 0
  })()

  // 检查全部必填题是否已填写
  const allRequiredAnswered = questions.every(q => {
    if (q.required === false) return true
    const a = answers[q.id]
    if (q.type === 'open') return typeof a === 'string' && a.trim().length > 0
    if (q.type === 'multi_choice') return Array.isArray(a) && a.length > 0
    return typeof a === 'string' && a.length > 0
  })

  const handleNext = () => {
    if (isLast) {
      setSubmitted(true)
      onSubmit(data.request_id, answers)
    } else {
      setCurrentIndex(i => Math.min(i + 1, questions.length - 1))
    }
  }

  const handlePrev = () => {
    setCurrentIndex(i => Math.max(i - 1, 0))
  }

  const handleSingleChoice = (value: string) => {
    setAnswers(prev => ({ ...prev, [currentQuestion.id]: prev[currentQuestion.id] === value ? '' : value }))
  }

  const handleMultiChoice = (value: string) => {
    setAnswers(prev => {
      const current = (prev[currentQuestion.id] as string[]) || []
      const next = current.includes(value) ? current.filter(v => v !== value) : [...current, value]
      return { ...prev, [currentQuestion.id]: next }
    })
  }

  const handleOpenChange = (value: string) => {
    setAnswers(prev => ({ ...prev, [currentQuestion.id]: value }))
  }

  if (questions.length === 0) return null

  return (
    <div className="questionnaire-container">
      {/* Header */}
      <div className="questionnaire-header">
        <span className="questionnaire-title">{data.title}</span>
        <span className="questionnaire-progress">
          {currentIndex + 1} / {questions.length}
        </span>
      </div>

      {/* Progress bar */}
      <div className="questionnaire-progress-bar">
        <div
          className="questionnaire-progress-fill"
          style={{ width: `${((currentIndex + 1) / questions.length) * 100}%` }}
        />
      </div>

      {/* Question body */}
      <div className="questionnaire-body">
        <label className="questionnaire-question-text">
          {currentQuestion?.required !== false && <span className="questionnaire-required">*</span>}
          {currentQuestion?.text}
        </label>

        {currentQuestion?.type === 'single_choice' && (
          <div className="questionnaire-options">
            {options.map((opt, i) => {
              const selected = answers[currentQuestion.id] === opt
              return (
                <button
                  key={i}
                  className={`questionnaire-option ${selected ? 'selected' : ''}`}
                  onClick={() => handleSingleChoice(opt)}
                  disabled={submitted}
                >
                  <span className={`questionnaire-radio ${selected ? 'checked' : ''}`}>
                    {selected && <span className="questionnaire-radio-dot" />}
                  </span>
                  <span>{opt}</span>
                </button>
              )
            })}
          </div>
        )}

        {currentQuestion?.type === 'multi_choice' && (
          <div className="questionnaire-options">
            {options.map((opt, i) => {
              const selected = ((answers[currentQuestion.id] as string[]) || []).includes(opt)
              return (
                <button
                  key={i}
                  className={`questionnaire-option ${selected ? 'selected' : ''}`}
                  onClick={() => handleMultiChoice(opt)}
                  disabled={submitted}
                >
                  <span className={`questionnaire-checkbox ${selected ? 'checked' : ''}`}>
                    {selected && <Check size={12} />}
                  </span>
                  <span>{opt}</span>
                </button>
              )
            })}
          </div>
        )}

        {currentQuestion?.type === 'open' && (
          <textarea
            className="questionnaire-textarea"
            value={(answers[currentQuestion.id] as string) || ''}
            onChange={e => handleOpenChange(e.target.value)}
            placeholder={t("questionnaire.placeholder")}
            rows={3}
            disabled={submitted}
          />
        )}
      </div>

      {/* Footer navigation */}
      <div className="questionnaire-footer">
        <button
          className="questionnaire-nav-btn"
          onClick={handlePrev}
          disabled={currentIndex === 0 || submitted}
        >
          <ChevronLeft size={16} />
          {t("questionnaire.prev")}
        </button>

        {/* Dot indicators */}
        <div className="questionnaire-dots">
          {questions.map((_, i) => (
            <button
              key={i}
              className={`questionnaire-dot ${i === currentIndex ? 'active' : ''} ${answers[questions[i]?.id] ? 'answered' : ''}`}
              onClick={() => !submitted && setCurrentIndex(i)}
              disabled={submitted}
            />
          ))}
        </div>

        <button
          className={`questionnaire-nav-btn primary ${submitted ? 'submitted' : ''}`}
          onClick={handleNext}
          disabled={!isCurrentAnswered || submitted}
        >
          {submitted ? (
            <>{t("questionnaire.submitted")}</>
          ) : isLast ? (
            <>{t("questionnaire.submit")} <Check size={16} /></>
          ) : (
            <>{t("questionnaire.next")} <ChevronRight size={16} /></>
          )}
        </button>
      </div>
    </div>
  )
}
