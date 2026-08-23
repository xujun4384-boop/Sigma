/**
 * 语音实时通话客户端逻辑。
 * 负责：麦克风采集(16k PCM) -> WebSocket 发往后端 -> 接收后端音频(24k PCM) -> 播放。
 * 完全独立于主 LLM 文本对话。
 */

// 音频采样配置
const INPUT_SAMPLE_RATE = 16000
const OUTPUT_SAMPLE_RATE = 24000
const INPUT_CHUNK_SIZE = 1024 // ScriptProcessor buffer 大小（约 64ms @16k）

export type VoiceStatus = 'idle' | 'connecting' | 'listening' | 'speaking'

export interface VoiceChatHandlers {
  onStatusChange?: (status: VoiceStatus) => void
  onError?: (message: string) => void
  onReady?: () => void
  /** 主 Sigma 任务过程事件（思考/工具/回复），用于弹窗过程展示 */
  onTaskEvent?: (taskId: string, event: Record<string, unknown>) => void
}

export class VoiceChatClient {
  private ws: WebSocket | null = null
  private micStream: MediaStream | null = null
  private micContext: AudioContext | null = null
  private playContext: AudioContext | null = null
  private processor: ScriptProcessorNode | null = null
  private micAnalyser: AnalyserNode | null = null
  private outputAnalyser: AnalyserNode | null = null
  private outputGain: GainNode | null = null
  private micSource: MediaStreamAudioSourceNode | null = null

  private handlers: VoiceChatHandlers
  private status: VoiceStatus = 'idle'
  private playQueue: AudioBuffer[] = []
  private isPlaying = false
  private currentSource: AudioBufferSourceNode | null = null

  constructor(handlers: VoiceChatHandlers = {}) {
    this.handlers = handlers
  }

  get currentStatus(): VoiceStatus {
    return this.status
  }

  private setStatus(status: VoiceStatus) {
    this.status = status
    this.handlers.onStatusChange?.(status)
  }

  /** 开始通话：采集麦克风 + 连接后端 */
  async start(wsUrl: string, config: { apiKey: string; speaker?: string }) {
    try {
      this.setStatus('connecting')

      // 1. 采集麦克风（16k）
      await this.setupMic()

      // 2. 建立 WebSocket
      await this.connectWs(wsUrl, config)

      // 3. 开始采集音频并发送
      this.processor!.connect(this.micContext!.destination)
      this.setStatus('listening')
    } catch (e) {
      this.setStatus('idle')
      this.handlers.onError?.(e instanceof Error ? e.message : String(e))
      await this.stop()
      throw e
    }
  }

