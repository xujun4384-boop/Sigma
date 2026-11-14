import type { PaintEngine } from './engine'
import { commandToStroke, type CommandIssue, type PaintCommand } from './protocol'

export interface ApplyOutcome {
  /** 成功应用的指令数 */
  applied: number
  /** 有问题的指令说明 */
  issues: CommandIssue[]
  /** 是否产生了新笔画 */
  painted: number
}

/**
 * 把一批指令应用到画布。
 *
 * play   —— 笔画逐笔生长（模型生成中实时呈现）
 * instant —— 立即落盘，不做动画（历史重建、导出前应用）
 */
export function applyCommands(
  engine: PaintEngine,
  commands: PaintCommand[],
  mode: 'play' | 'instant' = 'play',
): ApplyOutcome {
  let applied = 0
  let painted = 0

  for (const cmd of commands) {
    switch (cmd.op) {
      case 'layer': {
        engine.ensureLayer(cmd.id, cmd.name)
        if (cmd.visible !== undefined) engine.setLayerVisible(cmd.id, cmd.visible)
        if (cmd.opacity !== undefined) engine.setLayerOpacity(cmd.id, cmd.opacity)
        break
      }
      case 'stroke': {
        const stroke = commandToStroke(cmd)
        if (mode === 'play') engine.enqueue([stroke])
        else engine.applyStrokeNow(stroke)
        painted++
        break
      }
      case 'remove':
        engine.removeStrokeById(cmd.id)
        break
      case 'clearLayer':
        engine.clearLayerStrokes(cmd.layer)
        break
      case 'clear':
        engine.clear()
        break
    }
    applied++
  }

  if (mode === 'instant') engine.refresh()

  return { applied, issues: [], painted }
}

/**
 * 已应用笔迹的账本，用于流式去重。
 * 流式解析会把同一段 JSON 反复解析，同一条指令可能重复到达；
 * 这里同时记录笔迹所属图层，保证 clearLayer 只影响该层。
 */
export class AppliedLedger {
  private entries = new Map<string, string>()

  has(id: string): boolean {
    return this.entries.has(id)
  }

  /** 判断指令是否需要执行，并同步账本状态 */
  shouldApply(cmd: PaintCommand): boolean {
    switch (cmd.op) {
      case 'stroke':
        if (this.entries.has(cmd.id)) return false
        this.entries.set(cmd.id, cmd.layer)
        return true
      case 'remove':
        this.entries.delete(cmd.id)
        return true
      case 'clearLayer':
        for (const [id, layer] of this.entries) {
          if (layer === cmd.layer) this.entries.delete(id)
        }
        return true
      case 'clear':
        this.entries.clear()
        return true
      default:
        return true
    }
  }

  reset(): void {
    this.entries.clear()
  }
}
