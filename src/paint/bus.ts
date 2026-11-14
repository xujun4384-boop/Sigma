/**
 * 画布事件总线。
 *
 * 不经过 React state：流式指令可能每几毫秒到达一条，
 * 走 setState 会被批量合并、丢掉中间批次，画面上就会缺笔。
 * 总线保证每条事件都被顺序送达。
 *
 * 画布组件未挂载时（用户停留在其它页签），事件先缓存，
 * 挂载后按顺序补发，不会丢内容。
 */

export interface PaintPatch {
  /** 原始指令对象，由画布侧统一校验 */
  commands: unknown[]
  /** 是否为本次生成的最后一批 */
  final: boolean
}

type Listener = (patch: PaintPatch) => void

class PaintBus {
  private listeners = new Set<Listener>()
  private activityListeners = new Set<() => void>()
  private pending: PaintPatch[] = []

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn)
    if (this.pending.length > 0) {
      const backlog = this.pending
      this.pending = []
      for (const patch of backlog) fn(patch)
    }
    return () => {
      this.listeners.delete(fn)
    }
  }

  /**
   * 旁观者通知：只关心"有内容进来了"（例如自动切到画布页签），
   * 不消费事件缓存，避免抢走画布组件该收到的积压。
   */
  onActivity(fn: () => void): () => void {
    this.activityListeners.add(fn)
    return () => {
      this.activityListeners.delete(fn)
    }
  }

  emit(patch: PaintPatch): void {
    for (const fn of this.activityListeners) fn()
    if (this.listeners.size === 0) {
      this.pending.push(patch)
      return
    }
    for (const fn of this.listeners) fn(patch)
  }

  /** 用户手动清空画布时，同时丢弃未消费的缓存事件 */
  reset(): void {
    this.pending = []
  }

  get pendingCount(): number {
    return this.pending.length
  }
}

export const paintBus = new PaintBus()