  private async setupMic() {
    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: INPUT_SAMPLE_RATE, channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })

    this.micContext = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE })
    this.micSource = this.micContext.createMediaStreamSource(this.micStream)

    // 分析麦克风音量（用于粒子「倾听」状态）
    this.micAnalyser = this.micContext.createAnalyser()
    this.micAnalyser.fftSize = 256
    this.micSource.connect(this.micAnalyser)

    // ScriptProcessor 采集 PCM（16k 单声道）
    this.processor = this.micContext.createScriptProcessor(INPUT_CHUNK_SIZE, 1, 1)
    this.micSource.connect(this.processor)
    this.processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0)
      const pcm = this.floatToInt16(input)
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(pcm.buffer)
      }
    }

    // 播放上下文（24k）
    this.playContext = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE })
    this.outputGain = this.playContext.createGain()
    this.outputGain.connect(this.playContext.destination)
    this.outputAnalyser = this.playContext.createAnalyser()
    this.outputAnalyser.fftSize = 256
    this.outputGain.connect(this.outputAnalyser)
  }

  private floatToInt16(floatArray: Float32Array): Int16Array {
    const int16 = new Int16Array(floatArray.length)
    for (let i = 0; i < floatArray.length; i++) {
      const s = Math.max(-1, Math.min(1, floatArray[i]))
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    return int16
  }

  private connectWs(wsUrl: string, config: { apiKey: string; speaker?: string }) {
    return new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(wsUrl)
      this.ws = ws
      ws.binaryType = 'arraybuffer'

      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: 'start',
          apiKey: config.apiKey,
          speaker: config.speaker || 'zh_male_yunzhou_jupiter_bigtts',
          outputFormat: 'pcm_s16le',
        }))
      }

      ws.onmessage = (ev) => {
        if (typeof ev.data === 'string') {
          try {
            const msg = JSON.parse(ev.data)
            if (msg.type === 'ready') {
              this.handlers.onReady?.()
              resolve()
            } else if (msg.type === 'interrupt') {
              // 用户开口，立即打断 AI 播报
              this.interrupt()
            } else if (msg.type === 'task_event') {
              // 主 Sigma 任务过程事件（思考/工具/回复）
              this.handlers.onTaskEvent?.(msg.task_id, msg.event)
            } else if (msg.type === 'error') {
              this.handlers.onError?.(msg.message || '语音服务错误')
              reject(new Error(msg.message || '语音服务错误'))
            }
          } catch { /* 忽略非 JSON */ }
        } else if (ev.data instanceof ArrayBuffer) {
          this.enqueueAudio(ev.data)
        }
      }

      ws.onerror = () => {
        this.handlers.onError?.('语音连接失败')
        reject(new Error('语音连接失败'))
      }

      ws.onclose = () => {
        this.setStatus('idle')
      }
    })
  }

  /** 接收后端音频（pcm_s16le 24k），转 AudioBuffer 入队播放 */
  private enqueueAudio(data: ArrayBuffer) {
    if (!this.playContext) return
    const int16 = new Int16Array(data)
    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768
    }
    const buffer = this.playContext.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE)
    buffer.copyToChannel(float32, 0)
    this.playQueue.push(buffer)
    this.setStatus('speaking')
    this.drainQueue()
  }

  private drainQueue() {
    if (this.isPlaying || !this.playContext || this.playQueue.length === 0) return
    this.isPlaying = true
    const buffer = this.playQueue.shift()!
    const source = this.playContext.createBufferSource()
    this.currentSource = source
    source.buffer = buffer
    source.connect(this.outputGain!)
    source.onended = () => {
      this.isPlaying = false
      this.currentSource = null
      if (this.playQueue.length === 0) {
        this.setStatus('listening')
      }
      this.drainQueue()
    }
    source.start()
  }

  /** 打断：清空播放队列并停止当前播报，立即回到聆听态 */
  interrupt() {
    this.playQueue = []
    if (this.currentSource) {
      try { this.currentSource.onended = null; this.currentSource.stop() } catch { /* ignore */ }
      this.currentSource = null
    }
    this.isPlaying = false
    this.setStatus('listening')
  }

  /** 麦克风音量（0~1），用于粒子「倾听」状态 */
  getMicLevel(): number {
    if (!this.micAnalyser) return 0
    const data = new Uint8Array(this.micAnalyser.frequencyBinCount)
    this.micAnalyser.getByteTimeDomainData(data)
    let sum = 0
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128
      sum += v * v
    }
    return Math.min(1, Math.sqrt(sum / data.length) * 3)
  }

  /** 输出音量（0~1），用于粒子「说话」状态 */
  getOutputLevel(): number {
    if (!this.outputAnalyser) return 0
    const data = new Uint8Array(this.outputAnalyser.frequencyBinCount)
    this.outputAnalyser.getByteTimeDomainData(data)
    let sum = 0
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128
      sum += v * v
    }
    return Math.min(1, Math.sqrt(sum / data.length) * 3)
  }

  /** 停止通话 */
  async stop() {
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'stop' }))
        this.ws.close()
      }
    } catch { /* ignore */ }
    this.ws = null

    try {
      this.processor?.disconnect()
      this.micSource?.disconnect()
      this.micStream?.getTracks().forEach(t => t.stop())
      this.micContext?.close()
      this.playContext?.close()
    } catch { /* ignore */ }
    this.processor = null
    this.micSource = null
    this.micStream = null
    this.micContext = null
    this.playContext = null
    this.micAnalyser = null
    this.outputAnalyser = null
    this.playQueue = []
    this.isPlaying = false
    this.setStatus('idle')
  }
}
