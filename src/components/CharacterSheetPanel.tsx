import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { buildCharacter } from '../characters/rig'
import { renderCharacter } from '../characters/render'
import type { CharacterPreview } from '../characters/bus'
import { characterBus } from '../characters/bus'
import type { CharacterSpec, PoseParams } from '../characters/types'
import { DEFAULT_POSE } from '../characters/types'
import { getBackendUrl } from '../utils/config'
import './CharacterSheetPanel.css'

/**
 * 定妆对照图。
 *
 * 五格不是装饰：视角、坐姿、手臂、倾斜、表情各改一个参数，
 * 五格长得一样就说明参数没接进绘制，确认下来进镜头也不会动。
 */

const CELL_W = 180
const CELL_H = 270

interface Cell {
  label: string
  pose: Partial<PoseParams>
}

const CELLS: Cell[] = [
  { label: '正面 / 站', pose: { view: 'front', pose: 'stand' } },
  { label: '侧面 / 站', pose: { view: 'side', pose: 'stand' } },
  { label: '背面 / 站', pose: { view: 'back', pose: 'stand' } },
  { label: '坐姿 / 伸手', pose: { view: 'front', pose: 'sit', armL: 26, armR: 26, headTurn: 6 } },
  { label: '倾斜 / 惊讶', pose: { view: 'front', pose: 'stand', tilt: 10, eyes: 'surprised', mouth: 'open' } },
]

type Verdict = 'confirm' | 'revise'

interface SheetCell {
  key: string
  label: string
  role: string
  spec: CharacterSpec
  pose: Partial<PoseParams>
}

export default function CharacterSheetPanel({ preview }: { preview: CharacterPreview }) {
  const canvasRefs = useRef<Record<string, HTMLCanvasElement | null>>({})
  const [note, setNote] = useState('')
  const [sending, setSending] = useState<Verdict | null>(null)
  const [done, setDone] = useState<Verdict | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setDone(null)
    setSending(null)
    setError('')
    setNote('')
  }, [preview.token])

  // 主角走五格参数网格；有配角时每个角色各一格正面站姿，一屏看完谁是谁
  const cells = useMemo<SheetCell[]>(() => {
    const cast = preview.characters.length ? preview.characters : [{role: 'hero', spec: preview.spec}]
    const extras = cast.filter(c => c.role !== 'hero')
    if (extras.length) {
      return cast.map(c => ({
        key: c.role,
        label: c.role === 'hero' ? `主角 · ${c.spec.name}` : `${c.spec.name}（${c.role}）`,
        role: c.role,
        spec: c.spec,
        pose: { view: 'front' as const, pose: 'stand' as const },
      }))
    }
    return CELLS.map((cell, i) => ({
      key: `hero-${i}`,
      label: cell.label,
      role: 'hero',
      spec: preview.spec,
      pose: cell.pose,
    }))
  }, [preview])

  useEffect(() => {
    for (const cell of cells) {
      const canvas = canvasRefs.current[cell.key]
      if (!canvas) continue
      const drawing = buildCharacter(cell.spec, { ...DEFAULT_POSE, ...cell.pose }, 430)
      renderCharacter(canvas, drawing, { width: CELL_W, height: CELL_H }, preview.style)
    }
  }, [preview, cells])

  const submit = useCallback(async (verdict: Verdict) => {
    setSending(verdict)
    setError('')
    try {
      const base = await getBackendUrl()
      const res = await fetch(`${base}/api/character/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: preview.token, verdict, note: note.trim() }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || data.success === false) throw new Error(data.error || '提交失败')
      setDone(verdict)
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败')
    } finally {
      setSending(null)
    }
  }, [note, preview.token])

  const summary = preview.characters.length > 1
    ? preview.characters
      .map(c => `${c.role === 'hero' ? '主角' : c.role}：${c.spec.name}（${c.spec.hair} / ${c.spec.outfit}）`)
      .join('；')
    : `${preview.spec.name}｜发型 ${preview.spec.hair}｜服装 ${preview.spec.outfit}｜发色 ${preview.spec.colors.hair}`

  return (
    <div className="char-sheet">
      <div className="char-sheet-head">
        <div className="char-sheet-title">
          <span className="char-sheet-kicker">定妆</span>
          {preview.title || '角色定妆'}
        </div>
        <div className="char-sheet-summary">{summary}</div>
      </div>

      {preview.note && <div className="char-sheet-note">{preview.note}</div>}

      <div className="char-sheet-grid">
        {cells.map(cell => (
          <div className="char-sheet-cell" key={cell.key}>
            <canvas
              ref={el => { canvasRefs.current[cell.key] = el }}
              width={CELL_W}
              height={CELL_H}
            />
            <span>{cell.label}</span>
          </div>
        ))}
      </div>

      <div className="char-sheet-hint">
        {preview.characters.length > 1
          ? '整组定妆：每个角色一格里是同一个骨架参数展开的人。确认他们是不是不同的人、造型有没有互相串。'
          : '五格应当是同一个人的不同视角 / 姿态。任意两格完全一样，说明参数没有接进绘制。'}
      </div>

      <div className="char-sheet-actions">
        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="要改哪里？例如「头发短一点，围裙换成蓝色」。留空则直接确认。"
          rows={2}
          disabled={Boolean(done) || Boolean(sending)}
        />
        <div className="char-sheet-buttons">
          <button
            className="char-sheet-confirm"
            onClick={() => { void submit('confirm') }}
            disabled={Boolean(done) || Boolean(sending)}
          >
            {done === 'confirm' ? '已确认' : sending === 'confirm' ? '提交中…' : '确认这版'}
          </button>
          <button
            className="char-sheet-revise"
            onClick={() => { void submit('revise') }}
            disabled={Boolean(done) || Boolean(sending) || !note.trim()}
            title={note.trim() ? '' : '先写下要改的地方'}
          >
            {done === 'revise' ? '已提交修改要求' : sending === 'revise' ? '提交中…' : '要求调整'}
          </button>
          <button className="char-sheet-close" onClick={() => characterBus.clear()} disabled={Boolean(sending)}>
            关闭
          </button>
        </div>
        {error && <div className="char-sheet-error">{error}</div>}
        {done && <div className="char-sheet-done">已提交，继续等模型的下一步。</div>}
      </div>
    </div>
  )
}
