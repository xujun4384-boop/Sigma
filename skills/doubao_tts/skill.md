# doubao_tts skill
# ---------------------------------------------------------------------------
# 摘要
# 豆包语音合成大模型旁白生成。文本 → mp3 旁白，并返回字级时间戳。
# 音色按注册表自动匹配所属代次资源（1.0 / 2.0）。
# 与 edge-tts（video_tts）相比，音质更好、支持情感/语速控制，且带字级时间戳。
# 时间戳用于「旁白时间与视频内容精确契合」：字幕逐字对齐、分镜时长跟随旁白。
#
## 使用场景
# - 视频旁白 / 配音生成
# - 宣传片、新闻资讯、产品介绍配音
# - 需要「画面 + 旁白 + 字幕」精确对齐的视频
#
# 包含 1 种工具:
#   doubao_tts - 文本 → 旁白 mp3 + 字级时间戳
# ---------------------------------------------------------------------------

# ═══ 核心价值：字级时间戳 ═══

# 每次调用会返回每个字的起止时间:
#   words = [{"word": "你", "startTime": 0.195, "endTime": 0.395}, ...]
#   duration = 最后一个字的 endTime（即旁白总时长，秒）
#
# 用途:
#   1. 字幕对齐：用每个字的 startTime/endTime 生成逐字/逐句字幕
#   2. 分镜对齐：用 duration 反过来设定视频分镜时长（画面跟随旁白）
#   3. 语速适配：用 speech_rate 微调旁白时长，使其接近目标画面时长

# ═══ 推荐工作流 ═══

# 1. 脚本阶段确定每段旁白文本
# 2. doubao_tts(text="旁白文本", output_path="vo.mp3") → 拿到 mp3 + 时间戳 + 总时长
# 3. 用总时长设定分镜时长 → opendesign_video 生成画面
# 4. video_compose 叠加旁白音频 + 字幕（字幕时间戳来自 words）

# ═══ 参数详情 ═══

# ── doubao_tts ──
# 文本 → 旁白 mp3，返回字级时间戳。
#
# 参数:
#   text (string, 必填) 待合成的旁白文本
#   output_path (string, 必填) 输出 mp3 路径（相对路径放 video_work/<project>/ 下）
#   project (string, 可选) 项目名，与视频工具保持一致
#   speaker (string, 可选) 音色ID，留空则用 Settings「配音音色」，再空则内置默认（广告解说2.0）
#                       可选音色见 skills/doubao_tts/voices.py，前端 Settings 下拉也读同一份
#   speech_rate (integer, 可选, 默认0) 语速 -50~100（100=2倍速，-50=0.5倍速）
#   loudness_rate (integer, 可选, 默认0) 音量 -50~100
#
# 输出:
#   output_path: mp3 绝对路径
#   duration: 旁白总时长（秒）
#   words: 字级时间戳列表 [{"word","startTime","endTime","confidence"}]

# ═══ key 配置 ═══

# 需要豆包语音技术（火山引擎 openspeech）的 API Key。
# 在 Settings → Skill Keys 中配置 doubaoVoiceApiKey。
# 获取: console.volcengine.com/speech → API Key 管理
# ---------------------------------------------------------------------------
